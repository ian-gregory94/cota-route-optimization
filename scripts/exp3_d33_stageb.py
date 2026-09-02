#!/usr/bin/env python3
"""D33 re-measured at Stage B effort — preregistration §7.

Design frozen in `EXPERIMENT3_D33_STAGEB_DESIGN.md` before any gap here was
computed. This file runs that design; it does not choose it.

D33's method is imported from `exp3_gap_benchmark`, not reimplemented, so the
discovery-effort measurement stays byte-reproducible and the two runs differ in
exactly the declared way. **Only the anchor changes**: the delivered plan comes
from the frozen Stage B configuration on each of the five predeclared seeds
instead of a 2-restart width-32 solve on one seed. The exact reference is
exhaustive enumeration and has no effort parameter.

Two phases, because their costs differ by three orders of magnitude:

  A. anchors   -- 25 Stage B-effort solves, ~15 min each. Each reproduced plan
                  MUST match the stored receipt's plan_digest or the run stops.
  B. gaps      -- 375 enumerations, sub-second to ~75 s each.

    python scripts/exp3_d33_stageb.py --phase anchors --shard 0/2
    python scripts/exp3_d33_stageb.py --phase gaps
    python scripts/exp3_d33_stageb.py --status
"""
from __future__ import annotations

import argparse
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
from cota_opt.contract import ContractLimits                      # noqa: E402
from cota_opt.exp3_cell import run_cell                           # noqa: E402
from cota_opt.firewall import EXP3_STAGE_B, ObservationStore, digest  # noqa: E402
from cota_opt.geometry import SegmentTimeModel                    # noqa: E402
from cota_opt.harness import build_harness                        # noqa: E402
from cota_opt.mutate import edit_from_record                      # noqa: E402
from exp3_pin_envelope import load as pin_load                    # noqa: E402

import exp3_gap_benchmark as G                                    # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("d33b")
OUT = ROOT / "outputs" / "exp3"
D33B = OUT / "d33_stageb"
NULL = "<none>"

#: Frozen by EXPERIMENT3_D33_STAGEB_DESIGN.md. Every treatment is an actual
#: Stage B state so its plan digest can be verified against a stored receipt.
NETWORKS: dict[str, str] = {
    "control":            NULL,
    "lengthen_add_stop":  "add_stop-010#22c4c35ac5b2",
    "lengthen_extend":    "extend-025#441ece050fe8",
    "shorten_truncate":   "truncate-035#7cdb09a45253",
    "shorten_straighten": "straighten-021#110f4a755fe7",
}
STRATA = G.STRATA
SIZES = G.SIZES
SEEDS = list(EXP3_STAGE_B.solver.seeds)


def anchor_path(net: str, seed: int) -> Path:
    return D33B / "anchors" / f"{net}.{seed}.json"


def gaps_path() -> Path:
    return D33B / "gaps.jsonl"


def stage_b_receipts() -> dict:
    st = ObservationStore(OUT / "observations_stageB")
    out = {}
    for r in st.all():
        if r.spec.contract_digest == EXP3_STAGE_B.digest:
            out[(r.spec.state_key or NULL, r.spec.seed)] = r
    return out


def edits_for(state: str, idx: dict):
    if state == NULL:
        return []
    return G.resolve(state, idx)


