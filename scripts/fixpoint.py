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

# Search RNG scheme. Every checkpoint cell carries it, so a store written
# under an older scheme is re-solved rather than silently mixed with a newer
# one: cells produced by different generators are not the same experiment,
# and a frontier assembled from both could not be reproduced by any single
# command. "r2" = one generator per restart, seeded on (seed, restart index),
# which is what makes a killed solve resumable to the same answer.
RNG = "r2"


def key_str(k: tuple[str, str]) -> str:
    return f"{k[0]}{SEP}{k[1]}"


def key_tuple(s: str) -> tuple[str, str]:
    a, b = s.split(SEP, 1)
    return (a, b)


def solve(setup, mult, iters, restarts, width, seed, store=None, cell=None):
    """Solve one lambda cell, checkpointing after every restart.

    A full-effort cell is twenty restarts over about forty minutes and this
    sandbox reaps long-running processes, so the unit of work that has to
    survive a kill is the restart, not the cell. After each one the incumbent
    is written to the store; on restart the search rejoins at the next index
    and *re-evaluates* the saved plan rather than trusting the stored
    objective, so a checkpoint written under a different path set can never
    leak a stale number into a result.
    """
    part = f"part|{cell}" if cell else None
    resume = None
    if part and store is not None and store.has(part):
        rec = store.get(part)
        if int(rec.get("n_restarts", -1)) == int(restarts):
            resume = {"next_restart": int(rec["next_restart"]),
                      "best_idx": [int(i) for i in rec["best_idx"]],
                      "best_obj": float(rec["best_obj"]),
                      "moves": int(rec.get("moves", 0))}
            log.info("    rejoining at restart %d/%d",
                     resume["next_restart"], restarts)

    def progress(k, idx, obj, moves):
        store.put(part, {"next_restart": int(k), "n_restarts": int(restarts),
                         "best_idx": [int(i) for i in idx],
                         "best_obj": float(obj), "moves": int(moves),
                         "rng": RNG})

    return optimize_frequencies(
        setup.model, setup.budget, ladder=[], unserved_multiplier=mult,
        local_search_iterations=iters, seed=seed, ladders=setup.ladders,
        initial=setup.baseline_plan, n_restarts=restarts,
        candidate_width=width, greedy_start=False,
        progress=progress if (part and store is not None) else None,
        resume=resume)


