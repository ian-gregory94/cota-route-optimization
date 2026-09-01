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

Promotion requires an admissible comparison, not a score
--------------------------------------------------------
A state enters the frontier only if ``firewall.compare()`` admitted it against
the control. A raw objective is not sufficient and never was: for four
experiments the control and the treatments were optimized by different methods,
and every ranking built from those scores ranked the optimizer as much as the
geometry (D27). States whose comparison is refused are listed with the
dimensions that refused them, so a frontier can never quietly shrink.
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
NULL = "<none>"
TIE_FLOORS = 2.0
PER_KIND = 2
PER_CARDINALITY = 1


def load_receipts() -> dict:
    """Execution receipts by state key, from the observation store."""
    from cota_opt.firewall import ObservationStore
    store = ObservationStore(OUT / "observations")
    return {r.spec.state_key: r for r in store.all()}


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


def admissible_states(states: dict) -> tuple[dict, list[dict]]:
    """Split the census into states with a valid comparison and states without.

    Receipts live beside the score rows. A state with no receipt predates the
    firewall: it is not evidence, and saying so is the migration path.
    """
    from cota_opt.firewall import EXP3_STAGE_A, compare
    receipts = load_receipts()
    control = receipts.get(NULL)
    if control is None:
        return {}, [{"state": k, "why": "no control receipt to compare against"}
                    for k in states]
    ok, refused = {}, []
    for k, v in states.items():
        r = receipts.get(k)
        if r is None:
            refused.append({"state": k, "why": "no execution receipt "
                                               "(evaluated before the firewall)"})
            continue
        c = compare(control, r, EXP3_STAGE_A)
        if c:
            ok[k] = {**v, "comparison_id": c.id, "effect_pct": c.effect_pct}
        else:
            refused.append({"state": k, "why": "comparison refused",
                            "dimensions": sorted({d.dimension for d in
                                                  getattr(c, "undeclared", ())}),
                            "notes": list(getattr(c, "notes", ()))})
    return ok, refused


def main() -> int:
    states, reps, base, floor = load()
    admitted, refused = admissible_states(states)
    if refused:
        print(f"  {len(refused)} of {len(states)} states have no admissible "
              f"comparison and cannot be promoted")
        why = defaultdict(int)
        for r in refused:
            why[r["why"]] += 1
            for d in r.get("dimensions", ()):
                why[f"  refused on: {d}"] += 1
        for k, n in sorted(why.items(), key=lambda x: -x[1]):
            print(f"      {n:4d}  {k}")
        (OUT / "stageA_refused.json").write_text(json.dumps(refused, indent=2))
    if not admitted:
        # Never overwrite a prior frontier with an empty one in place: the old
        # selection is provenance, and a reader who finds an empty file where a
        # frontier used to be learns nothing about why (corrective plan, s1).
        prev = OUT / "stageA_promoted.json"
        if prev.exists():
            keep = OUT / "stageA_promoted.superseded.json"
            if not keep.exists():
                keep.write_text(prev.read_text())
                print(f"  preserved the previous frontier as {keep.name}")
        print("\nNo state has an admissible comparison against the control.")
        print("Nothing can be promoted. This is the correct outcome when the "
              "census was produced before the comparison firewall existed; "
              "re-score under a contract and run this again.")
        (OUT / "stageA_promoted.json").write_text(json.dumps(
            {"promoted": [], "refused": len(refused),
             "reason": "no admissible comparison against the control"}, indent=2))
        return 1
    states = admitted
    pct = {k: v["effect_pct"] for k, v in states.items()}
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
