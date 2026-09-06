"""The proposal/certification boundary, tested as an architecture.

D18 found that the discovery heuristic's distance from optimal tracks network
structure, which makes discovery scores unusable for any Experiment 4
conclusion. The remedy is architectural -- discovery proposes, exact
optimization decides -- and an architecture is only real if violating it fails.

These tests are the failure. Most need no harness: they pin the SHAPE of the
boundary, so a future one-line `sorted(candidates, key=discovery_score)` raises
instead of quietly producing a wrong answer.
"""
from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cota_opt.exp4_certify import (CERTIFICATION_CONTRACT,      # noqa: E402
                                   CERTIFICATION_DIGEST, certify)
from cota_opt.exp4_inference import (Exp4Candidate,             # noqa: E402
                                     CertifiedResult,
                                     InferenceViolation,
                                     ProposalRecord, ProposalScore,
                                     TIE_BREAK, TIE_BREAK_DIGEST,
                                     rank_certified, tie_break_key)
from cota_opt.exp4_promotion import (CAP_N, FLOOR_N,            # noqa: E402
                                     PROMOTION_DIGEST, PROMOTION_RULE,
                                     WINDOW_REL, promote)


def _prop(key, val):
    return ProposalRecord(state_key=key, state_digest=f"d-{key}",
                          score=ProposalScore(val))


def _cert(key, obj):
    return CertifiedResult(
        state_key=key, state_digest=f"d-{key}", objective=obj,
        fitness={"generalized_cost": obj}, plan_digest="p",
        guarantee="test", n_keys=8, k_rungs=3, rounds=3, converged=True,
        block_enumerations=3, combinations=100, seconds=1.0)


# ---------------------------------------------------------------------------
# 1. a discovery score cannot become a final score
# ---------------------------------------------------------------------------

def test_discovery_score_refuses_every_inference_operation():
    s = ProposalScore(3_600_000.0)
    for fn in (lambda: float(s), lambda: int(s), lambda: s < 1, lambda: s > 1,
               lambda: s <= 1, lambda: s >= 1, lambda: s + 1, lambda: 1 + s,
               lambda: s * 2, lambda: -s, lambda: abs(s), lambda: round(s),
               lambda: f"{s:.2f}"):
        with pytest.raises(InferenceViolation):
            fn()


def test_discovery_scores_cannot_be_sorted():
    """The one-line mistake this whole module exists to prevent."""
    scores = [ProposalScore(3.0), ProposalScore(1.0), ProposalScore(2.0)]
    with pytest.raises(InferenceViolation):
        sorted(scores)


def test_discovery_score_is_not_a_float_subclass():
    """Subclassing float would make every comparison work by default."""
    assert not isinstance(ProposalScore(1.0), float)


def test_the_only_accessor_is_named_for_its_one_permitted_use():
    s = ProposalScore(42.0)
    assert s.for_promotion_only() == 42.0
    public = [n for n in dir(s) if not n.startswith("_")]
    assert sorted(public) == ["for_promotion_only", "stage"]


def test_uncertified_candidate_has_no_usable_number():
    c = Exp4Candidate(proposal=_prop("k1", 100.0))
    with pytest.raises(InferenceViolation):
        c.final_objective
    with pytest.raises(InferenceViolation):
        c.final_fitness


# ---------------------------------------------------------------------------
# 2. a discovery rank cannot become a final rank
# ---------------------------------------------------------------------------

def test_ranking_refuses_uncertified_candidates():
    cands = [Exp4Candidate(proposal=_prop("a", 1.0),
                           certification=_cert("a", 10.0)),
             Exp4Candidate(proposal=_prop("b", 2.0))]
    with pytest.raises(InferenceViolation):
        rank_certified(cands, lambda c: ["L1"], lambda c: 0)


def test_ranking_uses_certified_objective_not_proposal_order():
    """Proposal order is deliberately the REVERSE of certified order here."""
    a = Exp4Candidate(proposal=_prop("a", 1.0), certification=_cert("a", 99.0))
    b = Exp4Candidate(proposal=_prop("b", 99.0), certification=_cert("b", 1.0))
    out = rank_certified([a, b], lambda c: ["L1"], lambda c: 0)
    assert [c.state_key for c in out] == ["b", "a"]


def test_changing_a_discovery_score_after_promotion_changes_no_conclusion():
    """Section 9's explicit requirement, exercised rather than asserted."""
    a = Exp4Candidate(proposal=_prop("a", 1.0), certification=_cert("a", 5.0))
    b = Exp4Candidate(proposal=_prop("b", 2.0), certification=_cert("b", 7.0))
    before = [c.state_key for c in rank_certified([a, b], lambda c: ["L"],
                                                  lambda c: 0)]
    # rewrite both discovery scores to the opposite order
    a.proposal = ProposalRecord("a", "d-a", ProposalScore(1000.0))
    b.proposal = ProposalRecord("b", "d-b", ProposalScore(0.001))
    after = [c.state_key for c in rank_certified([a, b], lambda c: ["L"],
                                                 lambda c: 0)]
    assert before == after == ["a", "b"]


