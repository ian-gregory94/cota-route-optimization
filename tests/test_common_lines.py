"""Model B: same-route common-lines waiting.

A synthetic route R with four patterns, chosen so every qualifying rule has a
case that exercises it:

    P_full   S1 -> S2 -> S3 -> S4     dir 0, 6 trips   full length
    P_full2  S1 -> S2 -> S3 -> S4     dir 0, 6 trips   an identical twin
    P_short  S1 -> S2                 dir 0, 4 trips   short-turn, never reaches S3
    P_rev    S4 -> S3 -> S2 -> S1     dir 1, 8 trips   the other direction

Plus route Q, P_other S1 -> S2 -> S3 -> S4, to prove that sharing a movement
is not enough — a different route is a different fare-free choice the model
treats separately (that is the cross-route hyperpath question, deferred).

Every expected multiplier below is derived in the test from trip counts, not
copied from a run.
"""
import numpy as np
import pandas as pd
import pytest

from cota_opt.network import PatternSegment, RoutePattern, StopNode, TransitNetwork
from cota_opt.pathset import (_headway_multiplier, common_lines_multiplier,
                              qualifying_patterns)
from cota_opt.raptor import build_raptor_network

import geopandas as gpd
from shapely.geometry import Point

from cota_opt.gtfs import GTFSFeed

COORDS = {"S1": (-83.000, 39.960), "S2": (-83.010, 39.960),
          "S3": (-83.020, 39.960), "S4": (-83.030, 39.960)}

SPECS = {
    "P_full": ("R", 0, ["S1", "S2", "S3", "S4"], 6),
    "P_full2": ("R", 0, ["S1", "S2", "S3", "S4"], 6),
    "P_short": ("R", 0, ["S1", "S2"], 4),
    "P_rev": ("R", 1, ["S4", "S3", "S2", "S1"], 8),
    "P_other": ("Q", 0, ["S1", "S2", "S3", "S4"], 5),
}
SEG_SEC = 600.0


def _net():
    stops = {s: StopNode(s, s, COORDS[s][1], COORDS[s][0]) for s in COORDS}
    patterns = {}
    for pid, (route, direction, stop_list, _n) in SPECS.items():
        segs = [PatternSegment(route, direction, pid, stop_list[i],
                               stop_list[i + 1], i, SEG_SEC)
                for i in range(len(stop_list) - 1)]
        patterns[pid] = RoutePattern(route, direction, pid, list(stop_list),
                                     segs, SPECS[pid][3])
    stop_routes, route_stops = {}, {}
    for p in patterns.values():
        for s in p.stops:
            stop_routes.setdefault(s, set()).add(p.route_id)
            route_stops.setdefault(p.route_id, set()).add(s)
    return TransitNetwork(stops=stops, patterns=patterns,
                          stop_routes=stop_routes, route_stops=route_stops)


def _tstats():
    rows = []
    for pid, (route, direction, stop_list, n) in SPECS.items():
        for t in range(n):
            rows.append({"trip_id": f"{pid}_{t}", "route_id": route,
                         "direction_id": direction, "pattern_id": pid,
                         "first_dep_sec": 8 * 3600 + t * 600,
                         "last_arr_sec": 8 * 3600 + t * 600
                         + SEG_SEC * (len(stop_list) - 1),
                         "runtime_min": SEG_SEC * (len(stop_list) - 1) / 60.0,
                         "n_stops": len(stop_list), "shape_id": pid,
                         "service_id": "WK"})
    return pd.DataFrame(rows)


def _sg():
    g = gpd.GeoDataFrame({"stop_id": list(COORDS)},
                         geometry=[Point(COORDS[s]) for s in COORDS],
                         crs="EPSG:4326")
    return g.to_crs("EPSG:32617")


@pytest.fixture
def rn():
    feed = GTFSFeed(tables={"transfers": pd.DataFrame(),
                            "stop_times": pd.DataFrame()}, source_dir=None)
    return build_raptor_network(feed, _net(), _tstats(), _sg(),
                                walk_radius_m=50.0, walk_speed_m_per_min=80.0,
                                periods={"all": (0.0, 24.0)},
                                with_timetable=False)


def _pat(rn, pid):
    return rn.pattern_ids.index(pid)


def _pos(rn, pi, stop):
    a, b = rn.pat_offsets[pi], rn.pat_offsets[pi + 1]
    return list(rn.pat_stops[a:b]).index(rn.stop_index[stop])


