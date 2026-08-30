#!/usr/bin/env python3
"""Experiment 3, Stage A — discovery over network states.

**Preregistered, 2026-08-30, before any Experiment 3 state was scored.**

Limit: **24 wall-clock hours or 420 unique network-state evaluations, whichever
comes first.**

*Phase A1 — the singles census.* All 84 single-mutation states plus three
zero-edit replicates. Every unique state gets its own rebuilt path set, its own
frequency re-optimization and its own Model B evaluation; exact-state caching
applies only where the geometry is identical, which is what the permutation-
invariant state digest means. This is the first evidence this project has ever
had on `split`, `add_stop` and `change_terminal`, and it supplies the noise
floor Phase A2 is measured against.

*The gate between them.* Before Phase A2 begins, the **complete** A2 search
policy is replayed on Experiment 2B's exhaustively enumerated 240-state space
and must recover the known optimum. If it fails, the run **stops after A1** and
reports the singles census. Improvising another search after seeing A1's results
is how a preregistration stops meaning anything.

*Phase A2 — bounded multi-start search.* The remaining ~333 evaluations, three
lanes: null-start ordered by measured A1 singles; seeded rotations of that
ordering; seeded random compatible k=2/k=3 starts. States are deduplicated
across all three, and unused quota from a terminated lane passes to the
seeded-random lane.

**Phase A2 is discovery only.** It does not establish exhaustive coverage, a
global optimum, or that every state was reachable — the space is far too large
for any of those. It selects a small frontier for Stage B, where convergence and
the certification gates apply.

    python scripts/exp3_stage_a.py --dry-run
    python scripts/exp3_stage_a.py
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cota_opt import exp3, geo                                  # noqa: E402
from cota_opt.contract import ContractLimits, ContractViolation  # noqa: E402
from cota_opt.exp3_score import score_state                     # noqa: E402
from cota_opt.experiment import Experiment                      # noqa: E402
from cota_opt.geometry import GeometryEdit, SegmentTimeModel    # noqa: E402
from cota_opt.harness import build_harness                      # noqa: E402
from cota_opt.mutate import edit_from_record                    # noqa: E402
from cota_opt.statesearch import (Checkpoint, NULL, Policy,     # noqa: E402
                                  State, run_policy)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("exp3_stage_a")
OUT = ROOT / "outputs" / "exp3"

DISCOVERY = (60_000, 2, 32)      # 2B's discovery effort, so the two compare
MAX_STATES = 420                 # preregistered
MAX_HOURS = 24.0                 # preregistered
N_REPLICATES = 3                 # the same-run noise floor (gate 3-3)

TIE_FLOORS = 2.0
DIVERSITY_PER_KIND = 2
PER_CARDINALITY = 1


def load_pool():
    doc = json.loads((OUT / "mutation_pool.json").read_text())
    pairs = json.loads((OUT / "incompatible_pairs.json").read_text())
    if doc["pool_version"] != exp3.POOL_VERSION:
        raise SystemExit(
            f"the frozen pool is {doc['pool_version']} but this code is "
            f"{exp3.POOL_VERSION}; a pool generated under different rules may "
            f"not be served this run's cache")
    by_id = {}
    for m in doc["mutations"]:
        e = edit_from_record(m)
        by_id[exp3.mutation_id(e)] = e
    inc = {tuple(sorted(p)) for p in pairs["pairs"]}
    return by_id, inc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed", type=int, default=20260825)
    ap.add_argument("--lam", type=float, default=exp3.PRIMARY_LAMBDA)
    ap.add_argument("--iterations", type=int, default=DISCOVERY[0])
    ap.add_argument("--restarts", type=int, default=DISCOVERY[1])
    ap.add_argument("--width", type=int, default=DISCOVERY[2])
    ap.add_argument("--max-states", type=int, default=MAX_STATES)
    ap.add_argument("--max-hours", type=float, default=MAX_HOURS)
    ap.add_argument("--replicates", type=int, default=N_REPLICATES)
    ap.add_argument("--checkpoint", default=str(OUT / "stageA_states.jsonl"))
    ap.add_argument("--common-lines", default="same_route")
    ap.add_argument("--phase", choices=["A1", "A2", "both"], default="both")
    ap.add_argument("--shard", default="",
                    help="I/N — run only the A1 singles whose index mod N is "
                         "I. A1's states are independent, so sharding it is "
                         "safe; A2 is a sequential search and is never "
                         "sharded. Each shard writes its own files and a "
                         "merge step combines them, because 2B lost 57 of 240 "
                         "subsets to two workers sharing a partition.")
    args = ap.parse_args()

    shard_i, shard_n = 0, 1
    if args.shard:
        shard_i, shard_n = (int(x) for x in args.shard.split("/"))
    suffix = f".shard{shard_i}" if args.shard else ""

    by_id, incompatible = load_pool()
    pool = sorted(by_id)
    effort = f"{args.iterations}/{args.restarts}/{args.width}"
    a1_budget = len(pool) + args.replicates
    a2_budget = max(0, args.max_states - a1_budget)

    plan = {
        "preregistered": "2026-08-30, before any Experiment 3 state was scored",
        "pool_version": exp3.POOL_VERSION,
        "pool_size": len(pool),
        "incompatible_pairs": len(incompatible),
        "lambda": args.lam,
        "effort": effort,
        "limit": f"{args.max_hours} wall-clock hours or {args.max_states} "
                 f"unique network-state evaluations, whichever first",
        "phase_A1_states": a1_budget,
        "phase_A2_budget": a2_budget,
        "policy": Policy().as_dict(),
        "checkpoint": args.checkpoint,
        "waiting_model": args.common_lines,
        "config_digest": exp3.config_digest(),
        "objective": "generalized_cost + lambda * w_unserved * unserved_demand,"
                     " w_unserved read from config/cost_weights.yaml",
        "promotion": {"tie_floors": TIE_FLOORS,
                      "diversity_per_kind": DIVERSITY_PER_KIND,
                      "per_cardinality": PER_CARDINALITY},
        "measured_cost_per_state_sec": 413,
        "caching": "exact-state only — the state digest is the permutation-"
                   "invariant mutation set, so a cache hit means identical "
                   "geometry and nothing weaker",
    }

    if args.dry_run:
        print("=" * 84)
        print("EXPERIMENT 3 STAGE A — plan")
        print("=" * 84)
        for k, v in plan.items():
            print(f"  {k:26s} {v}")
        print(f"\n  A1: {a1_budget} states x 413 s = "
              f"{a1_budget * 413 / 3600:.1f} h single-threaded")
        print(f"  A2: up to {a2_budget} states = "
              f"{a2_budget * 413 / 3600:.1f} h single-threaded")
        print(f"  the 24 h wall-clock cap binds first unless run in parallel")
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "stageA_plan.json").write_text(json.dumps(plan, indent=2) + "\n")
        print(f"\nartifacts: {OUT / 'stageA_plan.json'}")
        return 0

    t_start = time.time()
    deadline = t_start + args.max_hours * 3600.0
    exp = Experiment(name="exp3_stage_a", seed=args.seed,
                     algorithm="preregistered three-lane first-improvement "
                               "search over network states",
                     config_files=["assumptions.yaml", "cost_weights.yaml",
                                   "constraints.yaml", "sources.yaml"])
    log.info("experiment %s", exp.experiment_id)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "stageA_plan.json").write_text(json.dumps(plan, indent=2) + "\n")

    H = build_harness(seed=args.seed, common_lines=args.common_lines,
                      with_pathsets=False)
    sg = geo.stops_gdf(H.baseline.feed, H.assumptions["crs"]["projected"])
    stm = SegmentTimeModel.fit(H.baseline.network, sg)
    budget_vh = float(H.baseline.tstats["runtime_min"].sum() / 60.0)
    limits = ContractLimits(veh_hour_budget=budget_vh,
                            peak_vehicle_budget=197.0,
                            required_waiting_model=args.common_lines)

    rows_path = OUT / f"stageA_rows{suffix}.jsonl"
    refused: list[dict] = []

    def evaluate(edits, seed, tag) -> dict | None:
        try:
            s = score_state(list(edits), harness=H, seg_model=stm,
                            stops_gdf=sg, limits=limits, lam=args.lam,
                            seed=seed, iterations=args.iterations,
                            restarts=args.restarts, width=args.width,
                            waiting_model=args.common_lines)
        except ContractViolation as v:
            refused.append({"state": tag, "rule": v.rule, "detail": v.detail})
            log.warning("%s REFUSED: %s", tag, v)
            return None
        row = {**s.row(), "role": tag}
        with rows_path.open("a") as f:
            f.write(json.dumps(row) + "\n")
        log.info("%-58.58s obj=%.7g unserved=%.1f vh=%.1f %.0fs",
                 tag, s.metrics["objective"], s.metrics["unserved_demand"],
                 s.metrics["revenue_veh_hours"], s.seconds)
        return row

    cp_path = (Path(args.checkpoint) if not args.shard else
               OUT / f"stageA_states{suffix}.jsonl")
    cp = Checkpoint(cp_path)
    # Every shard reads the MERGED checkpoint too, so a state another shard has
    # already scored is never rescored. Its own file is what it appends to.
    merged = Path(args.checkpoint)
    if args.shard and merged.exists():
        cp.scores.update(Checkpoint(merged).scores)

    # ---------------- Phase A1: the singles census -----------------------
    log.info("PHASE A1 — %d single mutations + %d zero-edit replicates",
             len(pool), args.replicates)
    reps = []
    for i in (range(args.replicates) if shard_i == 0 else ()):
        key = f"{NULL}|rep{i}"
        if cp.get(key) is not None:
            continue
        r = evaluate([], args.seed + i, key)
        if r:
            reps.append(r)
            cp.put(key, r["objective"], {"role": "zero_edit_replicate"})
        if time.time() >= deadline:
            break

    singles: dict[str, float] = {}
    mine = [m for i, m in enumerate(pool) if i % shard_n == shard_i]
    if args.shard:
        log.info("shard %d/%d: %d of %d singles", shard_i, shard_n,
                 len(mine), len(pool))
    for mid in mine:
        if time.time() >= deadline or len(cp.scores) >= args.max_states:
            log.warning("A1 stopped early at the preregistered limit")
            break
        hit = cp.get(mid)
        if hit is not None:
            singles[mid] = hit
            continue
        r = evaluate([by_id[mid]], args.seed, mid)
        if r:
            singles[mid] = r["objective"]
            cp.put(mid, r["objective"], {"role": "A1_single"})

    # the noise floor, from THIS run at THIS effort, for the objective and
    # every component (gate 3-3)
    floor = None
    rep_rows = [json.loads(l) for l in rows_path.read_text().splitlines()
                if l.strip() and json.loads(l).get("role", "").startswith(NULL)]
    if len(rep_rows) >= 3:
        class F:
            def __init__(self, d):
                for k in ("generalized_cost", "unserved_demand",
                          "served_demand", "gc_per_served_trip",
                          "revenue_veh_hours", "peak_vehicles"):
                    setattr(self, k, float(d[k]))
        floor = exp3.noise_floor([F(d) for d in rep_rows[:3]], effort=effort,
                                 lam=args.lam)
        log.info("noise floor at %s — objective %.4f%%, unserved %.4f%%",
                 effort, floor.relative_pct["objective"],
                 floor.relative_pct["unserved_demand"])

    a1 = {"phase": "A1", "singles_scored": len(singles),
          "replicates": len(rep_rows),
          "noise_floor": floor.as_dict() if floor else None,
          "best_single": (min(singles, key=singles.get) if singles else None),
          "refused": refused}
    (OUT / "stageA_A1.json").write_text(json.dumps(a1, indent=2) + "\n")
    _write_table(rows_path)

    if args.phase == "A1" or args.shard:
        log.info("phase A1 %s— stopping; merge the shards before A2",
                 "only, as requested " if args.phase == "A1" else "shard done ")
        return 0

    # ---------------- the gate ------------------------------------------
    bench = OUT / "policy_benchmark.json"
    ok = bench.exists() and json.loads(bench.read_text()).get("pass") is True
    if not ok:
        log.error("the Phase A2 policy has NOT been validated on the "
                  "exhaustive benchmark space. Phase A2 will not run; the "
                  "Phase A1 singles census stands as the Stage A result.")
        (OUT / "stageA_result.json").write_text(json.dumps(
            {**plan, "phase_reached": "A1", "a1": a1,
             "a2_blocked": "the policy benchmark did not pass"},
            indent=2) + "\n")
        return 1
    log.info("policy benchmark PASSED — phase A2 may run")

    # ---------------- Phase A2: the bounded search ------------------------
    remaining = max(0, args.max_states - len(cp.scores))
    log.info("PHASE A2 — budget %d unique states, %.1f h remaining",
             remaining, max(0.0, (deadline - time.time()) / 3600.0))

    def score(st: State) -> float:
        r = evaluate([by_id[i] for i in st.ids], args.seed, st.key)
        return r["objective"] if r else float("inf")

    a2 = run_policy(pool, score, incompatible, singles, remaining,
                    policy=Policy(), checkpoint=cp, deadline=deadline)

    _write_table(rows_path)
    (OUT / "stageA_result.json").write_text(json.dumps({
        **plan, "phase_reached": "A2", "a1": a1, "a2": a2,
        "elapsed_hours": round((time.time() - t_start) / 3600.0, 2),
        "unique_states_scored": len(cp.scores),
        "refused": refused,
        "stage": "A — DISCOVERY. These magnitudes are not findings. Gate 12: a "
                 "ranking at this effort inverted outright once (D24), and 2B's "
                 "stage C turned a -0.585%% discovery leader into a +0.007%% "
                 "certified null.",
    }, indent=2) + "\n")
    log.info("stage A done: %d unique states, best %s",
             len(cp.scores), a2["best"])
    return 0


def _write_table(rows_path: Path) -> None:
    if not rows_path.exists():
        return
    rows = [json.loads(l) for l in rows_path.read_text().splitlines()
            if l.strip()]
    pd.DataFrame(rows).to_csv(OUT / "stageA_states.csv", index=False)


if __name__ == "__main__":
    raise SystemExit(main())
