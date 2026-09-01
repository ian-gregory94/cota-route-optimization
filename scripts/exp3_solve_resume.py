#!/usr/bin/env python3
"""One network state, one start set, at ANY effort — resumable across slices.

Why this exists
---------------
A certification solve is 400000/20/0: roughly seventy minutes, where a
discovery solve is seven. This sandbox recycles its container on idle and no
tool call may run longer than about ten minutes, so a certification solve
cannot be run in one piece. It has to survive being stopped.

Two things make that exact rather than approximate:

* `optimize_frequencies` already seeds each perturbation restart from
  ``(seed, restart index)`` rather than a shared stream, so restart *k* is
  independent of whether restarts before it ran in this process. Its
  ``resume={"next_restart": k, "best_idx": [...]}`` therefore returns
  *precisely* what an uninterrupted run would have returned.
* The path sets — five and a half of the seven discovery minutes — depend only
  on the network, zones, OD and baseline headways, so they are content-address
  cached per state. The first slice pays for them; every later slice starts
  solving in seconds.

The checkpoint is written after every restart, fsynced, and re-read rather than
trusted: the saved plan is re-evaluated against the model on resume, so a
resumed run cannot inherit a number that no longer matches what it is scored
against.

    python scripts/exp3_solve_resume.py --state null --starts both \
        --iterations 400000 --restarts 20 --width 0 --deadline-seconds 480
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cota_opt import exp3, geo                                   # noqa: E402
from cota_opt.cache import cached                                # noqa: E402
from cota_opt.contract import ContractLimits                     # noqa: E402
from cota_opt.geometry import SegmentTimeModel, apply_edits      # noqa: E402
from cota_opt.harness import build_harness                       # noqa: E402
from cota_opt.mutate import edit_from_record                     # noqa: E402
from exp3_pin_envelope import load as pin_load                   # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("solve_resume")
OUT = ROOT / "outputs" / "exp3"


class Deadline(Exception):
    """Raised out of the progress callback: stop cleanly, having checkpointed."""


def _write_json(path: Path, obj: dict) -> None:
    """Write-then-rename with an fsync, so a kill cannot leave a torn file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as f:
        json.dump(obj, f)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def edits_for(spec: str):
    if spec == "null":
        return []
    pool = json.loads((OUT / "mutation_pool.json").read_text())
    idx = {m["id"]: m for m in pool["mutations"]}
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
    ap.add_argument("--state", required=True)
    ap.add_argument("--starts", default="both",
                    choices=("incumbent", "repaired", "greedy", "both"))
    ap.add_argument("--lam", type=float, default=exp3.PRIMARY_LAMBDA)
    ap.add_argument("--seed", type=int, default=20260825)
    ap.add_argument("--iterations", type=int, default=400_000)
    ap.add_argument("--restarts", type=int, default=20)
    ap.add_argument("--width", type=int, default=0)
    ap.add_argument("--common-lines", default="same_route")
    ap.add_argument("--deadline-seconds", type=float, default=480.0)
    ap.add_argument("--tag", default="")
    ap.add_argument("--out", default="certification.jsonl")
    args = ap.parse_args()

    t_start = time.time()
    deadline = t_start + args.deadline_seconds
    edits = edits_for(args.state)
    effort = f"{args.iterations}/{args.restarts}/{args.width}"
    tag = args.tag or (f"{exp3.state_digest(edits)[:12]}-{args.starts}"
                       f"-{args.iterations}_{args.restarts}_{args.width}"
                       f"-s{args.seed}-l{args.lam:g}")
    ckpt_path = OUT / "certify_ckpt" / f"{tag}.json"
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)

    ckpt = json.loads(ckpt_path.read_text()) if ckpt_path.exists() else {}
    if ckpt.get("done"):
        log.info("%s already complete: objective %.7g", tag, ckpt["objective"])
        print(json.dumps({k: ckpt[k] for k in ("objective", "unserved_demand",
                                               "revenue_veh_hours", "exchanges")}))
        return 0

    # ---- the pieces that do not depend on the solve ------------------------
    from exp2_treatments import _Baseline, fit_incumbent            # noqa: E402
    from cota_opt.configs import period_of_seconds, service_periods  # noqa: E402
    from cota_opt.exp2 import build_setup as path_level_setup       # noqa: E402
    from cota_opt.frequency import optimize_frequencies, repair_to_ladder
    from cota_opt.odmatrix import build_zone_system                 # noqa: E402
    from cota_opt.raptor import build_raptor_network                # noqa: E402
    from cota_opt.routeclass import classify_routes                 # noqa: E402

    H = build_harness(seed=args.seed, common_lines=args.common_lines,
                      with_pathsets=False)
    sg = geo.stops_gdf(H.baseline.feed, H.assumptions["crs"]["projected"])
    stm = SegmentTimeModel.fit(H.baseline.network, sg)
    a = H.assumptions
    pa = a["path_assignment"]
    periods = service_periods(a)
    net, ts = H.baseline.network, H.baseline.tstats
    if edits:
        ed = apply_edits(net, ts, stm, list(edits))
        net, ts = ed.network, ed.tstats

    rn = build_raptor_network(H.baseline.feed, net, ts, sg,
                              walk_radius_m=float(pa["walk_radius_m"]),
                              walk_speed_m_per_min=float(pa["walk_speed_m_per_min"]),
                              periods=periods, with_timetable=False)
    zs = build_zone_system(H.baseline.demand["bg_frame"], sg,
                           radius_m=float(pa["access_radius_m"]),
                           walk_speed_m_per_min=float(pa["walk_speed_m_per_min"]),
                           stop_index=rn.stop_index)
    tp = ts.copy()
    tp["period"] = tp["first_dep_sec"].map(lambda x: period_of_seconds(x, periods))
    rcls = classify_routes(tp.dropna(subset=["period"]), H.baseline.routes)
    b_ed = _Baseline(H.baseline, net, ts)
    CONS = pin_load()

    def setup(cache):
        return path_level_setup(b_ed, rn, zs, H.od, seed=args.seed,
                                route_classes=rcls, with_crowding=False,
                                lock_classes=("peak_express",),
                                constraints=CONS, n_random_scenarios=0,
                                pathset_cache=cache,
                                common_lines=args.common_lines)

    # Path sets are the expensive, solve-independent half. Cache them on the
    # state's own digest so slice two onward starts solving immediately.
    ps_params = {"state": exp3.state_digest(edits), "seed": args.seed,
                 "common_lines": args.common_lines,
                 "config": exp3.config_digest(),
                 "pool": getattr(exp3, "POOL_VERSION", "?")}

    def build_pathsets():
        c: dict = {}
        setup(c)
        return c

    psc = cached("exp3_pathsets", ps_params, build_pathsets)
    judge = setup(psc)
    if judge.checks.get("common_lines") != args.common_lines:
        raise SystemExit(f"evaluator priced as {judge.checks.get('common_lines')!r}")

    incumbent, scale = fit_incumbent(judge, judge.budget.revenue_veh_hours)
    initial, use_greedy = incumbent, False
    audit: dict = {"starts": args.starts}
    if args.starts in ("repaired", "both"):
        fixed, audit = repair_to_ladder(judge.model, judge.budget,
                                        judge.ladders, incumbent)
        audit["starts"] = args.starts
        if fixed is not None:
            initial = fixed
    if args.starts == "greedy":
        initial, use_greedy = None, True
    if args.starts == "both":
        use_greedy = True

    keys = list(judge.model.keys)
    resume = None
    if ckpt.get("best_idx") is not None:
        resume = {"next_restart": ckpt["next_restart"],
                  "best_idx": ckpt["best_idx"], "best_obj": ckpt["best_obj"],
                  "moves": ckpt.get("moves", 0)}
        log.info("resuming %s at restart %d/%d", tag, resume["next_restart"],
                 args.restarts)

    def progress(next_restart, best_idx, best_obj, moves):
        _write_json(ckpt_path, {
            "tag": tag, "state": args.state, "starts": args.starts,
            "effort": effort, "seed": args.seed, "lambda": args.lam,
            "next_restart": int(next_restart),
            "best_idx": [int(v) for v in np.asarray(best_idx).tolist()],
            "best_obj": float(best_obj), "moves": int(moves),
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        left = deadline - time.time()
        log.info("restart %d/%d  best=%.7g  %.0fs left",
                 next_restart, args.restarts, best_obj, left)
        # Never START a restart the slice cannot finish. The per-restart cost is
        # measured from the START OF THE SOLVE, not of the process: the path-set
        # build is a one-off that the first slice pays and no later slice does,
        # and charging it to restart zero makes the first slice refuse to run a
        # restart it had time for.
        base = resume["next_restart"] if resume else 0
        done = max(next_restart - base, 1)
        per = (time.time() - t_solve[0]) / done
        if next_restart < args.restarts and left < per * 1.15:
            raise Deadline()

    t_solve = [time.time()]
    last = [0.0]

    def on_pass(phase, evals, max_evals, moves, cur):
        now = time.time()
        if now - last[0] < 20.0:
            return
        last[0] = now
        log.info("  %-10s pass: %d/%d evals, %d moves, obj=%.7g, %.0fs in, "
                 "%.0fs left", phase, evals, max_evals, moves, cur,
                 now - t_solve[0], deadline - now)

    try:
        r = optimize_frequencies(
            judge.model, judge.budget, ladder=[], unserved_multiplier=args.lam,
            local_search_iterations=args.iterations, seed=args.seed,
            ladders=judge.ladders, initial=initial, n_restarts=args.restarts,
            candidate_width=args.width, greedy_start=use_greedy,
            resume=resume, progress=progress, on_pass=on_pass)
    except Deadline:
        log.info("slice deadline: checkpointed, %s not finished", tag)
        return 7

    hw = dict(judge.baseline_plan.headways)
    for k, v in r.plan.headways.items():
        if k in hw:
            hw[k] = float(v)
    fit = judge.model.evaluate_array(np.array([hw[k] for k in judge.model.keys]))
    m = exp3.metrics(fit, args.lam)
    row = {"tag": tag, "state": args.state, "starts": args.starts,
           "effort": effort, "seed": args.seed, "lambda": args.lam,
           "incumbent_scale": scale, "repair": audit,
           "exchanges": r.meta.get("exchanges"),
           "n_starts": r.meta.get("n_starts"),
           "seconds_total": round(time.time() - t_start, 1), **m}
    _write_json(ckpt_path, {**row, "done": True,
                            "best_idx": ckpt.get("best_idx"),
                            "next_restart": args.restarts})
    with (OUT / args.out).open("a") as f:
        f.write(json.dumps(row) + "\n")
        f.flush()
        os.fsync(f.fileno())
    log.info("%s DONE obj=%.7g unserved=%.1f vh=%.1f", tag, m["objective"],
             m["unserved_demand"], m["revenue_veh_hours"])
    print(json.dumps({k: row[k] for k in ("objective", "unserved_demand",
                                          "revenue_veh_hours", "exchanges")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
