#!/usr/bin/env python3
"""Run Experiment 1 — Pareto-optimal weekday frequency redistribution.

Usage:  python scripts/run_exp1.py [--iterations N] [--restarts N]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd
import yaml

from cota_opt.baseline import build_baseline
from cota_opt.configs import load_constraints, load_cost_weights
from cota_opt.cost import CostWeights
from cota_opt.exp1 import build_setup, compare_to_baseline, plan_diff
from cota_opt.experiment import Experiment
from cota_opt.frequency import optimize_frequencies, pareto_filter
from cota_opt.paths import config_dir
from cota_opt.verify import verify_result

log = logging.getLogger("exp1")

UPLOADS = Path("/mnt/user-data/uploads/Downloads")
DEMAND_FILES = {"rac": UPLOADS / "oh_rac_S000_JT00_2022.csv.gz",
                "wac": UPLOADS / "oh_wac_S000_JT00_2022.csv.gz",
                "centroids": UPLOADS / "CenPop2020_Mean_BG39.txt"}


def _rebuild_demand(b, a2):
    """Re-derive the stop→route demand proxy under changed proxy assumptions."""
    from cota_opt.baseline import _build_demand
    return _build_demand(b.feed, b.network, DEMAND_FILES, a2,
                         a2["crs"]["projected"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=400_000)
    ap.add_argument("--restarts", type=int, default=20)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    scen = yaml.safe_load((config_dir() / "scenarios" / "exp1_frequency.yaml")
                          .read_text())["experiment"]
    seed = int(scen["seed"])
    multipliers = [float(m) for m in scen["pareto"]["unserved_weight_multipliers"]]

    exp = Experiment(name=scen["name"], seed=seed, algorithm=scen["algorithm"],
                     config_files=["assumptions.yaml", "cost_weights.yaml",
                                   "constraints.yaml", "sources.yaml",
                                   "scenarios/exp1_frequency.yaml"])
    log.info("experiment %s", exp.experiment_id)

    b = build_baseline(demand_files=DEMAND_FILES, write=True)
    setup = build_setup(b)
    bf = setup.model.evaluate(setup.baseline_plan)
    log.info("baseline: gc=%.6e unserved=%.0f vh=%.2f",
             bf.generalized_cost, bf.unserved_demand, bf.revenue_veh_hours)

    # --- sweep -----------------------------------------------------------
    results = []
    for m in multipliers:
        r = optimize_frequencies(
            setup.model, setup.budget, ladder=[], unserved_multiplier=m,
            local_search_iterations=args.iterations, seed=seed,
            ladders=setup.ladders, initial=setup.baseline_plan,
            n_restarts=args.restarts)
        results.append(r)
    front = pareto_filter(results)
    log.info("%d solutions, %d on the frontier", len(results), len(front))

    # --- frontier table --------------------------------------------------
    rows = [{"solution": "baseline (COTA scheduled)",
             "unserved_multiplier": None,
             "generalized_cost": bf.generalized_cost,
             "gc_change_pct": 0.0,
             "unserved_demand": bf.unserved_demand,
             "unserved_change_pct": 0.0,
             "served_demand": bf.served_demand,
             "mean_wait_min": bf.mean_wait_min,
             "gc_per_served_trip": bf.gc_per_served_trip,
             "revenue_veh_hours": bf.revenue_veh_hours,
             "on_pareto_front": False}]
    front_ids = {id(r) for r in front}
    for r in results:
        c = compare_to_baseline(setup, r)
        rows.append({"solution": r.label, "unserved_multiplier": r.meta["unserved_multiplier"],
                     "generalized_cost": c["generalized_cost"],
                     "gc_change_pct": c["gc_change_pct"],
                     "unserved_demand": c["unserved_demand"],
                     "unserved_change_pct": c["unserved_change_pct"],
                     "served_demand": c["served_demand"],
                     "mean_wait_min": c["mean_wait_min"],
                     "gc_per_served_trip": c["gc_per_served_trip"],
                     "revenue_veh_hours": c["revenue_veh_hours"],
                     "on_pareto_front": id(r) in front_ids})
    ftab = pd.DataFrame(rows)
    ftab.to_csv(exp.artifact_path("pareto_frontier.csv"), index=False)

    # --- verification of every solution ----------------------------------
    ver = {}
    for r in results:
        ver[r.label] = verify_result(setup.model, r.plan, setup.budget, setup.ladders)
    ver["baseline"] = verify_result(setup.model, setup.baseline_plan,
                                    setup.budget, setup.ladders)
    all_ok = all(v["vectorized_matches_scalar"] and v["within_veh_hour_budget"]
                 and v["within_peak_budget"] and v["all_headways_on_ladder"]
                 and v["minimum_service_preserved"] for v in ver.values())
    (exp.artifact_path("verification.json")).write_text(
        json.dumps(ver, indent=2, default=str))
    log.info("verification: all checks pass = %s", all_ok)

    # --- seed stability --------------------------------------------------
    stability = []
    for sd in (seed, seed + 1, seed + 2, seed + 3):
        r = optimize_frequencies(
            setup.model, setup.budget, ladder=[], unserved_multiplier=1.0,
            local_search_iterations=args.iterations, seed=sd,
            ladders=setup.ladders, initial=setup.baseline_plan,
            n_restarts=args.restarts)
        stability.append({"seed": sd,
                          "gc_change_pct": (r.fitness.generalized_cost / bf.generalized_cost - 1) * 100,
                          "unserved_change_pct": (r.fitness.unserved_demand / bf.unserved_demand - 1) * 100})
    stab = pd.DataFrame(stability)
    stab.to_csv(exp.artifact_path("seed_stability.csv"), index=False)
    log.info("seed stability (gc %%): mean %.2f sd %.2f",
             stab["gc_change_pct"].mean(), stab["gc_change_pct"].std())

    # --- assumption sensitivity -----------------------------------------
    sens = []
    base_w = load_cost_weights()
    variants = {
        "baseline assumptions": ({}, {}),
        "wait weight 1.5x": ({"waiting": base_w["waiting"] * 1.5}, {}),
        "wait weight 0.67x": ({"waiting": base_w["waiting"] * 0.67}, {}),
        "transfer penalty 0": ({"transfer_penalty": 0.0}, {}),
        "retention floor 0.10": ({}, {"retention_floor": 0.10}),
        "retention floor 0.50": ({}, {"retention_floor": 0.50}),
        "no crowding penalty": ({}, {"crowding_penalty_per_excess_load": 0.0}),
        "layover 25%": ({}, {"layover_ratio": 0.25}),
        "demand scale 20k trips": ({}, {"assumed_weekday_linked_trips": 20000}),
        "demand scale 60k trips": ({}, {"assumed_weekday_linked_trips": 60000}),
        "demand scale 80k trips": ({}, {"assumed_weekday_linked_trips": 80000}),
        "jobs weighted 2x residents": ({}, {"job_weight": 2.0}),
        "catchment 400 m": ({}, {"catchment_radius_m": 400.0}),
    }
    for name, (wdelta, adelta) in variants.items():
        w2 = CostWeights.from_config({**base_w, **wdelta})
        import copy
        a2 = copy.deepcopy(b.assumptions)
        for k, v in adelta.items():
            if k in ("retention_floor",):
                a2["waiting"][k] = v
            elif k in ("crowding_penalty_per_excess_load",):
                a2["crowding"][k] = v
            elif k in ("layover_ratio",):
                a2["operations"][k] = v
            elif k in ("assumed_weekday_linked_trips", "job_weight",
                       "catchment_radius_m"):
                a2["demand_proxy"][k] = v
        b2 = copy.copy(b)
        b2.assumptions = a2
        if name in ("jobs weighted 2x residents", "catchment 400 m"):
            b2 = build_baseline(demand_files=DEMAND_FILES, write=False)
            b2.assumptions = a2
            b2.demand = _rebuild_demand(b2, a2)
        s2 = build_setup(b2, weights=w2)
        bf2 = s2.model.evaluate(s2.baseline_plan)
        r2 = optimize_frequencies(
            s2.model, s2.budget, ladder=[], unserved_multiplier=1.0,
            local_search_iterations=args.iterations, seed=seed,
            ladders=s2.ladders, initial=s2.baseline_plan, n_restarts=args.restarts)
        sens.append({"variant": name,
                     "gc_change_pct": (r2.fitness.generalized_cost / bf2.generalized_cost - 1) * 100,
                     "unserved_change_pct": (r2.fitness.unserved_demand / bf2.unserved_demand - 1) * 100
                     if bf2.unserved_demand else float("nan")})
        log.info("sensitivity %-24s gc %+.2f%%", name, sens[-1]["gc_change_pct"])
    sdf = pd.DataFrame(sens)
    sdf.to_csv(exp.artifact_path("sensitivity.csv"), index=False)

    # --- plan detail for the balanced solution ---------------------------
    balanced = min(front, key=lambda r: abs(r.meta["unserved_multiplier"] - 1.0))
    diff = plan_diff(setup, balanced)
    diff.to_csv(exp.artifact_path("plan_diff_balanced.csv"), index=False)
    balanced.plan.to_frame().to_csv(exp.artifact_path("frequency_plan_balanced.csv"),
                                    index=False)
    setup.baseline_plan.to_frame().to_csv(exp.artifact_path("frequency_plan_baseline.csv"),
                                          index=False)
    for r in front:
        r.plan.to_frame().to_csv(
            exp.artifact_path(f"plan_{r.label.replace('=', '_')}.csv"), index=False)

    cmp_bal = compare_to_baseline(setup, balanced)
    exp.log_metrics(
        baseline=setup.checks,
        n_solutions=len(results), n_pareto=len(front),
        balanced_solution=cmp_bal,
        verification_all_pass=bool(all_ok),
        seed_stability_gc_pct_sd=float(stab["gc_change_pct"].std()),
        demand_source=setup.model.demand.source,
        demand_notes=setup.model.demand.notes,
        frontier=ftab.to_dict(orient="records"),
        sensitivity=sdf.to_dict(orient="records"),
    )
    exp.save()

    print("\n" + "=" * 78)
    print("EXPERIMENT 1 — PARETO FRONTIER (proxy demand)")
    print("=" * 78)
    print(ftab[["solution", "gc_change_pct", "unserved_change_pct",
                "mean_wait_min", "revenue_veh_hours", "on_pareto_front"]]
          .round(3).to_string(index=False))
    print("\nSENSITIVITY")
    print(sdf.round(3).to_string(index=False))
    print("\nSEED STABILITY")
    print(stab.round(3).to_string(index=False))
    print(f"\nverification all pass: {all_ok}")
    print(f"artifacts: {exp.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
