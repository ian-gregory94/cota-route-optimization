#!/usr/bin/env python3
"""Phase A2 effects against the CORRECTED control.

Step 6 of the corrective plan. Phase A2's 91 multi-edit states are not
re-scored and the 420-state search is not resumed: D30 measured that a
previously-fallback state returns a bit-identical objective under
`starts="both"` -- 8 of 8 stratified states, identical plan hashes, `both`
choosing greedy every time -- and every A2 state fell back. Their numbers are
already in the basin the corrected pipeline selects.

What was wrong was the thing they were compared against. The old control was
scored on the incumbent start, which for the unedited network was accepted and
therefore optimized worse (D27). Correcting it moves every A2 effect by the
same offset.

**These effects are NOT firewall-admissible.** The A2 states carry no
ExecutionReceipt -- they predate the firewall -- so `compare()` refuses them and
should. That refusal is not a technicality to be worked around: it means nobody
can promote or certify from these numbers. They are reported because the
interaction question A2 was run to answer does not depend on their absolute
magnitudes, and because knowing where they land is worth having before deciding
whether to spend eleven hours giving them receipts.

    python scripts/exp3_a2_recompute.py
"""
from __future__ import annotations

import glob
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cota_opt.firewall import EXP3_STAGE_A, ObservationStore   # noqa: E402

OUT = ROOT / "outputs" / "exp3"
OLD_CONTROL = 2962742.7176865116        # incumbent start — the contaminated one


def corrected_control() -> float | None:
    base = EXP3_STAGE_A.solver.seeds[0]
    for r in ObservationStore(OUT / "observations").all():
        if r.spec.state_key == "<none>" and r.spec.seed == base:
            return r.objective
    return None


def main() -> int:
    new = corrected_control()
    if new is None:
        print("no corrected control receipt yet; run the re-score first")
        return 1

    rows = {}
    for f in glob.glob(str(OUT / "stageA_rows*.jsonl")):
        for line in open(f):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("cardinality", 0) >= 2:
                rows[r["state_key"]] = r
    if not rows:
        print("no multi-edit states found")
        return 1

    offset = 100.0 * (OLD_CONTROL - new) / new
    print(f"Phase A2 — {len(rows)} multi-edit states against the corrected control\n")
    print(f"  old control (incumbent start)  {OLD_CONTROL:.4f}")
    print(f"  corrected control (both)       {new:.4f}")
    print(f"  every effect shifts by         {offset:+.4f} percentage points\n")

    out = []
    for k, r in rows.items():
        old_pct = 100.0 * (r["objective"] - OLD_CONTROL) / OLD_CONTROL
        new_pct = 100.0 * (r["objective"] - new) / new
        out.append({"state": k, "cardinality": r["cardinality"],
                    "objective": r["objective"],
                    "effect_pct_old_control": old_pct,
                    "effect_pct_corrected_control": new_pct,
                    "sign_flipped": (old_pct < 0) != (new_pct < 0)})
    out.sort(key=lambda x: x["effect_pct_corrected_control"])

    flipped = sum(1 for x in out if x["sign_flipped"])
    better = sum(1 for x in out if x["effect_pct_corrected_control"] < 0)
    print(f"  states beating the OLD control       {sum(1 for x in out if x['effect_pct_old_control'] < 0)}/{len(out)}")
    print(f"  states beating the CORRECTED control {better}/{len(out)}")
    print(f"  sign flips                           {flipped}/{len(out)}\n")
    print(f"  {'state':56s} {'k':>2s} {'old %':>9s} {'corrected %':>12s}")
    for x in out[:12]:
        print(f"  {x['state'][:56]:56s} {x['cardinality']:2d} "
              f"{x['effect_pct_old_control']:+9.4f} "
              f"{x['effect_pct_corrected_control']:+12.4f}")
    if len(out) > 12:
        print(f"  ... {len(out)-12} more")

    v = [x["effect_pct_corrected_control"] for x in out]
    print(f"\n  best {min(v):+.4f}%   median {st.median(v):+.4f}%   "
          f"worst {max(v):+.4f}%")

    doc = {
        "n_states": len(out),
        "old_control_objective": OLD_CONTROL,
        "corrected_control_objective": new,
        "offset_percentage_points": offset,
        "states_beating_old_control": sum(1 for x in out
                                          if x["effect_pct_old_control"] < 0),
        "states_beating_corrected_control": better,
        "sign_flips": flipped,
        "admissibility":
            "NOT firewall-admissible. These states carry no ExecutionReceipt "
            "-- they predate the firewall -- so compare() refuses them, and "
            "nothing may be promoted or certified from these numbers. Giving "
            "them receipts means re-scoring 91 states, roughly eleven hours.",
        "why_not_rescored":
            "D30 measured that a previously-fallback state returns a "
            "bit-identical objective under starts='both' (8/8 stratified "
            "states, identical plan hashes, both choosing greedy every time), "
            "and every A2 state fell back. The numerators are already in the "
            "basin the corrected pipeline selects; only the comparison point "
            "was wrong.",
        "search_disclosure":
            "Phase A2 was terminated after the discovery of an "
            "optimizer-initialization asymmetry, at roughly 131 of a "
            "preregistered 420 evaluations, with all search states still in "
            "lane 1 of 3. It is NOT a completed multi-start search: it "
            "establishes no exhaustive coverage, no global optimum, and not "
            "that every state was reachable. Existing states were retained "
            "because they were sufficient for the interaction question; "
            "further discovery search was judged lower value than "
            "matched-start certification.",
        "states": out,
    }
    (OUT / "a2_recomputed.json").write_text(json.dumps(doc, indent=2) + "\n")
    print(f"\n  NOT firewall-admissible: no receipts, so compare() refuses "
          f"these\n  and nothing may be promoted or certified from them.")
    print(f"\nwrote {OUT / 'a2_recomputed.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
