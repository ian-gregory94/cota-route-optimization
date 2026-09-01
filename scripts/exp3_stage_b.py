#!/usr/bin/env python3
"""Experiment 3 Stage B — certification of the 39 corrected-negative singles.

Preregistered in `EXPERIMENT3_STAGE_B_PREREGISTRATION.md`, committed before any
cell ran. This runs the cells; `exp3_stage_b_report.py` does the analysis, and
the criterion it applies is fixed in that document, not here.

200 cells: the control plus 39 candidates, each at five predeclared seeds,
20 restarts. Path sets are rebuilt per (state, seed) on purpose — sharing them
across seeds would suppress part of the very seed-to-seed variation the paired
statistic is measuring.

One cell per unit of work, idempotent, slice-bounded, shardable. A certification
cell is ~11 minutes warm and ~17 cold, so it does not fit a foreground tool call
and runs under the loop pattern (OPERATIONS 3, 18).

    python scripts/exp3_stage_b.py --list
    bash scripts/exp3_stage_b_shard.sh 0/2
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
from cota_opt.contract import ContractLimits, ContractViolation   # noqa: E402
from cota_opt.exp3_cell import run_cell                           # noqa: E402
from cota_opt.firewall import (EXP3_STAGE_B,                      # noqa: E402
                               EXP3_STAGE_B_ESCALATED,
                               ObservationStore, admit)
from cota_opt.geometry import SegmentTimeModel                    # noqa: E402
from cota_opt.harness import build_harness                        # noqa: E402
from cota_opt.mutate import edit_from_record                      # noqa: E402
from exp3_pin_envelope import load as pin_load                    # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("stage_b")
OUT = ROOT / "outputs" / "exp3"
NULL = "<none>"


def contract(escalated: bool):
    return EXP3_STAGE_B_ESCALATED if escalated else EXP3_STAGE_B


def store(escalated: bool) -> ObservationStore:
    return ObservationStore(OUT / ("observations_stageB_esc" if escalated
                                   else "observations_stageB"))


def promoted() -> list[str]:
    """The 39, from the frozen Stage A census. Fixed before Stage B ran."""
    d = json.loads((OUT / "stageA_census.json").read_text())
    return sorted(r["state"] for r in d["states"] if r["effect_pct"] < 0)


def cells(escalated: bool, only: list[str] | None = None) -> list[tuple[str, int]]:
    c = contract(escalated)
    states = [NULL] + (only if only is not None else promoted())
    return [(s, seed) for s in states for seed in c.solver.seeds]


def done(escalated: bool) -> set[tuple[str, int]]:
    """Cells with an admissible receipt under this contract and source."""
    c = contract(escalated)
    frozen_f = OUT / "EVAL_PATH_FROZEN"
    frozen = frozen_f.read_text().strip() if frozen_f.exists() else None
    out = set()
    for r in store(escalated).all():
        if r.spec.contract_digest != c.digest:
            continue
        if frozen and r.code_version != frozen:
            continue
        out.add((r.spec.state_key or NULL, r.spec.seed))
    return out


def edits_for(spec: str, idx: dict):
    if spec == NULL:
        return []
    out = []
    for part in spec.split("+"):
        key = part.split("#")[0]
        hit = idx.get(part) or idx.get(key) or next(
            (m for m in idx.values() if m["id"].split("#")[0] == key), None)
        if hit is None:
            raise SystemExit(f"no pool entry for {part!r}")
        out.append(edit_from_record(hit))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--escalated", action="store_true",
                    help="40 restarts, same five seeds, nothing else changed")
    ap.add_argument("--only", default="",
                    help="comma-separated states to run (escalation subset); "
                         "the control is always included")
    ap.add_argument("--shard", default="",
                    help="i/n — every nth cell of a CANONICALLY SORTED list "
                         "(OPERATIONS 12); the union is checked by the report")
    ap.add_argument("--deadline-seconds", type=float, default=1400.0)
    ap.add_argument("--cell-seconds", type=float, default=760.0,
                    help="a 20-restart cell, warm path sets")
    ap.add_argument("--cold-extra", type=float, default=420.0)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    deadline = time.time() + args.deadline_seconds

    only = [s for s in args.only.split(",") if s.strip()] or None
    c = contract(args.escalated)
    have = done(args.escalated)
    todo = [x for x in sorted(cells(args.escalated, only)) if x not in have]
    total = len(todo)
    if args.shard:
        i, n = (int(v) for v in args.shard.split("/"))
        todo = [x for j, x in enumerate(todo) if j % n == i]
    if args.list:
        for s, seed in todo:
            print(f"{s}\t{seed}")
        return 0
    if not todo:
        log.info("all cells complete for %s", c.version)
        return 0
    log.info("%s: %d cells remaining%s", c.version, total,
             f", {len(todo)} in this shard" if args.shard else "")

    H = build_harness(seed=c.solver.seeds[0], common_lines=c.evaluator,
                      with_pathsets=False)
    sg = geo.stops_gdf(H.baseline.feed, H.assumptions["crs"]["projected"])
    stm = SegmentTimeModel.fit(H.baseline.network, sg)
    limits = ContractLimits(
        veh_hour_budget=float(H.baseline.tstats["runtime_min"].sum() / 60.0),
        peak_vehicle_budget=197.0, required_waiting_model=c.evaluator)
    CONS = pin_load()
    idx = {m["id"]: m for m in
           json.loads((OUT / "mutation_pool.json").read_text())["mutations"]}
    st = store(args.escalated)
    rows = OUT / (f"stageB{'_esc' if args.escalated else ''}"
                  f"{'.shard' + args.shard.split('/')[0] if args.shard else ''}.jsonl")

    n_done = 0
    for state, seed in todo:
        edits = edits_for(state, idx)
        ps_key = key_of("exp3_pathsets",
                        exp3.pathset_cache_params(edits, seed, c.evaluator))
        ps_path = cache_dir() / f"{ps_key}.pkl"
        psc: dict = {}
        if ps_path.exists():
            try:
                psc = pickle.loads(ps_path.read_bytes())
            except Exception as e:
                log.warning("cache %s unreadable (%s)", ps_key, e)
                psc = {}
        warm = bool(psc)
        need = args.cell_seconds + (0 if warm else args.cold_extra)
        if time.time() + need > deadline:
            log.info("stopping cleanly: %.0fs needed for %s/%d, %.0fs left",
                     need, state, seed, deadline - time.time())
            break

        t0 = time.time()
        try:
            s, rec = run_cell(c, edits, harness=H, seg_model=stm, stops_gdf=sg,
                              limits=limits, constraints=CONS,
                              pathset_cache=psc, cache_hit=warm, seed=seed)
        except ContractViolation as v:
            log.error("%s/%d REFUSED: %s", state, seed, v)
            continue
        if not warm and psc:
            try:
                ps_path.write_bytes(pickle.dumps(psc, protocol=pickle.HIGHEST_PROTOCOL))
            except Exception as e:
                log.warning("could not cache path sets: %s", e)
        st.put(rec)
        v = admit(rec, c)
        row = {**s.row(), "state": state, "seed": seed,
               "contract": c.digest, "escalated": bool(args.escalated),
               "receipt_digest": rec.digest, "code_version": rec.code_version,
               "restarts_completed": rec.restarts_completed,
               "converged": rec.converged, "admissible": bool(v)}
        with rows.open("a") as f:
            f.write(json.dumps(row) + "\n")
            f.flush()
            os.fsync(f.fileno())
        n_done += 1
        log.info("%-46.46s seed %d obj=%.6f restarts=%d conv=%s adm=%s %.0fs",
                 state, seed, s.metrics["objective"], rec.restarts_completed,
                 rec.converged, bool(v), time.time() - t0)
        if not v:
            log.error("INADMISSIBLE:\n%s", v)
    log.info("slice ran %d cells", n_done)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
