#!/usr/bin/env python3
"""Experiment 3 infrastructure: describe the stop network, price a stop.

Descriptive only. Nothing here is an Experiment 3 result, and none of these
numbers is an accessibility uplift -- Experiment 3's benchmark is the finalized
Experiment 2 frontier, which does not exist yet.

The one substantive question it answers now is whether COTA's own schedule can
price a stop. If it can, Experiment 3 rests on measurement; if it cannot, every
consolidation result would inherit whatever dwell figure was assumed, and that
has to be known before the experiment is designed rather than after.

One harness load, light table work after it. Runs at nice 19 and waits for
memory, because the authoritative Experiment 1 job has priority.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from cota_opt import geo
from cota_opt.configs import period_of_seconds, service_periods
from cota_opt.experiment import Experiment
from cota_opt.harness import build_harness
from cota_opt.stopevidence import estimate, find_comparisons, validate, verdict
from cota_opt.stops import along_route_distances, audit, spacing_summary, summary

log = logging.getLogger("exp3audit")
OUT = ROOT / "outputs"


def wait_for_memory(min_free_mb: int = 1800, tries: int = 40) -> None:
    for _ in range(tries):
        try:
            free = int([l for l in Path("/proc/meminfo").read_text().splitlines()
                        if l.startswith("MemAvailable")][0].split()[1]) // 1024
        except Exception:
            return
        if free >= min_free_mb:
            return
        log.warning("only %d MB available, waiting", free)
        time.sleep(30)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-segment-sec", type=float, default=120.0)
    ap.add_argument("--seed", type=int, default=20260825)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    wait_for_memory()

    exp = Experiment(
        name="exp3_stop_audit", seed=args.seed,
        algorithm="descriptive stop audit; scheduled stop-service penalty from "
                  "same-route stop-skipping natural experiments",
        config_files=["assumptions.yaml", "sources.yaml"])
    log.info("experiment %s", exp.experiment_id)

    # descriptive work only: no path sets, so this neither pays for an
    # enumeration nor contends with the authoritative run for a core
    H = build_harness(seed=args.seed, with_pathsets=False)
    b, a = H.baseline, H.assumptions
    sg = geo.stops_gdf(b.feed, a["crs"]["projected"])
    coords = {r.stop_id: (float(r.geometry.x), float(r.geometry.y))
              for r in sg.itertuples()}
    names = dict(zip(b.feed.stops["stop_id"],
                     b.feed.stops.get("stop_name", b.feed.stops["stop_id"])))
    lonlat = {r.stop_id: (float(r.stop_lon), float(r.stop_lat))
              for r in b.feed.stops.itertuples()
              if pd.notna(r.stop_lon) and pd.notna(r.stop_lat)}
    periods = service_periods(a)

    # COTA's shape_dist_traveled is in kilometres -- a unit error caught earlier
    # by comparing against projected geometry. Reuse that finding rather than
    # re-deriving it, and fall back to straight-line if the diagnostic is absent.
    units = (b.diagnostics.get("vehicle_miles", {}) or {}).get("sdt_units")
    sdt_to_m = {"kilometers": 1000.0, "miles": 1609.344,
                "meters": 1.0}.get(units)
    log.info("shape_dist_traveled units: %s (x%s to metres)", units, sdt_to_m)

    zone_flow = np.zeros(H.zones.n)
    np.add.at(zone_flow, H.od.origin, H.od.flow)
    np.add.at(zone_flow, H.od.dest, H.od.flow)

    # ---- spacing and the audit ----------------------------------------
    spacing = along_route_distances(b.feed, b.tstats, b.network, coords, sdt_to_m)
    spacing.to_csv(exp.artifact_path("stop_spacing.csv"), index=False)
    by_route = spacing_summary(spacing)
    by_route.to_csv(exp.artifact_path("spacing_by_route.csv"), index=False)
    by_route.to_csv(OUT / "exp3_spacing_by_route.csv", index=False)

    stops, cat = audit(H.raptor, b.network, b.tstats, H.zones, zone_flow,
                       spacing, periods, names, lonlat)
    stops.to_csv(exp.artifact_path("stop_audit.csv"), index=False)
    stops.to_csv(OUT / "exp3_stop_audit.csv", index=False)
    s = summary(stops, spacing)

    # ---- can the schedule price a stop? -------------------------------
    ts = b.tstats.copy()
    ts["period"] = ts["first_dep_sec"].map(lambda x: period_of_seconds(x, periods))
    pop = (ts.dropna(subset=["period"]).groupby("pattern_id")["period"]
           .apply(set).to_dict())
    comps = find_comparisons(b.network, b.tstats, pop,
                             min_segment_sec=args.min_segment_sec)
    pen = estimate(comps)
    val = validate(comps)
    label, why = verdict(pen.summary, val)
    if not comps.empty:
        comps.to_csv(exp.artifact_path("stop_skip_comparisons.csv"), index=False)
        comps.to_csv(OUT / "exp3_stop_comparisons.csv", index=False)
        pen.by_route.to_csv(exp.artifact_path("penalty_by_route.csv"), index=False)

    out = {"stop_audit": s, "stop_penalty": pen.summary,
           "penalty_validation": val, "penalty_verdict": label,
           "penalty_explanation": why,
           "distance_basis": {"along_route": sdt_to_m and units or "straight_line",
                              "walking": "router footpaths: straight-line within "
                                         "radius plus transfers.txt, NO "
                                         "pedestrian network and NO barriers"}}
    (OUT / "exp3_audit.json").write_text(json.dumps(out, indent=2, default=str))
    exp.log_metrics(**out)
    exp.save()

    pd.set_option("display.width", 200)
    print("\n" + "=" * 92)
    print("EXPERIMENT 3 INFRASTRUCTURE — descriptive only, not a result")
    print("=" * 92)
    print("\nSTOP NETWORK")
    for k, v in s.items():
        print(f"  {k:34s} {v:,.4f}" if isinstance(v, float) else f"  {k:34s} {v}")
    print("\nSPACING BY ROUTE (tightest 10)")
    print(by_route.head(10).round(1).to_string(index=False))
    print("\nCAN COTA'S SCHEDULE PRICE A STOP?")
    for k, v in pen.summary.items():
        if k == "interpretation":
            continue
        print(f"  {k:34s} {v:,.4f}" if isinstance(v, float) else f"  {k:34s} {v}")
    if val.get("n_folds"):
        print("\n  held out by route:")
        for k, v in val.items():
            if k == "exploitable_direction":
                continue
            print(f"    {k:32s} {v:,.4f}" if isinstance(v, float)
                  else f"    {k:32s} {v}")
    print(f"\n  VERDICT: {label.upper()} — {why}")
    if not pen.by_route.empty:
        print("\n  penalty by route (most comparisons first):")
        print(pen.by_route.head(10).round(1).to_string(index=False))
    print(f"\nartifacts: {exp.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
