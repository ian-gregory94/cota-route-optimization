#!/usr/bin/env python3
"""Build the full Experiment 2 candidate audit table.

Reads the screening checkpoints, re-applies each edit to recover exactly what
it did to the network, and writes one auditable row per candidate: what
changed, what evidence supports it, what it scored, and what a planner would
object to. The screening rank is one column among thirty, which is the point.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from cota_opt import geo
from cota_opt.audit import (PRIMARY_MAX_MODELLED_PCT, audit_row, audit_table,
                            top_routes_by_veh_hours)
from cota_opt.cache import ResultStore
from cota_opt.candidates import generate_all, stop_context
from cota_opt.configs import service_periods
from cota_opt.geometry_eval import baseline_headways
from cota_opt.experiment import Experiment
from cota_opt.geometry import SegmentTimeModel, apply_edits
from cota_opt.harness import build_harness

log = logging.getLogger("audit")
OUT = ROOT / "outputs"


class _Screen:
    def __init__(self, rec):
        self.gc_change_pct = rec.get("gc_change_pct", np.nan)
        self.unserved_change_pct = rec.get("unserved_change_pct", np.nan)
        self.headway_scale = rec.get("headway_scale", np.nan)
        self.error = rec.get("error")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    exp = Experiment(name="exp2_audit", seed=20260825,
                     algorithm="per-candidate network diff and evidence class",
                     config_files=["assumptions.yaml", "sources.yaml"])
    H = build_harness()
    b, a = H.baseline, H.assumptions
    sg = geo.stops_gdf(b.feed, a["crs"]["projected"])
    model = SegmentTimeModel.fit(b.network, sg)
    ctx = stop_context(b.network, H.zones, H.raptor.stop_ids, model)

    zone_flow = np.zeros(H.zones.n)
    np.add.at(zone_flow, H.od.origin, H.od.flow)
    np.add.at(zone_flow, H.od.dest, H.od.flow)
    express = {r for r, c in H.classes.items() if c.klass == "peak_express"}
    trips_by_route = b.tstats.groupby("route_id").size().to_dict()
    cands = generate_all(b.network, ctx, H.zones, H.raptor.stop_ids, zone_flow,
                         trips_by_route, exclude_routes=express, per_kind=12)

    store = ResultStore(OUT / "exp2_screen.jsonl")
    hw, _ = baseline_headways(b.tstats, service_periods(a))
    big = top_routes_by_veh_hours(b.tstats, 10)
    log.info("top-10 routes by vehicle-hours: %s", sorted(big))

    rows = []
    for e in cands:
        rec = store.get(f"screen|{e.key}")
        screen = _Screen(rec) if rec else None
        try:
            ed = apply_edits(b.network, b.tstats, model, [e])
        except Exception as exc:
            log.warning("cannot apply %s: %s", e.key, exc)
            continue
        rows.append(audit_row(e, ed, ctx, b.network, b.tstats, hw, screen, big))

    df = audit_table(rows)
    df.to_csv(exp.artifact_path("audit.csv"), index=False)
    df.to_csv(OUT / "exp2_audit.csv", index=False)
    exp.log_metrics(n_candidates=len(df),
                    primary=int((df["evidence_class"] == "primary").sum()),
                    novel_link=int((df["evidence_class"] == "novel_link").sum()),
                    primary_threshold_pct=PRIMARY_MAX_MODELLED_PCT,
                    screened=int(df["screen_gc_change_pct"].notna().sum()))
    exp.save()

    pd.set_option("display.width", 240)
    print("\n" + "=" * 100)
    print("EXPERIMENT 2 CANDIDATE AUDIT")
    print("=" * 100)
    print(f"{len(df)} candidates; "
          f"{(df['evidence_class'] == 'primary').sum()} primary "
          f"(<= {PRIMARY_MAX_MODELLED_PCT}% modelled links), "
          f"{(df['evidence_class'] == 'novel_link').sum()} novel-link")
    print("\nBY EDIT TYPE AND EVIDENCE CLASS")
    print(pd.crosstab(df["kind"], df["evidence_class"]).to_string())
    print("\nSUPPLY EFFECTS BY EDIT TYPE (before the budget is restored)")
    print(df.groupby("kind").agg(
        n=("candidate_id", "size"),
        runtime_pct=("runtime_change_pct", "median"),
        vh_freed=("veh_hours_freed_raw", "median"),
        stops_net=("stop_count_change", "median"),
        modelled_pct=("modelled_share_pct", "median"),
        demand_net=("unique_demand_net", "median"),
        concerns=("n_concerns", "mean")).round(2).to_string())
    scr = df[df["screen_gc_change_pct"].notna()]
    if len(scr):
        print(f"\nSCREENED SO FAR: {len(scr)}/{len(df)}")
        cols = ["kind", "routes", "evidence_class", "screen_gc_change_pct",
                "screen_unserved_change_pct", "modelled_share_pct",
                "unique_demand_net", "stops_losing_only_service", "n_concerns"]
        print(scr.sort_values("screen_unserved_change_pct")[cols]
              .head(15).round(3).to_string(index=False))
    print(f"\nartifacts: {exp.dir}")
    print(f"full table: {OUT / 'exp2_audit.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
