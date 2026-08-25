"""CRS discipline, stop allocation, and network abstraction tests."""
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from cota_opt.demand import (allocate_to_stops, route_demand_proxy,
                             split_by_period, to_block_groups)


def _stops(projected="EPSG:32617"):
    g = gpd.GeoDataFrame(
        {"stop_id": ["S1", "S2", "S3"]},
        geometry=[Point(-83.00, 39.96), Point(-83.001, 39.96), Point(-83.20, 39.96)],
        crs="EPSG:4326")
    return g.to_crs(projected)


def _bg(projected="EPSG:32617"):
    g = gpd.GeoDataFrame(
        {"geoid_bg": ["A", "B"], "workers": [100.0, 50.0], "jobs": [10.0, 0.0]},
        geometry=[Point(-83.0005, 39.96), Point(-82.50, 39.96)],
        crs="EPSG:4326")
    return g.to_crs(projected)


def test_allocation_requires_a_projected_crs():
    with pytest.raises(ValueError, match="projected CRS"):
        allocate_to_stops(_bg("EPSG:4326"), _stops("EPSG:4326"), 600)


def test_allocation_rejects_crs_mismatch():
    with pytest.raises(ValueError, match="CRS mismatch"):
        allocate_to_stops(_bg("EPSG:32617"), _stops("EPSG:26917"), 600)


def test_allocation_conserves_mass_within_catchment():
    out = allocate_to_stops(_bg(), _stops(), 600)
    # BG "A" (100 workers) sits between S1 and S2; BG "B" is far from everything
    assert out["workers_access"].sum() == pytest.approx(100.0)
    assert out.attrs["unreachable_workers"] == pytest.approx(50.0)
    assert set(out["stop_id"]) <= {"S1", "S2"}


def test_allocation_is_distance_decayed():
    out = allocate_to_stops(_bg(), _stops(), 600).set_index("stop_id")
    # the BG is ~43 m from S1 and ~43 m from S2 → near-equal split
    assert out.loc["S1", "workers_access"] == pytest.approx(
        out.loc["S2", "workers_access"], rel=0.15)


def test_far_stop_gets_nothing():
    out = allocate_to_stops(_bg(), _stops(), 600)
    assert "S3" not in set(out["stop_id"])


def test_block_to_block_group_aggregation():
    df = pd.DataFrame({"geoid_block": ["390490001001000", "390490001001001",
                                       "390490002002000"],
                       "total": [5, 7, 3]})
    bg = to_block_groups(df).set_index("geoid_bg")["total"]
    assert bg["390490001001"] == 12
    assert bg["390490002002"] == 3


def test_county_filter_applies():
    df = pd.DataFrame({"geoid_block": ["390490001001000", "391590001001000"],
                       "total": [5, 7]})
    bg = to_block_groups(df, county_fips={"39049"})
    assert len(bg) == 1 and bg["total"].iloc[0] == 5


def test_route_demand_splits_shared_stops_without_double_counting():
    access = pd.DataFrame({"stop_id": ["S1", "S2"],
                           "workers_access": [100.0, 60.0],
                           "jobs_access": [0.0, 0.0]})
    stop_routes = {"S1": {"R1", "R2"}, "S2": {"R2"}}
    d = route_demand_proxy(access, stop_routes).set_index("route_id")["demand_potential"]
    assert d["R1"] == pytest.approx(50.0)     # half of S1
    assert d["R2"] == pytest.approx(110.0)    # half of S1 + all of S2
    assert d.sum() == pytest.approx(160.0)    # total mass preserved


def test_period_shares_must_sum_to_one():
    rd = pd.DataFrame({"route_id": ["R1"], "demand_potential": [100.0]})
    with pytest.raises(ValueError, match="sum to 1"):
        split_by_period(rd, {"am": 0.5, "pm": 0.3})
    out = split_by_period(rd, {"am": 0.4, "pm": 0.6})
    assert out["demand_potential"].sum() == pytest.approx(100.0)
