"""Adversarial tests for the semantic comparison firewall.

Each test constructs a comparison that MUST be refused, and passes only if no
`ComparisonResult` can be produced. They test the firewall, not the strings in
its implementation: none of them greps for a message, and the D27 regression
(`test_the_exp3_start_asymmetry_is_caught_generically`) contains no check
named for Experiment 3, for greedy, or for start sets at all.
"""
from __future__ import annotations

import dataclasses

import pytest

from cota_opt.firewall import (CERTIFICATION, DISCOVERY, EXP3_STAGE_A,
                               ComparisonResult, ContractError, EventType,
                               ExecutionEvent, ExecutionReceipt,
                               ExperimentContract, InadmissibleComparison,
                               Severity, SolverPolicy, StartPolicy, StopRule,
                               admit, balance_audit, build_spec, compare,
                               health_report, neutral)

CONTRACT = EXP3_STAGE_A


def spec(contract=CONTRACT, **kw):
    base = dict(state_digest="s0", state_key="<none>", cardinality=0,
                members=(), envelope_digest="env-1", config_digest="cfg-1",
                data_digest="data-1", code_version="abc123")
    base.update(kw)
    return build_spec(contract, **base)


def receipt(contract=CONTRACT, *, obj=1_000_000.0, **kw):
    """A well-formed receipt that satisfies the default contract."""
    sp = kw.pop("spec_", None) or spec(contract, **{
        k: kw.pop(k) for k in ("state_digest", "state_key", "cardinality",
                               "members", "envelope_digest", "config_digest")
        if k in kw})
    base = dict(
        evaluator_used=contract.evaluator, objective_used=contract.objective,
        envelope_used_vh=2517.18, pathset_digest="ps-1", code_version="abc123",
        start_policy_requested=contract.solver.start_policy,
        starts_attempted=("repaired", "greedy"), winning_start="greedy",
        restarts_requested=contract.solver.restarts,
        restarts_completed=contract.solver.restarts,
        evaluations_performed=4000, termination=StopRule.NO_IMPROVING_MOVE,
        converged=True, objective=obj, metrics={"unserved_demand": 9800.0},
        plan_digest="plan-1", feasible=True)
    base.update(kw)
    return ExecutionReceipt(spec=sp, **base)


def treated(**kw):
    """A treatment arm differing ONLY on declared dimensions."""
    kw.setdefault("obj", 995_000.0)
    kw.setdefault("state_digest", "s1")
    kw.setdefault("state_key", "add_stop-010")
    kw.setdefault("cardinality", 1)
    kw.setdefault("members", ("add_stop-010",))
    kw.setdefault("pathset_digest", "ps-2")
    kw.setdefault("plan_digest", "plan-2")
    if "members" in kw and kw["state_key"] != "add_stop-010":
        kw["members"] = (kw["state_key"],)
    return receipt(**kw)


# --------------------------------------------------------------------------
# the baseline: a legitimate comparison must still work
# --------------------------------------------------------------------------

def test_a_matched_comparison_is_admitted():
    r = compare(receipt(), treated(), CONTRACT)
    assert isinstance(r, ComparisonResult), str(r)
    assert r.effect == pytest.approx(-5000.0)
    assert r.effect_pct == pytest.approx(-0.5)
    assert r.above_noise_floor is True
    assert "spec.state_digest" in r.declared_differences


def test_identical_states_compare_to_null():
    r = compare(receipt(), receipt(), CONTRACT)
    assert isinstance(r, ComparisonResult)
    assert r.effect == 0.0
    assert r.above_noise_floor is False


def test_a_declared_no_op_mutation_compares_as_null():
    """Same geometry reached by a mutation that changes nothing."""
    noop = receipt(state_key="noop-001", state_digest="s0",
                   cardinality=1, members=("noop-001",))
    r = compare(receipt(), noop, CONTRACT)
    assert isinstance(r, ComparisonResult)
    assert r.effect == 0.0


# --------------------------------------------------------------------------
# THE D27 REGRESSION — no mention of Experiment 3, greedy, or start sets
# --------------------------------------------------------------------------

