"""Proposal revision 2: multi-start with structural seeding.

C9 revision 1 failed because a single steepest-descent trajectory covers one
basin, not a space. These pin the properties the revision claims, so a later
change that quietly reverts to single-basin behaviour fails here rather than in
a recall number three hours downstream.
"""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cota_opt.exp4_proposal import (N_DIVERSIFIED,            # noqa: E402
                                    PROPOSAL_DIGEST, PROPOSAL_RULE,
                                    SEED_SCHEDULE_BASE, TOTAL_EVAL_BUDGET,
                                    _spread, build_seed_family,
                                    diversified_starts, run_multi_start)

POOL = [f"L{i}" for i in range(8)]


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------

def test_seed_family_is_deterministic_and_ordered():
    a = build_seed_family(POOL, 1, 3, pinned_lines=["L0"])
    b = build_seed_family(POOL, 1, 3, pinned_lines=["L0"])
    assert [s.name for s in a] == [s.name for s in b]
    assert [s.lines for s in a] == [s.lines for s in b]


def test_diversified_starts_are_deterministic():
    a = diversified_starts(POOL, 1, 3, 12)
    b = diversified_starts(POOL, 1, 3, 12)
    assert [s.lines for s in a] == [s.lines for s in b]


def test_the_same_schedule_is_used_for_every_cell():
    """No cell may receive seeds chosen for it."""
    src = inspect.getsource(diversified_starts)
    assert "base: int = SEED_SCHEDULE_BASE" in src
    tree = ast.parse(ROOT.joinpath("src/cota_opt/exp4_proposal.py").read_text())
    assigns = {t.id for st in ast.walk(tree) if isinstance(st, ast.Assign)
               for t in st.targets if isinstance(t, ast.Name)}
    assert "SEED_SCHEDULE_BASE" in assigns
    # one schedule constant, not a per-cell mapping
    assert isinstance(SEED_SCHEDULE_BASE, int)


def test_proposal_rule_digest_is_stable():
    assert PROPOSAL_DIGEST
    from cota_opt.firewall.core import digest
    assert digest(PROPOSAL_RULE) == PROPOSAL_DIGEST


# ---------------------------------------------------------------------------
# the seeds actually span the treatment dimension
# ---------------------------------------------------------------------------

def test_spread_selects_evenly_not_the_first_k():
    """Taking the first k puts every seed in one corner of the pool."""
    got = _spread(POOL, 3)
    assert got != tuple(POOL[:3])
    assert len(got) == 3
    idx = sorted(POOL.index(x) for x in got)
    # the span must cover most of the pool, not cluster at the front
    assert idx[-1] - idx[0] >= len(POOL) // 2


def test_family_spans_every_cardinality_in_range():
    fam = build_seed_family(POOL, 1, 4)
    sizes = {len(s.lines) for s in fam}
    assert {1, 2, 3, 4} <= sizes


def test_family_includes_the_dense_and_sparse_corners():
    fam = build_seed_family(POOL, 2, 5)
    names = {s.name for s in fam}
    assert "max_lines" in names and "min_lines" in names
    mx = next(s for s in fam if s.name == "max_lines")
    mn = next(s for s in fam if s.name == "min_lines")
    assert len(mx.lines) == 5 and len(mn.lines) == 2


def test_two_seeds_of_the_same_size_cover_different_lines():
    fam = build_seed_family(POOL, 1, 3)
    for k in (2, 3):
        same = [s.lines for s in fam if len(s.lines) == k
                and s.kind == "structural"]
        if len(same) >= 2:
            assert len(set(same)) == len(same), (
                f"two structural seeds of size {k} sit on the same lines")


def test_off_density_variants_appear_when_a_line_is_pinned():
    fam = build_seed_family(POOL, 1, 4, pinned_lines=["L0"])
    kinds = {s.kind for s in fam}
    assert "off_density" in kinds
    off = [s for s in fam if s.kind == "off_density"]
    activates = [s for s in off if "L0" in s.lines]
    excludes = [s for s in off if "L0" not in s.lines]
    assert activates and excludes, (
        "both the basin where the pin binds and its complement must be seeded")


def test_greedy_constructions_enter_the_family_when_supplied():
    fam = build_seed_family(POOL, 1, 3, greedy_add=("L1", "L4"),
                            greedy_drop=("L0", "L2", "L7"))
    names = {s.name for s in fam}
    assert {"greedy_add", "greedy_drop"} <= names


def test_seeds_respect_the_cardinality_bounds():
    fam = build_seed_family(POOL, 2, 4, pinned_lines=["L0"],
                            greedy_add=("L1",), greedy_drop=tuple(POOL))
    for s in fam:
        assert 2 <= len(s.lines) <= 4, f"{s.name} is outside the bounds"


# ---------------------------------------------------------------------------
# the multi-start driver
# ---------------------------------------------------------------------------

class _Sel:
    def __init__(self, lines):
        self.lines = frozenset(lines)
        self.pinned_off = frozenset()
        self.state_key = "|".join(sorted(lines))
        self.state_digest = self.state_key


