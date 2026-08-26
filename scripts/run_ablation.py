#!/usr/bin/env python3
"""Ablation: which of the three Experiment 1 model gaps was doing the damage?

Configurations, each solved under the identical resource envelope:

  A  path       route geometry fixed, RAPTOR path assignment on real LODES OD
                — fixes gap 1 (passengers can now re-route)
  B  path+class + peak-only express routes locked at their designed timetable
                — fixes gap 3 (a 180-min "headway" is a timetable, not neglect)
  C  path+class+crowd
                + crowding priced at each route-period's peak load point
                — fixes gap 2 (crowding now binds on trunk routes)

The expensive part (RAPTOR path enumeration over six periods) is built once and
shared, so the three configurations differ only in the model, not the data.
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
from cota_opt.baseline import CENTRAL_OHIO_FIPS, build_baseline
from cota_opt.configs import (load_constraints, load_cost_weights,
                              period_of_seconds, service_periods)
from cota_opt.cost import CostWeights
from cota_opt.exp2 import build_setup, plan_diff
from cota_opt.experiment import Experiment
from cota_opt.frequency import optimize_frequencies, pareto_filter
from cota_opt.odmatrix import (_top_k, build_zone_system, filter_to_accessible,
                               from_lodes_od, scale_to)
from cota_opt.raptor import build_raptor_network
from cota_opt.registry import Registry
from cota_opt.routeclass import classify_routes, summary_frame

log = logging.getLogger("ablation")

UPLOADS = Path("/mnt/user-data/uploads/Downloads")
DEMAND_FILES = {"rac": UPLOADS / "oh_rac_S000_JT00_2022.csv.gz",
                "wac": UPLOADS / "oh_wac_S000_JT00_2022.csv.gz",
                "centroids": UPLOADS / "CenPop2020_Mean_BG39.txt"}


def band_of(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["band"] = pd.cut(d["baseline_headway_min"], [0, 15, 30, 60, 120, 1e9],
                       labels=["<=15", "16-30", "31-60", "61-120", ">120"])
    return (d.groupby("band", observed=True)
            .agg(n=("route_id", "size"),
                 mean_headway_change=("headway_change_min", "mean"),
                 veh_hours_change=("veh_hours_change", "sum")).reset_index())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=60_000)
    ap.add_argument("--restarts", type=int, default=1)
    ap.add_argument("--width", type=int, default=28)
    ap.add_argument("--lambdas", type=str, default="0.5,1,2,4")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    seed = 20260825
    multipliers = [float(x) for x in args.lambdas.split(",")]

    exp = Experiment(name="exp3_ablation", seed=seed,
                     algorithm="RAPTOR path sets + marginal-exchange search",
                     config_files=["assumptions.yaml", "cost_weights.yaml",
                                   "constraints.yaml", "sources.yaml"])
    log.info("experiment %s", exp.experiment_id)

    t0 = time.time()
    b = build_baseline(demand_files=DEMAND_FILES, write=False)
    a = b.assumptions
    pa = a["path_assignment"]
    periods = service_periods(a)
    sg = geo.stops_gdf(b.feed, a["crs"]["projected"])
    rn = build_raptor_network(b.feed, b.network, b.tstats, sg,
                              walk_radius_m=float(pa["walk_radius_m"]),
                              walk_speed_m_per_min=float(pa["walk_speed_m_per_min"]),
                              periods=periods, with_timetable=False)
    zs = build_zone_system(b.demand["bg_frame"], sg,
                           radius_m=float(pa["access_radius_m"]),
                           walk_speed_m_per_min=float(pa["walk_speed_m_per_min"]),
                           stop_index=rn.stop_index)
    reg = Registry()
    od_all = from_lodes_od(reg.path_for("lodes_od_oh"), zs,
                           county_fips=CENTRAL_OHIO_FIPS)
    od_acc = filter_to_accessible(od_all, zs)
    od = _top_k(od_acc, int(pa["od_top_k"]))
    coverage = {"commute_flow_total": od_all.total(),
                "accessible_share": od_acc.total() / od_all.total(),
                "top_k_share_of_accessible": od.total() / od_acc.total()}
    od = scale_to(od, float(a["demand_proxy"]["assumed_weekday_linked_trips"]))

    # route classification from observed service patterns
    ts = b.tstats.copy()
    ts["period"] = ts["first_dep_sec"].map(lambda s: period_of_seconds(s, periods))
    ts = ts.dropna(subset=["period"])
    classes = classify_routes(ts, b.feed.routes)
    cls_df = summary_frame(classes)
    cls_df.to_csv(exp.artifact_path("route_classes.csv"), index=False)
    log.info("route classes: %s", cls_df["class"].value_counts().to_dict())

    configs = [
        ("A path", dict(with_crowding=False, lock_classes=())),
        ("B path+class", dict(with_crowding=False, lock_classes=("peak_express",))),
        ("C path+class+crowd", dict(with_crowding=True,
                                    lock_classes=("peak_express",))),
    ]

    all_rows, band_rows, detail_out = [], [], {}
    pathset_cache: dict = {}
    for name, kw in configs:
        log.info("=== configuration %s ===", name)
        setup = build_setup(b, rn, zs, od, seed=seed, route_classes=classes,
                            pathset_cache=pathset_cache, **kw)
        bf = setup.model.evaluate(setup.baseline_plan)
        log.info("%s baseline: gc=%.6e unserved=%.0f served=%.0f",
                 name, bf.generalized_cost, bf.unserved_demand, bf.served_demand)
        detail_out[name] = {"checks": setup.checks,
                            "baseline": setup.model.detail(setup.baseline_plan)}
        results = []
        for m in multipliers:
            t = time.time()
            r = optimize_frequencies(
                setup.model, setup.budget, ladder=[], unserved_multiplier=m,
                local_search_iterations=args.iterations, seed=seed,
                ladders=setup.ladders, initial=setup.baseline_plan,
                n_restarts=args.restarts, candidate_width=args.width,
                greedy_start=False)
            gc_pct = (r.fitness.generalized_cost / bf.generalized_cost - 1) * 100
            un_pct = (r.fitness.unserved_demand / bf.unserved_demand - 1) * 100
            log.info("  %s lambda=%-4s %4.0fs gc %+7.2f%% unserved %+7.2f%% vh=%.1f",
                     name, m, time.time() - t, gc_pct, un_pct,
                     r.fitness.revenue_veh_hours)
            results.append(r)
            all_rows.append({
                "config": name, "lambda": m,
                "gc_change_pct": gc_pct, "unserved_change_pct": un_pct,
                "gc_per_trip_change_pct": (r.fitness.gc_per_served_trip
                                           / bf.gc_per_served_trip - 1) * 100,
                "served_change_pct": (r.fitness.served_demand
                                      / bf.served_demand - 1) * 100,
                "revenue_veh_hours": r.fitness.revenue_veh_hours,
                "vh_vs_budget_pct": (r.fitness.revenue_veh_hours
                                     / setup.budget.revenue_veh_hours - 1) * 100})
        front = pareto_filter(results)
        for r in front:
            all_rows[[i for i, x in enumerate(all_rows)
                      if x["config"] == name
                      and x["lambda"] == r.meta["unserved_multiplier"]][0]
                     ]["on_pareto_front"] = True
        balanced = min(front, key=lambda r: abs(r.meta["unserved_multiplier"] - 1.0))
        diff = plan_diff(setup, balanced.plan)
        diff.to_csv(exp.artifact_path(
            f"plan_diff_{name.split()[0]}.csv"), index=False)
        bt = band_of(diff)
        bt.insert(0, "config", name)
        band_rows.append(bt)
        detail_out[name]["balanced"] = setup.model.detail(balanced.plan)
        detail_out[name]["balanced_lambda"] = balanced.meta["unserved_multiplier"]
        # what happens to the trunk route that Experiment 1 gutted
        r10 = diff[diff["route_id"] == "010"][
            ["period", "baseline_headway_min", "optimized_headway_min"]]
        detail_out[name]["route_010"] = r10.to_dict(orient="records")
        log.info("  route 010 under %s:\n%s", name, r10.round(1).to_string(index=False))

    tab = pd.DataFrame(all_rows)
    tab["on_pareto_front"] = tab.get("on_pareto_front", False)
    tab["on_pareto_front"] = tab["on_pareto_front"].fillna(False)
    tab.to_csv(exp.artifact_path("ablation_frontier.csv"), index=False)
    bands = pd.concat(band_rows, ignore_index=True)
    bands.to_csv(exp.artifact_path("ablation_bands.csv"), index=False)

    exp.log_metrics(coverage=coverage, configs=detail_out,
                    route_class_counts=cls_df["class"].value_counts().to_dict(),
                    setup_seconds=time.time() - t0)
    exp.save()

    print("\n" + "=" * 100)
    print("ABLATION — which Experiment 1 model gap mattered")
    print("=" * 100)
    print(tab.round(2).to_string(index=False))
    print("\nWHERE SERVICE MOVES, by current service level (balanced solution)")
    print(bands.round(2).to_string(index=False))
    print("\nROUTE 010 E BROAD/W BROAD — the route Experiment 1 cut to 60 min")
    for name in detail_out:
        print(f"  {name}: {detail_out[name]['route_010']}")
    print(f"\nartifacts: {exp.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
