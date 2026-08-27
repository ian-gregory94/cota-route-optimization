#!/usr/bin/env python3
"""Gate 7: is the balanced point stable across seeds, and is the plan identified?

Two questions, one set of replicates.

**The effect.** Solve lambda=2 at full effort on the frozen set under several
seeds and compare the spread of the result to the result itself. A 7% coverage
gain means nothing if independent seeds scatter by 3%.

**The plan.** D14 found two plans whose objectives differ by 0.01% while their
headways differ on a quarter of the network's route-periods by an average of
eight minutes. That was across two candidate sets; if independent seeds on the
*same* set disagree as widely, the optimum is flat and no individual route
headway may be quoted as a recommendation. The aggregate result is unaffected
either way, but which of the two it is changes what may be said.

Thresholds are committed in ACCEPTANCE.md before this runs.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from cota_opt.cache import ResultStore
from cota_opt.experiment import Experiment
from cota_opt.frequency import optimize_frequencies
from cota_opt.harness import build_harness

log = logging.getLogger("seedcheck")
OUT = ROOT / "outputs"
SEP = "::"
RNG = "r2"

#: committed in ACCEPTANCE.md before the run
SIGMA_MARGIN = 3.0          # |effect| must exceed this many standard deviations
PLAN_AGREEMENT_PCT = 10.0   # route-periods differing, above which the plan is
                            # called unidentified rather than merely noisy


def key_str(k) -> str:
    return f"{k[0]}{SEP}{k[1]}"


def key_tuple(s: str):
    a, b = s.split(SEP, 1)
    return (a, b)


def solve(setup, mult, iters, restarts, width, seed, store, cell):
    part = f"part|{cell}"
    resume = None
    if store.has(part):
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
                         "best_obj": float(obj), "moves": int(moves), "rng": RNG})

    return optimize_frequencies(
        setup.model, setup.budget, ladder=[], unserved_multiplier=mult,
        local_search_iterations=iters, seed=seed, ladders=setup.ladders,
        initial=setup.baseline_plan, n_restarts=restarts,
        candidate_width=width, greedy_start=False, progress=progress,
        resume=resume)


def plan_disagreement(plans: dict[int, dict]) -> dict:
    """How far apart the replicate plans are, pair by pair."""
    seeds = sorted(plans)
    keys = sorted(plans[seeds[0]])
    rows = []
    for a, b in combinations(seeds, 2):
        d = np.array([float(plans[b][k]) - float(plans[a][k]) for k in keys])
        ch = np.abs(d) > 1e-9
        rows.append({"seed_a": a, "seed_b": b,
                     "n_changed": int(ch.sum()),
                     "share_changed_pct": 100.0 * float(ch.mean()),
                     "mean_abs_change_min": float(np.abs(d[ch]).mean())
                     if ch.any() else 0.0,
                     "max_abs_change_min": float(np.abs(d).max())})
    df = pd.DataFrame(rows)
    return {"pairs": rows,
            "n_route_periods": len(keys),
            "mean_share_changed_pct": float(df["share_changed_pct"].mean()),
            "worst_share_changed_pct": float(df["share_changed_pct"].max()),
            "mean_abs_change_min": float(df["mean_abs_change_min"].mean())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--common-lines", type=str, default=None,
                    choices=[None, "pattern", "same_route"])
    ap.add_argument("--lam", type=float, default=2.0)
    ap.add_argument("--seeds", type=str, default="20260825,20260826,20260827")
    ap.add_argument("--iterations", type=int, default=400_000)
    ap.add_argument("--restarts", type=int, default=20)
    ap.add_argument("--width", type=int, default=0)
    ap.add_argument("--from-certify", action="store_true",
                    help="use the certified widened set rather than the "
                         "fixpoint's frozen one")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    suffix = "" if args.common_lines in (None, "pattern") else "_modelB"
    seeds = [int(x) for x in args.seeds.split(",")]
    src = ResultStore(OUT / (f"certify{suffix}.jsonl" if args.from_certify
                             else f"fixpoint{suffix}.jsonl"))
    store = ResultStore(OUT / f"seedcheck{suffix}.jsonl")

    prefix = "certify|lam" if args.from_certify else "final|lam"
    finals = {r["lambda"]: {key_tuple(k): float(v) for k, v in r["plan"].items()}
              for r in src.rows()
              if r["cell"].startswith(prefix) and "adequacy" not in r["cell"]}
    if not finals:
        log.error("no %s cells found -- run the upstream job first", prefix)
        return 2

    exp = Experiment(
        name=f"exp6_seedcheck{suffix}", seed=seeds[0],
        algorithm="lambda held fixed, seed varied, on one frozen candidate set",
        config_files=["assumptions.yaml", "cost_weights.yaml",
                      "constraints.yaml", "sources.yaml"])
    t0 = time.time()
    H = build_harness(seed=seeds[0], common_lines=args.common_lines)

    # the replicates must share one candidate set, or seed spread and set
    # spread are confounded -- which is the confound D14 could not separate
    extra = [(f"final_lam{m}", finals[m]) for m in sorted(finals)]
    import hashlib
    payload = [[n, sorted((key_str(k), round(float(v), 6)) for k, v in p.items())]
               for n, p in extra]
    tag = "sc-" + hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    psets = H.pathsets_with(extra, tag=tag, seed=seeds[0])
    setup = H.setup(with_crowding=True, lock_classes=("peak_express",),
                    seed=seeds[0], pathsets=psets)
    bf = setup.model.evaluate(setup.baseline_plan)
    n_paths = sum(p.n_paths for p in setup.pathsets.values())
    log.info("one shared set: %d paths, lambda=%s, %d seeds",
             n_paths, args.lam, len(seeds))

    rows, plans = [], {}
    for sd in seeds:
        cell = f"seed{sd}|lam{args.lam}|{RNG}"
        if store.has(cell):
            rec = store.get(cell)
            plans[sd] = {key_tuple(k): float(v) for k, v in rec["plan"].items()}
            rows.append({k: v for k, v in rec.items() if k not in ("plan", "cell")})
            log.info("  seed %-9s resumed (gc %+.3f%%)", sd, rec["gc_change_pct"])
            continue
        t = time.time()
        r = solve(setup, args.lam, args.iterations, args.restarts, args.width,
                  sd, store, cell)
        plans[sd] = dict(r.plan.headways)
        rec = {"seed": sd, "lambda": args.lam, "n_paths": n_paths,
               "seconds": time.time() - t,
               "gc_change_pct": (r.fitness.generalized_cost / bf.generalized_cost - 1) * 100,
               "unserved_change_pct": (r.fitness.unserved_demand / bf.unserved_demand - 1) * 100,
               "served_change_pct": (r.fitness.served_demand / bf.served_demand - 1) * 100,
               "gc_per_trip_change_pct": (r.fitness.gc_per_served_trip
                                          / bf.gc_per_served_trip - 1) * 100,
               "revenue_veh_hours": r.fitness.revenue_veh_hours}
        store.put(cell, {**rec, "plan": {key_str(k): float(v)
                                         for k, v in r.plan.headways.items()}})
        rows.append(rec)
        log.info("  seed %-9s %4.0fs gc %+7.3f%% unserved %+7.3f%%",
                 sd, rec["seconds"], rec["gc_change_pct"],
                 rec["unserved_change_pct"])

    df = pd.DataFrame(rows).sort_values("seed", ignore_index=True)
    df.to_csv(OUT / f"seedcheck{suffix}.csv", index=False)

    stats = {}
    for col in ("gc_change_pct", "unserved_change_pct", "served_change_pct",
                "gc_per_trip_change_pct"):
        v = df[col].to_numpy(float)
        sd_ = float(v.std(ddof=1)) if len(v) > 1 else float("nan")
        stats[col] = {"mean": float(v.mean()), "sd": sd_,
                      "min": float(v.min()), "max": float(v.max()),
                      "sigmas": abs(float(v.mean())) / sd_ if sd_ > 0 else float("inf")}

    dis = plan_disagreement(plans)
    effect_ok = stats["unserved_change_pct"]["sigmas"] >= SIGMA_MARGIN
    plan_identified = dis["worst_share_changed_pct"] < PLAN_AGREEMENT_PCT

    if effect_ok and plan_identified:
        why = ("the coverage effect clears its own spread with room, and "
               "independent seeds agree on the plan: individual route headways "
               "may be quoted")
    elif effect_ok:
        why = ("the coverage effect clears its own spread, but independent "
               f"seeds disagree on {dis['worst_share_changed_pct']:.1f}% of "
               "route-periods -- the optimum is flat, so the aggregate result "
               "stands and NO individual route headway may be quoted as a "
               "recommendation")
    else:
        why = ("the coverage effect does not clear its own seed spread by "
               f"{SIGMA_MARGIN:.0f} sigma; it cannot be reported as measured")

    out = {"common_lines": H.common_lines, "lambda": args.lam, "seeds": seeds,
           "n_paths": n_paths, "enumeration_tag": tag,
           "set": "certified" if args.from_certify else "frozen",
           "effort": {"iterations": args.iterations, "restarts": args.restarts,
                      "width": args.width},
           "stats": stats, "plan_disagreement": dis,
           "thresholds": {"sigma_margin": SIGMA_MARGIN,
                          "plan_agreement_pct": PLAN_AGREEMENT_PCT,
                          "committed": "ACCEPTANCE.md, before this ran"},
           "effect_clears_spread": bool(effect_ok),
           "plan_identified": bool(plan_identified),
           "explanation": why, "seconds": time.time() - t0}
    (OUT / f"seedcheck{suffix}.json").write_text(json.dumps(out, indent=2, default=str))
    exp.log_metrics(**out)
    exp.save()

    print("\n" + "=" * 92)
    print(f"GATE 7 — seed stability at lambda={args.lam} ({H.common_lines}, "
          f"{n_paths:,} paths)")
    print("=" * 92)
    print(df[["seed", "gc_change_pct", "unserved_change_pct",
              "served_change_pct", "gc_per_trip_change_pct"]]
          .round(4).to_string(index=False))
    print("\n  spread:")
    for k, v in stats.items():
        print(f"    {k:26s} mean {v['mean']:+8.4f}  sd {v['sd']:7.4f}  "
              f"= {v['sigmas']:6.2f} sigma")
    print(f"\n  plan disagreement across seeds ({dis['n_route_periods']} route-periods):")
    print(f"    worst pair differs on {dis['worst_share_changed_pct']:.1f}% "
          f"(mean {dis['mean_share_changed_pct']:.1f}%), "
          f"average move {dis['mean_abs_change_min']:.2f} min")
    print(f"\n  effect clears {SIGMA_MARGIN:.0f} sigma: "
          f"{'YES' if effect_ok else 'NO'}")
    print(f"  plan identified (< {PLAN_AGREEMENT_PCT:.0f}% disagreement): "
          f"{'YES' if plan_identified else 'NO'}")
    print(f"\n  {why}")
    print(f"\nartifacts: {exp.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