# --------------------------------------------------------------------------
# Phase A -- anchors, at Stage B effort, digest-verified
# --------------------------------------------------------------------------
def run_anchors(shard: str, deadline: float) -> int:
    idx = G.pool_index()
    receipts = stage_b_receipts()
    want = [(n, s) for n in NETWORKS for s in SEEDS]
    want.sort()
    if shard:
        i, k = (int(v) for v in shard.split("/"))
        want = [x for j, x in enumerate(want) if j % k == i]
    todo = [(n, s) for n, s in want if not anchor_path(n, s).exists()]
    if not todo:
        log.info("all anchors present for this shard")
        return 0
    log.info("%d anchors to reproduce", len(todo))

    H = build_harness(seed=SEEDS[0], common_lines=EXP3_STAGE_B.evaluator,
                      with_pathsets=False)
    sg = geo.stops_gdf(H.baseline.feed, H.assumptions["crs"]["projected"])
    stm = SegmentTimeModel.fit(H.baseline.network, sg)
    limits = ContractLimits(
        veh_hour_budget=float(H.baseline.tstats["runtime_min"].sum() / 60.0),
        peak_vehicle_budget=197.0,
        required_waiting_model=EXP3_STAGE_B.evaluator)
    CONS = pin_load()

    for net, seed in todo:
        if time.time() + 1300 > deadline:
            log.info("stopping cleanly before %s/%d", net, seed)
            break
        state = NETWORKS[net]
        rec = receipts.get((state, seed))
        if rec is None:
            raise SystemExit(f"no Stage B receipt for {state}/{seed}; "
                             "the design named a state Stage B never ran")
        edits = edits_for(state, idx)
        ps_key = key_of("exp3_pathsets", exp3.pathset_cache_params(
            edits, seed, EXP3_STAGE_B.evaluator))
        ps_path = cache_dir() / f"{ps_key}.pkl"
        psc: dict = {}
        if ps_path.exists():
            try:
                psc = pickle.loads(ps_path.read_bytes())
            except Exception as e:
                log.warning("cache %s unreadable (%s)", ps_key, e)
        warm = bool(psc)

        t0 = time.time()
        s, _ = run_cell(EXP3_STAGE_B, edits, harness=H, seg_model=stm,
                        stops_gdf=sg, limits=limits, constraints=CONS,
                        pathset_cache=psc, cache_hit=warm, seed=seed)
        got = digest(s.plan)

        # The check the design turns on. A mismatch is a reproducibility
        # failure, not a nuisance: stop, report nothing, escalate.
        if got != rec.plan_digest:
            raise SystemExit(
                f"ANCHOR DIGEST MISMATCH for {net} ({state}) seed {seed}:\n"
                f"  Stage B receipt plan_digest : {rec.plan_digest}\n"
                f"  reproduced plan digest      : {got}\n"
                "Stage B is not reproducing under its own frozen contract. "
                "Nothing further may be computed from these plans. STOP.")

        headways = (dict(s.plan.headways) if hasattr(s.plan, "headways")
                    else dict(s.plan))
        anchor_path(net, seed).parent.mkdir(parents=True, exist_ok=True)
        anchor_path(net, seed).write_text(json.dumps({
            "network": net, "state": state, "seed": seed,
            "contract": EXP3_STAGE_B.digest,
            "plan_digest": got,
            "receipt_plan_digest": rec.plan_digest,
            "digest_verified": True,
            "objective": s.metrics["objective"],
            "receipt_objective": rec.objective,
            "objective_matches": abs(s.metrics["objective"] - rec.objective) < 1e-9,
            "headways": {f"{a}|{b}": float(v) for (a, b), v in headways.items()}
            if headways and isinstance(next(iter(headways)), tuple)
            else {str(k): float(v) for k, v in headways.items()},
            "seconds": round(time.time() - t0, 1),
        }, indent=2))
        log.info("%-20s seed %d  digest VERIFIED %s  obj=%.6f  %.0fs",
                 net, seed, got, s.metrics["objective"], time.time() - t0)
    return 0


# --------------------------------------------------------------------------
# Phase B -- gaps, anchored on the verified Stage B plans
# --------------------------------------------------------------------------
def load_anchor(net: str, seed: int) -> dict | None:
    p = anchor_path(net, seed)
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    if not d.get("digest_verified"):
        raise SystemExit(f"anchor {net}/{seed} is not digest-verified")
    out = {}
    for k, v in d["headways"].items():
        out[tuple(k.split("|")) if "|" in k else k] = float(v)
    return out


def done_gaps() -> set[tuple]:
    p = gaps_path()
    if not p.exists():
        return set()
    out = set()
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        out.add((r["network"], r["seed"], r["stratum"], r["n_free"]))
    return out


