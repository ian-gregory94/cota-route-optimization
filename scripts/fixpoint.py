#!/usr/bin/env python3
"""Path-set fixpoint: iterate enumeration and optimization until the set stops growing.

The path-based model scores plans against candidate paths enumerated in
advance under a fixed sweep of headway scenarios. That is a real approximation
and, measured, the largest remaining one: under the most aggressive plans on
the frontier, 17.6% of passenger flow could reach its destination more cheaply
by a path the optimizer was never shown. Every such pair is charged too much,
so the plan's cost is overstated and the frontier sits too high.

The fix is a fixpoint. Solve, feed the resulting plans back in as enumeration
scenarios, re-enumerate, re-solve, repeat until adequacy stops improving.
Because the candidate set only ever grows, each iteration's model is a tighter
lower bound than the last, so the loop is monotone by construction.

Every cell is checkpointed to JSONL, so the run resumes where it died and
partial results are readable while it is still going.
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

from cota_opt.adequacy import adequacy
from cota_opt.cache import ResultStore
from cota_opt.configs import load_cost_weights
from cota_opt.cost import CostWeights
from cota_opt.experiment import Experiment
from cota_opt.frequency import optimize_frequencies
from cota_opt.harness import build_harness

log = logging.getLogger("fixpoint")
OUT = ROOT / "outputs"
SEP = "::"


def key_str(k: tuple[str, str]) -> str:
    return f"{k[0]}{SEP}{k[1]}"


def key_tuple(s: str) -> tuple[str, str]:
    a, b = s.split(SEP, 1)
    return (a, b)


def solve(setup, mult, iters, restarts, width, seed):
    return optimize_frequencies(
        setup.model, setup.budget, ladder=[], unserved_multiplier=mult,
        local_search_iterations=iters, seed=seed, ladders=setup.ladders,
        initial=setup.baseline_plan, n_restarts=restarts,
        candidate_width=width, greedy_start=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=400_000)
    ap.add_argument("--restarts", type=int, default=20)
    ap.add_argument("--width", type=int, default=0, help="0 = full width")
    ap.add_argument("--lambdas", type=str, default="0.5,1,2,8")
    ap.add_argument("--max-iterations", type=int, default=4)
    ap.add_argument("--tol", type=float, default=0.002,
                    help="stop when worst improvable flow share moves less than this")
    ap.add_argument("--seed", type=int, default=20260825)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    lams = [float(x) for x in args.lambdas.split(",")]
    (OUT / "fixpoint_plans").mkdir(parents=True, exist_ok=True)

    exp = Experiment(name="exp6_fixpoint", seed=args.seed,
                     algorithm="path-set fixpoint: enumerate, solve, re-enumerate",
                     config_files=["assumptions.yaml", "cost_weights.yaml",
                                   "constraints.yaml", "sources.yaml"])
    log.info("experiment %s", exp.experiment_id)
    store = ResultStore(OUT / "fixpoint.jsonl")

    t0 = time.time()
    H = build_harness(seed=args.seed)
    a = H.assumptions
    pa = a["path_assignment"]
    w = CostWeights.from_config(load_cost_weights())
    wk = dict(
        random_arrival_threshold_min=float(a["waiting"]["random_arrival_threshold_min"]),
        schedule_coefficient=float(a["waiting"]["schedule_coefficient"]))
    log.info("harness ready in %.0fs", time.time() - t0)

    extra: list[tuple[str, dict]] = []
    history: list[dict] = []
    prev_share = None

    for it in range(args.max_iterations):
        tag = "base" if not extra else "|".join(n for n, _ in extra)
        log.info("=" * 70)
        log.info("ITERATION %d, %d extra enumeration scenarios", it, len(extra))

        te = time.time()
        psets = H.pathsets_with(extra, tag=tag, seed=args.seed) if extra else H.pathsets
        enum_s = time.time() - te
        setup = H.setup(with_crowding=True, lock_classes=("peak_express",),
                        seed=args.seed, pathsets=psets)
        bf = setup.model.evaluate(setup.baseline_plan)
        n_paths = sum(p.n_paths for p in setup.pathsets.values())
        log.info("iteration %d: %d candidate paths, baseline gc=%.6e (enum %.0fs)",
                 it, n_paths, bf.generalized_cost, enum_s)

        plans: dict[float, dict] = {}
        for m in lams:
            cell = f"it{it}|lam{m}"
            if store.has(cell):
                rec = store.get(cell)
                plans[m] = {key_tuple(k): float(v) for k, v in rec["plan"].items()}
                log.info("  lambda=%-4s resumed from checkpoint (gc %+.2f%%)",
                         m, rec["gc_change_pct"])
                continue
            t = time.time()
            r = solve(setup, m, args.iterations, args.restarts, args.width, args.seed)
            gc_pct = (r.fitness.generalized_cost / bf.generalized_cost - 1) * 100
            un_pct = (r.fitness.unserved_demand / bf.unserved_demand - 1) * 100
            plans[m] = dict(r.plan.headways)
            store.put(cell, {
                "iteration": it, "lambda": m, "n_paths": n_paths,
                "seconds": time.time() - t,
                "baseline_gc": bf.generalized_cost,
                "baseline_unserved": bf.unserved_demand,
                "gc": r.fitness.generalized_cost,
                "unserved": r.fitness.unserved_demand,
                "served": r.fitness.served_demand,
                "gc_change_pct": gc_pct, "unserved_change_pct": un_pct,
                "revenue_veh_hours": r.fitness.revenue_veh_hours,
                "vh_vs_budget_pct": (r.fitness.revenue_veh_hours
                                     / setup.budget.revenue_veh_hours - 1) * 100,
                "plan": {key_str(k): float(v) for k, v in r.plan.headways.items()},
            })
            log.info("  lambda=%-4s %4.0fs gc %+7.2f%% unserved %+7.2f%%",
                     m, time.time() - t, gc_pct, un_pct)
            pd.DataFrame([{"route_id": k[0], "period": k[1], "headway_min": v}
                          for k, v in r.plan.headways.items()]).to_csv(
                OUT / "fixpoint_plans" / f"it{it}_lam{m}.csv", index=False)

        # Adequacy of THIS iteration's path set under the plans it just produced.
        ad_cell = f"it{it}|adequacy"
        if store.has(ad_cell):
            ad = store.get(ad_cell)["adequacy"]
        else:
            ad = {}
            for m in lams:
                rows = [adequacy(H.raptor, H.zones, ev.ps, ev, plans[m], w, wk,
                                 int(pa["max_rounds"]))
                        for ev in setup.model.evaluators.values()]
                wts = np.array([r["od_pairs_compared"] for r in rows], dtype=float)
                ad[str(m)] = {
                    "by_period": rows,
                    "flow_share_improvable": float(np.average(
                        [r["flow_share_improvable"] for r in rows], weights=wts)),
                    "mean_overstatement_pct": float(np.average(
                        [r["mean_overstatement_pct"] for r in rows], weights=wts)),
                }
                log.info("  adequacy lambda=%-4s improvable flow %.2f%%, "
                         "overstatement %.3f%%", m,
                         ad[str(m)]["flow_share_improvable"] * 100,
                         ad[str(m)]["mean_overstatement_pct"])
            store.put(ad_cell, {"iteration": it, "n_paths": n_paths, "adequacy": ad})

        worst = max(v["flow_share_improvable"] for v in ad.values())
        history.append({"iteration": it, "n_paths": n_paths,
                        "worst_flow_share_improvable": worst,
                        "enum_seconds": enum_s})
        pd.DataFrame(history).to_csv(OUT / "fixpoint_history.csv", index=False)
        log.info("iteration %d: worst improvable flow share %.3f%% (%d paths)",
                 it, worst * 100, n_paths)

        if prev_share is not None and abs(prev_share - worst) < args.tol:
            log.info("converged: improvable share moved %.4f, below tol %.4f",
                     abs(prev_share - worst), args.tol)
            break
        prev_share = worst
        extra = extra + [(f"opt_it{it}_lam{m}", plans[m]) for m in lams]

    hist = pd.DataFrame(history)
    hist.to_csv(OUT / "fixpoint_history.csv", index=False)
    exp.log_metrics(history=history, lambdas=lams,
                    search_iterations=args.iterations, restarts=args.restarts,
                    total_seconds=time.time() - t0)
    exp.save()

    print("\n" + "=" * 84)
    print("PATH-SET FIXPOINT")
    print("=" * 84)
    print(hist.to_string(index=False))
    print(f"\nartifacts: {exp.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