def test_the_exp3_start_asymmetry_is_caught_generically():
    """Two arms, identical requested policy, different realised execution.

    This is D27 exactly: nothing in the CONFIGURATION differs. The control kept
    its incumbent; the treatment's incumbent was rejected after the ladder snap
    and it silently ran a different search. The criterion is Ian's: no
    ``ComparisonResult`` may be produced. Nothing in the harness knows what a
    start set is -- the refusal comes from the generic rule that undeclared
    execution differences are not comparable.
    """
    control = receipt()
    treatment = treated(starts_attempted=("greedy",), starts_rejected=("repaired",),
                        rejection_reasons=("snapped incumbent left the envelope",),
                        fallback_occurred=True,
                        events=(ExecutionEvent(EventType.START_FALLBACK,
                                               "incumbent infeasible after snap",
                                               "frequency"),))
    out = compare(control, treatment, CONTRACT)
    assert not isinstance(out, ComparisonResult), "the D27 confound got through"
    assert not out                      # falsy, so `if compare(...)` fails closed


def test_execution_difference_alone_refuses_when_both_arms_are_admissible():
    """Isolates the comparison layer from the observation layer.

    Both arms individually satisfy the contract -- each attempted every start
    the policy requires -- yet one of them had to repair its way there. Equal
    entitlement, unequal execution, and the comparison is still refused.
    """
    control = receipt()
    treatment = treated(repair_occurred=True, repair_steps=7,
                        events=(ExecutionEvent(EventType.INCUMBENT_REPAIRED,
                                               "walked back into the envelope",
                                               "frequency"),))
    assert admit(control, CONTRACT) and admit(treatment, CONTRACT)
    out = compare(control, treatment, CONTRACT)
    assert isinstance(out, InadmissibleComparison)
    dims = {d.dimension for d in out.undeclared}
    assert {"repair_occurred", "repair_steps"} <= dims
    assert "REFUSED" in str(out) and "No treatment effect" in str(out)


def test_a_fallback_in_only_one_arm_is_refused_even_with_matching_fields():
    """Fields agree; only the event differs. Still not comparable."""
    control = receipt()
    treatment = treated(events=(ExecutionEvent(EventType.MODEL_FALLBACK,
                                               "evaluator degraded", "eval"),))
    out = compare(control, treatment, CONTRACT)
    assert isinstance(out, InadmissibleComparison)
    assert any(d.dimension == "opportunity_events" for d in out.undeclared)


def test_an_operationally_neutral_event_does_not_block_comparison():
    """A recovery provably equivalent to not happening is not a difference."""
    control = receipt()
    treatment = treated(events=(neutral(EventType.CHECKPOINT_RESUMED,
                                        "identical recomputation", "runner"),))
    assert isinstance(compare(control, treatment, CONTRACT), ComparisonResult)


# --------------------------------------------------------------------------
# each of the mismatches the corrective plan enumerates
# --------------------------------------------------------------------------

@pytest.mark.parametrize("field,value", [
    ("evaluator_used", "pattern_level"),
    ("objective_used", "unweighted_gc"),
    ("envelope_used_vh", 2600.0),
    ("code_version", "def456"),
    ("start_policy_requested", StartPolicy.GREEDY_ONLY),
    ("starts_attempted", ("greedy",)),
    ("restarts_completed", 1),
    ("termination", StopRule.DEADLINE),
    ("converged", False),
    ("repair_occurred", True),
    ("resumed", True),
])
def test_any_undeclared_mismatch_refuses(field, value):
    out = compare(receipt(), treated(**{field: value}), CONTRACT)
    assert isinstance(out, InadmissibleComparison), f"{field} slipped through"


def test_mismatched_pathset_policy_refuses():
    other = dataclasses.replace(CONTRACT, pathset_policy="shared_master")
    t = ExecutionReceipt(spec=spec(other, state_digest="s1", state_key="m",
                                   cardinality=1, members=("m",)),
                         evaluator_used=CONTRACT.evaluator,
                         objective_used=CONTRACT.objective,
                         starts_attempted=("repaired", "greedy"),
                         restarts_completed=2, converged=True, objective=9e5)
    assert isinstance(compare(receipt(), t, CONTRACT), InadmissibleComparison)


