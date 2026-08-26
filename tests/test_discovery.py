"""Model B discovery adequacy: can the corrected model find its own best paths?

The network is built so the failure it looks for actually happens. Route T is a
trunk with two half-frequency patterns that both carry S1 -> S4; route D is a
single-pattern direct. Under Model A's per-pattern pricing T looks worse than it
is, so an enumerator biased that way reaches for D. Under Model B, T's two
patterns combine and T wins -- but only if something goes looking for it.
"""
import copy

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from cota_opt.cost import CostWeights, expected_wait_min
from cota_opt.discovery import (classify, high_exposure_od, probe,
                                route_level_headways)
from cota_opt.gtfs import GTFSFeed
from cota_opt.network import PatternSegment, RoutePattern, StopNode, TransitNetwork
from cota_opt.odmatrix import ODTable, ZoneSystem
from cota_opt.pathset import PathSetEvaluator, build_pathset
from cota_opt.raptor import build_raptor_network, pattern_headways

W = CostWeights(walking=2.0, waiting=2.0, in_vehicle=1.0, transfer_wait=2.0,
                transfer_penalty=10.0)
WK = dict(random_arrival_threshold_min=12.0, schedule_coefficient=0.25)

COORDS = {"S1": (-83.000, 39.960), "S2": (-83.010, 39.960),
          "S3": (-83.020, 39.960), "S4": (-83.030, 39.960)}
SPECS = {
    "T_a": ("T", 0, ["S1", "S2", "S3", "S4"], 10, 300.0),
    "T_b": ("T", 0, ["S1", "S2", "S3", "S4"], 10, 300.0),
    "D_1": ("D", 0, ["S1", "S4"], 10, 1500.0),
}
HW = {("T", "all"): 12.0, ("D", "all"): 24.0}


def _net():
    stops = {s: StopNode(s, s, COORDS[s][1], COORDS[s][0]) for s in COORDS}
    patterns = {}
    for pid, (route, d, stop_list, _n, seg) in SPECS.items():
        segs = [PatternSegment(route, d, pid, stop_list[i], stop_list[i + 1],
                               i, seg) for i in range(len(stop_list) - 1)]
        patterns[pid] = RoutePattern(route, d, pid, list(stop_list), segs,
                                     SPECS[pid][3])
    sr, rs = {}, {}
    for p in patterns.values():
        for s in p.stops:
            sr.setdefault(s, set()).add(p.route_id)
            rs.setdefault(p.route_id, set()).add(s)
    return TransitNetwork(stops=stops, patterns=patterns, stop_routes=sr,
                          route_stops=rs)


def _tstats():
    rows = []
    for pid, (route, d, stop_list, n, seg) in SPECS.items():
        rt = seg * (len(stop_list) - 1)
        for t in range(n):
            rows.append({"trip_id": f"{pid}_{t}", "route_id": route,
                         "direction_id": d, "pattern_id": pid,
                         "first_dep_sec": 8 * 3600 + t * 600,
                         "last_arr_sec": 8 * 3600 + t * 600 + rt,
                         "runtime_min": rt / 60.0, "n_stops": len(stop_list),
                         "shape_id": pid, "service_id": "WK"})
    return pd.DataFrame(rows)


@pytest.fixture
def rn():
    g = gpd.GeoDataFrame({"stop_id": list(COORDS)},
                         geometry=[Point(COORDS[s]) for s in COORDS],
                         crs="EPSG:4326").to_crs("EPSG:32617")
    feed = GTFSFeed(tables={"transfers": pd.DataFrame(),
                            "stop_times": pd.DataFrame()}, source_dir=None)
    return build_raptor_network(feed, _net(), _tstats(), g, walk_radius_m=50.0,
                                walk_speed_m_per_min=80.0,
                                periods={"all": (0.0, 24.0)},
                                with_timetable=False)


@pytest.fixture
def zs(rn):
    access = {0: (np.array([rn.stop_index["S1"]]), np.array([0.0])),
              1: (np.array([rn.stop_index["S4"]]), np.array([0.0]))}
    z = object.__new__(type("Z", (ZoneSystem,), {}))
    z.access_of = lambda i: access[int(i)]
    return z


def _set(rn, zs, mode):
    od = ODTable(np.array([0]), np.array([1]), np.array([500.0]), "t", "")
    ps = build_pathset(rn, zs, od, "all", HW, W, WK, max_rounds=2,
                       max_paths_per_od=4, n_random_scenarios=0, seed=1,
                       common_lines=mode)
    ev = PathSetEvaluator(ps, W, WK, 500.0, retention_full_min=1e9,
                          retention_zero_min=1e9, retention_floor=1.0)
    return ps, ev


def _prune(ps, keep):
    """A path set restricted to the given path indices, offsets rebuilt."""
    out = copy.deepcopy(ps)
    legs = (np.concatenate([np.arange(ps.path_offsets[p], ps.path_offsets[p + 1])
                            for p in keep]) if keep
            else np.array([], dtype=np.int64))
    sizes = [int(ps.path_offsets[p + 1] - ps.path_offsets[p]) for p in keep]
    out.leg_path = np.repeat(np.arange(len(keep)), sizes)
    for f in ("leg_rp", "leg_ivt", "leg_walk", "leg_is_boarding",
              "leg_is_transfer", "leg_pattern", "leg_board_pos",
              "leg_alight_pos", "leg_headway_mult"):
        v = getattr(ps, f)
        if v is not None:
            setattr(out, f, v[legs])
    out.path_od = ps.path_od[keep]
    out.path_offsets = np.concatenate([[0], np.cumsum(sizes)]).astype(np.int64)
    out.od_offsets = np.array([0, len(keep)], dtype=np.int64)
    return out


