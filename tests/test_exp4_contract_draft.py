"""The draft Experiment 4 contracts must fail the things that went wrong before.

A contract is a set of claims about what may differ. These check the claims can
be falsified: that the D27 class of failure is still fatal when the treatment is
a whole network, that a genuine network comparison is nonetheless possible, and
that certification cannot exist without asserting convergence.
"""
from __future__ import annotations

import dataclasses

import pytest

from cota_opt.firewall import (ComparisonResult, ContractError, EventType,
                               ExecutionEvent, ExecutionReceipt,
                               ExperimentContract, InadmissibleComparison,
                               StartPolicy, StopRule, admit, build_spec,
                               compare)
from cota_opt.firewall.exp4_draft import (EXP4_CERTIFICATION_DRAFT,
                                          EXP4_DISCOVERY_DRAFT,
                                          NETWORK_DIFFERENCES)

C = EXP4_DISCOVERY_DRAFT


def _net(contract=C, *, key="net-A", digest_="nA", card=41, obj=3_000_000.0,
         **kw):
    sp = build_spec(contract, state_digest=digest_, state_key=key,
                    cardinality=card, members=(f"line-{i}" for i in range(3)),
                    envelope_digest="env-exp3", config_digest="cfg",
                    data_digest="data", code_version="src-abc")
    base = dict(evaluator_used=contract.evaluator,
                objective_used=contract.objective, envelope_used_vh=2517.18,
                pathset_digest=f"ps-{digest_}", code_version="src-abc",
                start_policy_requested=contract.solver.start_policy,
                starts_attempted=("repaired", "greedy"), winning_start="greedy",
                restarts_requested=contract.solver.restarts,
                restarts_completed=contract.solver.restarts,
                evaluations_performed=20_000,
                termination=StopRule.NO_IMPROVING_MOVE, converged=True,
                objective=obj, metrics={"unserved_demand": 9000.0},
                plan_digest=f"plan-{digest_}", feasible=True)
    base.update(kw)
    return ExecutionReceipt(spec=sp, **base)


def test_two_whole_networks_can_actually_be_compared():
    """The whitelist must not be so narrow that the experiment is impossible."""
    r = compare(_net(), _net(key="net-B", digest_="nB", card=38,
                     obj=2_950_000.0), C)
    assert isinstance(r, ComparisonResult), str(r)
    assert r.effect < 0
    assert "spec.state_digest" in r.declared_differences


def test_every_declared_difference_carries_a_written_reason():
    for dim, why in NETWORK_DIFFERENCES.items():
        assert why.strip(), dim
        assert len(why) > 40, f"{dim}: a reason, not a label"


def test_the_D27_class_stays_fatal_when_the_treatment_is_a_whole_network():
    """An execution difference decided by the network must refuse."""
    out = compare(_net(),
                  _net(key="net-B", digest_="nB", obj=2_950_000.0,
                       starts_attempted=("greedy",), fallback_occurred=True,
                       events=(ExecutionEvent(EventType.START_FALLBACK,
                                              "network's incumbent infeasible",
                                              "frequency"),)),
                  C)
    assert not isinstance(out, ComparisonResult)


@pytest.mark.parametrize("field,value", [
    ("repair_occurred", True),
    ("restarts_completed", 1),
    ("converged", False),
    ("termination", StopRule.DEADLINE),
    ("evaluator_used", "pattern_level"),
    ("envelope_used_vh", 2600.0),
])
def test_experiment_4_does_not_inherit_experiment_3_waivers(field, value):
    """Exp 3 declared the repair; Exp 4 must not, and does not."""
    out = compare(_net(), _net(key="net-B", digest_="nB", obj=2.95e6,
                               **{field: value}), C)
    assert isinstance(out, InadmissibleComparison), f"{field} slipped through"


def test_a_semantic_recovery_in_one_arm_only_refuses():
    """Dropping an unroutable OD pair in one network and not the other."""
    out = compare(_net(),
                  _net(key="net-B", digest_="nB", obj=2.95e6,
                       events=(ExecutionEvent(
                           EventType.DATA_FALLBACK,
                           "unroutable OD pairs dropped", "pathset"),)),
                  C)
    assert isinstance(out, InadmissibleComparison)
    assert any("DATA_FALLBACK" in d.dimension for d in out.undeclared)


def test_discovery_and_certification_cannot_be_compared_across():
    """The supernetwork master path set is a different evidence class."""
    d = _net()
    c = _net(EXP4_CERTIFICATION_DRAFT, key="net-B", digest_="nB",
             obj=2.95e6, restarts_completed=20, restarts_requested=20)
    assert isinstance(compare(d, c, C), InadmissibleComparison)


def test_the_certification_draft_asserts_convergence():
    assert EXP4_CERTIFICATION_DRAFT.solver.require_convergence
    with pytest.raises(ContractError):
        dataclasses.replace(
            EXP4_CERTIFICATION_DRAFT,
            solver=EXP4_DISCOVERY_DRAFT.solver)


def test_neither_draft_carries_a_noise_floor():
    """D32: Experiment 4's threshold comes from its own gap benchmark."""
    assert EXP4_DISCOVERY_DRAFT.noise_floor is None
    assert EXP4_CERTIFICATION_DRAFT.noise_floor is None
    r = compare(_net(), _net(key="net-B", digest_="nB", obj=2.95e6), C)
    assert r.above_noise_floor is None      # None, never False


def test_both_drafts_are_gen2():
    assert EXP4_DISCOVERY_DRAFT.methodology_generation == "gen2"
    assert EXP4_CERTIFICATION_DRAFT.methodology_generation == "gen2"
