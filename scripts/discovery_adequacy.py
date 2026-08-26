#!/usr/bin/env python3
"""Gate 11: does per-pattern RAPTOR find the paths Model B would want to use?

Model B fixes valuation, not discovery. RAPTOR still searches with per-pattern
headways, so a route sequence can be cheap under the corrected model while the
search that built the candidate set never had reason to explore it.

Targeted at the corridors where the failure is possible at all -- routes whose
several patterns overlap on the same movement -- and decided by the rule fixed
in ACCEPTANCE.md before this script existed. Nothing here tunes a threshold.

Run this BEFORE freezing the Model B yardstick.
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

from cota_opt.configs import load_cost_weights
from cota_opt.cost import CostWeights
from cota_opt.discovery import classify, high_exposure_od, probe
from cota_opt.experiment import Experiment
from cota_opt.harness import build_harness

log = logging.getLogger("discovery")
OUT = ROOT / "outputs"

#: routes the common-lines diagnostic named as carrying the correction. Fixed
#: here rather than re-derived, so the target set does not drift with the run.
DEFAULT_FOCUS = ("010", "005", "007", "001", "002", "102", "008", "033")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--common-lines", type=str, default="same_route",
                    choices=["pattern", "same_route"])
    ap.add_argument("--periods", type=str, default="am_peak,midday")
    ap.add_argument("--focus", type=str, default=",".join(DEFAULT_FOCUS))
    ap.add_argument("--top-od", type=int, default=4000,
                    help="highest-flow OD pairs per period riding a focus route")
    ap.add_argument("--all-routes", action="store_true",
                    help="drop the targeting and test every OD pair with a path")
    ap.add_argument("--seed", type=int, default=20260825)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    suffix = "" if args.common_lines == "pattern" else "_modelB"
    exp = Experiment(
        name=f"exp7_discovery_adequacy{suffix}", seed=args.seed,
        algorithm="route-level RAPTOR lower bound, then exact Model B pricing "
                  "of the reconstructed journey",
        config_files=["assumptions.yaml", "cost_weights.yaml",
                      "constraints.yaml", "sources.yaml"])
    log.info("experiment %s", exp.experiment_id)

    t0 = time.time()
    H = build_harness(seed=args.seed, common_lines=args.common_lines)
    a = H.assumptions
    pa = a["path_assignment"]
    w = CostWeights.from_config(load_cost_weights())
    wk = dict(
        random_arrival_threshold_min=float(a["waiting"]["random_arrival_threshold_min"]),
        schedule_coefficient=float(a["waiting"]["schedule_coefficient"]))
    setup = H.setup(with_crowding=False, lock_classes=("peak_express",))
    hw = dict(setup.baseline_plan.headways)
    focus = set(args.focus.split(","))
    log.info("waiting model = %s; focus routes = %s", H.common_lines,
             sorted(focus))

    frames, tested_flow, tested_gc = [], 0.0, 0.0
    for per in args.periods.split(","):
        ev = setup.model.evaluators.get(per)
        if ev is None:
            continue
        ps = ev.ps
        sub = np.array([hw[k] for k in ps.rp_keys])
        costs = ev.od_costs(sub)
        if args.all_routes:
            od = np.flatnonzero(np.isfinite(costs))
            if len(od) > args.top_od:
                od = od[np.argsort(-ps.od_flow[od])[:args.top_od]]
            od = np.sort(od)
        else:
            od = high_exposure_od(ps, ev, hw, H.raptor, per, focus,
                                  top_n=args.top_od)
        if len(od) == 0:
            log.info("%-8s no OD pair rides a focus route", per)
            continue
        tested_flow += float(ps.od_flow[od].sum())
        tested_gc += float((ps.od_flow[od] * costs[od]).sum())
        t = time.time()
        rows = probe(H.raptor, H.zones, ps, ev, hw, per, w, wk,
                     int(pa["max_rounds"]), od)
        log.info("%-8s tested %5d OD pairs (%.0f trips) in %4.0fs: "
                 "%d with a cheaper Model B path outside the set",
                 per, len(od), ps.od_flow[od].sum(), time.time() - t, len(rows))
        if not rows.empty:
            frames.append(rows)

    rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    res = classify(rows, tested_flow, tested_gc)
    if not rows.empty:
        rows.to_csv(exp.artifact_path("omitted_paths.csv"), index=False)
        res.by_route.to_csv(exp.artifact_path("by_route.csv"), index=False)
        rows.to_csv(OUT / f"discovery_omitted{suffix}.csv", index=False)

    out = {"common_lines": H.common_lines, "case": res.case,
           "explanation": res.explanation, "summary": res.summary,
           "periods": args.periods.split(","),
           "focus_routes": sorted(focus), "targeted": not args.all_routes,
           "seconds": time.time() - t0}
    (OUT / f"discovery_adequacy{suffix}.json").write_text(
        json.dumps(out, indent=2, default=str))
    exp.log_metrics(**out)
    exp.save()

    pd.set_option("display.width", 220)
    print("\n" + "=" * 96)
    print(f"GATE 11 — MODEL B DISCOVERY ADEQUACY  (waiting model: {H.common_lines})")
    print("=" * 96)
    for k, v in res.summary.items():
        print(f"  {k:34s} {v:,.4f}" if isinstance(v, float)
              else f"  {k:34s} {v}")
    print(f"\n  flow share affected   {100 * res.summary.get('flow_share', 0):.3f}%"
          f"   (negligible < 1.0%, material >= 3.0%)")
    print(f"  cost share affected   {100 * res.summary.get('gc_share', 0):.3f}%"
          f"   (negligible < 0.25%, material >= 1.0%)")
    print(f"\n  CASE {res.case}: {res.explanation}")
    if not res.by_route.empty:
        print("\n  routes carrying the omitted sequences:")
        print(res.by_route.head(10).round(2).to_string(index=False))
    if not rows.empty:
        print("\n  largest single omissions:")
        cols = ["period", "flow", "best_in_set_min", "omitted_path_min",
                "improvement_min", "improvement_pct", "route_sequence",
                "n_boardings", "sequence_already_in_set"]
        print(rows.nlargest(10, "flow_weighted_improvement")[cols]
              .round(2).to_string(index=False))
    print(f"\nartifacts: {exp.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