class _Cand:
    def __init__(self, sel, obj):
        self.selection = sel
        self.objective = obj
        self.feasible = True


def _fake_search(pool, scorer, periods, *, seed_lines, max_lines, min_lines,
                 pinned_off, pool_version, allow_swaps, pair_adds,
                 max_evaluations):
    """A stand-in that visits the seed and its single-add neighbours."""
    visited = [tuple(sorted(seed_lines))]
    for x in pool:
        if x not in seed_lines and len(seed_lines) + 1 <= max_lines:
            visited.append(tuple(sorted(tuple(seed_lines) + (x,))))
    out = []
    for v in visited[:max_evaluations]:
        sel = _Sel(v)
        out.append(_Cand(sel, scorer(sel)[0]))

    class R:
        evaluated = out
    return R()


def _scorer(sel):
    return (100.0 + len(sel.lines), {}, True, {})


def test_budget_is_shared_not_per_start():
    """A start that converges early must release what it did not use."""
    src = inspect.getsource(run_multi_start)
    assert "remaining = budget - charged" in src
    assert "max_evaluations=max(remaining, 1)" in src


def test_one_start_reaching_a_local_optimum_stops_nothing_globally():
    fam = build_seed_family(POOL, 1, 2)
    r = run_multi_start(POOL, _scorer, ["am_peak"], lo=1, hi=2, pins=(),
                        pool_version="test", seed_family=fam,
                        search_fn=_fake_search)
    assert len(r.starts_run) == len(fam), (
        "every preregistered start must run unless the budget is exhausted")


def test_proposal_set_is_the_union_of_everything_visited():
    """Not only the terminal optima -- a trajectory contributes its whole path."""
    fam = build_seed_family(POOL, 1, 2)
    r = run_multi_start(POOL, _scorer, ["am_peak"], lo=1, hi=2, pins=(),
                        pool_version="test", seed_family=fam,
                        search_fn=_fake_search)
    assert len(r.candidates) > len(fam), (
        "the proposal set is no bigger than the seed count, so only endpoints "
        "were kept")


def test_duplicates_are_counted_but_not_charged():
    fam = build_seed_family(POOL, 1, 2)
    r = run_multi_start(POOL, _scorer, ["am_peak"], lo=1, hi=2, pins=(),
                        pool_version="test", seed_family=fam,
                        search_fn=_fake_search)
    assert r.duplicate_visits > 0
    assert r.unique_evaluations == len(r.candidates), (
        "only first-time scores may be charged against a shared budget")


def test_budget_exhaustion_is_recorded():
    fam = build_seed_family(POOL, 1, 2)
    r = run_multi_start(POOL, _scorer, ["am_peak"], lo=1, hi=2, pins=(),
                        pool_version="test", seed_family=fam, budget=3,
                        search_fn=_fake_search)
    assert r.budget_exhausted


def test_saturation_curve_is_recorded_for_diagnosis():
    fam = build_seed_family(POOL, 1, 2)
    r = run_multi_start(POOL, _scorer, ["am_peak"], lo=1, hi=2, pins=(),
                        pool_version="test", seed_family=fam,
                        search_fn=_fake_search)
    assert r.saturation == sorted(r.saturation), "cumulative unique must rise"
    assert len(r.marginal) == len(r.saturation)
    assert r.payload()["marginal_unique_per_start"] == r.marginal


def test_multi_start_is_reproducible():
    fam = build_seed_family(POOL, 1, 2)
    a = run_multi_start(POOL, _scorer, ["am_peak"], lo=1, hi=2, pins=(),
                        pool_version="test", seed_family=fam,
                        search_fn=_fake_search)
    b = run_multi_start(POOL, _scorer, ["am_peak"], lo=1, hi=2, pins=(),
                        pool_version="test", seed_family=fam,
                        search_fn=_fake_search)
    assert sorted(a.candidates) == sorted(b.candidates)
    assert a.saturation == b.saturation


# ---------------------------------------------------------------------------
# the revision changed proposal only
# ---------------------------------------------------------------------------

def test_the_revision_declares_it_changes_no_inference():
    assert PROPOSAL_RULE["changes_to_inference"] == "none"
    assert PROPOSAL_RULE["revision"] == 2


def test_proposal_module_never_touches_promotion_or_certification():
    src = ROOT.joinpath("src/cota_opt/exp4_proposal.py").read_text()
    tree = ast.parse(src)
    imported = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            imported.add(n.module or "")
    for forbidden in ("exp4_promotion", "exp4_certify", "exp4_inference"):
        assert not any(forbidden in m for m in imported), (
            f"the proposal module imports {forbidden}; the revision is to "
            f"proposal generation ALONE")


def test_budget_is_far_above_what_revision_one_actually_used():
    """Revision 1 had a ceiling of 400 and used 13-23. The ceiling was never
    the binding constraint, so raising it alone would have changed nothing --
    the point of the revision is more STARTS, and the budget must not become
    the new limiter."""
    assert TOTAL_EVAL_BUDGET >= 1000
    assert N_DIVERSIFIED >= 12
