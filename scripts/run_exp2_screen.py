#!/usr/bin/env python3
"""Experiment 2, screening tier: which geometry edits are worth paying to evaluate?

Every candidate is priced with full RAPTOR on the edited network at headways
scaled so it spends exactly today's vehicle-hours. Frequency is *not*
reallocated, so these numbers rank candidates; they do not measure them. The
ranking exists to decide which handful earn a path-set enumeration and a real
frequency re-optimization.

Checkpointed per candidate, so it resumes rather than restarts.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from cota_opt import geo
from cota_opt.cache import ResultStore
from cota_opt.candidates import (candidate_frame, generate_all, stop_context)
from cota_opt.configs import load_cost_weights, service_periods
from cota_opt.cost import CostWeights
from cota_opt.exp3 import Screener, screen_frame
from cota_opt.experiment import Experiment
from cota_opt.geometry import SegmentTimeModel
from cota_opt.harness import build_harness

log = logging.getLogger("exp2screen")
OUT = ROOT / "outputs"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-kind", type=int, default=12)
    ap.add_argument("--origin-sample", type=int, default=300,
                    help="0 = every origin zone (slow)")
    ap.add_argument("--periods", type=str, default="am_peak,midday")
    ap.add_argument("--seed", type=int, default=20260825)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    exp = Experiment(name="exp2_geometry_screen", seed=args.seed,
                     algorithm="RAPTOR pricing at budget-matched headways",
                     config_files=["assumptions.yaml", "cost_weights.yaml",
                                   "constraints.yaml", "sources.yaml"])
    log.info("experiment %s", exp.experiment_id)
    store = ResultStore(OUT / "exp2_screen.jsonl")

    t0 = time.time()
    H = build_harness(seed=args.seed)
    b, a = H.baseline, H.assumptions
    sg = geo.stops_gdf(b.feed, a["crs"]["projected"])
    model = SegmentTimeModel.fit(b.network, sg)
    d = model.diagnostics
    log.info("running-time model: %d observed links, MAE median %.1fs, "
             "MAPE(>=30s) median %.1f%%", len(model.observed_links),
             d["mae_sec"].median(), d["mape_pct"].median())

    express = {r for r, c in H.classes.items() if c.klass == "peak_express"}
    log.info("excluding %d peak-express routes from geometry edits", len(express))

    zone_flow = np.zeros(H.zones.n)
    np.add.at(zone_flow, H.od.origin, H.od.flow)
    np.add.at(zone_flow, H.od.dest, H.od.flow)
    ctx = stop_context(b.network, H.zones, H.raptor.stop_ids, model)
    trips_by_route = b.tstats.groupby("route_id").size().to_dict()
    cands = generate_all(b.network, ctx, H.zones, H.raptor.stop_ids, zone_flow,
                         trips_by_route, exclude_routes=express,
                         per_kind=args.per_kind)
    cf = candidate_frame(cands)
    cf.to_csv(exp.artifact_path("candidates.csv"), index=False)
    cf.to_csv(OUT / "exp2_candidates.csv", index=False)

    w = CostWeights.from_config(load_cost_weights())
    wk = dict(
        random_arrival_threshold_min=float(a["waiting"]["random_arrival_threshold_min"]),
        schedule_coefficient=float(a["waiting"]["schedule_coefficient"]))
    budget_vh = float(b.tstats["runtime_min"].sum() / 60.0)

    sc = Screener(feed=b.feed, stops_projected=sg, assumptions=a, weights=w,
                  wait_kwargs=wk, od=H.od, bg_frame=b.demand["bg_frame"],
                  budget_vh=budget_vh, periods=service_periods(a),
                  screen_periods=tuple(args.periods.split(",")),
                  origin_sample=args.origin_sample,
                  max_rounds=int(a["path_assignment"]["max_rounds"]))
    log.info("budget %.1f revenue veh-hours; screening on %d origin zones, "
             "periods %s", budget_vh, len(sc.choose_origins()), sc.screen_periods)

    if store.has("baseline"):
        rec = store.get("baseline")
        base = (rec["gc"], rec["unserved"], rec["served"])
        log.info("baseline screen resumed: gc=%.6e unserved=%.0f",
                 base[0], base[1])
    else:
        t = time.time()
        gc, uns, srv, k = sc.price(b.network, b.tstats, label="baseline")
        base = (gc, uns, srv)
        store.put("baseline", {"gc": gc, "unserved": uns, "served": srv,
                               "headway_scale": k, "veh_hours": budget_vh,
                               "seconds": time.time() - t})
        # the unedited network at its own headways must need no rescaling
        assert abs(k - 1.0) < 1e-9, f"baseline headway scale {k} should be 1"

    results = []
    for i, e in enumerate(cands):
        cell = f"screen|{e.key}"
        if store.has(cell):
            rec = store.get(cell)
            results.append(_from_record(rec))
            continue
        r = sc.screen(b.network, b.tstats, model, [e], base,
                      key=e.key, kind=e.kind, description=e.description)
        store.put(cell, _to_record(r))
        results.append(r)
        log.info("[%2d/%d] %-11s %-26s gc %+7.3f%% unserved %+7.3f%%  (%.0fs)",
                 i + 1, len(cands), e.kind, e.route_id, r.gc_change_pct,
                 r.unserved_change_pct, r.seconds)

    df = screen_frame(results)
    df.to_csv(exp.artifact_path("screen.csv"), index=False)
    df.to_csv(OUT / "exp2_screen.csv", index=False)
    exp.log_metrics(budget_vh=budget_vh, n_candidates=len(cands),
                    origin_sample=len(sc.choose_origins()),
                    screen_periods=list(sc.screen_periods),
                    excluded_routes=sorted(express),
                    running_time_model={
                        "observed_links": len(model.observed_links),
                        "mae_sec_median": float(d["mae_sec"].median()),
                        "mape_pct_median": float(d["mape_pct"].median())},
                    total_seconds=time.time() - t0)
    exp.save()

    pd.set_option("display.width", 220)
    pd.set_option("display.max_colwidth", 95)
    print("\n" + "=" * 110)
    print("EXPERIMENT 2 SCREEN — geometry at equal vehicle-hours, frequency NOT "
          "reallocated")
    print("These rank candidates. They do not measure them.")
    print("=" * 110)
    cols = ["kind", "gc_change_pct", "unserved_change_pct", "veh_hours_freed",
            "modelled_share_pct", "description"]
    print(df[cols].head(20).round(3).to_string(index=False))
    bad = df[df["error"].notna()]
    if len(bad):
        print(f"\n{len(bad)} candidates could not be applied:")
        print(bad[["key", "error"]].to_string(index=False))
    print(f"\nartifacts: {exp.dir}")
    return 0


def _to_record(r) -> dict:
    return {"kind": r.kind, "description": r.description,
            "gc": r.generalized_cost, "unserved": r.unserved_flow,
            "served": r.served_flow, "gc_change_pct": r.gc_change_pct,
            "unserved_change_pct": r.unserved_change_pct,
            "headway_scale": r.headway_scale,
            "veh_hours_at_baseline": r.veh_hours_at_baseline,
            "edit_report": r.edit_report, "seconds": r.seconds,
            "error": r.error}


def _from_record(rec: dict):
    from cota_opt.exp3 import ScreenResult
    return ScreenResult(
        key=rec["cell"].split("|", 1)[-1], kind=rec["kind"],
        description=rec["description"], generalized_cost=rec["gc"],
        unserved_flow=rec["unserved"], served_flow=rec["served"],
        gc_change_pct=rec["gc_change_pct"],
        unserved_change_pct=rec["unserved_change_pct"],
        headway_scale=rec["headway_scale"],
        veh_hours_at_baseline=rec["veh_hours_at_baseline"],
        edit_report=rec.get("edit_report", {}), seconds=rec["seconds"],
        error=rec.get("error"))


if __name__ == "__main__":
    raise SystemExit(main())
