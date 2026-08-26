#!/usr/bin/env python3
"""Gate 11 follow-up: does the wider candidate set change the answer?

Re-running the discovery diagnostic after augmenting candidate generation is
close to circular -- the diagnostic finds suspects with route-level RAPTOR and
the augmentation adds route-level RAPTOR's optima to the set. It proves the
wiring works, which is worth knowing given that the first attempt silently
contributed no paths at all, but it is not evidence of discovery adequacy.

The non-circular question is whether the omission changes the plan the
optimizer recommends. Solve Model B at matched effort on both candidate sets,
then score *both plans on the augmented evaluator* -- a superset, so it is the
legitimate common yardstick and neither plan grades its own homework.

Thresholds and the decision were committed to ACCEPTANCE.md before this ran.
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
from cota_opt.experiment import Experiment
from cota_opt.frequency import optimize_frequencies
from cota_opt.harness import build_harness

log = logging.getLogger("sensitivity")
OUT = ROOT / "outputs"
SEP = "::"

#: committed in ACCEPTANCE.md before the run
GC_LINE_PCT = 0.25
UNSERVED_LINE_PCT = 1.0


def wait_for_memory(min_free_mb: int = 2200, tries: int = 90) -> None:
    for _ in range(tries):
        try:
            free = int([l for l in Path("/proc/meminfo").read_text().splitlines()
                        if l.startswith("MemAvailable")][0].split()[1]) // 1024
        except Exception:
            return
        if free >= min_free_mb:
            return
        log.warning("only %d MB available, waiting", free)
        time.sleep(30)


def key_str(k) -> str:
    return f"{k[0]}{SEP}{k[1]}"


def solve(setup, mult, iters, restarts, width, seed, store=None, cell=None):
    """Same restart-level checkpointing the fixpoint uses."""
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
                         "best_obj": float(obj), "moves": int(moves)})

    return optimize_frequencies(
        setup.model, setup.budget, ladder=[], unserved_multiplier=mult,
        local_search_iterations=iters, seed=seed, ladders=setup.ladders,
        initial=setup.baseline_plan, n_restarts=restarts,
        candidate_width=width, greedy_start=False,
        progress=progress if (part and store is not None) else None,
        resume=resume)


def plan_diff(a: dict, b: dict) -> dict:
    keys = sorted(set(a) | set(b))
    d = np.array([float(b.get(k, np.nan)) - float(a.get(k, np.nan))
                  for k in keys])
    changed = np.abs(d) > 1e-9
    return {"n_route_periods": int(len(keys)),
            "n_changed": int(changed.sum()),
            "share_changed": float(changed.mean()) if len(keys) else 0.0,
            "max_abs_change_min": float(np.nanmax(np.abs(d))) if len(d) else 0.0,
            "mean_abs_change_min": float(np.nanmean(np.abs(d[changed])))
            if changed.any() else 0.0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lambdas", type=str, default="1,2,4")
    ap.add_argument("--iterations", type=int, default=100_000)
    ap.add_argument("--restarts", type=int, default=6)
    ap.add_argument("--width", type=int, default=0)
    ap.add_argument("--seed", type=int, default=20260825)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    wait_for_memory()

    lams = [float(x) for x in args.lambdas.split(",")]
    exp = Experiment(
        name="gate11_sensitivity", seed=args.seed,
        algorithm="Model B solved on augmented and un-augmented candidate "
                  "sets, both plans scored on the augmented evaluator",
        config_files=["assumptions.yaml", "cost_weights.yaml",
                      "constraints.yaml", "sources.yaml"])
    store = ResultStore(OUT / "gate11_sensitivity.jsonl")
    t0 = time.time()

    setups = {}
    for tag, rl in (("plain", False), ("wide", True)):
        H = build_harness(seed=args.seed, common_lines="same_route",
                          route_level=rl)
        setups[tag] = H.setup(with_crowding=True,
                              lock_classes=("peak_express",), seed=args.seed)
        n = sum(p.n_paths for p in setups[tag].pathsets.values())
        log.info("%s candidate set: %d paths", tag, n)

    n_plain = sum(p.n_paths for p in setups["plain"].pathsets.values())
    n_wide = sum(p.n_paths for p in setups["wide"].pathsets.values())

    # the augmented evaluator is the common yardstick: it is a superset, so it
    # can price anything the un-augmented set could
    yard = setups["wide"]
    base = yard.model.evaluate(yard.baseline_plan)

    rows = []
    for m in lams:
        plans = {}
        for tag in ("plain", "wide"):
            cell = f"{tag}|lam{m}"
            if store.has(cell):
                rec = store.get(cell)
                plans[tag] = {tuple(k.split(SEP, 1)): float(v)
                              for k, v in rec["plan"].items()}
                log.info("  lambda=%-4s %-5s resumed from checkpoint", m, tag)
                continue
            t = time.time()
            r = solve(setups[tag], m, args.iterations, args.restarts,
                      args.width, args.seed, store=store, cell=cell)
            plans[tag] = dict(r.plan.headways)
            store.put(cell, {"set": tag, "lambda": m,
                             "seconds": time.time() - t,
                             "own_gc": r.fitness.generalized_cost,
                             "own_unserved": r.fitness.unserved_demand,
                             "plan": {key_str(k): float(v)
                                      for k, v in r.plan.headways.items()}})
            log.info("  lambda=%-4s %-5s solved in %.0fs", m, tag,
                     time.time() - t)

        # both plans, one yardstick
        scored = {}
        for tag, hw in plans.items():
            f = yard.model.evaluate_array(
                np.array([hw[k] for k in yard.model.keys]))
            scored[tag] = f
        gc_gap = (scored["plain"].generalized_cost
                  / scored["wide"].generalized_cost - 1) * 100
        un_gap = (scored["plain"].unserved_demand
                  / scored["wide"].unserved_demand - 1) * 100
        rows.append({
            "lambda": m,
            "plain_gc_change_pct": (scored["plain"].generalized_cost
                                    / base.generalized_cost - 1) * 100,
            "wide_gc_change_pct": (scored["wide"].generalized_cost
                                   / base.generalized_cost - 1) * 100,
            "plain_unserved_change_pct": (scored["plain"].unserved_demand
                                          / base.unserved_demand - 1) * 100,
            "wide_unserved_change_pct": (scored["wide"].unserved_demand
                                         / base.unserved_demand - 1) * 100,
            "gc_gap_pct": gc_gap, "unserved_gap_pct": un_gap,
            "material": bool(gc_gap >= GC_LINE_PCT
                             or un_gap >= UNSERVED_LINE_PCT),
            **{f"diff_{k}": v for k, v in
               plan_diff(plans["plain"], plans["wide"]).items()},
        })
        log.info("  lambda=%-4s gap: gc %+.4f%%, unserved %+.4f%%  (%s)", m,
                 gc_gap, un_gap,
                 "MATERIAL" if rows[-1]["material"] else "below the line")

    fr = pd.DataFrame(rows)
    fr.to_csv(OUT / "gate11_sensitivity.csv", index=False)
    fr.to_csv(exp.artifact_path("sensitivity.csv"), index=False)
    any_material = bool(fr["material"].any())
    verdict = ("the augmentation changed the answer: the un-augmented set's "
               "plan is materially worse on the common yardstick, so the "
               "augmented set is the basis for every Model B result"
               if any_material else
               "the augmentation did not change the answer: the omission gate "
               "11 found is real and widespread but does not move the "
               "recommended plan past the pre-committed line")
    out = {"lambdas": lams, "n_paths_plain": n_plain, "n_paths_wide": n_wide,
           "paths_added_pct": 100.0 * (n_wide / n_plain - 1) if n_plain else None,
           "effort": {"iterations": args.iterations, "restarts": args.restarts,
                      "width": args.width, "seed": args.seed},
           "thresholds": {"gc_pct": GC_LINE_PCT,
                          "unserved_pct": UNSERVED_LINE_PCT,
                          "committed": "ACCEPTANCE.md, before this ran"},
           "rows": rows, "material": any_material, "verdict": verdict,
           "seconds": time.time() - t0}
    (OUT / "gate11_sensitivity.json").write_text(json.dumps(out, indent=2,
                                                            default=str))
    exp.log_metrics(**out)
    exp.save()

    print("\n" + "=" * 96)
    print("GATE 11 FOLLOW-UP — does the wider candidate set change the answer?")
    print("=" * 96)
    print(f"  candidate paths: {n_plain:,} -> {n_wide:,} "
          f"({out['paths_added_pct']:+.2f}%)")
    print(f"  effort: {args.iterations:,} iterations, {args.restarts} restarts, "
          f"seed {args.seed}, identical on both sets\n")
    print(fr.round(4).to_string(index=False))
    print(f"\n  thresholds (committed before the run): gc >= {GC_LINE_PCT}%, "
          f"unserved >= {UNSERVED_LINE_PCT}%")
    print(f"\n  VERDICT: {verdict}")
    print(f"\nartifacts: {exp.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
