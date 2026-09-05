#!/usr/bin/env python3
"""Build and freeze `pre_exp4_baseline_v1` — the incumbent Experiment 4 must beat.

EXPERIMENT4_CONTRACT.md fixes the hierarchy, and each step must be beaten in
turn:

    published COTA schedule -> Exp 1 frequency optimum
                            -> Exp 3 constrained route-mutation optimum
                            -> Exp 4 greenfield optimum

Experiment 2/2B contributes no incumbent geometry: it certified the null.

Two rules from the contract are load-bearing here.

**The tied set, not seed 1.** "If Experiment 3 certifies several structurally
different networks inside one noise floor, seed 1 is not 'the Exp 3 network.'"
So the incumbent is computed as the leader PLUS every certified candidate the
leader does not separate from, read out of the pairwise matrix rather than
assumed. Experiment 3's leader separates from all 28 others, so the set is a
singleton -- but it is a singleton because that was computed, and the same
script would carry five if five tied.

**A stored score is a reference, never a denominator (D24).** This file records
identities, digests and the effort each was measured at. It does NOT record a
number for Experiment 4 to divide by. Every promoted Exp 4 network is compared
against this incumbent re-solved in the same run at matched convergence.

    python scripts/exp4_baseline.py --write
    python scripts/exp4_baseline.py --verify
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "outputs" / "exp4"
BASELINE = OUT / "pre_exp4_baseline_v1.json"

from cota_opt.firewall import (EXP3_STAGE_B,                     # noqa: E402
                               EXP3_STAGE_B_ESCALATED)


def _git(*a: str) -> str:
    return subprocess.run(("git",) + a, cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()


def build() -> dict:
    e = json.loads((ROOT / "outputs/exp3/escalation_report.json").read_text())
    rows = {r["state"]: r for r in e["combined"]}
    leader = e["combined"][0]["state"]

    # the tied set, computed from the pairwise matrix
    mine = [p for p in e["pairwise"] if leader in (p["a"], p["b"])]
    tied_with = [(p["b"] if p["a"] == leader else p["a"])
                 for p in mine if not p["resolved"]]
    tied_set = [leader] + sorted(tied_with)

    members = []
    for s in tied_set:
        r = rows[s]
        members.append({
            "state_key": s,
            "effect_pct": r["mean_pct"],
            "sd_pct": r["sd_pct"],
            "ratio": r["ratio"],
            "measured_at_restarts": r["restarts"],
            "regime": r["regime"],
            "contract_digest": (EXP3_STAGE_B_ESCALATED.digest
                                if r["regime"] == "escalated"
                                else EXP3_STAGE_B.digest),
        })

    return {
        "version": "pre_exp4_baseline_v1",
        "built_at": subprocess.run(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"],
                                   capture_output=True, text=True).stdout.strip(),
        "repo_revision": _git("rev-parse", "HEAD"),
        "gen1_tag": "gen1-frozen-v1",
        "exp3_tag": "exp3-final-v1",
        "hierarchy": ["published COTA schedule", "Exp 1 frequency optimum",
                      "Exp 3 constrained route-mutation optimum",
                      "Exp 4 greenfield optimum (to be measured)"],
        "exp2_contributes_geometry": False,
        "exp2_note": "Experiment 2/2B certified the null and promoted no "
                     "geometry edit, so it contributes no incumbent geometry.",
        "incumbent": {
            "tied_set": members,
            "n_tied": len(members),
            "how_computed": "the leader plus every certified candidate it does "
                            "not separate from, read from the pairwise matrix. "
                            "Experiment 3's leader separates from all 28 "
                            "others, so this is a singleton by computation, "
                            "not by assumption.",
            "exp4_must_beat": "the best matched-effort member of this set, "
                              "re-solved in the same run at matched "
                              "convergence",
        },
        "regime_caveat": {
            "uniform_effort": False,
            "detail": "The incumbent was measured at 20 restarts. Experiment "
                      "3's certified set is split -- 23 of 29 at 40 restarts, "
                      "6 including this leader at 20 -- because section 6 "
                      "escalates what is unresolved or failing, which is by "
                      "construction the smaller margins. Phase 5b would have "
                      "closed the split and was abandoned with zero cells. An "
                      "Experiment 4 comparison must re-solve the incumbent in "
                      "its own run, so this affects the incumbent's HISTORICAL "
                      "figure, not the matched-effort comparison Exp 4 makes.",
        },
        "no_denominator": "A stored score is a reference, never a denominator "
                          "(D24). No number in this file may be used as the "
                          "base of an Experiment 4 percentage.",
        "provenance": {
            "escalation_report_sha256": hashlib.sha256(
                (ROOT / "outputs/exp3/escalation_report.json").read_bytes()
            ).hexdigest(),
            "stage_b_contract": EXP3_STAGE_B.digest,
            "escalated_contract": EXP3_STAGE_B_ESCALATED.digest,
        },
        "representation": {
            "off_is_representable": True,
            "off_note": "frequency.OFF (infinite headway). Experiment 4 builds "
                        "ladders with allow_off=True; this baseline's own "
                        "measurements were made under Gen1 ladders, which "
                        "cannot represent OFF. That asymmetry is intended: the "
                        "incumbent is a network COTA runs, and every one of its "
                        "route-periods is on.",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--verify", action="store_true")
    a = ap.parse_args()

    if a.write:
        b = build()
        BASELINE.write_text(json.dumps(b, indent=2))
        print(f"pre_exp4_baseline_v1 built {b['built_at']}")
        print(f"  tied set: {b['incumbent']['n_tied']} member(s)")
        for m in b["incumbent"]["tied_set"]:
            print(f"    {m['state_key']:<44} {m['effect_pct']:+.5f}% "
                  f"@ {m['measured_at_restarts']} restarts")
        print(f"  uniform effort: {b['regime_caveat']['uniform_effort']}")
        print(f"\nwrote {BASELINE}")
        return 0

    if not BASELINE.exists():
        print("no baseline written", file=sys.stderr)
        return 2
    stored = json.loads(BASELINE.read_text())
    fresh = build()
    ok = True
    for k in ("incumbent", "hierarchy", "provenance"):
        same = stored[k] == fresh[k]
        ok &= same
        print(f"  {k:<14} {'ok' if same else 'FAIL'}")
    print("BASELINE VERIFIED" if ok else "FAILED — the incumbent has moved")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