def test_a_stale_cache_entry_from_another_contract_refuses():
    """A receipt built under a different contract cannot be admitted here."""
    other = dataclasses.replace(CONTRACT, version="3.0")
    stale = ExecutionReceipt(
        spec=spec(other, state_digest="s1", state_key="m", cardinality=1,
                  members=("m",)),
        evaluator_used=CONTRACT.evaluator, objective_used=CONTRACT.objective,
        starts_attempted=("repaired", "greedy"), restarts_completed=2,
        converged=True, objective=9e5, cache_hit=True)
    assert not admit(stale, CONTRACT)
    assert isinstance(compare(receipt(), stale, CONTRACT), InadmissibleComparison)


def test_same_nominal_effort_but_different_completed_search_refuses():
    """Both asked for 2 restarts; one got 2, one got 1."""
    out = compare(receipt(restarts_completed=2),
                  treated(restarts_completed=1), CONTRACT)
    assert isinstance(out, InadmissibleComparison)


def test_evaluations_within_the_declared_tolerance_are_allowed():
    """Two states legitimately need different amounts of search."""
    r = compare(receipt(evaluations_performed=4000),
                treated(evaluations_performed=5200), CONTRACT)
    assert isinstance(r, ComparisonResult)


def test_evaluations_beyond_the_declared_tolerance_refuse():
    r = compare(receipt(evaluations_performed=4000),
                treated(evaluations_performed=400_000), CONTRACT)
    assert isinstance(r, InadmissibleComparison)


def test_a_severe_event_makes_an_observation_inadmissible():
    t = treated(events=(ExecutionEvent(EventType.CONVERGENCE_FAILURE, "diverged",
                                       "frequency", severity=Severity.SEVERE),))
    assert not admit(t, CONTRACT)
    assert isinstance(compare(receipt(), t, CONTRACT), InadmissibleComparison)


def test_an_infeasible_solution_is_inadmissible():
    assert not admit(treated(feasible=False), CONTRACT)


def test_certification_requires_both_arms_converged():
    cert = ExperimentContract(
        experiment="exp3", version="3.1", stage="certification",
        objective=CONTRACT.objective, objective_version=CONTRACT.objective_version,
        evaluator=CONTRACT.evaluator, envelope=CONTRACT.envelope,
        pathset_policy=CONTRACT.pathset_policy, pool_version=CONTRACT.pool_version,
        solver=CERTIFICATION,
        allowed_treatment_differences=CONTRACT.allowed_treatment_differences)
    c = receipt(cert, restarts_requested=20, restarts_completed=20,
                converged=False, termination=StopRule.DEADLINE,
                spec_=spec(cert))
    t = receipt(cert, obj=9e5, restarts_requested=20, restarts_completed=20,
                converged=False, termination=StopRule.DEADLINE,
                spec_=spec(cert, state_digest="s1", state_key="m",
                           cardinality=1, members=("m",)))
    assert isinstance(compare(c, t, cert), InadmissibleComparison)


# --------------------------------------------------------------------------
# the contract itself refuses to describe an incomparable experiment
# --------------------------------------------------------------------------

def test_a_treatment_dependent_start_policy_is_refused_at_contract_time():
    with pytest.raises(ContractError):
        ExperimentContract(
            experiment="x", version="1", stage="discovery", objective="o",
            objective_version="1", evaluator="e", envelope="v",
            pathset_policy="p", pool_version="q",
            solver=SolverPolicy(start_policy=StartPolicy.INCUMBENT_ONLY))


def test_a_treatment_dependent_start_policy_is_allowed_if_declared():
    c = ExperimentContract(
        experiment="x", version="1", stage="discovery", objective="o",
        objective_version="1", evaluator="e", envelope="v", pathset_policy="p",
        pool_version="q",
        solver=SolverPolicy(start_policy=StartPolicy.INCUMBENT_ONLY),
        allowed_treatment_differences=frozenset({"starts_attempted"}))
    assert c.digest


def test_certification_contract_must_require_convergence():
    with pytest.raises(ContractError):
        ExperimentContract(
            experiment="x", version="1", stage="certification", objective="o",
            objective_version="1", evaluator="e", envelope="v",
            pathset_policy="p", pool_version="q", solver=DISCOVERY,
            allowed_treatment_differences=frozenset())


# --------------------------------------------------------------------------
# the balance audit: the sweep that would have caught D27 on day one
# --------------------------------------------------------------------------