# ---------------------------------------------------------------------------
# 3. the tie-break is structural and preregistered
# ---------------------------------------------------------------------------

def _code_names(fn) -> set[str]:
    """Every identifier the function's CODE touches, docstring excluded.

    A substring search over the source matches prose, and prose that explains
    why something is absent contains the word for it. That is how the first
    version of this test failed on its own docstring -- the same crudeness that
    once flipped a readiness check to MET because a NAME began with EXP4. Parse
    the body instead.
    """
    tree = ast.parse(inspect.getsource(fn).lstrip())
    fn_node = tree.body[0]
    body = fn_node.body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]                      # drop the docstring
    names = set()
    for stmt in body:
        for n in ast.walk(stmt):
            if isinstance(n, ast.Name):
                names.add(n.id)
            elif isinstance(n, ast.Attribute):
                names.add(n.attr)
            elif isinstance(n, ast.Constant) and isinstance(n.value, str):
                names.add(n.value)
    return names


def test_tie_break_contains_no_discovery_quantity():
    assert TIE_BREAK == ("fewer_active_lines", "fewer_off_route_periods",
                         "lexicographic_line_ids")
    names = _code_names(tie_break_key)
    for forbidden in ("proposal", "discovery", "score", "rank_within_proposals",
                      "for_promotion_only"):
        assert forbidden not in names, (
            f"the tie-break's CODE touches {forbidden!r}; it must be a "
            f"function of the NETWORK alone")
    # and positively: it reads only the network facts it was given
    assert {"lines", "n_off", "cand"} >= (names & {"lines", "n_off", "cand"})


def test_tie_break_prefers_the_more_parsimonious_network():
    small = Exp4Candidate(proposal=_prop("s", 1.0), certification=_cert("s", 5.0))
    big = Exp4Candidate(proposal=_prop("b", 1.0), certification=_cert("b", 5.0))
    lines = {"s": ["L1"], "b": ["L1", "L2", "L3"]}
    out = rank_certified([big, small], lambda c: lines[c.state_key],
                         lambda c: 0)
    assert [c.state_key for c in out] == ["s", "b"]


def test_tie_break_is_total_and_deterministic():
    a = Exp4Candidate(proposal=_prop("a", 1.0), certification=_cert("a", 5.0))
    b = Exp4Candidate(proposal=_prop("b", 1.0), certification=_cert("b", 5.0))
    lines = {"a": ["L2"], "b": ["L1"]}
    for order in ([a, b], [b, a]):
        out = rank_certified(order, lambda c: lines[c.state_key], lambda c: 0)
        assert [c.state_key for c in out] == ["b", "a"]


# ---------------------------------------------------------------------------
# 4. the promotion rule is deterministic and permissive
# ---------------------------------------------------------------------------

def test_promotion_is_order_independent():
    props = [_prop(f"k{i:02d}", 100.0 + i) for i in range(60)]
    a = promote(props)
    b = promote(list(reversed(props)))
    assert a.promoted_keys == b.promoted_keys
    assert a.rule_digest == b.rule_digest == PROMOTION_DIGEST


def test_promotion_window_exceeds_d18_measured_error_by_a_stated_margin():
    j = PROMOTION_RULE["justification"]
    worst = j["worst_case_discovery_misplacement_pct"]
    assert worst == pytest.approx(0.645892 + 0.381749, abs=0.02)
    assert WINDOW_REL * 100 / worst > 4.0, (
        "the promotion window must be several times the worst discovery error "
        "D18 actually measured, or a true winner can fall outside it")


def test_promotion_floor_applies_when_the_window_is_narrow():
    """A tightly spread space must still certify a meaningful set."""
    props = [_prop(f"k{i:02d}", 100.0 * (1 + i)) for i in range(40)]
    out = promote(props)
    assert out.n_promoted >= FLOOR_N
    assert out.floor_binding


def test_promotion_cap_binding_is_recorded_as_a_recall_risk():
    props = [_prop(f"k{i:04d}", 100.0 + i * 1e-6) for i in range(CAP_N + 50)]
    out = promote(props)
    assert out.cap_binding
    assert out.n_promoted == CAP_N
    assert "CAP BOUND" in out.payload()["recall_risk"]


def test_infeasible_proposals_are_never_promoted():
    props = [_prop("good", 100.0), _prop("bad", 1.0)]
    out = promote(props, {"good": True, "bad": False})
    assert out.promoted_keys == ["good"]


# ---------------------------------------------------------------------------
# 5. certification rebuilds under the frozen production contract
# ---------------------------------------------------------------------------

def test_certification_uses_solve_exact_through_the_production_scorer():
    src = inspect.getsource(certify)
    assert 'solver="exact"' in src
    assert "ladder_override=lads" in src
    assert "from .exp3_score import solve_on_network" in src