def run_gaps(deadline: float, max_combos: int) -> int:
    idx = G.pool_index()
    have = done_gaps()
    todo = [(n, sd, st, k)
            for n in NETWORKS for sd in SEEDS for st in STRATA for k in SIZES
            if (n, sd, st, k) not in have
            and G.K_RUNGS ** k <= max_combos]
    if not todo:
        log.info("all gap cells complete")
        return 0
    log.info("%d gap cells remaining", len(todo))

    H = build_harness(seed=SEEDS[0], common_lines=EXP3_STAGE_B.evaluator,
                      with_pathsets=False)
    sg = geo.stops_gdf(H.baseline.feed, H.assumptions["crs"]["projected"])
    stm = SegmentTimeModel.fit(H.baseline.network, sg)
    CONS = pin_load()
    judges: dict[str, tuple] = {}

    for net, seed, stratum, n in todo:
        if time.time() + 120 > deadline:
            log.info("stopping cleanly before %s/%d/%s/%d", net, seed, stratum, n)
            break
        anchor = load_anchor(net, seed)
        if anchor is None:
            continue                      # its anchor has not been produced yet
        if net not in judges:
            j, inc, jnet = G.build_judge(edits_for(NETWORKS[net], idx),
                                         H, sg, stm, CONS)
            judges[net] = (j, inc, jnet)
        judge, incumbent, jnet = judges[net]

        free = G.choose_free(judge, stratum, n, net=jnet)
        lads = G.restricted_ladders(judge, free, G.K_RUNGS, anchor)
        t0 = time.time()
        exact_obj, _, n_eval = G.exact(judge, lads)
        t_exact = time.time() - t0

        # The delivered objective is the anchor plan's own objective under the
        # production evaluator -- the same plan Stage B shipped for this
        # (state, seed), priced the same way the exact reference is priced.
        import numpy as np
        keys = list(judge.model.keys)
        h = np.array([float(anchor[k]) for k in keys])
        fit = judge.model.evaluate_array(h)
        delivered = fit.scalarized(judge.model.w.unserved, G.LAM)

        gap = delivered - exact_obj
        row = {"network": net, "state": NETWORKS[net], "seed": seed,
               "stratum": stratum, "n_free": n, "k_rungs": G.K_RUNGS,
               "combinations": n_eval,
               "exact_objective": exact_obj,
               "delivered_objective": delivered,
               "gap_absolute": gap,
               "gap_pct": 100.0 * gap / exact_obj if exact_obj else None,
               "anchor": "stageb_solution",
               "effort": "stage_b", "contract": EXP3_STAGE_B.digest,
               "seconds_exact": round(t_exact, 1),
               "lambda": G.LAM, "methodology_generation": "gen1"}
        gaps_path().parent.mkdir(parents=True, exist_ok=True)
        with gaps_path().open("a") as f:
            f.write(json.dumps(row) + "\n")
            f.flush()
            os.fsync(f.fileno())
        log.info("%-20s seed %d %-16s N=%-2d gap=%+.7f%%  %.1fs",
                 net, seed, stratum, n, row["gap_pct"] or 0.0, t_exact)
    return 0


def status() -> int:
    a = sum(1 for n in NETWORKS for s in SEEDS if anchor_path(n, s).exists())
    g = len(done_gaps())
    print(f"anchors {a}/{len(NETWORKS) * len(SEEDS)}   "
          f"gaps {g}/{len(NETWORKS) * len(SEEDS) * len(STRATA) * len(SIZES)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=("anchors", "gaps"), default="anchors")
    ap.add_argument("--shard", default="")
    ap.add_argument("--deadline-seconds", type=float, default=1500.0)
    ap.add_argument("--max-combos", type=int, default=80_000)
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    if args.status:
        return status()
    deadline = time.time() + args.deadline_seconds
    D33B.mkdir(parents=True, exist_ok=True)
    if args.phase == "anchors":
        return run_anchors(args.shard, deadline)
    return run_gaps(deadline, args.max_combos)


if __name__ == "__main__":
    raise SystemExit(main())
