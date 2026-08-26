"""Path-set re-costing: the mechanism that lets passengers re-route."""
import numpy as np
import pytest

from cota_opt.cost import CostWeights, expected_wait_min
from cota_opt.pathset import PathSet, PathSetEvaluator

W = CostWeights(walking=2.0, waiting=2.0, in_vehicle=1.0, transfer_wait=2.0,
                transfer_penalty=10.0, unserved=60.0)
WK = dict(random_arrival_threshold_min=12.0, schedule_coefficient=0.25)


def _ps(paths, od_flow, rp_keys, walk_only=None):
    """Build a PathSet from ``paths`` = list of (od_index, [legs]).

    A leg is (rp_index or -1, in_vehicle_min, walk_min, is_transfer).
    Paths must be given grouped by OD index in ascending order.
    """
    leg_path, leg_rp, leg_ivt, leg_walk, leg_board, leg_xfer = [], [], [], [], [], []
    path_od, path_offsets = [], [0]
    n_od = len(od_flow)
    for pi, (oi, legs) in enumerate(paths):
        for rp, ivt, walk, xfer in legs:
            leg_path.append(pi)
            leg_rp.append(rp)
            leg_ivt.append(ivt)
            leg_walk.append(walk)
            leg_board.append(rp >= 0)
            leg_xfer.append(xfer)
        path_od.append(oi)
        path_offsets.append(len(leg_path))
    od_offsets = np.zeros(n_od + 1, dtype=np.int64)
    for pi, (oi, _) in enumerate(paths):
        od_offsets[oi + 1] = pi + 1
    for i in range(1, n_od + 1):
        od_offsets[i] = max(od_offsets[i], od_offsets[i - 1])
    return PathSet(
        period="all", n_od=n_od,
        leg_path=np.array(leg_path, dtype=np.int64),
        leg_rp=np.array(leg_rp, dtype=np.int64),
        leg_ivt=np.array(leg_ivt, float), leg_walk=np.array(leg_walk, float),
        leg_is_boarding=np.array(leg_board, bool),
        leg_is_transfer=np.array(leg_xfer, bool),
        path_od=np.array(path_od, dtype=np.int64),
        path_offsets=np.array(path_offsets, dtype=np.int64),
        od_offsets=od_offsets, od_flow=np.array(od_flow, float),
        od_walk_only=(np.array(walk_only, float) if walk_only is not None
                      else np.full(n_od, np.inf)),
        rp_keys=rp_keys)


def _ev(ps, **kw):
    kw.setdefault("retention_full_min", 1e9)     # retention off unless asked
    kw.setdefault("retention_zero_min", 1e9 + 1)
    kw.setdefault("retention_floor", 1.0)
    return PathSetEvaluator(ps, W, WK, 60.0, **kw)


def test_single_path_cost_is_the_weighted_sum():
    # one OD, one path: walk 5, ride route 0 for 20 min
    ps = _ps([(0, [(-1, 0.0, 5.0, False), (0, 20.0, 0.0, False)])],
             [100.0], [("R0", "all")])
    ev = _ev(ps)
    c = ev.od_costs(np.array([10.0]))
    # 2*5 walk + wait 2*5 + 20 ivt = 40
    assert c[0] == pytest.approx(40.0)


def test_transfer_path_pays_transfer_wait_and_penalty():
    ps = _ps([(0, [(0, 10.0, 0.0, False), (1, 5.0, 0.0, True)])],
             [100.0], [("R0", "all"), ("R1", "all")])
    ev = _ev(ps)
    c = ev.od_costs(np.array([10.0, 20.0]))
    # board R0: 2*5 = 10; ride 10; transfer to R1: wait 6+0.25*8 = 8 -> 2*8 = 16;
    # penalty 10; ride 5   => 51
    assert c[0] == pytest.approx(51.0)


def test_od_takes_the_cheaper_of_its_candidate_paths():
    ps = _ps([(0, [(0, 30.0, 0.0, False)]),      # slow route, frequent
              (0, [(1, 20.0, 0.0, False)])],     # fast route
             [100.0], [("R0", "all"), ("R1", "all")])
    ev = _ev(ps)
    # R0 at 10 min: 2*5 + 30 = 40 ; R1 at 20 min: 2*8 + 20 = 36 -> R1 wins
    assert ev.od_costs(np.array([10.0, 20.0]))[0] == pytest.approx(36.0)
    # make R1 hourly: 2*(6+0.25*48) + 20 = 56 -> R0 wins
    assert ev.od_costs(np.array([10.0, 60.0]))[0] == pytest.approx(40.0)