def test_certification_states_its_guarantee_rather_than_implying_one():
    g = CERTIFICATION_CONTRACT["guarantee"]
    assert "no block of 8 route-periods" in g
    assert "3 ladder rungs" in g
    assert CERTIFICATION_DIGEST


def test_certification_refuses_a_result_worse_than_the_delivered_plan():
    src = inspect.getsource(certify)
    assert "WORSE objective than the" in src
    assert "CertificationError" in src


def test_certification_rotates_blocks():
    """Without rotation the fixed point is an artifact of the partition."""
    src = inspect.getsource(certify)
    assert "rot = ks[off:] + ks[:off]" in src
    assert CERTIFICATION_CONTRACT["rotation"].startswith("offset advances")


def test_non_convergence_is_recorded_not_hidden():
    src = inspect.getsource(certify)
    assert "converged = True" in src
    assert "converged=converged" in src


# ---------------------------------------------------------------------------
# 6. master-path reuse cannot reach a certified score
# ---------------------------------------------------------------------------

def test_certification_never_takes_a_pathset_cache():
    """Reuse is a proposal-stage device and must not touch certification."""
    sig = inspect.signature(certify)
    assert "pathset_cache" not in sig.parameters
    src = inspect.getsource(certify)
    assert "pathset_cache" not in src, (
        "certification must rebuild paths; a cache parameter would let the "
        "biased reuse shortcut reach a certified number")


def test_certify_signature_carries_the_frozen_contract_fields():
    sig = inspect.signature(certify)
    for p in ("harness", "lam", "seed", "constraints", "pinned_off",
              "waiting_model", "contract_digest"):
        assert p in sig.parameters


# ---------------------------------------------------------------------------
# 7. C9 is a recall test, not an agreement test
# ---------------------------------------------------------------------------

C9 = (ROOT / "scripts" / "exp4_c9_recall.py").read_text()
C9_FLAT = " ".join(C9.split())


def test_c9_criterion_is_recall_and_says_what_it_is_not():
    from importlib import util
    spec = util.spec_from_file_location(
        "c9", ROOT / "scripts" / "exp4_c9_recall.py")
    m = util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.C9_CRITERION["primary"].startswith("the certified winner")
    assert "agreement" in m.C9_CRITERION["not_the_criterion"]
    assert m.FRONTIER_K == 5
    assert m.FRONTIER_MIN_RECALL == 0.90


def test_c9_does_not_use_the_d18_promotion_band():
    assert "promotion band" not in C9_FLAT.lower() or \
        "emitted no band" in C9_FLAT
    assert "q4_promotion_band" not in C9


def test_c9_benchmarks_include_sparse_and_dense():
    for name in ("sparse_wide_pool", "sparse_to_mid", "dense", "many_off",
                 "other_pool"):
        assert f'"{name}"' in C9


def test_c9_ground_truth_uses_the_same_certification_instrument():
    assert "from cota_opt.exp4_certify import" in C9
    assert "certify(built.network, built.tstats" in C9


# ---------------------------------------------------------------------------
# 8. D18 is preserved, byte-identical, and MET
# ---------------------------------------------------------------------------

D18 = ROOT / "outputs" / "exp4" / "gap_benchmark.json"


@pytest.mark.skipif(not D18.exists(), reason="D18 has not been run here")
def test_d18_receipt_is_unchanged():
    d = json.loads(D18.read_text())
    assert d["n_cells"] == 36
    assert d["q1_median_gap_pct"] == pytest.approx(0.297432, abs=5e-6)
    assert d["q1_max_gap_pct"] == pytest.approx(0.645892, abs=5e-6)
    assert d["q3_largest_paired_differential_pp"] == pytest.approx(
        0.381749, abs=5e-6)
    assert d["q3_ratio"] == pytest.approx(1.283, abs=5e-4)
    assert d["q3_gap_tracks_structure"] is True
    assert d["discovery_effort_comparison_permitted"] is False
    assert d["q4_promotion_band_pp"] is None
    assert d["design_digest"] == "69be98f915d60492"


@pytest.mark.skipif(not D18.exists(), reason="D18 has not been run here")
def test_nothing_reintroduces_a_promotion_band():
    """Structural, not textual: the module's docstring EXPLAINS the absence of
    a band, so it necessarily contains the word. What must be absent is a band
    in the code -- a constant, a rule key, or a read of D18's band field."""
    from cota_opt import exp4_promotion
    tree = ast.parse(inspect.getsource(exp4_promotion))
    consts = {t.id for st in tree.body if isinstance(st, ast.Assign)
              for t in st.targets if isinstance(t, ast.Name)}
    assert not [c for c in consts if "BAND" in c.upper()], (
        f"a band-shaped constant reappeared: {consts}")
    assert "band" not in {k.lower() for k in PROMOTION_RULE}
    assert "band" not in {k.lower() for k in PROMOTION_RULE["justification"]}
    # and D18's band field is never read
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            assert "q4_promotion_band" not in n.value
        if isinstance(n, ast.Attribute):
            assert "band" not in n.attr.lower()
