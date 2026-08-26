"""Baseline builder: turns the registered GTFS feed into the analysis tables.

Produces (under ``data/processed``):
  trip_stats.parquet, route_summary.csv, route_period_stats.csv,
  stop_spacing.csv, system_summary.json, validation_report.json,
  stops.geojson, routes.geojson, stop_demand_access.csv, route_demand.csv

All figures are *scheduled estimates* from GTFS unless explicitly labeled
otherwise.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import geo
from .calendar_utils import representative_weekday
from .configs import load_assumptions, service_periods
from .demand import (allocate_to_stops, build_bg_frame, read_bg_centroids,
                     read_lodes, route_demand_proxy, split_by_period,
                     to_block_groups)
from .download import unpack_gtfs
from .gtfs import GTFSFeed, load_feed, validate_feed
from .network import TransitNetwork, period_headways
from .paths import data_processed
from .registry import Registry
from .summaries import (route_period_stats, route_summary, system_summary,
                        trip_stats)

log = logging.getLogger(__name__)

# Franklin County + the six adjacent counties COTA's service area touches.
CENTRAL_OHIO_FIPS = {"39049", "39041", "39045", "39089", "39097", "39129", "39159"}


@dataclass
class Baseline:
    feed: GTFSFeed
    service_date: str
    service_ids: set[str]
    n_typical_days: int
    tstats: pd.DataFrame
    routes: pd.DataFrame
    route_periods: pd.DataFrame
    headways: pd.DataFrame
    system: Any
    network: TransitNetwork
    validation: dict
    stop_spacing: pd.DataFrame
    veh_miles: float | None
    assumptions: dict
    demand: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)


def build_baseline(registry: Registry | None = None,
                   demand_files: dict[str, Path] | None = None,
                   write: bool = True) -> Baseline:
    reg = registry or Registry()
    gtfs_dir = unpack_gtfs(reg)
    feed = load_feed(gtfs_dir)
    report = validate_feed(feed)
    log.info("validation: %d errors, %d warnings",
             len(report.errors), len(report.warnings))

    a = load_assumptions()
    periods = service_periods(a)
    projected = a["crs"]["projected"]

    date, sids, n_days = representative_weekday(feed)
    log.info("representative weekday: %s (service_ids=%s, occurs %d days)",
             date, sorted(sids), n_days)

    ts = trip_stats(feed, sids)
    rsum = route_summary(ts, feed)
    rps = route_period_stats(ts, periods)
    hw = period_headways(ts, periods)
    vmiles, vm_diag = _scheduled_vehicle_miles(feed, ts, projected)
    sysm = system_summary(feed, ts, str(date), periods, vmiles)
    net = TransitNetwork.from_feed(feed, ts)
    spacing = geo.mean_stop_spacing_m(feed, ts, projected)

    diagnostics: dict[str, Any] = {"vehicle_miles": vm_diag}
    diagnostics["unassigned_trips"] = int(len(ts) - rps["n_trips"].sum())
    diagnostics["n_patterns"] = int(ts["pattern_id"].nunique())
    diagnostics["n_transfer_stops"] = len(net.transfer_stops())

    demand: dict[str, Any] = {"status": "NOT_AVAILABLE"}
    if demand_files:
        demand = _build_demand(feed, net, demand_files, a, projected)

    b = Baseline(feed=feed, service_date=str(date), service_ids=sids,
                 n_typical_days=n_days, tstats=ts, routes=rsum,
                 route_periods=rps, headways=hw, system=sysm, network=net,
                 validation=report.to_dict(), stop_spacing=spacing,
                 veh_miles=vmiles, assumptions=a, demand=demand,
                 diagnostics=diagnostics)
    if write:
        _write(b, projected)
    return b


def _scheduled_vehicle_miles(feed: GTFSFeed, ts: pd.DataFrame,
                             projected: str) -> tuple[float | None, dict]:
    """Vehicle-miles from stop_times.shape_dist_traveled, cross-checked on shapes.

    ``shape_dist_traveled`` units are feed-defined; we verify them against the
    projected shape geometry length before trusting the number.
    """
    diag: dict[str, Any] = {}
    st = feed.stop_times[feed.stop_times["trip_id"].isin(ts["trip_id"])]
    geom_miles = geo.scheduled_vehicle_miles(feed, ts, projected)
    diag["from_shape_geometry_miles"] = geom_miles
    if "shape_dist_traveled" not in st.columns:
        diag["method"] = "shape_geometry"
        return geom_miles, diag
    per_trip = pd.to_numeric(st["shape_dist_traveled"], errors="coerce") \
        .groupby(st["trip_id"]).max()
    sdt_total = float(per_trip.sum())
    diag["from_shape_dist_traveled"] = sdt_total
    if geom_miles and geom_miles > 0:
        ratio = sdt_total / geom_miles
        diag["sdt_over_geometry_ratio"] = ratio
        # GTFS does not fix shape_dist_traveled units; infer them from the
        # projected geometry, which is unambiguous.
        if 0.95 <= ratio <= 1.05:
            diag["sdt_units"] = "miles"
            diag["method"] = "shape_dist_traveled (miles, geometry-confirmed)"
            diag["agreement_pct"] = abs(ratio - 1) * 100
            return sdt_total, diag
        if 1.55 <= ratio <= 1.67:           # 1 mile = 1.609 km
            km_as_miles = sdt_total / 1.609344
            diag["sdt_units"] = "kilometers"
            diag["from_shape_dist_traveled_converted_miles"] = km_as_miles
            diag["agreement_pct"] = abs(km_as_miles / geom_miles - 1) * 100
            diag["method"] = ("shape_dist_traveled (km, converted; "
                              "cross-checked against projected geometry)")
            return km_as_miles, diag
        diag["sdt_units"] = "UNKNOWN"
        diag["method"] = "shape_geometry (shape_dist_traveled units unrecognized)"
        return geom_miles, diag
    diag["method"] = "shape_dist_traveled (unverified units)"
    return sdt_total, diag


def _build_demand(feed: GTFSFeed, net: TransitNetwork, files: dict[str, Path],
                  a: dict, projected: str) -> dict[str, Any]:
    """LODES RAC/WAC + block-group centroids → per-stop and per-route demand proxy."""
    out: dict[str, Any] = {"status": "PROXY"}
    cent = read_bg_centroids(files["centroids"])
    rac = to_block_groups(read_lodes(files["rac"], "h_geocode"), CENTRAL_OHIO_FIPS)
    wac = to_block_groups(read_lodes(files["wac"], "w_geocode"), CENTRAL_OHIO_FIPS)
    keep = set(rac["geoid_bg"]) | set(wac["geoid_bg"])
    cent = cent[cent["geoid_bg"].isin(keep)]
    bg = build_bg_frame(cent, rac, wac, projected)

    stops = geo.stops_gdf(feed, projected)
    served = set().union(*net.route_stops.values()) if net.route_stops else set()
    stops = stops[stops["stop_id"].isin(served)]

    radius = float(a["demand_proxy"]["catchment_radius_m"])
    access = allocate_to_stops(bg, stops, radius)
    rdem = route_demand_proxy(access, net.stop_routes,
                              float(a["demand_proxy"]["resident_weight"]),
                              float(a["demand_proxy"]["job_weight"]))
    rdem_p = split_by_period(rdem, a["demand_proxy"]["period_shares"])

    out.update({
        "stop_access": access,
        "route_demand": rdem,
        "route_demand_period": rdem_p,
        "bg_frame": bg,
        "n_block_groups": int(len(bg)),
        "total_workers": float(bg["workers"].sum()),
        "total_jobs": float(bg["jobs"].sum()),
        "workers_within_catchment": float(access["workers_access"].sum()),
        "jobs_within_catchment": float(access["jobs_access"].sum()),
        "unreachable_workers": float(access.attrs["unreachable_workers"]),
        "unreachable_jobs": float(access.attrs["unreachable_jobs"]),
        "catchment_radius_m": radius,
        "n_stops_with_access": int(len(access)),
    })
    return out


def _write(b: Baseline, projected: str) -> None:
    d = data_processed()
    d.mkdir(parents=True, exist_ok=True)
    b.tstats.to_parquet(d / "trip_stats.parquet")
    b.routes.to_csv(d / "route_summary.csv", index=False)
    b.route_periods.to_csv(d / "route_period_stats.csv", index=False)
    b.headways.to_csv(d / "baseline_headways.csv", index=False)
    b.stop_spacing.to_csv(d / "stop_spacing.csv", index=False)
    (d / "validation_report.json").write_text(json.dumps(b.validation, indent=2))
    (d / "system_summary.json").write_text(json.dumps(
        {**b.system.to_dict(), "n_typical_days": b.n_typical_days,
         "service_ids": sorted(b.service_ids), "diagnostics": b.diagnostics},
        indent=2, default=str))
    geo.export_geojson(geo.stops_gdf(b.feed, projected), d / "stops.geojson")
    geo.export_geojson(geo.routes_gdf(b.feed, b.tstats, projected),
                       d / "routes.geojson")
    if b.demand.get("status") == "PROXY":
        b.demand["stop_access"].to_csv(d / "stop_demand_access.csv", index=False)
        b.demand["route_demand"].to_csv(d / "route_demand.csv", index=False)
        b.demand["route_demand_period"].to_csv(d / "route_demand_period.csv",
                                               index=False)
    log.info("wrote processed tables to %s", d)


def headway_percentiles(rps: pd.DataFrame) -> pd.DataFrame:
    """Headway distribution by period, trip-weighted."""
    rows = []
    for per, grp in rps.groupby("period"):
        h = grp["mean_headway_min"]
        w = grp["n_trips"]
        rows.append({
            "period": per,
            "route_directions": len(grp),
            "trips": int(w.sum()),
            "median_headway_min": float(np.median(h)),
            "p25": float(np.percentile(h, 25)),
            "p75": float(np.percentile(h, 75)),
            "min": float(h.min()), "max": float(h.max()),
            "trip_weighted_mean": float((h * w).sum() / w.sum()),
            "pct_routes_15min_or_better": float((h <= 15).mean() * 100),
        })
    return pd.DataFrame(rows)
