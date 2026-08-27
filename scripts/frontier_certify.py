#!/usr/bin/env python3
"""Gate 4 repair: certify the frontier corner the probe loop never visited.

The fixpoint probes at lambda in {0.5, 1, 2, 8} and the final frontier is
solved at {0.25 ... 16}. So the extreme cost-favouring points are solved at an
effort *and* a lambda the enumeration never saw, and Model A's adequacy check
caught exactly that: 9.72% improvable flow at lambda=0.25 and 1.62% at 0.5,
against 0.66-0.99% everywhere else and a 1.029% line. The check working is the
good news; the frontier corner failing it is the bad news.

This is one more fixpoint step, aimed at the plans that failed. The seven
full-effort plans go back in as enumeration scenarios, the set is rebuilt once,
and **every** lambda is re-solved on it -- not only the failing ones. Solving
two lambdas on a wider set and leaving five on the old one would put two
yardsticks in one frontier, which is the thing gate 5 exists to prevent.

Certified means the same line the loop converged at, unchanged: improvable
flow under every final plan below that share. If a lambda still fails, the
honest report is that the corner is not certifiable at this cost and the
frontier is quoted without it -- not a moved line.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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

log = logging.getLogger("certify")
OUT = ROOT / "outputs"
SEP = "::"
RNG = "r2"


def key_str(k) -> str:
    return f"{k[0]}{SEP}{k[1]}"


def key_tuple(s: str):
    a, b = s.split(SEP, 1)
    return (a, b)


def scenario_tag(extra) -> str:
    """Content hash of the scenario list -- see fixpoint.py for why not names."""
    if not extra:
        return "base"
    payload = [[n, sorted((key_str(k), round(float(v), 6)) for k, v in plan.items())]
               for n, plan in extra]
    return "sc-" + hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def solve(setup, mult, iters, restarts, width, seed, store, cell):
    """Restart-level checkpointing, same contract as the fixpoint's."""
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--common-lines", type=str, default=None,
                    choices=[None, "pattern", "same_route"])
    ap.add_argument("--lambdas", type=str, default="0.25,0.5,1,2,4,8,16")
    ap.add_argument("--iterations", type=int, default=400_000)
    ap.add_argument("--restarts", type=int, default=20)
    ap.add_argument("--width", type=int, default=0, help="0 = full width")
    ap.add_argument("--line", type=float, default=None,
                    help="gate 4 line; default = the share the loop converged at")
    ap.add_argument("--seed", type=int, default=20260825)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    suffix = "" if args.common_lines in (None, "pattern") else "_modelB"
    lams = [float(x) for x in args.lambdas.split(",")]
    src = ResultStore(OUT / f"fixpoint{suffix}.jsonl")
    store = ResultStore(OUT / f"certify{suffix}.jsonl")
    (OUT / f"certify_plans{suffix}").mkdir(parents=True, exist_ok=True)

    # the line comes from the run being repaired, not from this script
    hist = pd.read_csv(OUT / f"fixpoint_history{suffix}.csv")
    line = float(args.line if args.line is not None
                 else hist["worst_flow_share_improvable"].iloc[-1])
    log.info("gate 4 line: %.4f%% (from the fixpoint's last iteration)", line * 100)

    finals = {r["lambda"]: {key_tuple(k): float(v) for k, v in r["plan"].items()}
              for r in src.rows()
              if r["cell"].startswith("final|lam") and "adequacy" not in r["cell"]}
    if not finals:
        log.error("no final|lam cells in %s -- run the fixpoint first",
                  f"fixpoint{suffix}.jsonl")
        return 2
    log.info("feeding %d full-effort plans back as enumeration scenarios: %s",
             len(finals), ", ".join(f"lam{m}" for m in sorted(finals)))

    exp = Experiment(
        name=f"exp6_certify{suffix}", seed=args.seed,
        algorithm="one fixpoint step on the full-effort plans, then every "
                  "lambda re-solved on the widened set and re-checked",
        config_files=["assumptions.yaml", "cost_weights.yaml",
                      "constraints.yaml", "sources.yaml"])
    t0 = time.time()
    H = build_harness(seed=args.seed, common_lines=args.common_lines)
    a = H.assumptions
    pa = a["path_assignment"]
    w = CostWeights.from_config(load_cost_weights())
    wk = dict(
        random_arrival_threshold_min=float(a["waiting"]["random_arrival_threshold_min"]),
        schedule_coefficient=float(a["waiting"]["schedule_coefficient"]))

    extra = [(f"final_lam{m}", finals[m]) for m in sorted(finals)]
    tag = scenario_tag(extra)
    log.info("enumeration tag %s", tag)
    te = time.time()
    psets = H.pathsets_with(extra, tag=tag, seed=args.seed)
    setup = H.setup(with_crowding=True, lock_classes=("peak_express",),
                    seed=args.seed, pathsets=psets)
    bf = setup.model.evaluate(setup.baseline_plan)
    n_paths = sum(p.n_paths for p in setup.pathsets.values())
    log.info("widened set: %d candidate paths, baseline gc=%.6e (enum %.0fs)",
             n_paths, bf.generalized_cost, time.time() - te)

    rows, plans = [], {}
    for m in lams:
        cell = f"certify|lam{m}|{RNG}"
        if store.has(cell):
            rec = store.get(cell)
            plans[m] = {key_tuple(k): float(v) for k, v in rec["plan"].items()}
            rows.append({k: v for k, v in rec.items() if k not in ("plan", "cell")})
            log.info("  lambda=%-5s resumed (gc %+.2f%%)", m, rec["gc_change_pct"])
            continue
        t = time.time()
        r = solve(setup, m, args.iterations, args.restarts, args.width,
                  args.seed, store, cell)
        plans[m] = dict(r.plan.headways)
        rec = {"lambda": m, "n_paths": n_paths, "seconds": time.time() - t,
               "gc": r.fitness.generalized_cost,
               "unserved": r.fitness.unserved_demand,
               "served": r.fitness.served_demand,
               "gc_change_pct": (r.fitness.generalized_cost / bf.generalized_cost - 1) * 100,
               "unserved_change_pct": (r.fitness.unserved_demand / bf.unserved_demand - 1) * 100,
               "served_change_pct": (r.fitness.served_demand / bf.served_demand - 1) * 100,
               "gc_per_trip_change_pct": (r.fitness.gc_per_served_trip
                                          / bf.gc_per_served_trip - 1) * 100,
               "revenue_veh_hours": r.fitness.revenue_veh_hours,
               "vh_vs_budget_pct": (r.fitness.revenue_veh_hours
                                    / setup.budget.revenue_veh_hours - 1) * 100}
        store.put(cell, {**rec, "plan": {key_str(k): float(v)
                                         for k, v in r.plan.headways.items()}})
        rows.append(rec)
        log.info("  lambda=%-5s %4.0fs gc %+7.2f%% unserved %+7.2f%% vh=%.1f",
                 m, rec["seconds"], rec["gc_change_pct"],
                 rec["unserved_change_pct"], rec["revenue_veh_hours"])
        pd.DataFrame([{"route_id": k[0], "period": k[1], "headway_min": v}
                      for k, v in r.plan.headways.items()]).to_csv(
            OUT / f"certify_plans{suffix}" / f"lam{m}.csv", index=False)

    ad = {}
    for m in lams:
        cell = f"certify|adequacy|lam{m}|{RNG}"
        if store.has(cell):
            ad[m] = store.get(cell)["adequacy"]
            log.info("  adequacy lambda=%-5s resumed, improvable %.3f%%",
                     m, ad[m]["flow_share_improvable"] * 100)
            continue
        per = [adequacy(H.raptor, H.zones, ev.ps, ev, plans[m], w, wk,
                        int(pa["max_rounds"]))
               for ev in setup.model.evaluators.values()]
        wts = np.array([r["od_pairs_compared"] for r in per], dtype=float)
        ad[m] = {"by_period": per,
                 "flow_share_improvable": float(np.average(
                     [r["flow_share_improvable"] for r in per], weights=wts)),
                 "mean_overstatement_pct": float(np.average(
                     [r["mean_overstatement_pct"] for r in per], weights=wts))}
        store.put(cell, {"lambda": m, "n_paths": n_paths, "adequacy": ad[m]})
        log.info("  adequacy lambda=%-5s improvable %.3f%%, overstatement %.4f%%",
                 m, ad[m]["flow_share_improvable"] * 100,
                 ad[m]["mean_overstatement_pct"])

    fr = pd.DataFrame(rows).sort_values("lambda", ignore_index=True)
    fr["improvable_flow_pct"] = fr["lambda"].map(
        lambda m: ad[m]["flow_share_improvable"] * 100)
    fr["overstatement_pct"] = fr["lambda"].map(
        lambda m: ad[m]["mean_overstatement_pct"])
    fr["certified"] = fr["improvable_flow_pct"] <= line * 100
    fr.to_csv(OUT / f"certify_frontier{suffix}.csv", index=False)
    fr.to_csv(exp.artifact_path("frontier.csv"), index=False)

    failed = list(fr.loc[~fr["certified"], "lambda"])
    out = {"common_lines": H.common_lines, "n_paths": n_paths,
           "line_pct": line * 100, "lambdas": lams,
           "effort": {"iterations": args.iterations, "restarts": args.restarts,
                      "width": args.width, "seed": args.seed},
           "enumeration_tag": tag, "rows": rows,
           "adequacy": {str(k): {kk: vv for kk, vv in v.items() if kk != "by_period"}
                        for k, v in ad.items()},
           "failed_lambdas": failed,
           "all_certified": not failed,
           "seconds": time.time() - t0}
    (OUT / f"certify{suffix}.json").write_text(json.dumps(out, indent=2, default=str))
    exp.log_metrics(**out)
    exp.save()

    print("\n" + "=" * 104)
    print(f"GATE 4 CERTIFICATION — {H.common_lines} — line {line*100:.3f}%")
    print("=" * 104)
    print(fr.drop(columns=[c for c in ("gc", "unserved", "served", "n_paths")
                           if c in fr.columns]).round(3).to_string(index=False))
    if failed:
        print(f"\n  STILL FAILING: lambda {failed}. The corner is not certifiable "
              f"at this cost; quote the frontier without it rather than moving "
              f"the line.")
    else:
        print(f"\n  ALL {len(lams)} LAMBDAS CERTIFIED on {n_paths:,} paths.")
    print(f"\nartifacts: {exp.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
