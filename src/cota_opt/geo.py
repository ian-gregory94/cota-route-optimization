"""Geospatial artifacts: stops/routes GeoDataFrames, stop spacing, vehicle-miles.

CRS rule (AGENTS.md #4): all metric computation happens in the projected CRS
from config (default EPSG:32617, meters). WGS84 is I/O only.
"""
from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point

from .gtfs import GTFSFeed

log = logging.getLogger(__name__)

GEOGRAPHIC = "EPSG:4326"


def stops_gdf(feed: GTFSFeed, projected: str) -> gpd.GeoDataFrame:
    s = feed.stops.copy()
    s["stop_lat"] = pd.to_numeric(s["stop_lat"], errors="coerce")
    s["stop_lon"] = pd.to_numeric(s["stop_lon"], errors="coerce")
    s = s.dropna(subset=["stop_lat", "stop_lon"])
    g = gpd.GeoDataFrame(
        s, geometry=[Point(xy) for xy in zip(s["stop_lon"], s["stop_lat"])],
        crs=GEOGRAPHIC)
    return g.to_crs(projected)


def shapes_gdf(feed: GTFSFeed, projected: str) -> gpd.GeoDataFrame:
    sh = feed.shapes
    if sh.empty:
        return gpd.GeoDataFrame(columns=["shape_id", "geometry"],
                                geometry="geometry", crs=projected)
    sh = sh.copy()
    for c in ("shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"):
        sh[c] = pd.to_numeric(sh[c], errors="coerce")
    sh = sh.dropna(subset=["shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"])
    rows = []
    for sid, grp in sh.sort_values("shape_pt_sequence").groupby("shape_id"):
        if len(grp) < 2:
            continue
        rows.append({"shape_id": sid, "geometry": LineString(
            list(zip(grp["shape_pt_lon"], grp["shape_pt_lat"])))})
    g = gpd.GeoDataFrame(rows, geometry="geometry", crs=GEOGRAPHIC)
    return g.to_crs(projected)


def routes_gdf(feed: GTFSFeed, tstats: pd.DataFrame, projected: str) -> gpd.GeoDataFrame:
    """One representative geometry per route (longest shape among its trips)."""
    shp = shapes_gdf(feed, projected)
    if shp.empty or "shape_id" not in tstats.columns:
        return gpd.GeoDataFrame(columns=["route_id", "geometry"],
                                geometry="geometry", crs=projected)
    shp = shp.set_index("shape_id")
    shp["length_m"] = shp.geometry.length
    rows = []
    for rid, grp in tstats.dropna(subset=["shape_id"]).groupby("route_id"):
        cand = [s for s in grp["shape_id"].unique() if s in shp.index]
        if not cand:
            continue
        best = max(cand, key=lambda s: float(shp.loc[s, "length_m"]))
        rows.append({"route_id": rid, "shape_id": best,
                     "length_m": float(shp.loc[best, "length_m"]),
                     "geometry": shp.loc[best, "geometry"]})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=projected)


def scheduled_vehicle_miles(feed: GTFSFeed, tstats: pd.DataFrame,
                            projected: str) -> float | None:
    """Σ over trips of shape length. None if shapes are unusable."""
    shp = shapes_gdf(feed, projected)
    if shp.empty or "shape_id" not in tstats.columns:
        return None
    lengths = shp.set_index("shape_id").geometry.length  # meters
    m = tstats["shape_id"].map(lengths)
    if m.isna().all():
        return None
    return float(m.dropna().sum() / 1609.344)


def mean_stop_spacing_m(feed: GTFSFeed, tstats: pd.DataFrame,
                        projected: str) -> pd.DataFrame:
    """Mean consecutive-stop spacing per route (meters, straight-line lower bound).

    Uses each route's most common pattern to avoid double counting.
    """
    stops = stops_gdf(feed, projected).set_index("stop_id")
    st = feed.stop_times[feed.stop_times["trip_id"].isin(tstats["trip_id"])]
    rows = []
    top_pattern_trip = (
        tstats.groupby(["route_id", "pattern_id"])
        .agg(n=("trip_id", "count"), trip_id=("trip_id", "first"))
        .reset_index().sort_values("n", ascending=False)
        .groupby("route_id").first())
    for rid, row in top_pattern_trip.iterrows():
        seq = st[st["trip_id"] == row["trip_id"]].sort_values("stop_sequence")
        pts = [stops.geometry.get(sid) for sid in seq["stop_id"]]
        pts = [p for p in pts if p is not None]
        if len(pts) < 2:
            continue
        d = [pts[i].distance(pts[i + 1]) for i in range(len(pts) - 1)]
        rows.append({"route_id": rid, "mean_spacing_m": float(np.mean(d)),
                     "n_stops": len(pts)})
    return pd.DataFrame(rows)


def export_geojson(gdf: gpd.GeoDataFrame, path: Path) -> None:
    """Write GeoJSON in WGS84 (the interchange convention)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_crs(GEOGRAPHIC).to_file(path, driver="GeoJSON")
    log.info("wrote %s (%d features)", path, len(gdf))
