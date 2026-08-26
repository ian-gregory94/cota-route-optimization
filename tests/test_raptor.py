"""RAPTOR tests on a synthetic network whose answers are computed by hand.

Network:

    Pattern PA (route A):  S1 -> S2 -> S3 -> S4    10 min per segment
    Pattern PB (route B):  S1 -> S5 -> S4          12 min per segment
    Pattern PC (route C):  S2 -> S6                 5 min
    Footpath:              S3 <-> S6                4 min walk

Every expected number below is derived in the test itself.
"""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from cota_opt.cost import CostWeights, expected_wait_min
from cota_opt.gtfs import GTFSFeed
from cota_opt.network import PatternSegment, RoutePattern, StopNode, TransitNetwork
from cota_opt.raptor import (build_raptor_network, earliest_arrival,
                             generalized_cost, pattern_headways, reconstruct)

W = CostWeights(walking=2.0, waiting=2.0, in_vehicle=1.0, transfer_wait=2.0,
                transfer_penalty=10.0)
WK = dict(random_arrival_threshold_min=12.0, schedule_coefficient=0.25)

# stop coordinates, chosen so S3 and S6 are ~320 m apart (4 min at 80 m/min)
COORDS = {"S1": (-83.000, 39.960), "S2": (-83.010, 39.960), "S3": (-83.020, 39.960),
          "S4": (-83.030, 39.960), "S5": (-83.015, 39.950),
          "S6": (-83.02373, 39.960)}

SPECS = {
    "PA": ("A", 0, ["S1", "S2", "S3", "S4"], [600, 600, 600]),
    "PB": ("B", 0, ["S1", "S5", "S4"], [720, 720]),
    "PC": ("C", 0, ["S2", "S6"], [300]),
}


def _net():
    stops = {s: StopNode(s, s, lat, lon) for s, (lon, lat) in
             ((k, v) for k, v in COORDS.items())}
    stops = {s: StopNode(s, s, COORDS[s][1], COORDS[s][0]) for s in COORDS}
    patterns = {}
    for pid, (route, direction, stop_list, secs) in SPECS.items():
        segs = [PatternSegment(route, direction, pid, stop_list[i], stop_list[i + 1],
                               i, float(secs[i])) for i in range(len(secs))]
        patterns[pid] = RoutePattern(route, direction, pid, list(stop_list), segs, 10)
    stop_routes, route_stops = {}, {}
    for p in patterns.values():
        for s in p.stops:
            stop_routes.setdefault(s, set()).add(p.route_id)
            route_stops.setdefault(p.route_id, set()).add(s)
    return TransitNetwork(stops=stops, patterns=patterns,
                          stop_routes=stop_routes, route_stops=route_stops)


def _stops_gdf():
    g = gpd.GeoDataFrame({"stop_id": list(COORDS)},
                         geometry=[Point(COORDS[s]) for s in COORDS],
                         crs="EPSG:4326")
    return g.to_crs("EPSG:32617")


def _tstats():
    rows = []
    for pid, (route, direction, stop_list, secs) in SPECS.items():
        for t in range(10):
            rows.append({"trip_id": f"{pid}_{t}", "route_id": route,
                         "direction_id": direction, "pattern_id": pid,
                         "first_dep_sec": 8 * 3600 + t * 600,
                         "last_arr_sec": 8 * 3600 + t * 600 + sum(secs),
                         "runtime_min": sum(secs) / 60.0, "n_stops": len(stop_list),
                         "shape_id": pid, "service_id": "WK"})
    return pd.DataFrame(rows)


def _stop_times():
    """stop_times rows matching _tstats(), so the timetable can be attached."""
    rows = []
    for pid, (route, direction, stop_list, secs) in SPECS.items():
        cum = [0] + list(np.cumsum(secs))
        for t in range(10):
            t0 = 8 * 3600 + t * 600
            for i, sid in enumerate(stop_list):
                rows.append({"trip_id": f"{pid}_{t}", "stop_id": sid,
                             "stop_sequence": i + 1,
                             "arrival_sec": float(t0 + cum[i]),
                             "departure_sec": float(t0 + cum[i])})
    return pd.DataFrame(rows)


def _feed():
    return GTFSFeed(tables={"transfers": pd.DataFrame(),
                            "stop_times": _stop_times()}, source_dir=None)


@pytest.fixture
def rn():
    return build_raptor_network(
        _feed(), _net(), _tstats(), _stops_gdf(),
        walk_radius_m=400.0, walk_speed_m_per_min=80.0,
        periods={"all": (0.0, 24.0)}, with_timetable=False)


def _headways(h: dict[str, float]):
    return {(r, "all"): v for r, v in h.items()}


def _pat_h(rn, h):
    return pattern_headways(rn, _headways(h), "all")


def test_network_structure(rn):
    assert set(rn.stop_ids) == set(COORDS)
    assert set(rn.pattern_ids) == {"PA", "PB", "PC"}
    # S3<->S6 is the only pair inside 400 m
    links = {(rn.stop_ids[i], rn.stop_ids[int(rn.fp_to[k])])
             for i in range(rn.n_stops)
             for k in range(rn.fp_offsets[i], rn.fp_offsets[i + 1])}
    assert ("S3", "S6") in links and ("S6", "S3") in links


