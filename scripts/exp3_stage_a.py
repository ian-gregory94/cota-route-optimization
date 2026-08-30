#!/usr/bin/env python3
"""Experiment 3, Stage A — discovery over network states.

Searches many valid network states at cheap effort, re-optimizing frequency on
every one of them. **Stage A supports candidate selection and nothing else.**
Its magnitudes are not findings — gate 12 exists because a ranking at this
effort inverted outright once already (D24), and Experiment 2B's stage C then
turned a −0.585% discovery leader into a +0.007% certified null.

Promotion is a tie band plus structural diversity plus cardinality leaders, not
a top N. At discovery effort every state inside a floor of the leader is a tie,
and taking the top N discards the true winner whenever the ranking is off by one
floor — which, in this project, it has been.

Resume is exact and sub-state: the checkpoint is append-only JSONL keyed on the
full cache key, so a run that dies loses the state in flight and nothing else.

    python scripts/exp3_stage_a.py --dry-run     # plan only, scores nothing
    python scripts/exp3_stage_a.py               # the real sweep
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cota_opt import exp3, geo                                  # noqa: E402
from cota_opt.cache import digest                               # noqa: E402
from cota_opt.contract import ContractLimits, ContractViolation  # noqa: E402
from cota_opt.exp3_score import score_state                     # noqa: E402
from cota_opt.experiment import Experiment                      # noqa: E402
from cota_opt.geometry import GeometryEdit, SegmentTimeModel    # noqa: E402
from cota_opt.harness import build_harness                      # noqa: E402
from cota_opt.mutate import edit_from_record                    # noqa: E402
from cota_opt.statesearch import Checkpoint, State, search      # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("exp3_stage_a")
OUT = ROOT / "outputs" / "exp3"

#: Discovery effort. The same 60,000/2/32 Experiment 2B ranked at, so the two
#: discovery stages are comparable — and labelled discovery-stage for the same
#: reason.
DISCOVERY = (60_000, 2, 32)

#: Restart seeds. Seed 0 starts from the null; the rest start from single
#: mutations spread deterministically across the sorted pool.
STAGE_A_SEEDS = tuple(range(12))

#: Promotion, committed before any state is scored.
TIE_FLOORS = 2.0        # everything within this many floors of the leader
DIVERSITY_PER_KIND = 2  # best states featuring each mutation kind
PER_CARDINALITY = 1     # best state at each size, nested or not


def load_pool() -> tuple[list[GeometryEdit], dict[str, GeometryEdit],
                         set[tuple[str, str]]]:
    doc = json.loads((OUT / "mutation_pool.json").read_text())
    pairs = json.loads((OUT / "incompatible_pairs.json").read_text())
    if doc["pool_version"] != exp3.POOL_VERSION:
        raise SystemExit(
            f"the frozen pool is {doc['pool_version']} but this code is "
            f"{exp3.POOL_VERSION}. A pool generated under different rules may "
            f"not be served this run's cache, and vice versa.")
    edits, by_id = [], {}
    for m in doc["mutations"]:
        e = edit_from_record(m)
        edits.append(e)
        by_id[exp3.mutation_id(e)] = e
    inc = {tuple(sorted(p)) for p in pairs["pairs"]}
    return edits, by_id, inc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan — pool size, seeds, effort, "
                         "checkpoint, estimated runtime — and score nothing")
    ap.add_argument("--seed", type=int, default=20260825)
    ap.add_argument("--lam", type=float, default=exp3.PRIMARY_LAMBDA)
    ap.add_argument("--iterations", type=int, default=DISCOVERY[0])
    ap.add_argument("--restarts", type=int, default=DISCOVERY[1])
    ap.add_argument("--width", type=int, default=DISCOVERY[2])
    ap.add_argument("--max-cardinality", type=int, default=4)
    ap.add_argument("--max-evaluations", type=int, default=600)
    ap.add_argument("--replicates", type=int, default=3,
                    help="zero-edit solves for the same-run noise floor "
                         "(gate 3-3). Fewer than 3 and there is no floor.")
    ap.add_argument("--checkpoint", default=str(OUT / "stageA_states.jsonl"))
    ap.add_argument("--common-lines", default="same_route")
    args = ap.parse_args()

    pool_edits, by_id, incompatible = load_pool()
    pool_ids = sorted(by_id)
    effort = f"{args.iterations}/{args.restarts}/{args.width}"

    plan = {
        "pool_version": exp3.POOL_VERSION,
        "pool_size": len(pool_ids),
        "incompatible_pairs": len(incompatible),
        "lambda": args.lam,
        "effort": effort,
        "seeds": list(STAGE_A_SEEDS),
        "max_cardinality": args.max_cardinality,
        "max_evaluations": args.max_evaluations,
        "replicates": args.replicates,
        "checkpoint": args.checkpoint,
        "waiting_model": args.common_lines,
        "config_digest": exp3.config_digest(),
        "objective": "generalized_cost + lambda * w_unserved * unserved_demand,"
                     " w_unserved read from config/cost_weights.yaml",
        "promotion": {"tie_floors": TIE_FLOORS,
                      "diversity_per_kind": DIVERSITY_PER_KIND,
                      "per_cardinality": PER_CARDINALITY},
    }

    if args.dry_run:
        print("=" * 84)
        print("EXPERIMENT 3 STAGE A — plan")
        print("=" * 84)
        for k, v in plan.items():
            print(f"  {k:22s} {v}")
        # ~75 s per state on this container at 60k/2/32, measured from 2B's
        # stage A log; the null replicates cost the same each.
        n = args.max_evaluations + args.replicates
        print(f"\n  states to score        <= {n} "
              f"(search budget {args.max_evaluations} + "
              f"{args.replicates} zero-edit replicates)")
        print(f"  measured cost/state    ~75 s at {effort} (2B stage A)")
        print(f"  estimated runtime      ~{n * 75 / 3600:.1f} h, resumable")
        print(f"  checkpoint             {args.checkpoint}")
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "stageA_plan.json").write_text(json.dumps(plan, indent=2) + "\n")
        print(f"\nartifacts: {OUT / 'stageA_plan.json'}")
        return 0

    exp = Experiment(name="exp3_stage_a", seed=args.seed,
                     algorithm="neighbourhood search over network states",
                     config_files=["assumptions.yaml", "cost_weights.yaml",
                                   "constraints.yaml", "sources.yaml"])
    log.info("experiment %s", exp.experiment_id)

    H = build_harness(seed=args.seed, common_lines=args.common_lines,
                      with_pathsets=False)
    sg = geo.stops_gdf(H.baseline.feed, H.assumptions["crs"]["projected"])
    stm = SegmentTimeModel.fit(H.baseline.network, sg)
    budget_vh = float(H.baseline.tstats["runtime_min"].sum() / 60.0)
    limits = ContractLimits(veh_hour_budget=budget_vh,
                            peak_vehicle_budget=197.0,
                            required_waiting_model=args.common_lines)

    cp = Checkpoint(Path(args.checkpoint))
    rows: list[dict] = []
    refused: list[dict] = []

    def score(st: State) -> float:
        edits = [by_id[i] for i in st.ids]
        try:
            s = score_state(edits, harness=H, seg_model=stm, stops_gdf=sg,
                            limits=limits, lam=args.lam, seed=args.seed,
                            iterations=args.iterations,
                            restarts=args.restarts, width=args.width,
                            waiting_model=args.common_lines)
        except ContractViolation as v:
            # A state the contract refuses is recorded and priced out of the
            # search, not allowed to kill a sweep hundreds of states in.
            refused.append({"state": st.key, "rule": v.rule,
                            "detail": v.detail})
            log.warning("state %s REFUSED: %s", st.key, v)
            return float("inf")
        rows.append(s.row())
        log.info("%-56.56s obj=%.6g  unserved=%.1f  vh=%.1f  %.0fs",
                 st.key, s.metrics["objective"], s.metrics["unserved_demand"],
                 s.metrics["revenue_veh_hours"], s.seconds)
        return s.metrics["objective"]

    # Gate 3-3: the floor is measured in THIS run, at THIS effort, for the
    # quantity actually compared — before the search, so no candidate can be
    # promoted against a floor that does not exist yet.
    reps = []
    for i in range(args.replicates):
        s = score_state([], harness=H, seg_model=stm, stops_gdf=sg,
                        limits=limits, lam=args.lam, seed=args.seed + i,
                        iterations=args.iterations, restarts=args.restarts,
                        width=args.width, waiting_model=args.common_lines)
        rows.append({**s.row(), "role": "zero_edit_replicate"})
        reps.append(type("F", (), s.metrics | {
            "generalized_cost": s.metrics["generalized_cost"],
            "unserved_demand": s.metrics["unserved_demand"],
            "served_demand": s.metrics["served_demand"],
            "gc_per_served_trip": s.metrics["gc_per_served_trip"],
            "revenue_veh_hours": s.metrics["revenue_veh_hours"],
            "peak_vehicles": s.metrics["peak_vehicles"]})())
    floor = exp3.noise_floor(reps, effort=effort, lam=args.lam)
    log.info("noise floor at %s: objective %.4f%%, unserved %.4f%%", effort,
             floor.relative_pct["objective"], floor.relative_pct["unserved_demand"])

    best, val, tr = search(pool_ids, score, incompatible,
                           seeds=STAGE_A_SEEDS,
                           max_cardinality=args.max_cardinality,
                           max_evaluations=args.max_evaluations,
                           checkpoint=cp)

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "stageA_states.csv", index=False)
    (OUT / "stageA_result.json").write_text(json.dumps({
        **plan,
        "best": best.key, "best_objective": val,
        "noise_floor": floor.as_dict(),
        "trace": tr.as_dict(),
        "refused": refused,
        "stage": "A — DISCOVERY. These magnitudes are not findings. Gate 12: a "
                 "ranking at this effort inverted outright once (D24), and 2B's "
                 "stage C turned a -0.585% discovery leader into a +0.007% "
                 "certified null.",
    }, indent=2) + "\n")
    log.info("stage A done: %d states scored, best %s at %.6g",
             len(rows), best.key, val)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
