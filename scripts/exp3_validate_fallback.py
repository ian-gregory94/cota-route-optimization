#!/usr/bin/env python3
"""Section 2 of the corrective plan: is `both` ever better than `greedy`?

The 40-state remediation list rests on an inference, not a demonstrated
invariant. A state whose incumbent was rejected ran the greedy build alone.
Under `starts="both"` it gets greedy AND a repaired incumbent, best kept — so
`both` cannot make it worse, but nothing yet shows it cannot make it BETTER.
If it can, the 40-state list is incomplete and the remediation set has to grow.

This runs a stratified sample of previously-fallback states at the original
discovery effort under `starts="greedy"` and `starts="both"`, everything else
identical, and records objective, unserved demand, vehicle-hours, the selected
frequency plan, and which start `both` actually chose.

Running `greedy` explicitly rather than trusting the recorded value is the
point: it also proves the recorded number reproduces, so a difference under
`both` cannot be blamed on drift somewhere else.

One state and one start set per process, so a slice always finishes what it
begins. Path sets are cached per state, so the second start set on a state
costs about ninety seconds instead of seven minutes.

    bash scripts/exp3_validate_slice.sh 470
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import pickle
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cota_opt import exp3, geo                                    # noqa: E402
from cota_opt.cache import cache_dir, key_of                      # noqa: E402
from cota_opt.contract import ContractLimits, ContractViolation   # noqa: E402
from cota_opt.exp3_score import score_state                       # noqa: E402
from cota_opt.geometry import SegmentTimeModel                    # noqa: E402
from cota_opt.harness import build_harness                        # noqa: E402
from cota_opt.mutate import edit_from_record                      # noqa: E402
from exp3_pin_envelope import load as pin_load                    # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("validate")
OUT = ROOT / "outputs" / "exp3"
ROWS = OUT / "validation_fallback.jsonl"
PLANS = OUT / "validation_plans"
ARMS = ("greedy", "both")


def sample() -> list[dict]:
    return json.loads((OUT / "validation_sample.json").read_text())


def done() -> set[tuple[str, str]]:
    out = set()
    if ROWS.exists():
        for line in ROWS.open():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                out.add((r["state_key"], r["starts"]))
            except Exception:
                pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deadline-seconds", type=float, default=470.0)
    ap.add_argument("--state-seconds", type=float, default=440.0)
    ap.add_argument("--lam", type=float, default=exp3.PRIMARY_LAMBDA)
    ap.add_argument("--seed", type=int, default=20260825)
    ap.add_argument("--iterations", type=int, default=60_000)
    ap.add_argument("--restarts", type=int, default=2)
    ap.add_argument("--width", type=int, default=32)
    ap.add_argument("--common-lines", default="same_route")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    deadline = time.time() + args.deadline_seconds
    PLANS.mkdir(parents=True, exist_ok=True)

    have = done()
    todo = [(s, arm) for s in sample() for arm in ARMS
            if (s["state_key"], arm) not in have]
    log.info("%d of %d (state, start set) cells still to run",
             len(todo), len(sample()) * len(ARMS))
    if args.list or not todo:
        for s, arm in todo:
            print(f"{s['state_key']}\t{arm}")
        return 0

    H = build_harness(seed=args.seed, common_lines=args.common_lines,
                      with_pathsets=False)
    sg = geo.stops_gdf(H.baseline.feed, H.assumptions["crs"]["projected"])
    stm = SegmentTimeModel.fit(H.baseline.network, sg)
    budget_vh = float(H.baseline.tstats["runtime_min"].sum() / 60.0)
    CONS = pin_load()
    limits = ContractLimits(veh_hour_budget=budget_vh,
                            peak_vehicle_budget=197.0,
                            required_waiting_model=args.common_lines)
    pool = json.loads((OUT / "mutation_pool.json").read_text())
    idx = {m["id"]: m for m in pool["mutations"]}

    n = 0
    for spec, arm in todo:
        # A cached path set makes the second arm cheap; only guard the full cost
        # when the cache is cold.
        edits = []
        for part in spec["state_key"].split("+"):
            key = part.split("#")[0]
            hit = idx.get(part) or idx.get(key) or next(
                (m for m in idx.values() if m["id"].split("#")[0] == key), None)
            if hit is None:
                log.error("no pool entry for %r", part)
                return 2
            edits.append(edit_from_record(hit))

        ps_key = key_of("exp3_pathsets",
                        exp3.pathset_cache_params(edits, args.seed,
                                                  args.common_lines))
        ps_path = cache_dir() / f"{ps_key}.pkl"
        warm = ps_path.exists()
        need = 120.0 if warm else args.state_seconds
        if time.time() + need > deadline:
            log.info("stopping cleanly: %.0fs needed, %.0fs left",
                     need, deadline - time.time())
            break

        psc: dict = {}
        if warm:
            try:
                psc = pickle.loads(ps_path.read_bytes())
            except Exception as e:
                log.warning("cache %s unreadable (%s)", ps_key, e)
                psc = {}
        fresh = not psc

        t0 = time.time()
        try:
            s = score_state(list(edits), harness=H, seg_model=stm, stops_gdf=sg,
                            limits=limits, lam=args.lam, seed=args.seed,
                            iterations=args.iterations, restarts=args.restarts,
                            width=args.width, waiting_model=args.common_lines,
                            constraints=CONS, pathset_cache=psc, starts=arm)
        except ContractViolation as v:
            log.warning("%s [%s] REFUSED: %s", spec["label"], arm, v)
            continue
        if fresh and psc:
            try:
                ps_path.write_bytes(pickle.dumps(psc, protocol=pickle.HIGHEST_PROTOCOL))
            except Exception as e:
                log.warning("could not cache path sets: %s", e)

        plan_blob = json.dumps(s.plan, sort_keys=True)
        plan_hash = hashlib.sha256(plan_blob.encode()).hexdigest()[:16]
        (PLANS / f"{exp3.state_digest(edits)[:12]}-{arm}.json").write_text(plan_blob)
        rep = s.evaluator.get("incumbent_repair", {})
        row = {"label": spec["label"], "state_key": spec["state_key"],
               "cardinality": spec["cardinality"], "starts": arm,
               "seed": args.seed, "lambda": args.lam,
               "effort": f"{args.iterations}/{args.restarts}/{args.width}",
               "objective": s.metrics["objective"],
               "unserved_demand": s.metrics["unserved_demand"],
               "revenue_veh_hours": s.metrics["revenue_veh_hours"],
               "generalized_cost": s.metrics.get("generalized_cost"),
               "plan_hash": plan_hash,
               "best_start": rep.get("best_start"),
               "start_names": rep.get("start_names"),
               "exchanges": rep.get("exchanges"),
               "repair_steps": rep.get("steps"),
               "snapped_feasible": rep.get("snapped_feasible"),
               "recorded_objective": spec.get("recorded_objective"),
               "seconds": round(time.time() - t0, 1)}
        with ROWS.open("a") as f:
            f.write(json.dumps(row) + "\n")
            f.flush()
            os.fsync(f.fileno())
        n += 1
        log.info("%-15s [%-6s] obj=%.7g won=%-9s plan=%s %.0fs",
                 spec["label"], arm, row["objective"], str(row["best_start"]),
                 plan_hash, row["seconds"])

    log.info("slice ran %d cells; %d remain", n,
             len([1 for s in sample() for a in ARMS
                  if (s["state_key"], a) not in done()]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