def test_footpath_walk_time_is_distance_over_speed(rn):
    i = rn.idx("S3")
    for k in range(rn.fp_offsets[i], rn.fp_offsets[i + 1]):
        if rn.stop_ids[int(rn.fp_to[k])] == "S6":
            assert rn.fp_min[k] == pytest.approx(4.0, abs=0.15)
            return
    pytest.fail("S3->S6 footpath missing")


def test_direct_ride_cost_equals_wait_plus_in_vehicle(rn):
    cost, rounds, _ = generalized_cost(rn, "S1", _pat_h(rn, {"A": 10, "B": 1e9, "C": 1e9}),
                                       W, WK, max_rounds=3)
    # wait 10/2 = 5 -> weighted 10; ride 30 min -> 30. total 40
    assert cost[rn.idx("S4")] == pytest.approx(40.0)
    assert rounds[rn.idx("S4")] == 1


def test_faster_route_wins_when_its_headway_is_short_enough(rn):
    # A: 2*5 + 30 = 40.  B at 12-min headway: 2*6 + 24 = 36.
    cost, _, _ = generalized_cost(rn, "S1", _pat_h(rn, {"A": 10, "B": 12, "C": 1e9}),
                                  W, WK, max_rounds=3)
    assert cost[rn.idx("S4")] == pytest.approx(36.0)


def test_slower_headway_flips_the_choice_back(rn):
    # B at 30-min headway: wait = 6 + 0.25*18 = 10.5 -> 21 + 24 = 45 > 40
    cost, _, _ = generalized_cost(rn, "S1", _pat_h(rn, {"A": 10, "B": 30, "C": 1e9}),
                                  W, WK, max_rounds=3)
    assert cost[rn.idx("S4")] == pytest.approx(40.0)


def test_transfer_path_pays_wait_and_penalty(rn):
    # S1 -> S6 via A then C, with the S3<->S6 walk made expensive by removing it
    # is not possible here, so compare against the known walk alternative below.
    cost, rounds, _ = generalized_cost(
        rn, "S1", _pat_h(rn, {"A": 10, "B": 1e9, "C": 20}), W, WK, max_rounds=3)
    # via transfer: 2*5 (wait A) + 10 (ride S1->S2) + transfer wait 2*8=16
    #               + penalty 10 + ride 5  = 51
    # via walk:     2*5 + 20 (ride S1->S3) + 2*4 (walk) = 38   <- cheaper
    #               (the S3-S6 walk is 3.98 min at these coordinates, not 4.00)
    assert cost[rn.idx("S6")] == pytest.approx(38.0, abs=0.1)
    assert rounds[rn.idx("S6")] == 1


def test_transfer_wins_when_the_walk_is_removed(rn):
    """Same OD, but strip the footpath: the answer must become the transfer."""
    rn.fp_offsets = np.zeros(rn.n_stops + 1, dtype=np.int64)
    rn.fp_to = np.zeros(0, dtype=np.int64)
    rn.fp_min = np.zeros(0)
    cost, rounds, _ = generalized_cost(
        rn, "S1", _pat_h(rn, {"A": 10, "B": 1e9, "C": 20}), W, WK, max_rounds=3)
    assert cost[rn.idx("S6")] == pytest.approx(51.0)
    assert rounds[rn.idx("S6")] == 2


def test_unreachable_stop_is_infinite(rn):
    cost, _, _ = generalized_cost(rn, "S4", _pat_h(rn, {"A": 10, "B": 10, "C": 10}),
                                  W, WK, max_rounds=3)
    # S4 is terminal on both A and B; nothing runs backwards
    assert not np.isfinite(cost[rn.idx("S1")])


def test_round_bound_is_respected(rn):
    rn.fp_offsets = np.zeros(rn.n_stops + 1, dtype=np.int64)
    rn.fp_to = np.zeros(0, dtype=np.int64)
    rn.fp_min = np.zeros(0)
    one, _, _ = generalized_cost(rn, "S1", _pat_h(rn, {"A": 10, "B": 1e9, "C": 20}),
                                 W, WK, max_rounds=1)
    assert not np.isfinite(one[rn.idx("S6")])   # needs 2 boardings
    two, _, _ = generalized_cost(rn, "S1", _pat_h(rn, {"A": 10, "B": 1e9, "C": 20}),
                                 W, WK, max_rounds=2)
    assert two[rn.idx("S6")] == pytest.approx(51.0)


def test_cost_is_monotone_in_headway(rn):
    prev = -1.0
    for h in (5, 10, 15, 30, 60):
        c, _, _ = generalized_cost(rn, "S1", _pat_h(rn, {"A": h, "B": 1e9, "C": 1e9}),
                                   W, WK, max_rounds=3)
        v = c[rn.idx("S4")]
        assert v > prev
        prev = v


