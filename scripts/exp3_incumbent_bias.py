#!/usr/bin/env python3
"""Measure the incumbent-fallback bias: same state, same seed, repair off vs on.

The finding this exists to size
-------------------------------
`optimize_frequencies` accepts an `initial` plan only if that plan, once
snapped to the headway ladder, still fits the envelope. `fit_incumbent` fits
in continuous headway space, and the snap that follows moves about half the
route-periods to a shorter headway, which costs vehicle-hours. So the snapped
incumbent lands back outside the envelope, the optimizer logs `incumbent plan
is infeasible under this budget`, and falls back to `_greedy_build` -- the
build the caller disabled, and the one Experiment 1 measured as converging to
a worse optimum than the incumbent start.

The fallback is not evenly distributed across treatments. Measured over the
155 Stage A solves logged so far:

    extend            40/40   100.0%      truncate     0/14    0.0%
    reroute           21/22    95.5%      straighten   0/12    0.0%
    splice            12/13    92.3%      null          0/3    0.0%
    add_stop          52/63    82.5%
    k=2 and k=3       46/46   100.0%

Route-lengthening edits fall back; route-shortening edits and the unedited
control do not. Experiments 2 and 2B show the same split (exp2_treatments_full:
72/72 solves; exp2b_stageA_s0: 32/32).

So every cross-state comparison in this project so far has compared a control
optimized from its incumbent against treatments optimized by greedy build. This
script measures how much that is worth, in objective points, on states whose
recorded numbers already exist.

    python scripts/exp3_incumbent_bias.py --states null,splice-011-034-WESHIGW
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
sys.path.insert(0, str(ROOT / "scripts"))

from cota_opt import exp3, geo                                   # noqa: E402
from cota_opt.contract import ContractLimits                     # noqa: E402
from cota_opt.exp3_score import score_state                      # noqa: E402
from cota_opt.geometry import SegmentTimeModel                   # noqa: E402
from cota_opt.harness import build_harness                       # noqa: E402
from cota_opt.mutate import edit_from_record                     # noqa: E402
from exp3_pin_envelope import load as pin_load                   # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("bias")
OUT = ROOT / "outputs" / "exp3"


def pool_index() -> dict:
    pool = json.loads((OUT / "mutation_pool.json").read_text())
    return {m["id"]: m for m in pool["mutations"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", type=str, required=True,
                    help="comma-separated; 'null' means the unedited network, "
                         "otherwise '+'-joined mutation ids (bare or with #digest)")
    ap.add_argument("--lam", type=float, default=exp3.PRIMARY_LAMBDA)
    ap.add_argument("--seed", type=int, default=20260825)
    ap.add_argument("--iterations", type=int, default=60_000)
    ap.add_argument("--restarts", type=int, default=2)
    ap.add_argument("--width", type=int, default=32)
    ap.add_argument("--common-lines", type=str, default="same_route")
    ap.add_argument("--out", type=str, default="incumbent_bias.jsonl")
    ap.add_argument("--mode", type=str, default="asis",
                    choices=("asis", "repaired", "greedy", "both_starts"),
                    help="one start set per process, so a slice can finish it")
    args = ap.parse_args()

    H = build_harness(seed=args.seed, common_lines=args.common_lines,
                      with_pathsets=False)
    sg = geo.stops_gdf(H.baseline.feed, H.assumptions["crs"]["projected"])
    stm = SegmentTimeModel.fit(H.baseline.network, sg)
    budget_vh = float(H.baseline.tstats["runtime_min"].sum() / 60.0)
    CONS = pin_load()
    limits = ContractLimits(veh_hour_budget=budget_vh,
                            peak_vehicle_budget=197.0,
                            required_waiting_model=args.common_lines)
    idx = pool_index()
    path = OUT / args.out

    for spec in [s for s in args.states.split(",") if s.strip()]:
        spec = spec.strip()
        if spec == "null":
            edits = []
        else:
            edits = []
            for part in spec.split("+"):
                key = part.split("#")[0]
                hit = idx.get(part) or idx.get(key)
                if hit is None:
                    hit = next((m for m in idx.values()
                                if m["id"].split("#")[0] == key), None)
                if hit is None:
                    log.error("no pool entry for %r", part)
                    return 2
                edits.append(edit_from_record(hit))

        row = {"state": spec, "lam": args.lam, "seed": args.seed,
               "effort": f"{args.iterations}/{args.restarts}/{args.width}"}
        starts = {"asis": "incumbent", "repaired": "repaired",
                  "greedy": "greedy", "both_starts": "both"}[args.mode]
        for tag in (args.mode,):
            t0 = time.time()
            s = score_state(list(edits), harness=H, seg_model=stm,
                            stops_gdf=sg, limits=limits, lam=args.lam,
                            seed=args.seed, iterations=args.iterations,
                            restarts=args.restarts, width=args.width,
                            waiting_model=args.common_lines,
                            constraints=CONS, starts=starts)
            row[tag] = {**s.metrics,
                        "repair": s.evaluator.get("incumbent_repair", {}),
                        "seconds": round(time.time() - t0, 1)}
            log.info("%-40.40s %-8s obj=%.7g vh=%.1f exch=%s",
                     spec, tag, s.metrics["objective"],
                     s.metrics["revenue_veh_hours"],
                     row[tag]["repair"].get("exchanges"))


        with path.open("a") as f:
            f.write(json.dumps(row) + "\n")
            f.flush()
            import os
            os.fsync(f.fileno())
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
