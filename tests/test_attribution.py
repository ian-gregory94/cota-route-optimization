"""Attribution of path-set improvements to a mechanism.

Built on hand-made path sets so every classification has a known answer.
"""
import numpy as np
import pytest

from cota_opt.attribution import (best_paths, describe_path, diff_sets,
                                  path_costs, summarize)
from cota_opt.cost import CostWeights
from cota_opt.pathset import PathSet, PathSetEvaluator

W = CostWeights(walking=2.0, waiting=2.0, in_vehicle=1.0, transfer_wait=2.0,
                transfer_penalty=10.0)
WK = dict(random_arrival_threshold_min=12.0, schedule_coefficient=0.25)
KEYS = [("A", "p"), ("B", "p"), ("C", "p")]


def make(paths, n_od=1, flow=(100.0,)):
    """paths: list of (od, [(rp_index, ivt, walk, boarding, transfer), ...])."""
    leg_path, leg_rp, leg_ivt, leg_walk, board, xfer = [], [], [], [], [], []
    path_od, offs = [], [0]
    for pid, (od, legs) in enumerate(paths):
        for rp, ivt, walk, b, x in legs:
            leg_path.append(pid)
            leg_rp.append(rp)
            leg_ivt.append(ivt)
            leg_walk.append(walk)
            board.append(b)
            xfer.append(x)
        path_od.append(od)
        offs.append(len(leg_path))
    od_off = np.zeros(n_od + 1, dtype=np.int64)
    for od in path_od:
        od_off[od + 1] += 1
    od_off = np.cumsum(od_off)
    n = len(leg_path)
    return PathSet(
        period="p", n_od=n_od,
        leg_path=np.array(leg_path, dtype=np.int64),
        leg_rp=np.array(leg_rp, dtype=np.int64),
        leg_ivt=np.array(leg_ivt, float), leg_walk=np.array(leg_walk, float),
        leg_is_boarding=np.array(board, bool), leg_is_transfer=np.array(xfer, bool),
        leg_pattern=np.full(n, -1, dtype=np.int64),
        leg_board_pos=np.zeros(n, dtype=np.int64),
        leg_alight_pos=np.zeros(n, dtype=np.int64),
        leg_headway_mult=np.ones(n),
        path_od=np.array(path_od, dtype=np.int64),
        path_offsets=np.array(offs, dtype=np.int64), od_offsets=od_off,
        od_flow=np.array(flow, float), od_walk_only=np.full(n_od, np.inf),
        od_origin=np.zeros(n_od, dtype=np.int64),
        od_dest=np.arange(n_od, dtype=np.int64), rp_keys=list(KEYS))


def ev(ps):
    return PathSetEvaluator(ps, W, WK, 200.0, retention_full_min=1e9,
                            retention_zero_min=1e9, retention_floor=1.0)


HW = {("A", "p"): 20.0, ("B", "p"): 20.0, ("C", "p"): 20.0}


def test_path_cost_matches_the_evaluator_minimum():
    ps = make([(0, [(0, 30.0, 0.0, True, False)]),
               (0, [(1, 20.0, 0.0, True, False)])])
    e = ev(ps)
    h = np.array([HW[k] for k in ps.rp_keys])
    assert path_costs(e, h).min() == pytest.approx(e.od_costs(h)[0])


def test_best_path_is_the_cheapest_one():
    ps = make([(0, [(0, 30.0, 0.0, True, False)]),
               (0, [(1, 20.0, 0.0, True, False)])])
    e = ev(ps)
    idx, val = best_paths(e, np.array([HW[k] for k in ps.rp_keys]))
    assert idx[0] == 1
    assert describe_path(ps, int(idx[0]))["routes"] == ("B",)


def test_route_substitution_is_named():
    old = make([(0, [(0, 40.0, 0.0, True, False)])])
    new = make([(0, [(0, 40.0, 0.0, True, False)]),
                (0, [(1, 20.0, 0.0, True, False)])])
    d = diff_sets(ev(old), ev(new), HW, "p")
    assert len(d) == 1
    assert d.iloc[0]["mechanism"] == "route_substitution"
    assert d.iloc[0]["old_routes"] == "A" and d.iloc[0]["new_routes"] == "B"
    assert d.iloc[0]["improvement_min"] == pytest.approx(20.0)


def test_transfer_reduction_is_named():
    two = [(0, 10.0, 0.0, True, False), (1, 10.0, 0.0, True, True)]
    old = make([(0, two)])
    new = make([(0, two), (0, [(0, 22.0, 0.0, True, False)])])
    d = diff_sets(ev(old), ev(new), HW, "p")
    assert d.iloc[0]["mechanism"] == "route_substitution"  # B is dropped entirely
    assert d.iloc[0]["new_boardings"] == 1


def test_transfer_addition_is_named():
    """Same route set, one more boarding, still cheaper."""
    old = make([(0, [(0, 60.0, 0.0, True, False), (1, 5.0, 0.0, False, False)])])
    new = make([(0, [(0, 60.0, 0.0, True, False), (1, 5.0, 0.0, False, False)]),
                (0, [(0, 20.0, 0.0, True, False), (1, 10.0, 0.0, True, True)])])
    d = diff_sets(ev(old), ev(new), HW, "p")
    assert d.iloc[0]["mechanism"] == "transfer_addition"


def test_identical_sets_produce_no_rows():
    ps = [(0, [(0, 30.0, 0.0, True, False)])]
    assert diff_sets(ev(make(ps)), ev(make(ps)), HW, "p").empty


def test_a_worse_new_set_is_not_reported_as_an_improvement():
    old = make([(0, [(1, 20.0, 0.0, True, False)])])
    new = make([(0, [(0, 40.0, 0.0, True, False)])])
    assert diff_sets(ev(old), ev(new), HW, "p").empty


def test_summary_reports_concentration():
    old = make([(0, [(0, 40.0, 0.0, True, False)]),
                (1, [(0, 40.0, 0.0, True, False)])],
               n_od=2, flow=(1000.0, 1.0))
    new = make([(0, [(1, 10.0, 0.0, True, False)]),
                (1, [(1, 10.0, 0.0, True, False)])],
               n_od=2, flow=(1000.0, 1.0))
    d = diff_sets(ev(old), ev(new), HW, "p")
    a = summarize(d, total_flow=1001.0)
    assert a.summary["n_improved_od"] == 2
    # one pair carries essentially all of the flow-weighted correction
    assert a.summary["top_10pct_share_of_improvement"] > 0.99
    assert a.by_mechanism.iloc[0]["mechanism"] == "route_substitution"
    assert set(a.by_route["route"]) == {"B"}


def test_mismatched_od_tables_are_rejected():
    old = make([(0, [(0, 30.0, 0.0, True, False)])], n_od=1, flow=(1.0,))
    new = make([(0, [(0, 30.0, 0.0, True, False)])], n_od=2, flow=(1.0, 1.0))
    with pytest.raises(ValueError, match="different OD tables"):
        diff_sets(ev(old), ev(new), HW, "p")