def _mult(rn, pid, frm, to):
    pi = _pat(rn, pid)
    return common_lines_multiplier(rn, pi, _pos(rn, pi, frm), _pos(rn, pi, to),
                                   "all")


# 1 --------------------------------------------------------------------------

def test_one_qualifying_pattern_reproduces_model_a_exactly(rn):
    """S2 -> S3 on the reverse direction: only P_rev serves it that way."""
    pi = _pat(rn, "P_rev")
    b, a = _pos(rn, pi, "S3"), _pos(rn, pi, "S2")
    assert qualifying_patterns(rn, pi, b, a, "all") == [pi]
    model_b = common_lines_multiplier(rn, pi, b, a, "all")
    model_a = _headway_multiplier(rn, "P_rev", "R", 1, "all")
    assert model_b == pytest.approx(model_a)
    assert model_b == pytest.approx(1.0)        # P_rev is all of direction 1


# 2 --------------------------------------------------------------------------

def test_two_equal_patterns_halve_the_effective_headway(rn):
    """P_full and P_full2 are identical twins, 6 trips each of direction 0's 16."""
    pi = _pat(rn, "P_full")
    model_a = _headway_multiplier(rn, "P_full", "R", 0, "all")
    model_b = _mult(rn, "P_full", "S2", "S4")
    # direction 0 runs 6 + 6 + 4 = 16 trips; one pattern alone is 16/6
    assert model_a == pytest.approx(16 / 6)
    # both twins qualify for S2 -> S4, so 16/12
    assert model_b == pytest.approx(16 / 12)
    assert model_b == pytest.approx(model_a / 2)


# 3 --------------------------------------------------------------------------

def test_a_short_turn_that_cannot_reach_the_destination_does_not_contribute(rn):
    """S1 -> S4: P_short stops at S2, so it must not join the qualifying set."""
    pi = _pat(rn, "P_full")
    qs = qualifying_patterns(rn, pi, _pos(rn, pi, "S1"), _pos(rn, pi, "S4"), "all")
    assert set(qs) == {_pat(rn, "P_full"), _pat(rn, "P_full2")}
    assert _mult(rn, "P_full", "S1", "S4") == pytest.approx(16 / 12)


def test_the_short_turn_does_contribute_where_it_is_usable(rn):
    """S1 -> S2 is inside the short-turn, so all three direction-0 patterns count."""
    pi = _pat(rn, "P_full")
    qs = qualifying_patterns(rn, pi, _pos(rn, pi, "S1"), _pos(rn, pi, "S2"), "all")
    assert len(qs) == 3
    # 6 + 6 + 4 = 16 of direction 0's 16 trips, so the route headway applies
    assert _mult(rn, "P_full", "S1", "S2") == pytest.approx(1.0)


# 4 --------------------------------------------------------------------------

def test_patterns_sharing_the_boarding_stop_but_not_the_destination_are_excluded(rn):
    """P_rev serves S1 but only as its terminus; it cannot carry S1 -> S3."""
    pi = _pat(rn, "P_full")
    qs = qualifying_patterns(rn, pi, _pos(rn, pi, "S1"), _pos(rn, pi, "S3"), "all")
    assert _pat(rn, "P_rev") not in qs
    assert _pat(rn, "P_short") not in qs


# 5 --------------------------------------------------------------------------

def test_a_pattern_serving_both_stops_in_the_wrong_order_is_excluded(rn):
    """P_rev passes S2 and S3, but S3 first — it is going the other way."""
    pi = _pat(rn, "P_full")
    qs = qualifying_patterns(rn, pi, _pos(rn, pi, "S2"), _pos(rn, pi, "S3"), "all")
    assert _pat(rn, "P_rev") not in qs
    assert set(qs) == {_pat(rn, "P_full"), _pat(rn, "P_full2")}


# 6 --------------------------------------------------------------------------

def test_a_different_route_never_joins_the_same_route_set(rn):
    """Route Q runs the identical movement. That is the cross-route question,
    which Model B deliberately does not answer."""
    pi = _pat(rn, "P_full")
    qs = qualifying_patterns(rn, pi, _pos(rn, pi, "S1"), _pos(rn, pi, "S4"), "all")
    assert _pat(rn, "P_other") not in qs
    assert all(rn.pattern_route[q] == "R" for q in qs)


