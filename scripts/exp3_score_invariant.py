#!/usr/bin/env python3
"""Reproduce an Experiment 2B number with the Experiment 3 scoring chain.

`exp3_score.score_state` is a second implementation of a fifteen-step chain 2B
already had working. A second implementation that merely *looks* right is how
this project lost three days to an evaluator that reported the wrong waiting
model, so the chain is not trusted until it reproduces a number 2B recorded.

It did not, at first. Without refitting the incumbent to the envelope before
the solve — the step 2B wrote a docstring about — every solve reported
`exchanges=0`, reached −5.03% on unserved demand where Experiment 1 reaches
−6.65%, and returned **byte-identical results for three different seeds**. That
last part is the dangerous one: identical replicates make the same-run noise
floor exactly zero, and a zero floor licenses every margin that is not
precisely nil.

Two states, at 2B's own discovery effort: the zero-edit network and
`splice|011|034|WESHIGW`, whose relative effect 2B recorded as **−0.5846%** on
unserved demand.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cota_opt import geo                                     # noqa: E402
from cota_opt.contract import ContractLimits                 # noqa: E402
from cota_opt.exp3_score import score_state                  # noqa: E402
from cota_opt.geometry import GeometryEdit, SegmentTimeModel  # noqa: E402
from exp3_pin_envelope import load as pin_load              # noqa: E402
from cota_opt.harness import build_harness                   # noqa: E402

OUT = ROOT / "outputs"
TARGET = "splice|011|034|WESHIGW"
EFFORT = (60_000, 2, 32)
#: A discovery-effort re-solve will not land on 2B's number to the digit — the
#: search is stochastic and this is a different process. What it must do is land
#: close enough that the chain is demonstrably the same chain. One noise floor
#: (0.130 points at this effort) is the natural tolerance.
TOLERANCE_PTS = 0.130


def main() -> int:
    sa = pd.read_csv(OUT / "exp2b_stageA.csv")
    if "lambda" in sa:
        sa = sa[sa["lambda"] == 2.0]
    row = sa[sa.set_key == TARGET].iloc[0]
    expected = float(row.unserved_vs_noedit_pct)

    H = build_harness(seed=20260825, common_lines="same_route",
                      with_pathsets=False)
    sg = geo.stops_gdf(H.baseline.feed, H.assumptions["crs"]["projected"])
    stm = SegmentTimeModel.fit(H.baseline.network, sg)
    budget = float(H.baseline.tstats["runtime_min"].sum() / 60.0)
    CONS = pin_load()
    limits = ContractLimits(veh_hour_budget=budget, peak_vehicle_budget=197.0)

    kind, a, b, jx = TARGET.split("|")
    edit = GeometryEdit(kind=kind, route_id=a, with_route=b, junction=jx,
                        description=TARGET)

    def run(edits, tag):
        t = time.time()
        s = score_state(edits, harness=H, seg_model=stm, stops_gdf=sg,
                        limits=limits, lam=2.0, seed=20260825,
                        iterations=EFFORT[0], restarts=EFFORT[1],
                        width=EFFORT[2], waiting_model="same_route",
                        constraints=CONS)
        print(f"  {tag:<28s} unserved {s.metrics['unserved_demand']:9.1f}  "
              f"gc {s.metrics['generalized_cost']:11.0f}  "
              f"vh {s.metrics['revenue_veh_hours']:7.1f}  "
              f"scale x{s.incumbent_scale:.4f}  {time.time()-t:.0f}s")
        return s

    print("=" * 88)
    print("SCORING-CHAIN INVARIANT — reproduce an Experiment 2B number")
    print("=" * 88)
    print(f"  target        {TARGET}")
    print(f"  2B recorded   {expected:+.4f}% unserved vs no edit @ "
          f"{EFFORT[0]}/{EFFORT[1]}/{EFFORT[2]}")
    print(f"  tolerance     {TOLERANCE_PTS} points (one discovery-effort floor)")
    print()

    base = run([], "<none>")
    cand = run([edit], TARGET)
    got = 100.0 * (cand.metrics["unserved_demand"]
                   / base.metrics["unserved_demand"] - 1.0)
    gap = abs(got - expected)
    ok = gap <= TOLERANCE_PTS

    print()
    print(f"  reproduced    {got:+.4f}%   (2B: {expected:+.4f}%, "
          f"gap {gap:.4f} points)")
    print(f"  VERDICT: {'PASS' if ok else 'FAIL'}")
    if not ok:
        print("  The Experiment 3 scoring chain is NOT the chain 2B validated.")
        print("  Do not score anything until it is.")

    res = {"pass": ok, "target": TARGET, "expected_pct": expected,
           "reproduced_pct": got, "gap_points": gap,
           "tolerance_points": TOLERANCE_PTS,
           "effort": f"{EFFORT[0]}/{EFFORT[1]}/{EFFORT[2]}",
           "zero_edit": base.row(), "candidate": cand.row(),
           "why_this_exists":
               "A second implementation of the scoring chain that merely looks "
               "right is how this project lost three days to an evaluator "
               "reporting the wrong waiting model. Without refitting the "
               "incumbent to the envelope, every solve reported exchanges=0 "
               "and three seeds returned byte-identical results — a zero noise "
               "floor, which licenses every margin."}
    (OUT / "exp3" / "score_invariant.json").write_text(
        json.dumps(res, indent=2) + "\n")
    print(f"\nartifacts: {OUT / 'exp3' / 'score_invariant.json'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