def test_halving_headway_saves_exactly_the_wait_delta(rn):
    a, _, _ = generalized_cost(rn, "S1", _pat_h(rn, {"A": 10, "B": 1e9, "C": 1e9}),
                               W, WK, max_rounds=3)
    b, _, _ = generalized_cost(rn, "S1", _pat_h(rn, {"A": 5, "B": 1e9, "C": 1e9}),
                               W, WK, max_rounds=3)
    delta = W.waiting * (expected_wait_min(10, **WK) - expected_wait_min(5, **WK))
    assert a[rn.idx("S4")] - b[rn.idx("S4")] == pytest.approx(delta)


def test_pattern_headway_scales_with_trip_share(rn):
    """A pattern carrying half its direction's trips is half as frequent."""
    rn.pattern_trips_period[("PA", "all")] = 5
    rn.direction_trips_period[("A", 0, "all")] = 10
    ph = pattern_headways(rn, _headways({"A": 10, "B": 10, "C": 10}), "all")
    assert ph[rn.pattern_ids.index("PA")] == pytest.approx(20.0)


def test_journey_reconstruction_returns_the_right_legs(rn):
    rn.fp_offsets = np.zeros(rn.n_stops + 1, dtype=np.int64)
    rn.fp_to = np.zeros(0, dtype=np.int64)
    rn.fp_min = np.zeros(0)
    cost, rounds, par = generalized_cost(
        rn, "S1", _pat_h(rn, {"A": 10, "B": 1e9, "C": 20}), W, WK,
        max_rounds=3, trace=True)
    j = reconstruct(rn, par, "S6", int(rounds[rn.idx("S6")]), {"S1"})
    assert j is not None
    assert j.routes == ["A", "C"]
    assert j.n_transfers == 1
    assert j.in_vehicle_min == pytest.approx(15.0)   # 10 + 5
    assert [l.to_stop for l in j.legs] == ["S2", "S6"]


def test_walk_journey_reconstruction(rn):
    cost, rounds, par = generalized_cost(
        rn, "S1", _pat_h(rn, {"A": 10, "B": 1e9, "C": 1e9}), W, WK,
        max_rounds=3, trace=True)
    j = reconstruct(rn, par, "S6", int(rounds[rn.idx("S6")]), {"S1"})
    assert j is not None
    assert j.routes == ["A"]
    assert j.walk_min == pytest.approx(4.0, abs=0.15)


def test_timetabled_earliest_arrival_matches_the_schedule():
    rn = build_raptor_network(_feed(), _net(), _tstats(), _stops_gdf(),
                              walk_radius_m=400.0, walk_speed_m_per_min=80.0,
                              periods={"all": (0.0, 24.0)}, with_timetable=True)
    # Both PA and PB reach S4 and both leave S1 at 08:00, 08:10, ...
    # PA takes 3 x 600 = 1800 s; PB takes 2 x 720 = 1440 s. With no wait to
    # penalize, the timetabled router must pick the faster one, PB.
    rounds = earliest_arrival(rn, "S1", 8 * 3600, max_rounds=3)
    assert rounds[1, rn.idx("S4")] == pytest.approx(8 * 3600 + 1440)
    # S3 is only on PA, so it pins PA's own running time
    assert rounds[1, rn.idx("S3")] == pytest.approx(8 * 3600 + 1200)
    # one second after the 08:00 departures, everything waits for 08:10
    rounds2 = earliest_arrival(rn, "S1", 8 * 3600 + 1, max_rounds=3)
    assert rounds2[1, rn.idx("S4")] == pytest.approx(8 * 3600 + 600 + 1440)
    assert rounds2[1, rn.idx("S3")] == pytest.approx(8 * 3600 + 600 + 1200)


def test_timetabled_and_cost_routers_agree_on_ride_times():
    """The two routers share the segment data; in-vehicle times must match."""
    rn = build_raptor_network(_feed(), _net(), _tstats(), _stops_gdf(),
                              walk_radius_m=1.0, walk_speed_m_per_min=80.0,
                              periods={"all": (0.0, 24.0)}, with_timetable=True)
    tt = earliest_arrival(rn, "S1", 8 * 3600, max_rounds=3)
    ride_min = (tt[1, rn.idx("S3")] - 8 * 3600) / 60.0
    cost, _, _ = generalized_cost(rn, "S1", _pat_h(rn, {"A": 10, "B": 1e9, "C": 1e9}),
                                  CostWeights(waiting=0.0, in_vehicle=1.0,
                                              walking=2.0, transfer_penalty=10.0),
                                  WK, max_rounds=3)
    # with the wait weight zeroed, generalized cost is pure in-vehicle minutes
    assert cost[rn.idx("S3")] == pytest.approx(ride_min)


def test_timetabled_respects_round_limit():
    rn = build_raptor_network(_feed(), _net(), _tstats(), _stops_gdf(),
                              walk_radius_m=1.0, walk_speed_m_per_min=80.0,
                              periods={"all": (0.0, 24.0)}, with_timetable=True)
    rounds = earliest_arrival(rn, "S1", 8 * 3600, max_rounds=1)
    assert not np.isfinite(rounds[1, rn.idx("S6")])   # S6 needs two boardings