def _routes_of(ps, p):
    a, b = ps.path_offsets[p], ps.path_offsets[p + 1]
    rp = ps.leg_rp[a:b]
    return tuple(ps.rp_keys[int(k)][0] for k in rp[rp >= 0])


# -- the bound ---------------------------------------------------------------

def test_route_level_headways_are_never_worse_than_per_pattern(rn):
    per = pattern_headways(rn, HW, "all")
    lvl = route_level_headways(rn, HW, "all")
    assert np.all(lvl <= per + 1e-12)
    ti = rn.pattern_ids.index("T_a")
    assert per[ti] == pytest.approx(24.0)      # one of two patterns
    assert lvl[ti] == pytest.approx(12.0)      # the whole route


def test_a_single_pattern_route_is_unchanged_by_the_bound(rn):
    di = rn.pattern_ids.index("D_1")
    assert route_level_headways(rn, HW, "all")[di] == pytest.approx(
        pattern_headways(rn, HW, "all")[di])


# -- the failure the diagnostic exists to catch ------------------------------

def test_the_probe_finds_a_cheaper_model_b_path_when_one_is_missing(rn, zs):
    """Enumerate, drop the trunk, then look for what Model B would want back."""
    ps_a, _ = _set(rn, zs, "pattern")
    keep = [p for p in range(ps_a.n_paths) if _routes_of(ps_a, p) == ("D",)]
    assert keep, "the fixture must enumerate the direct route"
    ps = _prune(ps_a, keep)
    ev = PathSetEvaluator(ps, W, WK, 500.0, retention_full_min=1e9,
                          retention_zero_min=1e9, retention_floor=1.0)
    rows = probe(rn, zs, ps, ev, HW, "all", W, WK, 2, np.array([0]))
    assert len(rows) == 1
    r = rows.iloc[0]
    assert r["route_sequence"] == "T"
    assert r["improvement_min"] > 0
    assert not r["sequence_already_in_set"]
    # T's two patterns combine to the route headway of 12 minutes
    ivt = 3 * 300.0 / 60.0
    assert r["omitted_path_min"] == pytest.approx(
        ivt + 2.0 * expected_wait_min(12.0, **WK))


def test_no_omission_is_reported_when_the_set_already_holds_the_best_path(rn, zs):
    ps, ev = _set(rn, zs, "same_route")
    assert probe(rn, zs, ps, ev, HW, "all", W, WK, 2, np.array([0])).empty


def test_a_trivial_gain_is_not_reported_as_an_omission(rn, zs):
    ps_a, _ = _set(rn, zs, "pattern")
    keep = [p for p in range(ps_a.n_paths) if _routes_of(ps_a, p) == ("D",)]
    ps = _prune(ps_a, keep)
    ev = PathSetEvaluator(ps, W, WK, 500.0, retention_full_min=1e9,
                          retention_zero_min=1e9, retention_floor=1.0)
    rows = probe(rn, zs, ps, ev, HW, "all", W, WK, 2, np.array([0]),
                 min_gain_min=1e6, min_gain_frac=0.99)
    assert rows.empty


def test_the_bound_clears_a_pair_without_reconstructing_anything(rn, zs):
    """A set already holding the optimum is cleared by the bound alone."""
    ps, ev = _set(rn, zs, "same_route")
    sub = np.array([HW[k] for k in ps.rp_keys])
    best = float(ev.od_costs(sub)[0])
    ivt = 3 * 300.0 / 60.0
    assert best == pytest.approx(ivt + 2.0 * expected_wait_min(12.0, **WK))


# -- the decision rule -------------------------------------------------------

def _rows(flow, fw):
    return pd.DataFrame([{"od_index": 0, "flow": flow,
                          "flow_weighted_improvement": fw,
                          "improvement_min": 5.0, "improvement_pct": 5.0,
                          "route_sequence": "T",
                          "sequence_already_in_set": False}])


def test_an_empty_result_is_case_a():
    r = classify(pd.DataFrame(), tested_flow=1000.0, tested_gc=1e5)
    assert r.case == "A"
    assert r.summary["n_omitted"] == 0


def test_thresholds_route_to_the_committed_cases():
    assert classify(_rows(5.0, 100.0), 1000.0, 1e5).case == "A"    # 0.5%, 0.1%
    assert classify(_rows(20.0, 500.0), 1000.0, 1e5).case == "B"   # 2%, 0.5%
    assert classify(_rows(40.0, 500.0), 1000.0, 1e5).case == "C"   # 4%, 0.5%


def test_either_bound_alone_triggers_the_worse_case():
    """Tiny flow but large cost must still be material, and the converse."""
    assert classify(_rows(1.0, 1500.0), 1000.0, 1e5).case == "C"   # 0.1%, 1.5%
    assert classify(_rows(40.0, 10.0), 1000.0, 1e5).case == "C"    # 4%, 0.01%


def test_the_summary_carries_what_the_decision_was_made_on():
    r = classify(_rows(20.0, 500.0), 1000.0, 1e5)
    assert r.summary["flow_share"] == pytest.approx(0.02)
    assert r.summary["gc_share"] == pytest.approx(0.005)
    assert r.summary["tested_flow"] == 1000.0
    assert set(r.by_route["route"]) == {"T"}


# -- targeting ---------------------------------------------------------------

def test_high_exposure_selection_picks_ods_riding_the_named_routes(rn, zs):
    ps, ev = _set(rn, zs, "same_route")
    assert len(high_exposure_od(ps, ev, HW, rn, "all", {"T"})) == 1
    assert len(high_exposure_od(ps, ev, HW, rn, "all", {"ZZZ"})) == 0
