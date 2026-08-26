"""Reproducible baseline report generation (prose + machine-readable tables)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .baseline import Baseline, headway_percentiles
from .paths import outputs_dir
from .registry import Registry, load_sources

SECTIONS = ["DATA RETRIEVAL STATUS", "GTFS VALIDATION", "NETWORK SUMMARY",
            "ROUTE SUMMARY", "STOP SUMMARY", "SERVICE FREQUENCY",
            "SERVICE SPAN", "SCHEDULED RUNTIME", "APPROXIMATE RESOURCE METRICS",
            "AVAILABLE EXTERNAL DEMAND DATA", "AVAILABLE TRAFFIC DATA",
            "MISSING DATA", "KNOWN ASSUMPTIONS", "NEXT RESEARCH STEPS"]

# Step 17 — data-gap classification.
DATA_GAPS = [
    ("current stop-level boardings/alightings", "REQUIRES PUBLIC RECORDS REQUEST",
     "COTA operates APC-equipped buses; stop-level boardings are not in any "
     "public feed located. Not derivable from GTFS."),
    ("trip-level APC", "REQUIRES PUBLIC RECORDS REQUEST",
     "Same source as above; needed to calibrate the demand proxy."),
    ("driver work rules", "REQUIRES PUBLIC RECORDS REQUEST",
     "Union agreement (TWU Local 208) governs run length, breaks, spread; "
     "may be partly public but not retrieved."),
    ("operator availability", "LIKELY INTERNAL ONLY",
     "Headcount, absence and extraboard levels are operational data."),
    ("maintenance reserve", "ESTIMABLE",
     "NTD reports fleet size and vehicles operated in max service; the ratio "
     "bounds spare ratio. Not yet retrieved in this environment."),
    ("deadhead rules", "DERIVABLE (partially)",
     "GTFS block_id is present, so vehicle blocks and the pull-out/pull-in "
     "structure are partly reconstructable; depot locations are not in GTFS."),
    ("depot assignments", "LIKELY INTERNAL ONLY",
     "COTA garage locations are public; per-block assignment is not."),
    ("real fuel/energy cost", "PUBLICLY AVAILABLE",
     "NTD reports annual fuel/energy consumption and operating expense by mode."),
    ("observed route runtime distributions", "DERIVABLE",
     "GTFS-Realtime vehicle positions and trip updates are public; sustained "
     "collection yields empirical segment travel-time distributions."),
    ("transfer behavior", "ESTIMABLE",
     "Fare-system transfer data is internal; transfer rates can be estimated "
     "from network structure and a mode-choice model."),
    ("latent non-work OD demand", "ESTIMABLE",
     "LODES covers home→work only. Non-work travel needs NHTS rates, a "
     "regional travel model (MORPC), or LBS data."),
    ("service-area population/demographics", "PUBLICLY AVAILABLE",
     "ACS 5-year at tract/block-group level via the Census API."),
]


def _fmt(x: Any, nd: int = 1) -> str:
    if isinstance(x, float):
        return f"{x:,.{nd}f}"
    if isinstance(x, int):
        return f"{x:,}"
    return str(x)


def build_report(b: Baseline, exp_metrics: dict | None = None,
                 out_dir: Path | None = None) -> dict[str, Path]:
    d = out_dir or outputs_dir()
    d.mkdir(parents=True, exist_ok=True)
    reg = Registry()
    sources = load_sources()
    now = datetime.now(timezone.utc).isoformat()

    hp = headway_percentiles(b.route_periods)
    sysd = b.system.to_dict()
    L = []
    w = L.append

    w("# COTA Baseline Report")
    w("")
    w(f"Generated {now}")
    w("")
    w("All figures below are **scheduled estimates derived from COTA's published "
      "GTFS feed**. They are not COTA's reported operating statistics and have "
      "not been reconciled against the National Transit Database.")
    w("")

    # ---- 1 ----
    w("## DATA RETRIEVAL STATUS")
    w("")
    rows = []
    for key, s in sources.items():
        rec = reg.get(key)
        rows.append({"source": s.name, "publisher": s.publisher,
                     "status": "RETRIEVED" if rec else s.status,
                     "retrieved_at": rec.retrieved_at if rec else "",
                     "sha256": rec.sha256[:16] if rec else "",
                     "url": s.url})
    src_tab = pd.DataFrame(rows)
    w(src_tab[["source", "publisher", "status", "retrieved_at"]].to_markdown(index=False))
    w("")
    w("`BLOCKED_EGRESS` means the URL is confirmed correct but this sandbox "
      "cannot reach the host; the file was retrieved on the operator's machine "
      "and registered with full provenance. `UNKNOWN` means no authoritative "
      "URL has been located yet.")
    w("")

    # ---- 2 ----
    w("## GTFS VALIDATION")
    w("")
    v = b.validation
    w(f"- errors: **{v['n_errors']}**")
    w(f"- warnings: **{v['n_warnings']}**")
    w("")
    if v["issues"]:
        w("| severity | code | message | count |")
        w("|---|---|---|---|")
        for i in v["issues"]:
            w(f"| {i['severity']} | {i['code']} | {i['message']} | {i['count']} |")
    else:
        w("No structural issues found. Checks applied: required fields, unique "
          "IDs, trip→route / stop_time→trip / stop_time→stop / trip→service "
          "referential integrity, coordinate validity, stop-sequence "
          "monotonicity, non-decreasing departure times, calendar presence, "
          "shape references.")
    w("")

    # ---- 3 ----
    w("## NETWORK SUMMARY")
    w("")
    w(f"- feed version: `{_feed_version(b)}`")
    w(f"- representative weekday: **{b.service_date}** "
      f"(modal weekday service pattern; occurs on {b.n_typical_days} of the "
      f"Tue/Wed/Thu dates in the feed window)")
    w(f"- routes with weekday service: **{sysd['n_routes']}** "
      f"(of {len(b.feed.routes)} defined in the feed)")
    w(f"- stops served: **{_fmt(sysd['n_stops_served'])}**")
    w(f"- weekday trips: **{_fmt(sysd['n_trips'])}**")
    w(f"- distinct stop patterns: **{b.diagnostics['n_patterns']}**")
    w(f"- stops served by more than one route (transfer points): "
      f"**{_fmt(b.diagnostics['n_transfer_stops'])}**")
    w("")

    # ---- 4 ----
    w("## ROUTE SUMMARY")
    w("")
    w("Top 15 routes by scheduled revenue vehicle-hours:")
    w("")
    top = b.routes.head(15).copy()
    top = top[["route_id", "route_name", "n_trips", "n_patterns", "span_hours",
               "mean_runtime_min", "revenue_veh_hours"]].round(2)
    w(top.to_markdown(index=False))
    w("")
    w(f"Full table: `data/processed/route_summary.csv` ({len(b.routes)} routes).")
    w("")

    # ---- 5 ----
    w("## STOP SUMMARY")
    w("")
    sp = b.stop_spacing["mean_spacing_m"]
    w(f"- stops in feed: **{_fmt(len(b.feed.stops))}**")
    w(f"- stops with weekday service: **{_fmt(sysd['n_stops_served'])}**")
    w(f"- mean consecutive-stop spacing, median across routes: "
      f"**{sp.median():,.0f} m** ({sp.median()*3.28084:,.0f} ft)")
    w(f"- spacing range across routes: {sp.min():,.0f}–{sp.max():,.0f} m")
    w("")
    w("Spacing is straight-line distance between consecutive stops on each "
      "route's most common pattern, computed in EPSG:32617 (metres). It is a "
      "lower bound on on-street spacing.")
    w("")

    # ---- 6 ----
    w("## SERVICE FREQUENCY")
    w("")
    w(hp.round(2).to_markdown(index=False))
    w("")
    w("Headway = mean gap between consecutive first departures of trips on the "
      "same route+direction whose first departure falls in the period.")
    w("")

    # ---- 7 ----
    w("## SERVICE SPAN")
    w("")
    span = b.routes["span_hours"]
    w(f"- median route span: **{span.median():.1f} h**")
    w(f"- longest: {b.routes.loc[span.idxmax(), 'route_name']} "
      f"({span.max():.1f} h); shortest: "
      f"{b.routes.loc[span.idxmin(), 'route_name']} ({span.min():.1f} h)")
    w(f"- system first departure: {b.tstats['first_dep_sec'].min()/3600:.2f} h; "
      f"last arrival: {b.tstats['last_arr_sec'].max()/3600:.2f} h "
      f"(hours ≥24 are past-midnight service)")
    w("")

    # ---- 8 ----
    w("## SCHEDULED RUNTIME")
    w("")
    rt = b.tstats["runtime_min"]
    w(f"- mean one-way trip runtime: **{rt.mean():.1f} min**")
    w(f"- median {rt.median():.1f} min; p10 {rt.quantile(.1):.1f}; "
      f"p90 {rt.quantile(.9):.1f}; max {rt.max():.1f}")
    w("")
    w("Runtime = last scheduled arrival − first scheduled departure of a trip.")
    w("")

    # ---- 9 ----
    w("## APPROXIMATE RESOURCE METRICS")
    w("")
    vmd = b.diagnostics["vehicle_miles"]
    w(f"- scheduled **revenue vehicle-hours per weekday: "
      f"{_fmt(sysd['revenue_veh_hours'], 1)}** (Σ trip runtimes; excludes "
      f"layover, deadhead and pull-out/pull-in)")
    w(f"- scheduled **revenue vehicle-miles per weekday: "
      f"{_fmt(sysd['veh_miles_scheduled'], 0)}**")
    w(f"- peak simultaneously-running scheduled trips: "
      f"**{sysd['peak_concurrent_buses']}** (schedule sweep)")
    w("")
    w("Peak by period (schedule sweep — note these are peaks *within* a window, "
      "so early-morning and owl values are dominated by the boundary with the "
      "adjacent peak):")
    w("")
    w("| period | peak concurrent trips |")
    w("|---|---|")
    for p, n in sysd["peak_by_period"].items():
        w(f"| {p} | {n} |")
    w("")
    w("**Vehicle-mile method check.** `stop_times.shape_dist_traveled` is "
      f"{vmd.get('sdt_units', 'UNKNOWN')} in this feed — GTFS does not fix the "
      "unit, so it was inferred by comparison against the projected shape "
      f"geometry. The two independent methods agree to "
      f"{vmd.get('agreement_pct', float('nan')):.2f}% "
      f"({_fmt(vmd.get('from_shape_dist_traveled_converted_miles', float('nan')), 0)} "
      f"vs {_fmt(vmd['from_shape_geometry_miles'], 0)} miles).")
    w("")
    w("**These are not COTA's reported operating statistics.** Actual fleet "
      "requirement additionally depends on layover/recovery, deadhead, "
      "interlining across routes (GTFS `block_id` is present but not yet "
      "exploited), run-cutting and maintenance spare ratio — none of which are "
      "known here.")
    w("")

    # ---- 10 ----
    w("## AVAILABLE EXTERNAL DEMAND DATA")
    w("")
    if b.demand.get("status") == "PROXY":
        dm = b.demand
        w(f"- LEHD LODES8 (2022) RAC + WAC, Central Ohio counties: "
          f"**{_fmt(dm['total_workers'], 0)} workers** by residence and "
          f"**{_fmt(dm['total_jobs'], 0)} jobs** by workplace across "
          f"{dm['n_block_groups']:,} block groups")
        w(f"- 2020 Census population-weighted block-group centroids (Ohio)")
        w(f"- within {dm['catchment_radius_m']:.0f} m of a served COTA stop: "
          f"**{_fmt(dm['workers_within_catchment'], 0)} workers "
          f"({dm['workers_within_catchment']/dm['total_workers']*100:.1f}%)** and "
          f"**{_fmt(dm['jobs_within_catchment'], 0)} jobs "
          f"({dm['jobs_within_catchment']/dm['total_jobs']*100:.1f}%)**")
        w(f"- stops receiving allocated demand: {dm['n_stops_with_access']:,}")
        w("")
        w("Documented path: Census block home/work flow → block-group "
          "aggregation → population-weighted centroid → distance-decayed "
          "allocation to stops within the catchment → per-route boarding "
          "potential (a stop's mass is split among the routes serving it, so "
          "shared stops are not double-counted) → period split by assumed "
          "shares.")
        w("")
        w("**This is a proxy for relative demand, not observed ridership.** "
          "LODES covers home→work commuting only, is not transit-mode-specific, "
          "and the period split is assumed. It is adequate for ranking where "
          "service is worth more; it is not a ridership forecast.")
    else:
        w("Not built in this run.")
    w("")
    w("ACS variables identified for future use (not yet retrieved): "
      "B01003_001E population; B08301 means of transportation to work "
      "(B08301_010E public transit); B08201/B25044 vehicles available "
      "(zero-car households); B19013_001E median household income; B23025 "
      "employment status; B18101/S1810 disability. No normative demographic "
      "weighting is embedded in the optimization.")
    w("")

    # ---- 11 ----
    w("## AVAILABLE TRAFFIC DATA")
    w("")
    w("| source | status |")
    w("|---|---|")
    w("| MORPC regional traffic counts | UNKNOWN — portal not reachable from "
      "this sandbox; no authoritative direct URL confirmed |")
    w("| ODOT TDMS / traffic monitoring | UNKNOWN — same |")
    w("| COTA GTFS-Realtime (vehicle positions, trip updates, alerts) | URLs "
      "confirmed on cota.com/data; not collected (egress blocked) |")
    w("")
    w("Traffic-count data is not required for Experiment 1 (frequency "
      "reallocation on fixed geometry with scheduled runtimes). It becomes "
      "necessary when segment runtimes are made congestion-responsive.")
    w("")

    # ---- 12 ----
    w("## MISSING DATA")
    w("")
    w("| variable | classification | note |")
    w("|---|---|---|")
    for name, cls, note in DATA_GAPS:
        w(f"| {name} | **{cls}** | {note} |")
    w("")

    # ---- 13 ----
    w("## KNOWN ASSUMPTIONS")
    w("")
    a = b.assumptions
    w("| assumption | value | basis |")
    w("|---|---|---|")
    w(f"| projected CRS | {a['crs']['projected']} | UTM 17N, metres; all planar "
      "distance math |")
    w(f"| service periods | {a['service_periods']} | analyst-defined |")
    w(f"| layover/recovery ratio | {a['operations']['layover_ratio']:.0%} | "
      "industry-typical 10–20%; **not a verified COTA work rule** |")
    w(f"| random-arrival headway threshold | "
      f"{a['waiting']['random_arrival_threshold_min']} min | standard practice |")
    w(f"| demand retention at long headways | floor "
      f"{a['waiting']['retention_floor']:.0%} at "
      f"{a['waiting']['retention_zero_min']:.0f} min | assumed elasticity, "
      "**uncalibrated** |")
    w(f"| avg passenger ride fraction of route | "
      f"{a['passenger']['avg_ride_fraction']:.0%} | typical US bus; "
      "**unverified for COTA** |")
    w(f"| transfer rate | {a['passenger']['transfer_rate']:.0%} | typical "
      "mid-size bus system; **COTA's observed rate is UNKNOWN** |")
    w(f"| bus planning capacity | {a['crowding']['bus_capacity']} | 40-ft "
      "seated+standing |")
    w(f"| demand catchment radius | {a['demand_proxy']['catchment_radius_m']:.0f} m "
      "| ~5 min walk; assumed |")
    w(f"| period demand shares | {a['demand_proxy']['period_shares']} | assumed "
      "weekday profile, **not COTA-observed** |")
    w("")
    w("Cost weights (equivalent in-vehicle minutes) are in "
      "`config/cost_weights.yaml`.")
    w("")

    # ---- 14 ----
    w("## NEXT RESEARCH STEPS")
    w("")
    for i, s in enumerate([
        "Retrieve the NTD agency profile for COTA and reconcile scheduled "
        "vehicle-hours/miles against reported actuals; this is the single "
        "highest-value validation available without a records request.",
        "Stand up sustained GTFS-Realtime collection to build empirical "
        "segment runtime distributions; this converts the reliability cost "
        "term from a placeholder into a measured quantity and reveals where "
        "schedule padding is mis-allocated.",
        "File a public records request for stop-level and trip-level APC "
        "boardings; this replaces the LODES proxy with observed demand and is "
        "the precondition for claiming a real COTA optimization result.",
        "Exploit GTFS `block_id` to reconstruct vehicle blocks, giving a true "
        "peak-vehicle count including interlining and layover rather than the "
        "continuous cycle/headway approximation.",
        "Implement RAPTOR or CSA over the existing network abstraction so "
        "passenger cost is computed on actual OD paths rather than route-level "
        "aggregates; this is what makes transfer timing optimizable.",
        "Add ACS zero-car-household and transit-commute variables as reporting "
        "dimensions (equity impact of any plan), kept strictly out of the "
        "objective function.",
    ], 1):
        w(f"{i}. {s}")
    w("")

    if exp_metrics:
        w("## EXPERIMENT 1 RESULT (summary)")
        w("")
        w("See `outputs/experiments/` for the full record. Headline: a "
          "frequency redistribution inside the same scheduled vehicle-hour and "
          "peak-vehicle envelope, evaluated against the **LODES-derived proxy "
          "demand**, not observed ridership.")
        w("")

    md = "\n".join(L)
    paths: dict[str, Path] = {}
    p = d / "baseline_report.md"
    p.write_text(md)
    paths["markdown"] = p

    src_tab.to_csv(d / "tables_data_sources.csv", index=False)
    hp.to_csv(d / "tables_frequency_by_period.csv", index=False)
    b.routes.to_csv(d / "tables_route_summary.csv", index=False)
    pd.DataFrame(DATA_GAPS, columns=["variable", "classification", "note"]) \
        .to_csv(d / "tables_data_gaps.csv", index=False)
    (d / "baseline_metrics.json").write_text(json.dumps({
        "generated_at": now,
        "feed_version": _feed_version(b),
        "service_date": b.service_date,
        "n_typical_days": b.n_typical_days,
        "system": sysd,
        "validation": {"n_errors": b.validation["n_errors"],
                       "n_warnings": b.validation["n_warnings"]},
        "diagnostics": b.diagnostics,
        "demand": {k: v for k, v in b.demand.items() if not hasattr(v, "shape")},
        "runtime_min": {"mean": float(b.tstats["runtime_min"].mean()),
                        "median": float(b.tstats["runtime_min"].median())},
        "stop_spacing_m": {"median": float(b.stop_spacing["mean_spacing_m"].median())},
    }, indent=2, default=str))
    paths["metrics"] = d / "baseline_metrics.json"
    return paths


def _feed_version(b: Baseline) -> str:
    fi = b.feed.source_dir / "feed_info.txt"
    if fi.exists():
        df = pd.read_csv(fi)
        if "feed_version" in df.columns and len(df):
            return str(df["feed_version"].iloc[0])
    return "UNKNOWN"
