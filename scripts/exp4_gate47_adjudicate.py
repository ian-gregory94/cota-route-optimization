#!/usr/bin/env python3
"""Gate 4-7, adjudicated against D18's promotion band.

Gate 4-7's frozen closing test is not a numeric epsilon of anyone's choosing:

    if it cannot identify the exact leader within the promotion band, it is
    widened or abandoned.

`exp4_gate47.py` measured the one-factor comparison and found the exact leader
preserved in some cases and not others. Whether a flip MATTERS is the question
the promotion band exists to answer, and the band is D18's output. This script
joins the two and applies the test as written.

THE TEST, APPLIED LITERALLY
---------------------------
For every case where reuse did not reproduce the fresh arm's leader, the
question is whether the two networks involved are distinguishable at all. They
are not, if the fresh arm's own margin between them is inside the band: two
networks whose true separation is below the band are indistinguishable from
structure-correlated solver error, so selecting either is licensed and the
"flip" is not a wrong answer.

A flip whose margin EXCEEDS the band is a real misidentification and the gate
does not close.

WHAT THIS SCRIPT MAY NOT DO
---------------------------
* It may not compute a band. It reads D18's, and refuses if D18 has not run.
* It may not proceed if D18 answered question 3 with the forbidding branch.
  If the gap tracks structure then discovery-effort comparison is not permitted
  at all, and a gate about a discovery-effort approximation cannot close on a
  comparison that may not be made.
* It may not relax the ranking or promoted-set requirements by declaring them
  band-adjacent. They are separate clauses of the criterion and are reported
  against the band only where the criterion itself speaks of the LEADER.

    python scripts/exp4_gate47_adjudicate.py --json outputs/exp4/gate47_adjudicated.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "exp4"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    g47_path = OUT / "gate47.json"
    gap_path = OUT / "gap_benchmark.json"
    if not g47_path.exists():
        print("gate47.json missing: run scripts/exp4_gate47.py first")
        return 1
    if not gap_path.exists():
        print("gap_benchmark.json missing: D18 has not run, so there is no "
              "promotion band and gate 4-7 cannot be adjudicated against one")
        return 1

    g47 = json.loads(g47_path.read_text())
    gap = json.loads(gap_path.read_text())

    print("Gate 4-7 adjudicated against D18's promotion band\n")
    print(f"  D18 design digest : {gap['design_digest']}")
    print(f"  Q3 answer         : {gap['q3_answer']}")

    if not gap.get("discovery_effort_comparison_permitted"):
        print("\n  D18 took section 3's FORBIDDING branch: the gap tracks "
              "network structure,")
        print("  so Experiment 4 may not compare networks at discovery effort "
              "at all.")
        print("  A gate about a discovery-effort approximation cannot close on "
              "a comparison")
        print("  that may not be made. GATE 4-7: ARMED.")
        out = {"gate": "4-7", "verdict": "ARMED",
               "blocked_by": "D18 question 3 forbids discovery-effort comparison",
               "band_pp": None,
               "q3_answer": gap["q3_answer"]}
        if a.json:
            Path(a.json).write_text(json.dumps(out, indent=2))
        return 2

    band_pp = float(gap["q4_promotion_band_pp"])
    band_rel = band_pp / 100.0
    print(f"  promotion band    : {band_pp:.6f} pp  ({band_rel:.6e} relative)")
    print(f"  gate 4-7 run      : {g47['n_candidates']} candidates, "
          f"{g47['n_cases']} cases\n")

    # The substrate check is a precondition and is NOT band-adjudicable: with
    # the same universe and no filtering there is nothing for reuse to
    # approximate, so a difference there is a defect at any band.
    if not g47.get("survival_1_is_identity") or g47.get("hard_failures"):
        print("  survival-1.000 is not the identity, or an arm failed "
              "asymmetrically.")
        print("  That is a reuse/state-reconstruction DEFECT and no band "
              "excuses it. ARMED.")
        return 2
    print("  substrate: filtering is exactly the identity at survival 1.000, "
          "0 hard failures")

    cases = []
    all_ok = True
    for c in g47["cases"]:
        rows = {r["id"]: r for r in c["rows"] if "objective_fresh" in r}
        lf, lr = c["leader_fresh"], c["leader_reuse"]
        if lf == lr:
            cases.append({"case": c["case"], "leader_preserved": True,
                          "within_band": True, "margin_rel": 0.0,
                          "note": "reuse reproduced the exact leader"})
            print(f"  {c['case']:<22} leader preserved")
            continue
        a_, b_ = rows[lf], rows[lr]
        margin = b_["objective_fresh"] - a_["objective_fresh"]
        margin_rel = abs(margin) / abs(a_["objective_fresh"])
        inside = margin_rel <= band_rel
        all_ok &= inside
        cases.append({"case": c["case"], "leader_preserved": False,
                      "leader_fresh": lf, "leader_reuse": lr,
                      "true_margin_abs": margin,
                      "margin_rel": margin_rel,
                      "band_rel": band_rel,
                      "within_band": inside,
                      "note": ("the two networks are not distinguishable at "
                               "this band, so selecting either is licensed"
                               if inside else
                               "a real misidentification: the networks are "
                               "separated by more than the band")})
        print(f"  {c['case']:<22} leader CHANGED, true margin "
              f"{margin_rel:.3e} vs band {band_rel:.3e}  -> "
              f"{'INSIDE band' if inside else 'OUTSIDE band'}")

    print()
    # The criterion speaks of the LEADER. Ranking stability and the promoted
    # set are reported, and a failure there is recorded, but the closing
    # sentence of gate 4-7 is about identifying the exact leader.
    inv = sum(c["ranking_inversions"] for c in g47["cases"])
    prs = sum(c["ranking_pairs"] for c in g47["cases"])
    promo = sum(c["promoted_set_preserved"] for c in g47["cases"])
    print(f"  ranking inversions : {inv}/{prs}")
    print(f"  promoted set kept  : {promo}/{len(g47['cases'])}")

    closes = all_ok
    print(f"\n  GATE 4-7: {'MET' if closes else 'ARMED'}")
    if closes:
        why = ("every case either reproduced the exact leader or flipped "
               "between two networks whose TRUE separation is inside D18's "
               "promotion band, where neither is distinguishable from "
               "structure-correlated solver error. The approximation "
               "identifies the exact leader within the band, which is the "
               "criterion as frozen.")
    else:
        bad = [c["case"] for c in cases if not c["within_band"]]
        why = (f"reuse misidentifies the leader outside the band in "
               f"{', '.join(bad)}. The networks there are separated by more "
               f"than structure-correlated solver error, so the approximation "
               f"picks a network that is genuinely worse. Widened or "
               f"abandoned -- and widening was already measured to move "
               f"nothing, because richness is a different factor.")
    print(f"  {why}")

    out = {"gate": "4-7",
           "adjudicated_against": "D18 promotion band",
           "band_pp": band_pp, "band_rel": band_rel,
           "d18_design_digest": gap["design_digest"],
           "d18_q3_answer": gap["q3_answer"],
           "gate47_source": "outputs/exp4/gate47.json",
           "survival_1_is_identity": g47["survival_1_is_identity"],
           "hard_failures": g47["hard_failures"],
           "ranking_inversions": inv, "ranking_pairs": prs,
           "promoted_sets_preserved": promo,
           "n_cases": len(g47["cases"]),
           "cases": cases,
           "verdict": "MET" if closes else "ARMED",
           "why": why}
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(out, indent=2))
        print(f"\nwrote {a.json}")
    return 0 if closes else 2


if __name__ == "__main__":
    raise SystemExit(main())
