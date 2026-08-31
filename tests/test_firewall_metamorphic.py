"""Metamorphic properties of the harness: things that must hold regardless of
how the harness is implemented.

These are the tests meant to catch the class of bug nobody has thought of yet.
Each states a relation between two runs rather than a value for one, so a
change that breaks the relation is caught even if every individual number
still looks reasonable — which is exactly how D27 survived four experiments of
individually reasonable numbers.
"""
from __future__ import annotations

import dataclasses
import random

import pytest

from cota_opt.firewall import (EXP3_STAGE_A, ComparisonResult, EventType,
                               ExecutionReceipt, InadmissibleComparison,
                               admit, build_spec, canonical_json, compare,
                               digest, neutral)
from cota_opt.firewall.core import Sem, fields_by_sem
from cota_opt.firewall.policy import StartPolicy, StopRule

C = EXP3_STAGE_A


def _spec(**kw):
    base = dict(state_digest="s0", state_key="<none>", cardinality=0,
                members=(), envelope_digest="env-1", config_digest="cfg-1",
                data_digest="data-1", code_version="abc123")
    base.update(kw)
    return build_spec(C, **base)


def _receipt(**kw):
    sp = kw.pop("spec_", None) or _spec(
        **{k: kw.pop(k) for k in ("state_digest", "state_key", "cardinality",
                                  "members") if k in kw})
    base = dict(evaluator_used=C.evaluator, objective_used=C.objective,
                envelope_used_vh=2517.18, pathset_digest="ps-1",
                code_version="abc123",
                start_policy_requested=C.solver.start_policy,
                starts_attempted=("repaired", "greedy"), winning_start="greedy",
                restarts_requested=2, restarts_completed=2,
                evaluations_performed=4000,
                termination=StopRule.NO_IMPROVING_MOVE, converged=True,
                objective=1_000_000.0, metrics={"unserved_demand": 9800.0},
                plan_digest="plan-1", feasible=True)
    base.update(kw)
    return ExecutionReceipt(spec=sp, **base)


# --- identity ------------------------------------------------------------

def test_identical_state_through_admissible_routes_compares_to_null():
    a, b = _receipt(), _receipt()
    r = compare(a, b, C)
    assert isinstance(r, ComparisonResult)
    assert r.effect == 0.0 and r.effect_pct == 0.0


def test_serialization_round_trip_preserves_identity():
    """Serialize, rebuild, and the digest must be the same."""
    r = _receipt()
    blob = canonical_json(r)
    assert canonical_json(r) == blob          # deterministic
    assert digest(r) == digest(_receipt())    # reconstruction agrees


def test_digest_is_insensitive_to_dict_insertion_order():
    a = _receipt(metrics={"unserved_demand": 9800.0, "veh_hours": 2515.0})
    b = _receipt(metrics={"veh_hours": 2515.0, "unserved_demand": 9800.0})
    assert digest(a) == digest(b)


def test_comparison_order_does_not_change_magnitude():
    a = _receipt()
    b = _receipt(state_digest="s1", state_key="m", cardinality=1,
                 members=("m",), pathset_digest="ps-2", objective=990_000.0)
    fwd, rev = compare(a, b, C), compare(b, a, C)
    assert isinstance(fwd, ComparisonResult) and isinstance(rev, ComparisonResult)
    assert fwd.effect == pytest.approx(-rev.effect)


def test_evaluation_order_does_not_change_admissibility():
    rs = [_receipt(state_digest=f"s{i}", state_key=f"m{i}", cardinality=1,
                   members=(f"m{i}",), pathset_digest=f"ps-{i}",
                   objective=1e6 - i) for i in range(6)]
    base = _receipt()
    a = [bool(compare(base, r, C)) for r in rs]
    shuffled = rs[:]
    random.Random(7).shuffle(shuffled)
    b = {r.spec.state_key: bool(compare(base, r, C)) for r in shuffled}
    assert all(a) and all(b.values())


# --- cache, resume, sharding --------------------------------------------

def test_cache_hit_and_miss_are_semantically_equivalent():
    """Cache provenance is bookkeeping, not experimental state."""
    cold, warm = _receipt(cache_hit=False), _receipt(cache_hit=True)
    assert admit(cold, C) and admit(warm, C)
    assert compare(cold, warm, C).effect == 0.0
    assert (admit(cold, C).execution_signature ==
            admit(warm, C).execution_signature)


def _amended(*extra):
    """A contract that additionally permits `extra` to differ.

    Amending a contract changes its digest, and a receipt built under the old
    digest is refused under the new one -- which is the point of section 13.
    So cells for an amended contract must be built under it.
    """
    return dataclasses.replace(
        C, allowed_treatment_differences=C.allowed_treatment_differences
        | set(extra),
        justifications={**C.justifications,
                        **{k: "declared for this test" for k in extra}})