def test_balance_audit_surfaces_treatment_correlated_execution():
    rs = []
    for i in range(10):                       # controls: never fall back
        rs.append(receipt(state_key="<none>"))
    for i in range(10):                       # lengthening edits: always do
        rs.append(treated(state_key=f"extend-{i:03d}",
                          starts_attempted=("greedy",), fallback_occurred=True,
                          events=(ExecutionEvent(EventType.START_FALLBACK,
                                                 "x", "frequency"),)))
    kind = lambda r: r.spec.state_key.split("-")[0]
    found = balance_audit(rs, kind)
    dims = {i.dimension for i in found}
    assert "START_FALLBACK" in dims
    assert "fallback_occurred" in dims
    assert "starts_attempted" in dims


def test_balance_audit_is_quiet_when_execution_is_balanced():
    rs = [receipt(state_key="<none>") for _ in range(6)] + \
         [treated(state_key=f"extend-{i}") for i in range(6)]
    assert balance_audit(rs, lambda r: r.spec.state_key.split("-")[0]) == []


def test_health_report_fails_closed_on_imbalance():
    rs = [receipt(state_key="<none>") for _ in range(5)] + \
         [treated(state_key="extend-1", starts_attempted=("greedy",),
                  fallback_occurred=True) for _ in range(5)]
    rep = health_report(rs, CONTRACT, lambda r: r.spec.state_key.split("-")[0])
    assert not rep.healthy
    assert rep.imbalances
    assert "TREATMENT-CORRELATED" in rep.text()


# --------------------------------------------------------------------------
# the observation store: cache identity is the whole spec, not the state name
# --------------------------------------------------------------------------

def test_the_cache_key_moves_when_any_semantic_field_moves(tmp_path):
    """A state name is not an identity. Everything that changes the meaning
    of an evaluation must change where its answer is filed."""
    import dataclasses as dc
    base = spec()
    seen = {base.cache_key}
    for field, value in (("evaluator", "pattern_level"),
                         ("objective", "unweighted"),
                         ("objective_version", "lambda=4.0"),
                         ("envelope_digest", "other"),
                         ("pathset_policy", "shared_master"),
                         ("pool_version", "v2"),
                         ("config_digest", "cfg-2"),
                         ("data_digest", "data-2"),
                         ("code_version", "def456"),
                         ("seed", 999),
                         ("state_digest", "s9")):
        k = dc.replace(base, **{field: value}).cache_key
        assert k not in seen, f"{field} does not change the cache key"
        seen.add(k)


def test_the_store_refuses_an_entry_from_an_incompatible_contract(tmp_path):
    from cota_opt.firewall import ObservationStore
    store = ObservationStore(tmp_path)
    store.put(receipt())
    other = dataclasses.replace(CONTRACT, version="3.0")
    got = store.get(spec(), other)
    assert not got
    assert "contract" in got.reason        # written under one, asked under another


def test_the_store_refuses_an_entry_that_no_longer_satisfies_its_contract(tmp_path):
    """The entry was written under this contract and is still wrong for it."""
    from cota_opt.firewall import ObservationStore
    store = ObservationStore(tmp_path)
    store.put(receipt(starts_attempted=("greedy",), restarts_completed=0))
    got = store.get(spec(), CONTRACT)
    assert not got and "inadmissible" in got.reason
    assert got.event is not None and got.event.type is EventType.CACHE_INVALIDATED


def test_a_valid_entry_round_trips(tmp_path):
    from cota_opt.firewall import ObservationStore
    store = ObservationStore(tmp_path)
    store.put(receipt())
    got = store.get(spec(), CONTRACT)
    assert isinstance(got, ExecutionReceipt)
    assert got.spec.digest == spec().digest


def test_only_the_store_names_files_in_the_observation_store():
    """A runner that builds its own path there has its own cache identity.

    Section 13 asks for one canonical key-generation path and a test that fails
    if a runner bypasses it. The store owns its filename prefix; nothing else
    may write it.
    """
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for p in list((root / "src").rglob("*.py")) + list((root / "scripts").rglob("*.py")):
        if p.parent.name == "firewall":     # the key generator and its store
            continue
        text = p.read_text()
        if '"cell-' in text or "'cell-" in text:
            offenders.append(str(p.relative_to(root)))
    assert not offenders, f"bypassing the observation store's identity: {offenders}"


