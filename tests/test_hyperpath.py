"""Hyperpath upper bound on the synthetic RAPTOR network.

    PA (route A):  S1 -> S2 -> S3 -> S4    600 s per segment
    PB (route B):  S1 -> S5 -> S4          720 s per segment

S1 -> S4 is carried by both: A in 1800 s, B in 1440 s. So a rider at S1 bound
for S4 has two acceptable lines and should wait on their combined frequency;
a rider bound for S3 has only A.
"""
import numpy as np
import pytest

from cota_opt.cost import CostWeights
from cota_opt.hyperpath import _alternatives, bound, summarize
from cota_opt.pathset import PathSet, PathSetEvaluator
from cota_opt.raptor import build_raptor_network

from test_raptor import W, WK, _feed, _net, _stops_gdf, _tstats


@pytest.fixture
def rn():
    return build_raptor_network(
        _feed(), _net(), _tstats(), _stops_gdf(),
        walk_radius_m=400.0, walk_speed_m_per_min=80.0,
        periods={"all": (0.0, 24.0)}, with_timetable=False)


KEYS = [("A", "all"), ("B", "all"), ("C", "all")]
HW = {("A", "all"): 20.0, ("B", "all"): 20.0, ("C", "all"): 20.0}


def _pat(rn, route):
    return next(i for i, r in enumerate(rn.pattern_route) if r == route)


def test_alternatives_finds_the_parallel_line(rn):
    pa = _pat(rn, "A")
    # A runs S1(0) -> S2(1) -> S3(2) -> S4(3); B also gets S1 to S4, faster
    alts = _alternatives(rn, pa, 0, 3, ivt_tolerance=1.25)
    assert len(alts) == 2
    assert {rn.pattern_route[q] for q, _ in alts} == {"A", "B"}


def test_a_movement_only_one_line_makes_has_no_alternative(rn):
    pa = _pat(rn, "A")
    assert len(_alternatives(rn, pa, 0, 2, ivt_tolerance=1.25)) == 1


def test_a_much_slower_alternative_is_not_attractive(rn):
    """B is faster than A here, so tighten the tolerance the other way."""
    pb = _pat(rn, "B")
    # A takes 1800 s against B's 1440: 1.25 x 1440 = 1800, so at 1.2 it is out
    assert len(_alternatives(rn, pb, 0, 2, ivt_tolerance=1.2)) == 1
    assert len(_alternatives(rn, pb, 0, 2, ivt_tolerance=1.3)) == 2


def _pathset(rn, route, bpos, apos, ivt_min, flow=100.0):
    pat = _pat(rn, route)
    rp = [k[0] for k in KEYS].index(route)
    return PathSet(
        period="all", n_od=1,
        leg_path=np.array([0]), leg_rp=np.array([rp]),
        leg_ivt=np.array([ivt_min]), leg_walk=np.array([0.0]),
        leg_is_boarding=np.array([True]), leg_is_transfer=np.array([False]),
        leg_pattern=np.array([pat]), leg_board_pos=np.array([bpos]),
        leg_alight_pos=np.array([apos]), leg_headway_mult=np.array([1.0]),
        path_od=np.array([0]), path_offsets=np.array([0, 1]),
        od_offsets=np.array([0, 1]), od_flow=np.array([flow]),
        od_walk_only=np.array([np.inf]), od_origin=np.array([0]),
        od_dest=np.array([1]), rp_keys=list(KEYS))


def _ev(ps):
    return PathSetEvaluator(ps, W, WK, 200.0, retention_full_min=1e9,
                            retention_zero_min=1e9, retention_floor=1.0)


def test_bound_halves_the_headway_for_two_equal_lines(rn):
    ps = _pathset(rn, "A", 0, 3, 30.0)
    df = bound(ps, _ev(ps), rn, HW, "all", W, WK)
    assert len(df) == 1
    r = df.iloc[0]
    assert r["n_attractive_lines"] == 2
    assert r["combined_headway_min"] == pytest.approx(10.0)
    assert r["own_headway_min"] == pytest.approx(20.0)
    assert r["saving_min"] > 0


def test_no_bound_where_there_is_no_alternative(rn):
    ps = _pathset(rn, "A", 0, 2, 20.0)
    assert bound(ps, _ev(ps), rn, HW, "all", W, WK).empty


def test_summary_calls_a_tiny_bound_negligible(rn):
    ps = _pathset(rn, "A", 0, 3, 30.0, flow=1.0)
    df = bound(ps, _ev(ps), rn, HW, "all", W, WK)
    out = summarize(df, baseline_gc=1e6, exp1_effect_pct=2.0)
    assert out.verdict == "negligible"
    assert out.summary["bound_share_of_generalized_cost_pct"] < 0.5


def test_summary_escalates_when_the_bound_rivals_the_claim(rn):
    ps = _pathset(rn, "A", 0, 3, 30.0, flow=1.0)
    df = bound(ps, _ev(ps), rn, HW, "all", W, WK)
    small = float(df["flow_weighted_saving"].sum()) * 20.0
    out = summarize(df, baseline_gc=small, exp1_effect_pct=2.0)
    assert out.verdict == "potentially_frontier_changing"
    assert "optimal-strategy" in out.explanation


def test_empty_input_is_negligible_not_an_error():
    import pandas as pd
    out = summarize(pd.DataFrame(), baseline_gc=1e6)
    assert out.verdict == "negligible"
    assert out.summary["n_legs_with_alternatives"] == 0


def test_path_set_without_ride_geometry_is_rejected(rn):
    ps = _pathset(rn, "A", 0, 3, 30.0)
    ps.leg_pattern = None
    with pytest.raises(ValueError, match="ride geometry"):
        bound(ps, _ev(ps), rn, HW, "all", W, WK)
