#!/usr/bin/env python3
"""Run Experiment 2 — frequency redistribution with path-based assignment."""
from __future__ import annotations

import argparse
import json
import logging
import pickle
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from cota_opt import geo
from cota_opt.baseline import CENTRAL_OHIO_FIPS, build_baseline
from cota_opt.configs import load_cost_weights, service_periods
from cota_opt.cost import CostWeights
from cota_opt.exp2 import build_setup, plan_diff
from cota_opt.experiment import Experiment
from cota_opt.frequency import optimize_frequencies, pareto_filter
from cota_opt.odmatrix import (build_zone_system, filter_to_accessible,
                               from_lodes_od, scale_to, _top_k)
from cota_opt.raptor import build_raptor_network
from cota_opt.registry import Registry

log = logging.getLogger("exp2")

UPLOADS = Path("/mnt/user-data/uploads/Downloads")
DEMAND_FILES = {"rac": UPLOADS / "oh_rac_S000_JT00_2022.csv.gz",
                "wac": UPLOADS / "oh_wac_S000_JT00_2022.csv.gz",
                "centroids": UPLOADS / "CenPop2020_Mean_BG39.txt"}
CACHE = Path("/tmp/exp2_setup.pkl")


def prepare(seed: int, rebuild: bool = False):
    b = build_baseline(demand_files=DEMAND_FILES, write=False)
    a = b.assumptions
    pa = a["path_assignment"]
    proj = a["crs"]["projected"]
    periods = service_periods(a)
    sg = geo.stops_gdf(b.feed, proj)
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
    coverage = {
        "commute_flow_total": od_all.total(),
        "accessible_share": od_acc.total() / od_all.total(),
        "top_k_share_of_accessible": od.total() / od_acc.total(),
    }
    od = scale_to(od, float(a["demand_proxy"]["assumed_weekday_linked_trips"]))
    setup = build_setup(b, rn, zs, od, seed=seed)
    return b, rn, zs, od, setup, coverage


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=200_000)
    ap.add_argument("--restarts", type=int, default=3)
    ap.add_argument("--lambdas", type=str, default="0.25,0.5,1,2,4,8")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    seed = 20260825
    multipliers = [float(x) for x in args.lambdas.split(",")]

    exp = Experiment(name="exp2_frequency_pathbased", seed=seed,
                     algorithm="RAPTOR path sets + marginal-exchange search",
                     config_files=["assumptions.yaml", "cost_weights.yaml",
                                   "constraints.yaml", "sources.yaml"])
    log.info("experiment %s", exp.experiment_id)

    t0 = time.time()
    b, rn, zs, od, setup, coverage = prepare(seed)
    log.info("setup built in %.0fs", time.time() - t0)
    log.info("checks: %s", json.dumps(setup.checks, default=str))

    bf = setup.model.evaluate(setup.baseline_plan)
    log.info("baseline: gc=%.6e unserved=%.0f served=%.0f vh=%.2f",
             bf.generalized_cost, bf.unserved_demand, bf.served_demand,
             bf.revenue_veh_hours)
    base_detail = setup.model.detail(setup.baseline_plan)

    results = []
    for m in multipliers:
        t = time.time()
        r = optimize_frequencies(
            setup.model, setup.budget, ladder=[], unserved_multiplier=m,
            local_search_iterations=args.iterations, seed=seed,
            ladders=setup.ladders, initial=setup.baseline_plan,
            n_restarts=args.restarts)
        log.info("lambda=%-5s %5.0fs gc %+.2f%% unserved %+.2f%% vh=%.1f",
                 m, time.time() - t,
                 (r.fitness.generalized_cost / bf.generalized_cost - 1) * 100,
                 (r.fitness.unserved_demand / bf.unserved_demand - 1) * 100,
                 r.fitness.revenue_veh_hours)
        results.append(r)
    front = pareto_filter(results)

    rows = [{"solution": "baseline (COTA scheduled)", "unserved_multiplier": None,
             "generalized_cost": bf.generalized_cost, "gc_change_pct": 0.0,
             "unserved_demand": bf.unserved_demand, "unserved_change_pct": 0.0,
             "served_demand": bf.served_demand,
             "gc_per_served_trip": bf.gc_per_served_trip,
             "revenue_veh_hours": bf.revenue_veh_hours, "on_pareto_front": False}]
    fid = {id(r) for r in front}
    for r in results:
        f = r.fitness
        rows.append({
            "solution": r.label, "unserved_multiplier": r.meta["unserved_multiplier"],
            "generalized_cost": f.generalized_cost,
            "gc_change_pct": (f.generalized_cost / bf.generalized_cost - 1) * 100,
            "unserved_demand": f.unserved_demand,
            "unserved_change_pct": (f.unserved_demand / bf.unserved_demand - 1) * 100,
            "served_demand": f.served_demand,
            "gc_per_served_trip": f.gc_per_served_trip,
            "gc_per_trip_change_pct": (f.gc_per_served_trip / bf.gc_per_served_trip - 1) * 100,
            "revenue_veh_hours": f.revenue_veh_hours,
            "on_pareto_front": id(r) in fid})
    ftab = pd.DataFrame(rows)
    ftab.to_csv(exp.artifact_path("pareto_frontier.csv"), index=False)

    balanced = min(front, key=lambda r: abs(r.meta["unserved_multiplier"] - 1.0))
    diff = plan_diff(setup, balanced.plan)
    diff.to_csv(exp.artifact_path("plan_diff_balanced.csv"), index=False)
    for r in front:
        r.plan.to_frame().to_csv(
            exp.artifact_path(f"plan_{r.label.replace('=', '_')}.csv"), index=False)
    setup.baseline_plan.to_frame().to_csv(
        exp.artifact_path("plan_baseline.csv"), index=False)

    # band table: where service moves, by current service level
    diff["band"] = pd.cut(diff["baseline_headway_min"], [0, 15, 30, 60, 120, 1e9],
                          labels=["<=15", "16-30", "31-60", "61-120", ">120"])
    band = diff.groupby("band", observed=True).agg(
        n=("route_id", "size"), mean_headway_change=("headway_change_min", "mean"),
        veh_hours_change=("veh_hours_change", "sum")).reset_index()
    band.to_csv(exp.artifact_path("band_table.csv"), index=False)

    exp.log_metrics(
        checks=setup.checks, coverage=coverage,
        baseline_detail=base_detail,
        balanced_detail=setup.model.detail(balanced.plan),
        frontier=ftab.to_dict(orient="records"),
        band_table=band.to_dict(orient="records"),
        model_evaluations=setup.model.n_evals,
        period_evaluations=setup.model.n_period_evals,
    )
    exp.save()
    with open(CACHE, "wb") as f:
        pickle.dump({"front": [(r.label, r.plan.headways) for r in front],
                     "baseline": setup.baseline_plan.headways,
                     "exp_dir": str(exp.dir)}, f)

    print("\n" + "=" * 92)
    print("EXPERIMENT 2 — PATH-BASED ASSIGNMENT (real LODES OD, RAPTOR paths)")
    print("=" * 92)
    print(ftab[["solution", "gc_change_pct", "unserved_change_pct",
                "gc_per_trip_change_pct", "revenue_veh_hours", "on_pareto_front"]]
          .round(3).to_string(index=False))
    print("\nWHERE SERVICE MOVES (balanced solution)")
    print(band.round(2).to_string(index=False))
    print(f"\nartifacts: {exp.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
