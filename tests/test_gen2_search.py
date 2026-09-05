"""Gen2 outer search — the three route-period states and the oracle contract."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cota_opt.exp4_network import Exp4Selection                    # noqa: E402
from cota_opt.frequency import OFF                                 # noqa: E402
from cota_opt.gen2_search import (Fate, enumerate_exact,           # noqa: E402
                                  provenance, search)

LINES = ["L1", "L2", "L3", "L4"]
PERIODS = ["am_peak", "midday"]


def _scorer(costs):
    """Objective from a table; lower is better. Feasible unless cost is None."""
    def s(sel: Exp4Selection):
        key = tuple(sorted(sel.lines))
        v = costs.get(key)
        if v is None:
            return float("inf"), {}, False, {}
        plan = {}
        for ln in sorted(sel.lines):
            for p in PERIODS:
                plan[f"{ln}|{p}"] = (OFF if sel.is_pinned_off(ln, p)
                                     else (OFF if ln == "L4" else 10.0))
        return float(v), {"objective": float(v)}, True, plan
    return s


# ----------------------------------------------------- the three OFF states
def test_absent_pinned_off_and_chosen_off_are_distinct():
    sel = Exp4Selection.of("v", ["L1", "L4"], [("L1", "midday")])
    plan = {"L1|am_peak": 10.0, "L1|midday": OFF,
            "L4|am_peak": OFF, "L4|midday": OFF}
    fates = {(f.line_id, f.period): f.fate
             for f in provenance(sel, plan, LINES, PERIODS)}

    assert fates[("L2", "am_peak")] is Fate.ABSENT       # not selected
    assert fates[("L1", "midday")] is Fate.PINNED_OFF    # input constraint
    assert fates[("L4", "am_peak")] is Fate.CHOSEN_OFF   # optimizer result
    assert fates[("L1", "am_peak")] is Fate.ACTIVE

    # the two OFFs deliver the same service and must not be the same state
    assert Fate.PINNED_OFF is not Fate.CHOSEN_OFF
    assert len({Fate.ABSENT, Fate.PINNED_OFF, Fate.CHOSEN_OFF, Fate.ACTIVE}) == 4


def test_provenance_covers_every_pool_line_not_just_the_selected():
    """"This search chose not to run line X" is part of the answer."""
    sel = Exp4Selection.of("v", ["L1"])
    fates = provenance(sel, {"L1|am_peak": 5.0, "L1|midday": 5.0},
                       LINES, PERIODS)
    assert len(fates) == len(LINES) * len(PERIODS)
    assert {f.line_id for f in fates} == set(LINES)


def test_a_selected_route_period_missing_from_the_plan_is_not_called_off():
    """A gap must not be laundered into an optimizer decision."""
    sel = Exp4Selection.of("v", ["L1"])
    fates = {(f.line_id, f.period): f.fate
             for f in provenance(sel, {"L1|am_peak": 5.0}, LINES, PERIODS)}
    assert fates[("L1", "midday")] is not Fate.CHOSEN_OFF


def test_active_carries_its_headway_and_off_does_not():
    sel = Exp4Selection.of("v", ["L1", "L4"])
    fs = {f.line_id: f for f in provenance(
        sel, {"L1|am_peak": 12.0, "L1|midday": 12.0,
              "L4|am_peak": OFF, "L4|midday": OFF}, ["L1", "L4"], ["am_peak"])}
    assert fs["L1"].headway_min == 12.0
    assert fs["L4"].headway_min is None


# ------------------------------------------------------------- the oracle
def test_enumeration_finds_the_true_optimum():
    costs = {("L1",): 10, ("L2",): 9, ("L3",): 11,
             ("L1", "L2"): 8, ("L1", "L3"): 3, ("L2", "L3"): 7,
             ("L1", "L2", "L3"): 6}
    r = enumerate_exact(["L1", "L2", "L3"], _scorer(costs), PERIODS)
    assert sorted(r.best.selection.lines) == ["L1", "L3"]
    assert r.best.objective == 3
    assert r.notes["complete"] is True


def test_enumeration_refuses_rather_than_truncating():
    """A partial enumeration is not an oracle."""
    with pytest.raises(ValueError, match="not an oracle"):
        enumerate_exact([f"L{i}" for i in range(12)], _scorer({}), PERIODS,
                        max_networks=10)


def test_infeasible_selections_are_excluded_not_scored_as_zero():
    costs = {("L1",): None, ("L2",): 5, ("L1", "L2"): None}
    r = enumerate_exact(["L1", "L2"], _scorer(costs), PERIODS)
    assert sorted(r.best.selection.lines) == ["L2"]
    assert r.notes["n_feasible"] == 1


# -------------------------------------------------------------- the search
def test_search_recovers_an_optimum_that_needs_a_paired_add():
    """Neither line helps alone; together they win. Add-only must fail."""
    costs = {("L1",): 10, ("L2",): 12, ("L3",): 12,
             ("L1", "L2"): 11, ("L1", "L3"): 11, ("L2", "L3"): 20,
             ("L1", "L2", "L3"): 2}
    sc, ls = _scorer(costs), ["L1", "L2", "L3"]
    add_only = search(ls, sc, PERIODS, seed_lines=["L1"],
                      allow_swaps=False, pair_adds=False)
    full = search(ls, sc, PERIODS, seed_lines=["L1"],
                  allow_swaps=True, pair_adds=True)
    assert add_only.best.objective > full.best.objective
    assert full.best.objective == 2


def test_every_candidate_records_its_parent_and_move():
    """A disagreement with the oracle must be diagnosable as a path."""
    costs = {("L1",): 10, ("L2",): 5, ("L1", "L2"): 3}
    r = search(["L1", "L2"], _scorer(costs), PERIODS, seed_lines=["L1"])
    assert r.evaluated[0].move == "seed" and r.evaluated[0].parent is None
    assert any(c.parent is not None and c.move.startswith(("add", "swap", "drop"))
               for c in r.evaluated[1:])
    d = r.best.as_dict()
    for k in ("state_key", "lines", "pinned_off", "objective", "fitness",
              "feasible", "parent", "move", "route_fates", "n_active",
              "n_chosen_off", "n_pinned_off", "n_absent"):
        assert k in d


def test_pinned_off_is_carried_through_the_search_and_never_invented():
    costs = {("L1",): 10, ("L2",): 5, ("L1", "L2"): 3}
    r = search(["L1", "L2"], _scorer(costs), PERIODS, seed_lines=["L1"],
               pinned_off=[("L1", "midday")])
    for c in r.evaluated:
        pinned = {(a, b) for a, b in c.selection.pinned_off}
        # only ever the declared pin, and only when its line is selected
        assert pinned <= {("L1", "midday")}
        if "L1" in c.selection.lines:
            assert ("L1", "midday") in pinned