def test_passengers_reroute_when_a_route_is_cut():
    """The behaviour route-level assignment could not represent."""
    ps = _ps([(0, [(0, 20.0, 0.0, False)]),
              (0, [(1, 26.0, 0.0, False)])],
             [100.0], [("R0", "all"), ("R1", "all")])
    ev = _ev(ps)
    good = ev.od_costs(np.array([10.0, 30.0]))[0]
    # cutting R0 to hourly must NOT cost the full R0 penalty — R1 absorbs them
    cut = ev.od_costs(np.array([60.0, 30.0]))[0]
    r1_only = 2 * expected_wait_min(30.0, **WK) + 26.0
    assert cut == pytest.approx(r1_only)
    assert cut < 2 * expected_wait_min(60.0, **WK) + 20.0   # cheaper than staying on R0
    assert cut > good


def test_unreachable_od_is_infinite_and_counts_as_structural():
    ps = _ps([(0, [(0, 10.0, 0.0, False)])], [100.0, 50.0], [("R0", "all")])
    ev = _ev(ps)
    c = ev.od_costs(np.array([10.0]))
    assert np.isfinite(c[0]) and not np.isfinite(c[1])
    r = ev.evaluate(np.array([10.0]))
    assert r["unserved_structural"] == pytest.approx(50.0)
    assert r["unserved_discouraged"] == pytest.approx(0.0)
    assert r["served_demand"] == pytest.approx(100.0)


def test_walk_only_fallback_caps_the_cost():
    ps = _ps([(0, [(0, 100.0, 0.0, False)])], [10.0], [("R0", "all")],
             walk_only=[25.0])
    ev = _ev(ps)
    assert ev.od_costs(np.array([60.0]))[0] == pytest.approx(25.0)


def test_cost_is_monotone_in_headway():
    ps = _ps([(0, [(0, 20.0, 0.0, False)])], [100.0], [("R0", "all")])
    ev = _ev(ps)
    vals = [ev.od_costs(np.array([h]))[0] for h in (5, 10, 15, 30, 60)]
    assert all(a < b for a, b in zip(vals, vals[1:]))


def test_retention_discourages_expensive_trips():
    ps = _ps([(0, [(0, 100.0, 0.0, False)])], [100.0], [("R0", "all")])
    ev = _ev(ps, retention_full_min=60.0, retention_zero_min=210.0,
             retention_floor=0.10)
    cheap = ev.evaluate(np.array([5.0]))
    dear = ev.evaluate(np.array([60.0]))
    assert dear["served_demand"] < cheap["served_demand"]
    assert dear["unserved_discouraged"] > cheap["unserved_discouraged"]
    assert dear["unserved_structural"] == cheap["unserved_structural"] == 0.0


def test_retention_endpoints_are_exact():
    ps = _ps([(0, [(0, 0.0, 0.0, False)])], [100.0], [("R0", "all")])
    ev = _ev(ps, retention_full_min=60.0, retention_zero_min=210.0,
             retention_floor=0.10)
    assert ev.retention(np.array([30.0]))[0] == pytest.approx(1.0)
    assert ev.retention(np.array([60.0]))[0] == pytest.approx(1.0)
    assert ev.retention(np.array([210.0]))[0] == pytest.approx(0.10)
    assert ev.retention(np.array([500.0]))[0] == pytest.approx(0.10)
    assert ev.retention(np.array([135.0]))[0] == pytest.approx(0.55)


def test_evaluate_totals_are_consistent():
    ps = _ps([(0, [(0, 20.0, 0.0, False)]),
              (1, [(1, 30.0, 0.0, False)])],
             [100.0, 40.0], [("R0", "all"), ("R1", "all")])
    ev = _ev(ps, retention_full_min=60.0, retention_zero_min=210.0,
             retention_floor=0.10)
    r = ev.evaluate(np.array([10.0, 20.0]))
    assert (r["served_demand"] + r["unserved_demand"]) == pytest.approx(140.0)
    assert r["generalized_cost"] >= r["generalized_cost_served_only"]
    assert r["mean_cost_per_served_trip"] == pytest.approx(
        r["generalized_cost_served_only"] / r["served_demand"])


def test_empty_path_set_returns_everything_unserved():
    ps = _ps([], [10.0, 5.0], [("R0", "all")])
    ev = _ev(ps)
    r = ev.evaluate(np.array([10.0]))
    assert r["unserved_demand"] == pytest.approx(15.0)
    assert r["served_demand"] == pytest.approx(0.0)