def _under(contract, **kw):
    sp = build_spec(contract, state_digest=kw.pop("state_digest", "s0"),
                    state_key=kw.pop("state_key", "<none>"),
                    cardinality=kw.pop("cardinality", 0),
                    members=kw.pop("members", ()), envelope_digest="env-1",
                    config_digest="cfg-1", data_digest="data-1",
                    code_version="abc123")
    return _receipt(spec_=sp, **kw)


def test_resume_is_comparable_only_when_declared_equivalent():
    """Resuming CHANGES the receipt, so it is a difference until declared.

    The resumable runner reproduces an uninterrupted solve exactly, but
    "reproduces exactly" is a claim the harness cannot verify from a flag. It
    is comparable when the experiment says so, and not before.
    """
    plain, resumed = _receipt(), _receipt(resumed=True)
    assert isinstance(compare(plain, resumed, C), InadmissibleComparison)
    declared = _amended("resumed")
    assert isinstance(compare(_under(declared), _under(declared, resumed=True),
                              declared), ComparisonResult)


def test_a_receipt_cannot_be_judged_against_a_contract_it_did_not_run_under():
    declared = _amended("resumed")
    assert not admit(_receipt(), declared)
    assert isinstance(compare(_receipt(), _under(declared), declared),
                      InadmissibleComparison)


def test_shard_membership_is_not_experimental_state():
    """Which worker ran a cell must not appear anywhere in its identity."""
    r = _receipt()
    flat = {**fields_by_sem(r, Sem.IDENTITY), **fields_by_sem(r, Sem.OPPORTUNITY)}
    assert not any("shard" in k or "worker" in k or "pid" in k for k in flat)


def test_operationally_neutral_recovery_preserves_the_execution_signature():
    plain = _receipt()
    recovered = _receipt(events=(neutral(EventType.PATHSET_REBUILT,
                                         "deterministic rebuild", "pathset"),))
    assert (admit(plain, C).execution_signature ==
            admit(recovered, C).execution_signature)
    assert isinstance(compare(plain, recovered, C), ComparisonResult)


# --- the signatures mean what they say ------------------------------------

def test_treatment_and_nuisance_signatures_split_cleanly():
    a = _receipt()
    b = _receipt(state_digest="s1", state_key="m", cardinality=1,
                 members=("m",), pathset_digest="ps-2", objective=990_000.0)
    oa, ob = admit(a, C), admit(b, C)
    assert oa.treatment_signature != ob.treatment_signature   # geometry differs
    assert oa.nuisance_signature == ob.nuisance_signature     # nothing else does


def test_an_undeclared_execution_change_moves_the_nuisance_signature():
    a = _receipt()
    # Undeclared, but still individually admissible -- so this isolates the
    # signature split rather than the admission check.
    b = _receipt(resumed=True)
    assert admit(a, C).nuisance_signature != admit(b, C).nuisance_signature


def test_a_declared_execution_change_moves_the_treatment_signature_instead():
    a = _receipt()
    b = _receipt(repair_occurred=True)     # declared, with a written reason
    assert admit(a, C).nuisance_signature == admit(b, C).nuisance_signature
    assert admit(a, C).treatment_signature != admit(b, C).treatment_signature


def test_evidence_signature_tracks_provenance_not_results():
    a = _receipt(objective=1e6)
    b = _receipt(objective=2e6, plan_digest="other")
    assert admit(a, C).evidence_signature == admit(b, C).evidence_signature
    c = _receipt(pathset_digest="different")
    assert admit(a, C).evidence_signature != admit(c, C).evidence_signature


# --- equivalent plumbing ---------------------------------------------------

def test_two_paths_declared_equivalent_must_agree():
    """If two execution paths claim mathematical equivalence, prove it.

    The resumable certification runner and the single-process scorer are
    declared equivalent. Equivalence means the same signatures and the same
    number, not merely a similar number.
    """
    declared = _amended("resumed")
    single = _under(declared, objective=2_956_120.583955)
    resumed = _under(declared, objective=2_956_120.583955, resumed=True,
                     events=(neutral(EventType.CHECKPOINT_RESUMED,
                                     "restart-seeded resume is exact",
                                     "frequency"),))
    r = compare(single, resumed, declared)
    assert isinstance(r, ComparisonResult)
    assert r.effect == 0.0
    assert (admit(single, declared).evidence_signature ==
            admit(resumed, declared).evidence_signature)
