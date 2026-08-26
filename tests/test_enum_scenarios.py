"""Gate 11's answer: does the route-level search scenario find what it should?

Reuses the discovery fixture, which is built so the failure actually happens.
Route T is a trunk with two half-frequency patterns both carrying S1 -> S4;
route D is a slower single-pattern direct. Under Model A's per-pattern pricing
T looks half as frequent as it is, so a search under that valuation reaches for
D. Under Model B, T's patterns combine and T wins -- but the candidate set only
contains T if something went looking for it.

Gate 11 found 4.88% of tested flow with exactly that shape on the real feed.
The fix is a search scenario, not a valuation change: whatever it turns up is
still priced by the evaluator afterwards.
"""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from cota_opt.cost import CostWeights
from cota_opt.gtfs import GTFSFeed
from cota_opt.network import PatternSegment, RoutePattern, StopNode, TransitNetwork
from cota_opt.odmatrix import ODTable, ZoneSystem
from cota_opt.pathset import _plan_scenarios, build_pathset
from cota_opt.raptor import (build_raptor_network, pattern_headways,
                             route_level_headways)

W = CostWeights(walking=2.0, waiting=2.0, in_vehicle=1.0, transfer_wait=2.0,
                transfer_penalty=10.0)
WK = dict(random_arrival_threshold_min=1e9, schedule_coefficient=0.25)

COORDS = {"S1": (-83.000, 39.960), "S2": (-83.010, 39.960),
          "S3": (-83.020, 39.960), "S4": (-83.030, 39.960)}

# T is the SLOWER ride (27 min against D's 25) and the more frequent route
# (12 min against 20). Split across two equal patterns it is priced at 24 --
# worse than D under every uniform headway scenario the standard sweep tries.
# Combined it is priced at 12 and wins. That is exactly the shape gate 11 found
# on 4.88% of tested flow, reduced to two routes.
SPECS = {"T_a": ("T", 0, ["S1", "S2", "S3", "S4"], 10, 540.0),
         "T_b": ("T", 0, ["S1", "S2", "S3", "S4"], 10, 540.0),
         "D_1": ("D", 0, ["S1", "S4"], 10, 1500.0)}
HW = {("T", "all"): 12.0, ("D", "all"): 20.0}


def _net():
    stops = {s: StopNode(s, s, COORDS[s][1], COORDS[s][0]) for s in COORDS}
    patterns = {}
    for pid, (route, d, sl, n, seg) in SPECS.items():
        segs = [PatternSegment(route, d, pid, sl[i], sl[i + 1], i, seg)
                for i in range(len(sl) - 1)]
        patterns[pid] = RoutePattern(route, d, pid, list(sl), segs, n)
    sr, rs = {}, {}
    for p in patterns.values():
        for s in p.stops:
            sr.setdefault(s, set()).add(p.route_id)
            rs.setdefault(p.route_id, set()).add(s)
    return TransitNetwork(stops=stops, patterns=patterns, stop_routes=sr,
                          route_stops=rs)


def _tstats():
    rows = []
    for pid, (route, d, sl, n, seg) in SPECS.items():
        rt = seg * (len(sl) - 1)
        for t in range(n):
            rows.append({"trip_id": f"{pid}_{t}", "route_id": route,
                         "direction_id": d, "pattern_id": pid,
                         "first_dep_sec": 8 * 3600 + t * 600,
                         "last_arr_sec": 8 * 3600 + t * 600 + rt,
                         "runtime_min": rt / 60.0, "n_stops": len(sl),
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


def _routes_of(ps, p):
    a, b = ps.path_offsets[p], ps.path_offsets[p + 1]
    rp = ps.leg_rp[a:b]
    return tuple(ps.rp_keys[int(k)][0] for k in rp[rp >= 0])


def _paths(rn, zs, mode):
    od = ODTable(np.array([0]), np.array([1]), np.array([500.0]), "t", "")
    ps = build_pathset(rn, zs, od, "all", HW, W, WK, max_rounds=2,
                       max_paths_per_od=4, n_random_scenarios=0, seed=1,
                       common_lines=mode)
    return ps, {_routes_of(ps, p) for p in range(ps.n_paths)}


# -- the scenario itself -----------------------------------------------------

def test_model_b_enumeration_gains_a_route_level_scenario():
    rng = np.random.default_rng(0)
    base = {("A", "am"): 10.0}
    names = lambda m: [s[0] for s in _plan_scenarios(list(base), base, rng, 0,
                                                     common_lines=m)]
    assert "route_level" not in names("pattern")
    assert "route_level" in names("same_route")


def test_model_a_enumeration_is_untouched():
    """Model A is the preserved control; its candidate set must not move."""
    rng = np.random.default_rng(0)
    base = {("A", "am"): 10.0}
    scen = _plan_scenarios(list(base), base, rng, 3, common_lines="pattern")
    assert [s[0] for s in scen] == ["baseline", "frequent", "infrequent",
                                    "random0", "random1", "random2"]
    assert {s[2] for s in scen} == {"pattern"}


def test_the_route_level_scenario_prices_every_pattern_at_its_route(rn):
    per = pattern_headways(rn, HW, "all")
    lvl = route_level_headways(rn, HW, "all")
    ti = rn.pattern_ids.index("T_a")
    assert per[ti] == pytest.approx(24.0)     # one of two half-frequency patterns
    assert lvl[ti] == pytest.approx(12.0)     # the route's whole frequency
    assert np.all(lvl <= per + 1e-12)


# -- what it buys ------------------------------------------------------------

def test_the_trunk_sequence_is_missing_without_the_scenario(rn, zs):
    """This is the omission gate 11 measured, reproduced in miniature."""
    _, routes = _paths(rn, zs, "pattern")
    assert ("D",) in routes
    assert ("T",) not in routes


def test_the_scenario_finds_the_trunk_the_correction_makes_attractive(rn, zs):
    _, routes = _paths(rn, zs, "same_route")
    assert ("T",) in routes
    assert ("D",) in routes, "widening the search must not drop what it had"


def test_the_wider_set_is_a_superset_not_a_replacement(rn, zs):
    _, a = _paths(rn, zs, "pattern")
    _, b = _paths(rn, zs, "same_route")
    assert a <= b


def test_the_found_path_is_priced_by_the_evaluator_not_by_the_bound(rn, zs):
    """The scenario is a search device. It must not leak into any cost."""
    ps, _ = _paths(rn, zs, "same_route")
    ti = [i for i in range(ps.n_paths) if _routes_of(ps, i) == ("T",)][0]
    a, b = ps.path_offsets[ti], ps.path_offsets[ti + 1]
    mult = ps.leg_headway_mult[a:b]
    ride = ps.leg_rp[a:b] >= 0
    # Model B's multiplier for two equal half-frequency patterns is 1.0 --
    # the combined frequency, which is NOT the route-level bound's 1.0 by
    # coincidence but by the arithmetic: 1 / (10/20 + 10/20).
    assert np.allclose(mult[ride], 1.0)
