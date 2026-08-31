#!/usr/bin/env python3
"""Section 5: retest Experiment 2B's decisive comparison under matched starts.

2B certified NULL for `splice|011|034|WESHIGW` at 400000/20/0 over three seeds.
That certification was produced with `starts="incumbent"`, which means the
control kept its incumbent and the treatment silently fell back to a greedy
build (D27) -- an asymmetry decided by the treatment.

D27's scoping says certification effort dissolves that gap (0.2240% at
discovery, 0.0082% at certification), and 2B's own record agrees without having
known why: it logged `discovery_effort_pct = -0.5846` against
`effect_pct = 0.0065` at certification, with `gate_12_stable = false`. The
discovery effect had already vanished under effort; nobody had a mechanism for
it.

None of that substitutes for the direct check. This reruns the decisive
comparison -- control and candidate, all three certification seeds,
`starts="both"` for every cell -- through the firewall, and produces
`ComparisonResult` artifacts rather than a pair of numbers.

Pass condition: the candidate stays inside the certification/noise criterion
and 2B's NULL stands, with a methodological note. Failure condition: it becomes
materially beneficial or harmful, and 2B is reopened.

One (state, seed) cell per process, idempotent, slice-bounded.

    bash scripts/exp2b_confirm_slice.sh 560
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
from cota_opt.firewall import (CERTIFICATION, ExperimentContract,  # noqa: E402
                               ObservationStore, admit, compare)
from cota_opt.geometry import SegmentTimeModel                    # noqa: E402
from cota_opt.harness import build_harness                        # noqa: E402
from cota_opt.mutate import edit_from_record                      # noqa: E402
from exp3_pin_envelope import load as pin_load                    # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("exp2b_confirm")
OUT = ROOT / "outputs" / "exp3"
STORE = ObservationStore(OUT / "observations_cert")
RESULT = ROOT / "outputs" / "exp2b_confirmation.json"

#: 2B's own certification effort and seeds, unchanged. The only thing this
#: retest alters is the start policy, which is the thing under suspicion.
EXP2B_CONFIRM = ExperimentContract(
    experiment="exp2b", version="2b-confirm-1", stage="certification",
    objective="lambda_scalarized_path_level", objective_version="lambda=2.0",
    evaluator="same_route", envelope="pinned_unedited_baseline",
    pathset_policy="rebuilt_per_state", pool_version="exp3-pool-v1",
    methodology_generation="gen1", solver=CERTIFICATION,
    allowed_treatment_differences=frozenset({
        "state_digest", "state_key", "cardinality", "members",
        "pathset_digest"}),
    opportunity_tolerances={"evaluations_performed": 1.0},
    noise_floor=0.00287,        # 2B's own certification floor, 0.287 points
)

CANDIDATE = "splice-011-034-WESHIGW"
CELLS = [(state, seed) for seed in CERTIFICATION.seeds
         for state in ("null", CANDIDATE)]


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


def done() -> dict:
    got = {}
    for r in STORE.all():
        got[(r.spec.state_key or "null", r.spec.seed)] = r
    return got


def report(have: dict) -> int:
    """Compare candidate against control, seed by seed, through the firewall."""
    rows, verdicts = [], []
    for seed in CERTIFICATION.seeds:
        c = have.get(("<none>", seed)) or have.get(("null", seed))
        t = next((v for (k, s), v in have.items()
                  if s == seed and k not in ("<none>", "null")), None)
        if not (c and t):
            continue
        res = compare(c, t, EXP2B_CONFIRM)
        if not res:
            rows.append({"seed": seed, "admissible": False,
                         "refusal": str(res)})
            verdicts.append(None)
            continue
        rows.append({"seed": seed, "admissible": True, **res.as_dict()})
        verdicts.append(res.effect_pct)

    if not verdicts or any(v is None for v in verdicts):
        print("\nNot every seed produced an admissible comparison yet.")
    else:
        mean = sum(verdicts) / len(verdicts)
        floor_pct = EXP2B_CONFIRM.noise_floor * 100
        measurable = abs(mean) > floor_pct
        print(f"\n{'seed':>12s} {'effect %':>12s}")
        for r, v in zip(rows, verdicts):
            print(f"{r['seed']:12d} {v:+12.4f}")
        print(f"{'mean':>12s} {mean:+12.4f}   floor {floor_pct:.4f}%  "
              f"({abs(mean)/floor_pct:.2f} floors)")
        print(f"\n2B recorded, incumbent starts : +0.0065% (0.02 floors, NULL)")
        print(f"this retest, matched starts   : {mean:+.4f}% "
              f"({abs(mean)/floor_pct:.2f} floors, "
              f"{'MEASURABLE' if measurable else 'NULL'})")
        if not measurable:
            print("\nPASS — 2B's certified NULL survives matched starts.")
        else:
            print("\nFAIL — the candidate is measurable under matched starts. "
                  "Experiment 2B must be reopened.")
        RESULT.write_text(json.dumps(
            {"contract": EXP2B_CONFIRM.digest,
             "methodology_generation": "gen1",
             "candidate": CANDIDATE, "effort": "400000/20/0",
             "seeds": list(CERTIFICATION.seeds),
             "start_policy": CERTIFICATION.start_policy.value,
             "per_seed": rows, "mean_effect_pct": mean,
             "floor_pct": floor_pct, "measurable": measurable,
             "recorded_2b_effect_pct": 0.0065,
             "recorded_2b_discovery_pct": -0.5845518890625012,
             "verdict": ("NULL — 2B's conclusion survives matched starts"
                         if not measurable else
                         "MEASURABLE — 2B must be reopened")}, indent=2) + "\n")
        print(f"\nwrote {RESULT}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deadline-seconds", type=float, default=540.0)
    ap.add_argument("--cell-seconds", type=float, default=520.0)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    deadline = time.time() + args.deadline_seconds

    have = done()
    seen = {(k if k == "<none>" else k.split("#")[0], sd) for k, sd in have}
    todo = [(s, sd) for s, sd in CELLS
            if (("<none>" if s == "null" else s), sd) not in seen]
    if args.report or args.list or not todo:
        for s, sd in todo:
            print(f"{s}\t{sd}")
        if args.report or not todo:
            return report(have)
        return 0

    H = build_harness(seed=CERTIFICATION.seeds[0], common_lines="same_route",
                      with_pathsets=False)
    sg = geo.stops_gdf(H.baseline.feed, H.assumptions["crs"]["projected"])
    stm = SegmentTimeModel.fit(H.baseline.network, sg)
    limits = ContractLimits(
        veh_hour_budget=float(H.baseline.tstats["runtime_min"].sum() / 60.0),
        peak_vehicle_budget=197.0, required_waiting_model="same_route")
    CONS = pin_load()

    for state, seed in todo:
        edits = edits_for(state)
        ps_key = key_of("exp3_pathsets",
                        exp3.pathset_cache_params(edits, seed, "same_route"))
        ps_path = cache_dir() / f"{ps_key}.pkl"
        warm = ps_path.exists()
        need = args.cell_seconds if warm else args.cell_seconds + 340
        if time.time() + need > deadline:
            log.info("stopping cleanly: %.0fs needed, %.0fs left",
                     need, deadline - time.time())
            break
        psc = {}
        if warm:
            try:
                psc = pickle.loads(ps_path.read_bytes())
            except Exception:
                psc = {}
        fresh = not psc
        try:
            s, rec = run_cell(EXP2B_CONFIRM, edits, harness=H, seg_model=stm,
                              stops_gdf=sg, limits=limits, constraints=CONS,
                              pathset_cache=psc, cache_hit=warm, seed=seed)
        except ContractViolation as v:
            log.error("%s seed %d REFUSED: %s", state, seed, v)
            continue
        if fresh and psc:
            ps_path.write_bytes(pickle.dumps(psc, protocol=pickle.HIGHEST_PROTOCOL))
        STORE.put(rec)
        v = admit(rec, EXP2B_CONFIRM)
        log.info("%-26s seed %d obj=%.7g unserved=%.1f starts=%s won=%s "
                 "restarts=%d admissible=%s", state, seed,
                 s.metrics["objective"], s.metrics["unserved_demand"],
                 rec.starts_attempted, rec.winning_start,
                 rec.restarts_completed, bool(v))
        if not v:
            log.error("INADMISSIBLE:\n%s", v)
    return report(done())


if __name__ == "__main__":
    raise SystemExit(main())