# --------------------------------------------------------------------------
# promotion and canonical results refuse to run on raw scores (sections 11-12)
# --------------------------------------------------------------------------

def test_promotion_refuses_states_without_comparison_receipts(tmp_path, monkeypatch):
    """A score is not a reason to promote. It never was."""
    import importlib.util
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    spec_ = importlib.util.spec_from_file_location(
        "exp3_promote", root / "scripts" / "exp3_promote.py")
    mod = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(mod)

    monkeypatch.setattr(mod, "load_receipts", lambda: {})
    states = {"add_stop-001": {"score": 9.0}, "extend-002": {"score": 8.0}}
    admitted, refused = mod.admissible_states(states)
    assert admitted == {}
    assert len(refused) == 2
    assert all("receipt" in r["why"] or "comparison" in r["why"] for r in refused)


def test_promotion_admits_only_states_whose_comparison_passes(tmp_path, monkeypatch):
    import importlib.util
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    spec_ = importlib.util.spec_from_file_location(
        "exp3_promote2", root / "scripts" / "exp3_promote.py")
    mod = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(mod)

    good = treated(state_key="add_stop-001", members=("add_stop-001",))
    bad = treated(state_key="extend-002", members=("extend-002",),
                  starts_attempted=("greedy",), fallback_occurred=True)
    monkeypatch.setattr(mod, "load_receipts",
                        lambda: {"<none>": receipt(),
                                 "add_stop-001": good, "extend-002": bad})
    admitted, refused = mod.admissible_states(
        {"add_stop-001": {"score": 9.0}, "extend-002": {"score": 8.0}})
    assert set(admitted) == {"add_stop-001"}
    assert [r["state"] for r in refused] == ["extend-002"]


def test_a_finding_cannot_rest_on_a_refused_comparison():
    from cota_opt.firewall import finding
    good = compare(receipt(), treated(), CONTRACT)
    bad = compare(receipt(), treated(starts_attempted=("greedy",)), CONTRACT)
    assert finding("a real effect", [good], experiment="exp3", stage="discovery")
    with pytest.raises(ValueError):
        finding("a claim on refused evidence", [good, bad],
                experiment="exp3", stage="discovery")
    with pytest.raises(ValueError):
        finding("an opinion", [], experiment="exp3", stage="discovery")


def test_superseding_an_observation_names_the_findings_that_depended_on_it():
    from cota_opt.firewall import FindingLog, finding
    import pathlib
    c = compare(receipt(), treated(), CONTRACT)
    f = finding("add_stop-010 beats the null", [c], experiment="exp3",
                stage="discovery")
    log = FindingLog(pathlib.Path("/tmp/findings.json"))
    log.add(f)
    assert log.dependents([c.treatment.receipt.digest]) == [f]
    hit = log.supersede([c.treatment.receipt.digest], "D27: start asymmetry")
    assert len(hit) == 1
    assert not log.findings[0].live
    assert log.findings[0].superseded.startswith("D27")
    assert log.dependents([c.treatment.receipt.digest]) == []


# --------------------------------------------------------------------------
# methodology generation: Gen2 is a different generation's answer, not a fix
# --------------------------------------------------------------------------

def test_the_generation_is_part_of_the_cache_identity():
    import dataclasses as dc
    assert spec().cache_key != dc.replace(
        spec(), methodology_generation="gen2").cache_key


def test_a_cell_from_another_generation_is_not_this_experiments_evidence():
    gen2 = dataclasses.replace(CONTRACT, methodology_generation="gen2")
    g2 = ExecutionReceipt(
        spec=spec(gen2), evaluator_used=CONTRACT.evaluator,
        objective_used=CONTRACT.objective,
        start_policy_requested=CONTRACT.solver.start_policy,
        starts_attempted=("repaired", "greedy"), restarts_completed=2,
        converged=True, objective=9e5)
    assert not admit(g2, CONTRACT)
    assert isinstance(compare(receipt(), g2, CONTRACT), InadmissibleComparison)


def test_a_comparison_records_the_generation_that_produced_it():
    r = compare(receipt(), treated(), CONTRACT)
    assert r.as_dict()["methodology_generation"] == "gen1"
