"""Regression cover for gate 4-7's one-factor design.

The first gate 4-7 benchmark varied reuse AND enumeration richness together and
was therefore unidentified. It reported a difference at survival fraction 1.000
-- where filtering keeps every path and is the identity -- which is impossible
for a difference caused by filtering, and nothing caught it.

These are the tests that would have. Most pin the DESIGN rather than the
numbers, so they run without a harness and cannot rot into
"the artifact exists": a benchmark whose two arms can differ in more than one
thing is broken whatever it prints.
"""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

GATE47 = ROOT / "scripts" / "exp4_gate47.py"
SRC = GATE47.read_text()
#: prose in this file is wrapped, so phrase assertions run against a
#: whitespace-collapsed copy rather than the raw source
FLAT = " ".join(SRC.split())


# ---------------------------------------------------------------------------
# 1. the confound cannot be reintroduced inside the decisive path
# ---------------------------------------------------------------------------

def test_enumeration_settings_are_constants_not_options():
    """Richness must not be settable per arm, or per run, in the gate script.

    `--scenarios` was a command-line option on the old benchmark and that is
    how the two arms ended up enumerating differently. Here the setting is a
    module constant used by the single `score` helper both arms call.
    """
    assert "COMMON_SCENARIOS = 0" in SRC
    assert "COMMON_MAX_PATHS = None" in SRC
    tree = ast.parse(SRC)
    opts = [n.args[0].value for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and getattr(getattr(n.func, "attr", None), "__str__", str)() ==
            "add_argument"
            and n.args and isinstance(n.args[0], ast.Constant)]
    assert "--scenarios" not in opts, (
        "the gate script must not expose an enumeration-richness option; that "
        "is the confound, not a parameter")
    assert "--master-paths-per-od" not in opts


def test_both_arms_go_through_one_scoring_helper():
    """Two call sites with two settings is how the arms drifted apart."""
    tree = ast.parse(SRC)
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "score_exp4_network"]
    assert len(calls) == 1, (
        f"score_exp4_network is called from {len(calls)} places; both arms must "
        f"share one helper so neither can be given different enumeration "
        f"settings")
    kw = {k.arg for k in calls[0].keywords}
    assert {"n_random_scenarios", "max_paths_per_od"} <= kw
    for k in calls[0].keywords:
        if k.arg == "n_random_scenarios":
            assert isinstance(k.value, ast.Name) and \
                k.value.id == "COMMON_SCENARIOS"
        if k.arg == "max_paths_per_od":
            assert isinstance(k.value, ast.Name) and \
                k.value.id == "COMMON_MAX_PATHS"


# ---------------------------------------------------------------------------
# 2. one canonical candidate universe, asserted before scoring
# ---------------------------------------------------------------------------

def test_universe_is_built_before_the_arms_and_digested():
    assert "universe_digest = digest(" in SRC
    assert "ordered_ids = tuple(" in SRC
    # the digest must be computed before either arm scores anything
    assert SRC.index("universe_digest = digest(") < SRC.index("for c in universe:")


def test_universe_identity_is_asserted_not_assumed():
    assert "the two arms were handed different universes" in FLAT
    assert "universe drifted between construction and use" in FLAT
    # and the assertion must precede the scoring loop
    assert SRC.index("the two arms were handed different universes") < \
        SRC.index("# ---- 4. score")


def test_admission_is_arm_independent():
    """A candidate is admitted by ASSEMBLY, which no arm influences.

    Admitting on "did this arm manage to score it" lets the two arms end up
    with different sets, which is the confound in a different costume.
    """
    assert "def assemble_or_none" in SRC
    assert "asymmetric_scoring_failure" in FLAT, (
        "a candidate that scores in one arm and not the other must be recorded "
        "as a discrepancy, never silently skipped")


def test_fresh_does_not_enumerate_its_own_candidates():
    """FRESH rebuilds path/network/evaluator state, not the candidate list."""
    assert "_subsets(sup_lines, lo, hi)" in SRC
    # exactly one place builds candidates, and it is before the arms
    assert SRC.count("for sub in _subsets(") == 1
    assert SRC.index("for sub in _subsets(") < SRC.index("# ---- 4. score")


# ---------------------------------------------------------------------------
# 3. FRESH really rebuilds; REUSE really reuses
# ---------------------------------------------------------------------------

def test_fresh_arm_forces_a_rebuild_and_reuse_arm_does_not():
    """`pathset_cache` is the switch: an empty dict rebuilds, a filled one reuses."""
    from cota_opt.exp2 import build_setup
    src = inspect.getsource(build_setup)
    assert "if pathset_cache is not None and per in pathset_cache:" in src, (
        "the reuse path is keyed on the period already being present in the "
        "cache; if that changes, FRESH and REUSE stop meaning what this "
        "benchmark says they mean")
    assert "fresh_cache: dict = {}" in SRC
    assert "fr = score(sel, case, fresh_cache)" in SRC
    assert "ru = score(sel, case, filt)" in SRC
    # REUSE must be fed the filtered master, not a fresh dict
    assert "filt[per], prov[per] = filter_for_network(mps, list(ck))" in SRC


def test_rp_keys_come_from_the_assembled_network_not_from_an_arm():
    assert "def rp_keys_of(built)" in SRC
    assert "route-period keys derived from" in FLAT, (
        "the derivation must be asserted against the evaluator's own rp_keys "
        "on every candidate, or a silent mismatch indexes the filter against "
        "the wrong vector")


# ---------------------------------------------------------------------------
# 4. survival = 1.000 must be the identity
# ---------------------------------------------------------------------------