def main() -> int:
    ap = argparse.ArgumentParser()
    # Probe effort drives the fixpoint iterations. Their job is to produce
    # plans diverse enough to expose missing paths, not to be the answer, so
    # they run one rung below the measured plateau (L3: -1.83% vs L4's -1.87%
    # on the convergence study). The answer itself is solved at full effort on
    # the converged set, and its adequacy is then re-checked -- if the full-
    # effort plan still finds improvable flow, the loop was not done.
    ap.add_argument("--iterations", type=int, default=300_000)
    ap.add_argument("--restarts", type=int, default=10)
    ap.add_argument("--width", type=int, default=80)
    ap.add_argument("--final-iterations", type=int, default=400_000)
    ap.add_argument("--final-restarts", type=int, default=20)
    ap.add_argument("--final-width", type=int, default=0, help="0 = full width")
    ap.add_argument("--final-lambdas", type=str,
                    default="0.25,0.5,1,2,4,8,16")
    ap.add_argument("--lambdas", type=str, default="0.5,1,2,8")
    ap.add_argument("--max-iterations", type=int, default=3)
    ap.add_argument("--tol", type=float, default=0.002,
                    help="stop when worst improvable flow share moves less than this")
    ap.add_argument("--seed", type=int, default=20260825)
    ap.add_argument("--common-lines", type=str, default=None,
                    choices=[None, "pattern", "same_route"],
                    help="waiting model; None uses the config default")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    lams = [float(x) for x in args.lambdas.split(",")]
    final_lams = [float(x) for x in args.final_lambdas.split(",")]
    # Model A's outputs are the control and are never overwritten, so a
    # corrected run writes to its own files.
    suffix = "" if args.common_lines in (None, "pattern") else "_modelB"
    (OUT / f"fixpoint_plans{suffix}").mkdir(parents=True, exist_ok=True)

    exp = Experiment(name=f"exp6_fixpoint{suffix}", seed=args.seed,
                     algorithm="path-set fixpoint: enumerate, solve, re-enumerate",
                     config_files=["assumptions.yaml", "cost_weights.yaml",
                                   "constraints.yaml", "sources.yaml"])
    log.info("experiment %s", exp.experiment_id)
    store = ResultStore(OUT / f"fixpoint{suffix}.jsonl")

    t0 = time.time()
    H = build_harness(seed=args.seed, common_lines=args.common_lines)
    a = H.assumptions
    pa = a["path_assignment"]
    w = CostWeights.from_config(load_cost_weights())
    wk = dict(
        random_arrival_threshold_min=float(a["waiting"]["random_arrival_threshold_min"]),
        schedule_coefficient=float(a["waiting"]["schedule_coefficient"]))
    log.info("harness ready in %.0fs; waiting model = %s", time.time() - t0,
             H.common_lines)

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
            cell = f"it{it}|lam{m}|{RNG}"
            if store.has(cell):
                rec = store.get(cell)
                plans[m] = {key_tuple(k): float(v) for k, v in rec["plan"].items()}
                log.info("  lambda=%-4s resumed from checkpoint (gc %+.2f%%)",
                         m, rec["gc_change_pct"])
                continue
            t = time.time()
            r = solve(setup, m, args.iterations, args.restarts, args.width,
                      args.seed, store=store, cell=cell)
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
                OUT / f"fixpoint_plans{suffix}" / f"it{it}_lam{m}.csv", index=False)

        # Adequacy of THIS iteration's path set under the plans it just produced.
        # Checkpointed per (iteration, lambda), not per iteration: an adequacy
        # sweep is one RAPTOR pass per period per lambda, and losing three
        # finished lambdas because the fourth was interrupted is a waste the
        # store can trivially prevent.
        ad = {}
        for m in lams:
            ad_cell = f"it{it}|adequacy|lam{m}|{RNG}"
            if store.has(ad_cell):
                ad[str(m)] = store.get(ad_cell)["adequacy"]
                log.info("  adequacy lambda=%-4s resumed, improvable flow %.2f%%",
                         m, ad[str(m)]["flow_share_improvable"] * 100)
                continue
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
            store.put(ad_cell, {"iteration": it, "lambda": m, "n_paths": n_paths,
                                "adequacy": ad[str(m)]})
            log.info("  adequacy lambda=%-4s improvable flow %.2f%%, "
                     "overstatement %.3f%%", m,
                     ad[str(m)]["flow_share_improvable"] * 100,
                     ad[str(m)]["mean_overstatement_pct"])

        worst = max(v["flow_share_improvable"] for v in ad.values())
        history.append({"iteration": it, "n_paths": n_paths,
                        "worst_flow_share_improvable": worst,
                        "enum_seconds": enum_s})
        pd.DataFrame(history).to_csv(OUT / f"fixpoint_history{suffix}.csv", index=False)
        log.info("iteration %d: worst improvable flow share %.3f%% (%d paths)",
                 it, worst * 100, n_paths)

        if prev_share is not None and abs(prev_share - worst) < args.tol:
            log.info("converged: improvable share moved %.4f, below tol %.4f",
                     abs(prev_share - worst), args.tol)
            break
        prev_share = worst
        extra = extra + [(f"opt_it{it}_lam{m}", plans[m]) for m in lams]

    # ------------------------------------------------------------------
    # Final answer: full effort on the converged set, across the whole
    # frontier, then re-check adequacy. If a full-effort plan still finds
    # improvable flow, the probe iterations did not reach the fixpoint and
    # the run says so rather than reporting a number it cannot stand behind.
    # ------------------------------------------------------------------
    log.info("=" * 70)
    log.info("FINAL FRONTIER: full effort (%d iters, %d restarts) on the "
             "converged set (%d paths)", args.final_iterations,
             args.final_restarts, n_paths)
    final_rows, final_plans = [], {}
    for m in final_lams:
        cell = f"final|lam{m}|{RNG}"
        if store.has(cell):
            rec = store.get(cell)
            final_plans[m] = {key_tuple(k): float(v) for k, v in rec["plan"].items()}
            final_rows.append({k: v for k, v in rec.items() if k != "plan"})
            log.info("  lambda=%-5s resumed from checkpoint (gc %+.2f%%)",
                     m, rec["gc_change_pct"])
            continue
        t = time.time()
        r = solve(setup, m, args.final_iterations, args.final_restarts,
                  args.final_width, args.seed, store=store, cell=cell)
        gc_pct = (r.fitness.generalized_cost / bf.generalized_cost - 1) * 100
        un_pct = (r.fitness.unserved_demand / bf.unserved_demand - 1) * 100
        final_plans[m] = dict(r.plan.headways)
        rec = {"phase": "final", "lambda": m, "n_paths": n_paths,
               "seconds": time.time() - t,
               "baseline_gc": bf.generalized_cost,
               "baseline_unserved": bf.unserved_demand,
               "baseline_served": bf.served_demand,
               "gc": r.fitness.generalized_cost,
               "unserved": r.fitness.unserved_demand,
               "served": r.fitness.served_demand,
               "gc_change_pct": gc_pct, "unserved_change_pct": un_pct,
               "served_change_pct": (r.fitness.served_demand
                                     / bf.served_demand - 1) * 100,
               "gc_per_trip_change_pct": (r.fitness.gc_per_served_trip
                                          / bf.gc_per_served_trip - 1) * 100,
               "revenue_veh_hours": r.fitness.revenue_veh_hours,
               "vh_vs_budget_pct": (r.fitness.revenue_veh_hours
                                    / setup.budget.revenue_veh_hours - 1) * 100}
        store.put(cell, {**rec,
                         "plan": {key_str(k): float(v)
                                  for k, v in r.plan.headways.items()}})
        final_rows.append(rec)
        log.info("  lambda=%-5s %4.0fs gc %+7.2f%% unserved %+7.2f%% vh=%.1f",
                 m, time.time() - t, gc_pct, un_pct, r.fitness.revenue_veh_hours)
        pd.DataFrame([{"route_id": k[0], "period": k[1], "headway_min": v}
                      for k, v in r.plan.headways.items()]).to_csv(
            OUT / f"fixpoint_plans{suffix}" / f"final_lam{m}.csv", index=False)

    fr = pd.DataFrame(final_rows)
    fr.to_csv(OUT / f"fixpoint_frontier{suffix}.csv", index=False)

    # Does the converged set hold up under plans it never saw during the loop?
    fad = {}
    for m in final_lams:
        fa_cell = f"final|adequacy|lam{m}|{RNG}"
        if store.has(fa_cell):
            fad[str(m)] = store.get(fa_cell)["adequacy"]
            log.info("  final adequacy lambda=%-5s resumed, improvable flow %.2f%%",
                     m, fad[str(m)]["flow_share_improvable"] * 100)
            continue
        rows = [adequacy(H.raptor, H.zones, ev.ps, ev, final_plans[m], w, wk,
                         int(pa["max_rounds"]))
                for ev in setup.model.evaluators.values()]
        wts = np.array([r["od_pairs_compared"] for r in rows], dtype=float)
        fad[str(m)] = {
            "by_period": rows,
            "flow_share_improvable": float(np.average(
                [r["flow_share_improvable"] for r in rows], weights=wts)),
            "mean_overstatement_pct": float(np.average(
                [r["mean_overstatement_pct"] for r in rows], weights=wts))}
        store.put(fa_cell, {"lambda": m, "n_paths": n_paths,
                            "adequacy": fad[str(m)]})
        log.info("  final adequacy lambda=%-5s improvable flow %.2f%%, "
                 "overstatement %.3f%%", m,
                 fad[str(m)]["flow_share_improvable"] * 100,
                 fad[str(m)]["mean_overstatement_pct"])
    final_worst = max(v["flow_share_improvable"] for v in fad.values())
    log.info("final worst improvable flow share: %.3f%%", final_worst * 100)

    # Common-yardstick re-scoring: every plan any earlier configuration
    # produced, priced by this converged model. Scoring is cheap; the point is
    # that no configuration gets to grade its own homework.
    rescored = []
    for csv in sorted((OUT / "matrix_plans").glob("*.csv")):
        cell = f"rescore|{csv.stem}|{RNG}"
        if store.has(cell):
            rescored.append({k: v for k, v in store.get(cell).items()
                             if k != "cell"})
            continue
        d = pd.read_csv(csv, dtype={"route_id": str})
        col = ("headway_min" if "headway_min" in d.columns
               else "optimized_headway_min")
        hw = dict(setup.baseline_plan.headways)
        for row in d.itertuples():
            hw[(row.route_id, row.period)] = float(getattr(row, col))
        fit = setup.model.evaluate_array(
            np.array([hw[k] for k in setup.model.keys]))
        rec = {"source": csv.stem,
               "gc_change_pct": (fit.generalized_cost / bf.generalized_cost - 1) * 100,
               "unserved_change_pct": (fit.unserved_demand
                                       / bf.unserved_demand - 1) * 100,
               "revenue_veh_hours": fit.revenue_veh_hours,
               "vh_vs_budget_pct": (fit.revenue_veh_hours
                                    / setup.budget.revenue_veh_hours - 1) * 100}
        store.put(cell, rec)
        rescored.append(rec)
    if rescored:
        rs = pd.DataFrame(rescored)
        rs.to_csv(OUT / f"fixpoint_rescored{suffix}.csv", index=False)
        log.info("re-scored %d earlier plans on the converged yardstick",
                 len(rs))

    hist = pd.DataFrame(history)
    hist.to_csv(OUT / f"fixpoint_history{suffix}.csv", index=False)
    exp.log_metrics(common_lines=H.common_lines,
                    history=history, lambdas=lams, final_lambdas=final_lams,
                    final_adequacy=fad,
                    final_worst_improvable_flow_share=final_worst,
                    converged_n_paths=n_paths,
                    search_iterations=args.iterations, restarts=args.restarts,
                    total_seconds=time.time() - t0)
    exp.save()

    print("\n" + "=" * 84)
    print("PATH-SET FIXPOINT")
    print("=" * 84)
    print(hist.to_string(index=False))
    print("\nFINAL FRONTIER (full effort, converged set)")
    print(fr.drop(columns=[c for c in ("phase", "baseline_gc",
                                       "baseline_unserved", "baseline_served")
                           if c in fr.columns]).round(3).to_string(index=False))
    print(f"\nworst improvable flow share under a final plan: "
          f"{final_worst * 100:.3f}%")
    print(f"\nartifacts: {exp.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
