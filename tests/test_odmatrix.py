"""OD matrix construction, zone access, and the gravity fallback."""
import gzip

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from cota_opt.odmatrix import (ODTable, _top_k, build_zone_system,
                               filter_to_accessible, from_gravity,
                               from_lodes_od, scale_to, split_by_period)

PROJ = "EPSG:32617"


def _bg():
    """Four block groups; the fourth is far from any stop."""
    rows = [("390490001001", -83.000, 39.960, 100.0, 20.0),
            ("390490001002", -83.010, 39.960, 80.0, 200.0),
            ("390490002001", -83.020, 39.960, 60.0, 10.0),
            ("390490002002", -82.500, 39.960, 40.0, 5.0)]
    df = pd.DataFrame(rows, columns=["geoid_bg", "lon", "lat", "workers", "jobs"])
    g = gpd.GeoDataFrame(df, geometry=[Point(r.lon, r.lat) for r in df.itertuples()],
                         crs="EPSG:4326")
    return g.to_crs(PROJ)


def _stops():
    g = gpd.GeoDataFrame({"stop_id": ["S1", "S2", "S3"]},
                         geometry=[Point(-83.000, 39.960), Point(-83.010, 39.960),
                                   Point(-83.020, 39.960)],
                         crs="EPSG:4326")
    return g.to_crs(PROJ)


@pytest.fixture
def zs():
    return build_zone_system(_bg(), _stops(), radius_m=600.0,
                             walk_speed_m_per_min=80.0,
                             stop_index={"S1": 0, "S2": 1, "S3": 2})


def test_zone_system_links_only_nearby_stops(zs):
    assert zs.n == 4
    have = np.diff(zs.access_offsets) > 0
    assert have.tolist() == [True, True, True, False]
    stops, walk = zs.access_of(0)
    assert 0 in stops.tolist()
    assert all(w <= 600.0 / 80.0 for w in walk)


def test_zone_access_walk_time_is_zero_at_the_stop(zs):
    stops, walk = zs.access_of(0)
    k = stops.tolist().index(0)          # zone 0 sits exactly on stop S1
    assert walk[k] == pytest.approx(0.0, abs=1e-6)


def test_filter_to_accessible_drops_pairs_without_both_ends(zs):
    od = ODTable(np.array([0, 0, 3]), np.array([1, 3, 1]),
                 np.array([10.0, 5.0, 7.0]))
    out = filter_to_accessible(od, zs)
    assert len(out) == 1
    assert out.origin[0] == 0 and out.dest[0] == 1


def test_top_k_keeps_the_largest_flows(zs):
    od = ODTable(np.array([0, 1, 2]), np.array([1, 2, 0]),
                 np.array([1.0, 50.0, 10.0]))
    out = _top_k(od, 2)
    assert sorted(out.flow.tolist()) == [10.0, 50.0]


def test_top_k_is_a_noop_when_k_exceeds_size(zs):
    od = ODTable(np.array([0]), np.array([1]), np.array([5.0]))
    assert len(_top_k(od, 99)) == 1


def test_scale_to_preserves_shape_and_hits_the_target():
    od = ODTable(np.array([0, 1]), np.array([1, 0]), np.array([3.0, 7.0]))
    out = scale_to(od, 100.0)
    assert out.total() == pytest.approx(100.0)
    assert out.flow[1] / out.flow[0] == pytest.approx(7 / 3)


def test_scale_to_rejects_empty_table():
    with pytest.raises(ValueError):
        scale_to(ODTable(np.array([]), np.array([]), np.array([])), 10.0)


def test_period_split_conserves_total():
    od = ODTable(np.array([0, 1]), np.array([1, 0]), np.array([10.0, 30.0]))
    parts = split_by_period(od, {"am": 0.4, "pm": 0.6})
    assert sum(p.total() for p in parts.values()) == pytest.approx(40.0)
    assert parts["am"].total() == pytest.approx(16.0)


def test_period_split_rejects_shares_that_do_not_sum_to_one():
    od = ODTable(np.array([0]), np.array([1]), np.array([1.0]))
    with pytest.raises(ValueError, match="sum to 1"):
        split_by_period(od, {"am": 0.5, "pm": 0.2})


def test_lodes_od_aggregates_blocks_into_block_groups(tmp_path, zs):
    p = tmp_path / "od.csv.gz"
    rows = ["w_geocode,h_geocode,S000",
            # two blocks of BG ...0001001 -> one block of BG ...0001002
            "390490001002000,390490001001000,3",
            "390490001002001,390490001001001,4",
            # a pair outside the zone system
            "999990001001000,999990001001000,9"]
    with gzip.open(p, "wt") as f:
        f.write("\n".join(rows) + "\n")
    od = from_lodes_od(p, zs)
    assert len(od) == 1
    assert od.flow[0] == pytest.approx(7.0)
    assert od.origin[0] == zs.index["390490001001"]
    assert od.dest[0] == zs.index["390490001002"]


def test_lodes_od_county_filter(tmp_path, zs):
    p = tmp_path / "od.csv.gz"
    with gzip.open(p, "wt") as f:
        f.write("w_geocode,h_geocode,S000\n"
                "390490001002000,390490001001000,3\n")
    assert len(from_lodes_od(p, zs, county_fips={"39049"})) == 1
    with pytest.raises(ValueError, match="no LODES OD rows matched"):
        from_lodes_od(p, zs, county_fips={"39999"})


def test_gravity_reproduces_its_margins(zs):
    od = from_gravity(zs, mean_trip_km=1.0, max_km=100.0)
    # doubly-constrained: origin totals must match workers for zones in play
    by_o = np.bincount(od.origin, weights=od.flow, minlength=zs.n)
    have = np.diff(zs.access_offsets) > 0
    played = have & (zs.workers > 0)
    assert by_o[played].sum() == pytest.approx(zs.workers[played].sum(), rel=0.02)


def test_gravity_deterrence_shortens_trips_as_beta_rises(zs):
    short = from_gravity(zs, mean_trip_km=0.5, max_km=100.0)
    long_ = from_gravity(zs, mean_trip_km=3.0, max_km=100.0)

    def mean_dist(od):
        dx = zs.x[od.origin] - zs.x[od.dest]
        dy = zs.y[od.origin] - zs.y[od.dest]
        d = np.sqrt(dx * dx + dy * dy) / 1000.0
        return float((d * od.flow).sum() / od.flow.sum())

    assert mean_dist(short) < mean_dist(long_)


def test_gravity_needs_zones_with_access():
    empty = build_zone_system(_bg().iloc[[3]], _stops(), radius_m=10.0,
                              walk_speed_m_per_min=80.0,
                              stop_index={"S1": 0, "S2": 1, "S3": 2})
    with pytest.raises(ValueError, match="no zones"):
        from_gravity(empty)
