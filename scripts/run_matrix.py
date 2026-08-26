#!/usr/bin/env python3
"""The full experiment matrix, at one search setting, fully checkpointed.

Four models over the same resource envelope, the same demand, the same solver
and the same effort — so a difference between rows is a difference in the model
and nothing else. That was not true of the earlier ablation, which compared a
20k-iteration search against a 400k-iteration one.

  R  route-level assignment, demand derived from the SAME OD table
     — this is Experiment 1's mechanism with every other confound removed, so
       the R-to-A gap is the assignment method on its own
  A  RAPTOR path assignment
  B  + peak-only express routes held at their designed timetable
  C  + crowding priced at each route-period's peak load point

Every (model, lambda, seed) cell is written to a JSONL store as it completes,
so the run resumes rather than restarts.
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

from cota_opt.cache import ResultStore
from cota_opt.cost import CostWeights
from cota_opt.exp2 import plan_diff
from cota_opt.experiment import Experiment
from cota_opt.frequency import (FrequencyModel, FrequencyPlan, PassengerDemand,
                                optimize_frequencies, pareto_filter)
from cota_opt.harness import build_harness

log = logging.getLogger("matrix")


def route_demand_from_od(setup, baseline_plan) -> PassengerDemand:
    """Boardings per (route, period) implied by the OD table at baseline.

    Gives the route-level model exactly the demand the path model works with, so
    the two differ only in how a traveller responds to a frequency change.
    """
    model = setup.model
    totals: dict[tuple[str, str], float] = {}
    for per, ev in model.evaluators.items():
        sub = np.array([baseline_plan.headways[k] for k in ev.ps.rp_keys])
        boardings = ev.boardings_by_rp(sub)
        for k, v in zip(ev.ps.rp_keys, boardings):
            if k[1] == per:
                totals[k] = totals.get(k, 0.0) + float(v)
    return PassengerDemand(
        totals, source="OD-derived boardings at baseline assignment",
        notes="Route-level demand taken from the same LODES OD table the path "
              "model uses, so the two models see identical demand.")


def build_route_level(setup, baseline_plan) -> FrequencyModel:
    """Experiment 1's model class, but fed the OD-derived demand."""
    m = setup.model
    return FrequencyModel(m.services, m.periods,
                          route_demand_from_od(setup, baseline_plan),
                          m.w, m.a, m.connections)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, required=True)
    ap.add_argument("--restarts", type=int, required=True)
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--lambdas", default="1,2,0.5,4,8,0.25,16")
    ap.add_argument("--seeds", default="20260825")
    ap.add_argument("--models", default="C,B,A,R")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    seed0 = int(args.seeds.split(",")[0])
    h = build_harness(seed=seed0)

    setups = {}
    setups["C"] = h.setup(True, ("peak_express",), seed0)
    setups["B"] = h.setup(False, ("peak_express",), seed0)
    setups["A"] = h.setup(False, (), seed0)
    base = setups["A"].baseline_plan

    models = {"A": setups["A"].model, "B": setups["B"].model, "C": setups["C"].model}
    ladders = {k: setups[k].ladders for k in ("A", "B", "C")}
    budgets = {k: setups[k].budget for k in ("A", "B", "C")}
    if "R" in args.models:
        models["R"] = build_route_level(setups["A"], base)
        ladders["R"] = setups["A"].ladders
        budgets["R"] = setups["A"].budget

    # every model is scored on the SAME yardstick for reporting: model C
    scorer = setups["C"].model
    sf = scorer.evaluate(base)
    log.info("common scorer baseline: gc=%.6e unserved=%.0f vh=%.2f",
             sf.generalized_cost, sf.unserved_demand, sf.revenue_veh_hours)

    store = ResultStore(ROOT / "outputs" / "matrix.jsonl")
    exp = Experiment(name="exp5_matrix", seed=seed0,
                     algorithm=f"matched search {args.iterations}/{args.restarts}/{args.width}",
                     config_files=["assumptions.yaml", "cost_weights.yaml",
                                   "constraints.yaml"])

    for name in args.models.split(","):
        name = name.strip()
        if name not in models:
            continue
        m, lad, bud = models[name], ladders[name], budgets[name]
        own = m.evaluate(base)
        for seed in [int(s) for s in args.seeds.split(",")]:
            for lam in [float(x) for x in args.lambdas.split(",")]:
                cell = (f"m={name}|lam={lam}|seed={seed}"
                        f"|eff={args.iterations}/{args.restarts}/{args.width}")
                if store.has(cell):
                    continue
                t = time.time()
                r = optimize_frequencies(
                    m, bud, ladder=[], unserved_multiplier=lam,
                    local_search_iterations=args.iterations, seed=seed,
                    ladders=lad, initial=base, n_restarts=args.restarts,
                    candidate_width=args.width, greedy_start=False)
                secs = time.time() - t
                # score on the common yardstick, whatever model produced it
                sc = scorer.evaluate(r.plan)
                rec = {
                    "model": name, "lambda": lam, "seed": seed,
                    "iterations": args.iterations, "restarts": args.restarts,
                    "width": args.width, "seconds": secs,
                    "own_gc_change_pct": (r.fitness.generalized_cost / own.generalized_cost - 1) * 100,
                    "own_unserved_change_pct": (r.fitness.unserved_demand / own.unserved_demand - 1) * 100,
                    "scored_gc_change_pct": (sc.generalized_cost / sf.generalized_cost - 1) * 100,
                    "scored_unserved_change_pct": (sc.unserved_demand / sf.unserved_demand - 1) * 100,
                    "scored_served_change_pct": (sc.served_demand / sf.served_demand - 1) * 100,
                    "veh_hours": r.fitness.revenue_veh_hours,
                    "within_budget": bool(r.fitness.revenue_veh_hours
                                          <= bud.vh_cap() * (1 + 1e-9)),
                    "exchanges": r.meta["exchanges"],
                }
                store.put(cell, rec)
                pdir = ROOT / "outputs" / "matrix_plans"
                pdir.mkdir(parents=True, exist_ok=True)
                r.plan.to_frame().to_csv(
                    pdir / f"{name}_lam{lam}_seed{seed}.csv", index=False)
                d = plan_diff(setups["A"], r.plan)
                r10 = d[d.route_id == "010"]
                log.info("%s lam=%-5s seed=%d %5.0fs | own gc %+6.2f%% uns %+6.2f%% "
                         "| scored gc %+6.2f%% uns %+6.2f%% | r10 am_peak %.1f",
                         name, lam, seed, secs, rec["own_gc_change_pct"],
                         rec["own_unserved_change_pct"], rec["scored_gc_change_pct"],
                         rec["scored_unserved_change_pct"],
                         float(r10[r10.period == "am_peak"].optimized_headway_min.iloc[0])
                         if len(r10[r10.period == "am_peak"]) else float("nan"))

    df = pd.DataFrame(store.rows())
    df = df[df["cell"].str.startswith("m=")]
    df.to_csv(exp.artifact_path("matrix.csv"), index=False)
    exp.log_metrics(rows=df.to_dict(orient="records"),
                    scorer_baseline={"gc": sf.generalized_cost,
                                     "unserved": sf.unserved_demand,
                                     "veh_hours": sf.revenue_veh_hours})
    exp.save()
    print("\n" + "=" * 104)
    print("MATRIX — identical envelope, demand, solver and effort; scored on one yardstick (model C)")
    print("=" * 104)
    cols = ["model", "lambda", "seed", "scored_gc_change_pct",
            "scored_unserved_change_pct", "veh_hours", "seconds"]
    print(df[cols].round(3).to_string(index=False))
    print(f"\nartifacts: {exp.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
