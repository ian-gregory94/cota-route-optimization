#!/usr/bin/env python3
"""How much search does this problem actually need?

The ablation solved the corrected model with 20k iterations and no restarts
while Experiment 1 got 400k and 20 restarts. Any comparison across that gap
confounds the model change with the search budget — and it does so in the
direction that flatters the ablation's conclusion.

Rather than guess a "fair" setting, this measures one: the same cell is solved
at increasing effort until the objective stops moving. Whatever level the curve
flattens at is the setting the full matrix then uses, and the curve itself is
the evidence that the setting is adequate.

Every cell is checkpointed, so this can be killed and resumed.
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

import pandas as pd

from cota_opt.cache import ResultStore
from cota_opt.frequency import optimize_frequencies
from cota_opt.harness import build_harness

log = logging.getLogger("convergence")

# (label, iterations, restarts, candidate_width)  width 0 == full
LEVELS = [
    ("L0 ablation", 20_000, 0, 24),
    ("L1", 60_000, 2, 32),
    ("L2", 150_000, 5, 48),
    ("L3", 300_000, 10, 80),
    ("L4 exp1-matched", 400_000, 20, 0),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lambdas", default="1.0")
    ap.add_argument("--seed", type=int, default=20260825)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    h = build_harness(seed=args.seed)
    setup = h.setup(with_crowding=True, lock_classes=("peak_express",),
                    seed=args.seed)
    model, base = setup.model, setup.baseline_plan
    bf = model.evaluate(base)
    base_obj_at = lambda lam: bf.scalarized(model.w.unserved, lam)
    log.info("baseline gc=%.6e unserved=%.0f vh=%.2f",
             bf.generalized_cost, bf.unserved_demand, bf.revenue_veh_hours)

    store = ResultStore(ROOT / "outputs" / "convergence.jsonl")
    for lam in [float(x) for x in args.lambdas.split(",")]:
        for label, iters, restarts, width in LEVELS:
            cell = f"conv|lam={lam}|{label}|seed={args.seed}"
            if store.has(cell):
                log.info("skip (done) %s", cell)
                continue
            t = time.time()
            r = optimize_grid(model, setup, base, lam, iters, restarts, width,
                              args.seed)
            secs = time.time() - t
            rec = {
                "lambda": lam, "level": label, "iterations": iters,
                "restarts": restarts, "width": width, "seconds": secs,
                "objective_change_pct": (r.fitness.scalarized(model.w.unserved, lam)
                                         / base_obj_at(lam) - 1) * 100,
                "gc_change_pct": (r.fitness.generalized_cost / bf.generalized_cost - 1) * 100,
                "unserved_change_pct": (r.fitness.unserved_demand / bf.unserved_demand - 1) * 100,
                "veh_hours": r.fitness.revenue_veh_hours,
                "exchanges": r.meta["exchanges"],
            }
            store.put(cell, rec)
            r.plan.to_frame().to_csv(
                ROOT / "outputs" / f"plan_conv_lam{lam}_{label.split()[0]}.csv",
                index=False)
            log.info("  lam=%-4s %-16s %5.0fs obj %+7.4f%% gc %+6.2f%% uns %+6.2f%% ex=%d",
                     lam, label, secs, rec["objective_change_pct"],
                     rec["gc_change_pct"], rec["unserved_change_pct"],
                     rec["exchanges"])

    df = pd.DataFrame(store.rows())
    df = df[df["cell"].str.startswith("conv|")]
    df.to_csv(ROOT / "outputs" / "convergence.csv", index=False)
    print("\n" + "=" * 96)
    print("SEARCH CONVERGENCE — same cell, increasing effort")
    print("=" * 96)
    cols = ["lambda", "level", "iterations", "restarts", "width", "seconds",
            "objective_change_pct", "gc_change_pct", "unserved_change_pct"]
    print(df[cols].round(4).to_string(index=False))
    return 0


def optimize_grid(model, setup, base, lam, iters, restarts, width, seed):
    return optimize_frequencies(
        model, setup.budget, ladder=[], unserved_multiplier=lam,
        local_search_iterations=iters, seed=seed, ladders=setup.ladders,
        initial=base, n_restarts=restarts, candidate_width=width,
        greedy_start=False)


if __name__ == "__main__":
    raise SystemExit(main())
