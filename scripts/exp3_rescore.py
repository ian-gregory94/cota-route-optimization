#!/usr/bin/env python3
"""Re-score the Phase A1 states that were solved in the wrong basin (D27).

Not a change to the preregistered policy — a completion of it. The policy says
every unique state gets "its own rebuilt path set, frequency re-optimization,
and Model B evaluation". These 40 states got a frequency re-optimization that
stopped in a different basin from the one the other 75 landed in, because
whether the optimizer accepted the incumbent start was decided by the edit
applied to the network (D27). Re-scoring them under a start set that does not
depend on the treatment makes all 115 comparable, which is what the policy
asked for in the first place.

Only states ACCEPTED on the incumbent start need this. A state that fell back
already ran the greedy build, and `starts="both"` keeps the best of the two, so
its number cannot move.

Every cell runs through ``exp3_cell.run_cell`` under ``EXP3_STAGE_A``, so it
produces an ``ExecutionReceipt`` as well as a score, and the receipt goes into
the ``ObservationStore``. That is the point: the corrected census has to be
admissible evidence, not merely better numbers. ``exp3_promote.py`` builds its
frontier from comparisons against the re-scored control, and refuses any state
whose receipt is missing or whose comparison the firewall will not admit.

Idempotent and slice-bounded, per OPERATIONS 1-3: it never starts a state the
slice cannot finish, appends with an fsync, and can be re-run until the list is
empty. Path sets are cached to disk per state, so a state interrupted after its
path build costs 1.7 minutes on the retry instead of 7.

    bash scripts/exp3_rescore_slice.sh 470
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
from cota_opt.firewall import (EXP3_STAGE_A, ObservationStore,     # noqa: E402
                               admit)
from cota_opt.geometry import SegmentTimeModel                    # noqa: E402
from cota_opt.harness import build_harness                        # noqa: E402
from cota_opt.mutate import edit_from_record                      # noqa: E402
from exp3_pin_envelope import load as pin_load                    # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("rescore")
OUT = ROOT / "outputs" / "exp3"
ROWS = OUT / "stageA_rescored.jsonl"
CONTRACT = EXP3_STAGE_A
STORE = ObservationStore(OUT / "observations")
STARTS = CONTRACT.solver.start_policy.value


def wanted() -> list[str]:
    return [l.strip() for l in (OUT / "rescore_needed.txt").read_text().splitlines()
            if l.strip()]


def done() -> set[str]:
    """States already re-scored WITH a receipt.

    A row written before the firewall existed carries no receipt, so the state
    it names has a corrected number and no evidence. Treating it as done would
    leave it permanently unpromotable while looking finished, so it is not
    done: it is re-run under a contract.
    """
    out = set()
    if ROWS.exists():
        for line in ROWS.open():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:       # a torn final line is expected, not fatal
                continue
            if r.get("receipt_digest") and r.get("contract") == CONTRACT.digest:
                out.add(r["role"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deadline-seconds", type=float, default=1400.0)
    ap.add_argument("--state-seconds", type=float, default=460.0,
                    help="assumed cost of one state with COLD path sets; a warm "
                         "one is about a quarter of that. Never start a state "
                         "inside this -- a state killed mid-solve is a state "
                         "thrown away, and the loop would retry it forever.")
    ap.add_argument("--lam", type=float, default=exp3.PRIMARY_LAMBDA)
    ap.add_argument("--seed", type=int, default=20260825)
    ap.add_argument("--iterations", type=int, default=60_000)
    ap.add_argument("--restarts", type=int, default=2)
    ap.add_argument("--width", type=int, default=32)
    ap.add_argument("--common-lines", default="same_route")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    deadline = time.time() + args.deadline_seconds

    todo = [s for s in wanted() if s not in done()]
    log.info("%d of %d states still to re-score", len(todo), len(wanted()))
    if args.list or not todo:
        for s in todo:
            print(s)
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
    for role in todo:
        # Cost depends on whether this state's path sets are already built, so
        # the guard has to know which. Charging every state the cold price
        # wastes most of a slice; charging every state the warm price kills one
        # mid-build.
        # (the cache probe happens below; this is the conservative bound)
        if time.time() + args.state_seconds > deadline:
            log.info("stopping cleanly: not enough slice left for another state")
            break
        # Replicates carry their own seed: Phase A1 scored `<none>|repN` at
        # `seed + N`, and that spread IS the noise floor. Re-scoring all three
        # at one seed would return three identical numbers and a floor of zero,
        # which licenses every margin -- the exact failure this project already
        # had once.
        bare = role.split("|")[0]
        seed = args.seed
        if "|rep" in role:
            seed = args.seed + int(role.split("|rep")[1])
        edits = []
        if bare not in ("<none>", "null", ""):
            for part in bare.split("+"):
                key = part.split("#")[0]
                hit = idx.get(part) or idx.get(key) or next(
                    (m for m in idx.values() if m["id"].split("#")[0] == key), None)
                if hit is None:
                    log.error("no pool entry for %r (role %r)", part, role)
                    return 2
                edits.append(edit_from_record(hit))

        # Disk-backed path sets, keyed the same way the certification runner
        # keys them, so the two share one cache instead of building twice.
        ps_key = key_of("exp3_pathsets",
                        exp3.pathset_cache_params(edits, seed,
                                                  args.common_lines))
        ps_path = cache_dir() / f"{ps_key}.pkl"
        warm = ps_path.exists()
        psc: dict = {}
        if warm:
            try:
                psc = pickle.loads(ps_path.read_bytes())
                log.info("path sets from cache for %s", role)
            except Exception as e:
                log.warning("cache %s unreadable (%s), rebuilding", ps_key, e)
                psc = {}
        fresh = not psc
        warm = bool(psc)          # "exists" is not "loaded": a corrupt entry
                                  # is a cold start, and saying otherwise puts
                                  # a false cache_hit in the receipt.

        # A state with warm path sets costs about a quarter of a cold one.
        # Guarding both at the cold price throws away most of every slice.
        need = 150.0 if warm else args.state_seconds
        if time.time() + need > deadline:
            log.info("stopping cleanly: %.0fs needed for %s, %.0fs left",
                     need, role, deadline - time.time())
            break

        t0 = time.time()
        try:
            s, rec = run_cell(CONTRACT, list(edits), harness=H, seg_model=stm,
                              stops_gdf=sg, limits=limits, constraints=CONS,
                              pathset_cache=psc, cache_hit=warm, seed=seed)
        except ContractViolation as v:
            log.warning("%s REFUSED: %s", role, v)
            continue
        STORE.put(rec)
        verdict = admit(rec, CONTRACT)
        if not verdict:
            # A cell that does not satisfy its own contract is not evidence.
            # Recorded, reported, and barred from the census.
            log.error("%s produced an INADMISSIBLE observation:\n%s", role, verdict)

        if fresh and psc:
            try:
                ps_path.write_bytes(pickle.dumps(psc, protocol=pickle.HIGHEST_PROTOCOL))
            except Exception as e:
                log.warning("could not cache path sets for %s: %s", role, e)

        row = {**s.row(), "role": role, "starts": STARTS,
               "repair": s.evaluator.get("incumbent_repair", {}),
               "receipt_digest": rec.digest, "spec_digest": rec.spec.digest,
               "contract": CONTRACT.digest,
               "admissible": bool(admit(rec, CONTRACT))}
        with ROWS.open("a") as f:
            f.write(json.dumps(row) + "\n")
            f.flush()
            os.fsync(f.fileno())
        n += 1
        log.info("%-52.52s obj=%.7g unserved=%.1f vh=%.1f %.0fs",
                 role, s.metrics["objective"], s.metrics["unserved_demand"],
                 s.metrics["revenue_veh_hours"], time.time() - t0)

    log.info("slice re-scored %d states; %d remain",
             n, len([s for s in wanted() if s not in done()]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