def test_short_overlapping_trunk_movement_combines_all_qualifying_service(rn):
    """Every direction-0 pattern overlaps S1 -> S2, so waiting is route-level."""
    for pid in ("P_full", "P_full2", "P_short"):
        assert _mult(rn, pid, "S1", "S2") == pytest.approx(1.0)


# 7 --------------------------------------------------------------------------

def test_model_b_is_never_worse_than_model_a_and_the_chosen_pattern_is_in_the_set(rn):
    """The correction is a strict generalisation: adding qualifying patterns can
    only lower the effective headway, never raise it."""
    for pid, frm, to in (("P_full", "S1", "S4"), ("P_full", "S1", "S2"),
                         ("P_full2", "S2", "S4"), ("P_short", "S1", "S2"),
                         ("P_rev", "S4", "S1")):
        pi = _pat(rn, pid)
        b, a = _pos(rn, pi, frm), _pos(rn, pi, to)
        assert pi in qualifying_patterns(rn, pi, b, a, "all")
        model_a = _headway_multiplier(rn, pid, SPECS[pid][0],
                                      SPECS[pid][1], "all")
        model_b = common_lines_multiplier(rn, pi, b, a, "all")
        assert model_b <= model_a + 1e-12


def test_the_cache_returns_the_same_answer_it_computed(rn):
    pi = _pat(rn, "P_full")
    b, a = _pos(rn, pi, "S1"), _pos(rn, pi, "S4")
    cache: dict = {}
    first = common_lines_multiplier(rn, pi, b, a, "all", cache)
    assert len(cache) == 1
    assert common_lines_multiplier(rn, pi, b, a, "all", cache) == first


def test_a_period_with_no_service_falls_back_rather_than_dividing_by_zero(rn):
    pi = _pat(rn, "P_full")
    b, a = _pos(rn, pi, "S1"), _pos(rn, pi, "S4")
    assert common_lines_multiplier(rn, pi, b, a, "no_such_period") == 1.0


# -- end to end through build_pathset ---------------------------------------

def test_model_b_path_set_prices_no_higher_than_model_a(rn):
    """Same network, same OD, two waiting models: B can only be cheaper."""
    import numpy as np
    from cota_opt.cost import CostWeights
    from cota_opt.odmatrix import ODTable, ZoneSystem
    from cota_opt.pathset import PathSetEvaluator, build_pathset

    W = CostWeights(walking=2.0, waiting=2.0, in_vehicle=1.0,
                    transfer_wait=2.0, transfer_penalty=10.0)
    WK = dict(random_arrival_threshold_min=12.0, schedule_coefficient=0.25)
    access = {0: (np.array([rn.stop_index["S1"]]), np.array([0.0])),
              1: (np.array([rn.stop_index["S4"]]), np.array([0.0]))}
    z = object.__new__(type("Z", (ZoneSystem,), {}))
    z.access_of = lambda i: access[int(i)]
    od = ODTable(np.array([0]), np.array([1]), np.array([100.0]), "t", "")
    # route Q runs the identical movement on a single pattern, so if it is
    # attractive the router picks it and the two models trivially agree. Make
    # R the sane choice so the comparison is actually about R's patterns.
    base = {("R", "all"): 5.0, ("Q", "all"): 60.0}

    def cost(mode):
        ps = build_pathset(rn, z, od, "all", base, W, WK, max_rounds=2,
                           max_paths_per_od=4, n_random_scenarios=0, seed=1,
                           common_lines=mode)
        ev = PathSetEvaluator(ps, W, WK, 500.0, retention_full_min=1e9,
                              retention_zero_min=1e9, retention_floor=1.0)
        return float(ev.od_costs(np.array([base[k] for k in ps.rp_keys]))[0])

    a, b = cost("pattern"), cost("same_route")
    assert b <= a + 1e-9
    # S1 -> S4 is carried by both full patterns, so B halves that wait:
    # Model A waits on 5 x 16/6 = 13.33 min, Model B on 5 x 16/12 = 6.67
    assert b < a
    from cota_opt.cost import expected_wait_min
    ivt = 3 * SEG_SEC / 60.0
    assert a == pytest.approx(ivt + 2.0 * expected_wait_min(5 * 16 / 6, **WK))
    assert b == pytest.approx(ivt + 2.0 * expected_wait_min(5 * 16 / 12, **WK))


def test_model_a_remains_the_default(rn):
    from cota_opt.configs import load_assumptions
    pa = load_assumptions()["path_assignment"]
    assert pa.get("common_lines", "pattern") == "pattern"
