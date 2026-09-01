#!/usr/bin/env python3
"""Select Stage A's promoted frontier — a band, never a top N.

The promotion rule was committed before Stage A ran, and the reason is D24: at
discovery effort a ranking inverted outright, so every state within a floor of
the leader is a tie and taking the top N discards the true winner whenever the
ranking is off by one floor. Which, in this project, it has been.

Promoted:

* everything within **2.0 floors** of the leader;
* the best **2 states featuring each mutation kind**, so a kind cannot be
  eliminated by the leader's neighbourhood rather than on its merits;
* the best state at **each cardinality**, not required to be nested — 2B found
  cardinality winners are not nested, so a nested rule would miss them;
* the **null**, always. It is the incumbent, and Experiment 2B's answer.
"""
from __future__ import annotations

import glob
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "outputs" / "exp3"
TIE_FLOORS = 2.0
PER_KIND = 2
PER_CARDINALITY = 1


def load() -> tuple[dict, dict, float, float]:
    seen: dict[str, dict] = {}
    for f in glob.glob(str(OUT / "stageA_states*.jsonl")):
        for line in open(f):
            if line.strip():
                try:
                    r = json.loads(line)
                    seen[r["state"]] = r
                except (json.JSONDecodeError, KeyError):
                    continue
    reps = {k: v for k, v in seen.items() if k.startswith("<none>|rep")}
    base = sum(v["score"] for v in reps.values()) / len(reps)
    floor = 3 * st.stdev([v["score"] for v in reps.values()]) / base * 100
    states = {k: v for k, v in seen.items()
              if not k.startswith("<none>|rep")}
    return states, reps, base, floor


def main() -> int:
    states, reps, base, floor = load()
    pct = {k: 100 * (v["score"] - base) / base for k, v in states.items()}
    ranked = sorted(pct, key=lambda k: pct[k])
    leader = ranked[0]
    band = floor * TIE_FLOORS

    promoted: dict[str, str] = {}

    def add(k: str, why: str) -> None:
        promoted.setdefault(k, why)

    add("<none>", "the incumbent, always")
    for k in ranked:
        if pct[k] <= pct[leader] + band:
            add(k, f"within {TIE_FLOORS} floors of the leader")

    by_kind: dict[str, list[str]] = defaultdict(list)
    for k in ranked:
        for m in ([] if k == "<none>" else k.split("+")):
            by_kind[m.split("-")[0]].append(k)
    for kind, ks in sorted(by_kind.items()):
        for k in ks[:PER_KIND]:
            add(k, f"best {PER_KIND} featuring kind {kind}")

    by_card: dict[int, list[str]] = defaultdict(list)
    for k in ranked:
        by_card[0 if k == "<none>" else k.count("+") + 1].append(k)
    for c, ks in sorted(by_card.items()):
        for k in ks[:PER_CARDINALITY]:
            add(k, f"best at cardinality {c}")

    rows = [{"state": k, "objective_pct_vs_null": round(pct.get(k, 0.0), 4),
             "floors": round(abs(pct.get(k, 0.0)) / floor, 2),
             "cardinality": 0 if k == "<none>" else k.count("+") + 1,
             "why_promoted": why}
            for k, why in sorted(promoted.items(), key=lambda kv: pct.get(kv[0], 0.0))]

    doc = {
        "stage": "A — DISCOVERY. These magnitudes are not findings; the "
                 "promoted set is a selection of what to look at in Stage B.",
        "states_scored": len(states),
        "replicates": len(reps),
        "objective_floor_pct": round(floor, 4),
        "tie_band_pct": round(band, 4),
        "leader": leader,
        "leader_pct": round(pct[leader], 4),
        "n_promoted": len(promoted),
        "promotion_rule": {
            "tie_floors": TIE_FLOORS, "per_kind": PER_KIND,
            "per_cardinality": PER_CARDINALITY,
            "committed": "before Stage A ran",
            "why_not_top_n": "D24 — a ranking at this effort inverted "
                             "outright, so every state within a floor is a "
                             "tie and a top-N rule discards the true winner "
                             "whenever the ranking is off by one floor",
        },
        "promoted": rows,
        "caveat": "Discovery only. This does not establish exhaustive "
                  "coverage, a global optimum, or that every state was "
                  "reachable.",
    }
    (OUT / "stageA_promoted.json").write_text(json.dumps(doc, indent=2) + "\n")

    print("=" * 84)
    print("EXPERIMENT 3 STAGE A — PROMOTED FRONTIER")
    print("=" * 84)
    print(f"  states scored     {len(states)} (+{len(reps)} replicates)")
    print(f"  objective floor   {floor:.4f}%   tie band {band:.4f}%")
    print(f"  leader            {pct[leader]:+.4f}%  {leader[:52]}")
    print(f"  promoted          {len(promoted)}")
    print()
    for r in rows:
        print(f"  {r['objective_pct_vs_null']:+8.4f}%  k={r['cardinality']}  "
              f"{r['why_promoted'][:44]:<44s} {r['state'][:40]}")
    print(f"\nartifacts: {OUT / 'stageA_promoted.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