def test_survival_one_identity_is_checked_first_and_is_a_hard_failure():
    assert "survival_1_not_identity" in SRC
    assert "min_survival'] >= 1.0" in SRC or 'min_survival"] >= 1.0' in SRC
    # it must gate the verdict, not merely be reported
    assert "unit_ok" in SRC and "and unit_ok" in SRC


def test_filter_at_full_survival_preserves_the_path_arrays():
    """The identity claim, exercised on a synthetic path set with no harness."""
    from cota_opt.exp4_masterpath import filter_for_network
    from cota_opt.pathset import PathSet

    rp = [("r1", "am_peak"), ("r2", "am_peak")]
    ps = PathSet(
        period="am_peak", n_od=2,
        leg_path=np.array([0, 0, 1, 2], dtype=np.int64),
        leg_rp=np.array([0, 1, 0, 1], dtype=np.int64),
        leg_ivt=np.array([5.0, 6.0, 7.0, 8.0]),
        leg_walk=np.array([1.0, 0.0, 2.0, 0.0]),
        leg_is_boarding=np.array([True, True, True, True]),
        leg_is_transfer=np.array([False, True, False, False]),
        path_od=np.array([0, 0, 1], dtype=np.int64),
        path_offsets=np.array([0, 2, 3, 4], dtype=np.int64),
        od_offsets=np.array([0, 2, 3], dtype=np.int64),
        od_flow=np.array([10.0, 20.0]),
        od_walk_only=np.array([99.0, 99.0]),
        rp_keys=list(rp))

    out, prov = filter_for_network(ps, list(rp))
    assert prov["survival_fraction"] == 1.0
    assert prov["kept_paths"] == prov["master_paths"] == 3
    assert np.array_equal(out.leg_path, ps.leg_path)
    assert np.array_equal(out.leg_rp, ps.leg_rp)
    assert np.array_equal(out.leg_ivt, ps.leg_ivt)
    assert np.array_equal(out.path_od, ps.path_od)
    assert np.array_equal(out.path_offsets, ps.path_offsets)
    assert list(out.rp_keys) == list(rp)


def test_filter_drops_exactly_the_paths_that_use_an_absent_route():
    """And the survival fraction is not decorative."""
    from cota_opt.exp4_masterpath import filter_for_network
    from cota_opt.pathset import PathSet

    rp = [("r1", "am_peak"), ("r2", "am_peak")]
    ps = PathSet(
        period="am_peak", n_od=2,
        leg_path=np.array([0, 0, 1, 2], dtype=np.int64),
        leg_rp=np.array([0, 1, 0, 1], dtype=np.int64),
        leg_ivt=np.array([5.0, 6.0, 7.0, 8.0]),
        leg_walk=np.array([1.0, 0.0, 2.0, 0.0]),
        leg_is_boarding=np.array([True, True, True, True]),
        leg_is_transfer=np.array([False, True, False, False]),
        path_od=np.array([0, 0, 1], dtype=np.int64),
        path_offsets=np.array([0, 2, 3, 4], dtype=np.int64),
        od_offsets=np.array([0, 2, 3], dtype=np.int64),
        od_flow=np.array([10.0, 20.0]),
        od_walk_only=np.array([99.0, 99.0]),
        rp_keys=list(rp))

    # candidate runs r1 only: path 0 uses both routes and dies, path 1 uses r1
    # and lives, path 2 uses r2 and dies.
    out, prov = filter_for_network(ps, [("r1", "am_peak")])
    assert prov["kept_paths"] == 1
    assert prov["survival_fraction"] == pytest.approx(1 / 3)
    assert out.n_paths == 1
    assert np.array_equal(out.leg_rp, np.array([0]))
    assert list(out.rp_keys) == [("r1", "am_peak")]


# ---------------------------------------------------------------------------
# 5. what the gate compares, and how it closes
# ---------------------------------------------------------------------------

def test_all_seven_fitness_fields_are_compared_and_unknown_names_rejected():
    from cota_opt.exp4_score import ScoredExp4Network
    import dataclasses
    seven = {"generalized_cost", "unserved_demand", "served_demand",
             "revenue_veh_hours", "peak_vehicles", "mean_wait_min",
             "gc_per_served_trip"}
    assert "FIELDS = [" in SRC
    for f in seven:
        assert f'"{f}"' in SRC
    assert "fitness is missing" in FLAT
    fnames = {f.name for f in dataclasses.fields(ScoredExp4Network)}
    assert "fitness" in fnames


def test_closure_requires_leader_ranking_and_promoted_set_together():
    assert "closes = bool(case_reports) and leaders and ranks and promo" in SRC
    assert "and unit_ok" in SRC
    assert "not hard_failures" in SRC
    # and the loose readings must be explicitly refused
    assert "Same leader most of the time does not close it" in FLAT


def test_widening_the_master_is_not_offered_as_the_remedy():
    assert "Widening the master is NOT the remedy" in FLAT


def test_pinned_off_is_checked_in_both_arms():
    assert "pinned_off_leak" in SRC
    assert '("fresh", fr), ("reuse", ru)' in SRC


def test_deterministic_rerun_fields_are_recorded_for_byte_comparison():
    """The receipt must carry what a rerun would be compared on."""
    for k in ("universe_digest", "ordered_ids", "master", "worst_field_rel_diff",
              "leader_fresh", "leader_reuse", "promoted_fresh", "promoted_reuse"):
        assert f'"{k}"' in SRC


def test_the_superseded_benchmark_is_named_and_preserved():
    assert "masterpath_benchmark.json" in SRC
    assert "Preserved, not deleted" in FLAT
    assert (ROOT / "scripts" / "exp4_masterpath_benchmark.py").exists(), (
        "the confounded benchmark is evidence of why the amendment was needed "
        "and must not be deleted")
