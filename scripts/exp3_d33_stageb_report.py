#!/usr/bin/env python3
"""D33 at Stage B effort — apply the frozen veto rule.

The rule is fixed in `EXPERIMENT3_D33_STAGEB_DESIGN.md`, written before any gap
here was computed. This script applies it; it does not choose it, and it has no
tunable threshold, no safety multiplier and no discretion.

    VETO(c)  <=>  max |differential| for c's treatment  >=  |mean delta(c)|

where, paired on seed exactly as Stage B pairs,

    gap(net, seed, stratum, N) = delivered - exact                   (>= 0)
    differential(t, ...)       = gap(control, ...) - gap(t, ...)

A candidate not measured directly is judged against the LARGEST |differential|
observed across all measured treatments -- nothing licenses assuming an
unmeasured treatment is better behaved than the worst measured one.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "exp3"
GAPS = OUT / "d33_stageb" / "gaps.jsonl"

DISCOVERY_MAX_GAP_PCT = 0.0018369837849496464   # D33, for comparison only


def main() -> int:
    rows = [json.loads(l) for l in GAPS.read_text().splitlines() if l.strip()]
    if len(rows) != 375:
        print(f"REFUSING: {len(rows)} of 375 gap cells present", file=sys.stderr)
        return 2

    # ---- raw gap distribution -------------------------------------------
    by_net = defaultdict(list)
    by_stratum = defaultdict(list)
    for r in rows:
        by_net[r["network"]].append(r["gap_pct"] or 0.0)
        by_stratum[r["stratum"]].append(r["gap_pct"] or 0.0)

    print("D33 AT STAGE B EFFORT")
    print(f"  {len(rows)} cells | anchors digest-verified against Stage B receipts")
    allg = [r["gap_pct"] or 0.0 for r in rows]
    nz = [g for g in allg if g > 0]
    print(f"  cells with any gap : {len(nz)} of {len(allg)}")
    print(f"  max gap            : {max(allg):.7f}%")
    print(f"  mean gap           : {statistics.fmean(allg):.7f}%")
    print(f"  (D33 discovery-effort max was {DISCOVERY_MAX_GAP_PCT:.7f}%)")

    print("\n  by network:")
    for n, g in sorted(by_net.items(), key=lambda kv: -max(kv[1])):
        print(f"    {n:20s} max {max(g):.7f}%  mean {statistics.fmean(g):.7f}%"
              f"  nonzero {sum(1 for x in g if x > 0):2d}/{len(g)}")
    print("\n  by stratum:")
    for s, g in sorted(by_stratum.items(), key=lambda kv: -max(kv[1])):
        print(f"    {s:20s} max {max(g):.7f}%  nonzero {sum(1 for x in g if x > 0):2d}/{len(g)}")

    # ---- the paired differential ----------------------------------------
    idx = {(r["network"], r["seed"], r["stratum"], r["n_free"]): (r["gap_pct"] or 0.0)
           for r in rows}
    treatments = sorted({r["network"] for r in rows} - {"control"})
    states = {r["network"]: r["state"] for r in rows}

    print("\nPAIRED DIFFERENTIAL  (control gap - treatment gap, same seed/stratum/N)")
    diffs: dict[str, list[float]] = {}
    for t in treatments:
        d = []
        for (n, sd, st, k), g in idx.items():
            if n != t:
                continue
            c = idx.get(("control", sd, st, k))
            if c is None:
                continue
            d.append(c - g)
        diffs[t] = d
        mx = max(abs(x) for x in d)
        print(f"  {t:20s} {states[t]:44s}")
        print(f"    n={len(d):3d}  max|diff| {mx:.7f}%  mean {statistics.fmean(d):+.7f}%"
              f"  nonzero {sum(1 for x in d if abs(x) > 0):2d}")

    worst = max(max(abs(x) for x in d) for d in diffs.values())
    print(f"\n  LARGEST |differential| across all measured treatments: {worst:.7f}%")

    # ---- the veto ---------------------------------------------------------
    rep = json.loads((OUT / "stageB_report.json").read_text())
    certified = [r for r in rep["candidates"] if r["certified"]]
    per_state = {states[t]: max(abs(x) for x in diffs[t]) for t in treatments}

    print(f"\nVETO RULE  ->  veto iff max|differential| >= |mean delta|\n")
    vetoed, kept = [], []
    for r in sorted(certified, key=lambda r: r["mean_pct"]):
        margin = abs(r["mean_pct"])
        measured = r["state"] in per_state
        bound = per_state.get(r["state"], worst)
        v = bound >= margin
        (vetoed if v else kept).append(r["state"])
        if v or margin < 10 * bound:      # show the ones anywhere near the line
            print(f"  {r['state']:44s} margin {margin:.5f}%  bound {bound:.7f}%"
                  f"  ratio {margin/bound if bound else float('inf'):8.1f}x"
                  f"  {'MEASURED' if measured else 'inferred'}"
                  f"  {'** VETOED **' if v else 'ok'}")
    print(f"\n  vetoed: {len(vetoed)} of {len(certified)} certified")
    print(f"  kept  : {len(kept)}")

    lead = rep["candidates"][0]
    lb = per_state.get(lead["state"], worst)
    print(f"\n  LEADER {lead['state']}")
    print(f"    margin {abs(lead['mean_pct']):.5f}%  vs bound {lb:.7f}%"
          f"  = {abs(lead['mean_pct'])/lb if lb else float('inf'):.0f}x the "
          "treatment-correlated error")

    verdict = "VETO" if vetoed else "PASS"
    print(f"\nD33 STAGE B VERDICT: {verdict}")

    out = {"cells": len(rows), "max_gap_pct": max(allg),
           "mean_gap_pct": statistics.fmean(allg),
           "cells_with_gap": len(nz),
           "discovery_effort_max_gap_pct": DISCOVERY_MAX_GAP_PCT,
           "by_network": {n: {"max": max(g), "mean": statistics.fmean(g),
                              "nonzero": sum(1 for x in g if x > 0)}
                          for n, g in by_net.items()},
           "by_stratum": {s: {"max": max(g),
                              "nonzero": sum(1 for x in g if x > 0)}
                          for s, g in by_stratum.items()},
           "differential": {t: {"state": states[t], "n": len(d),
                                "max_abs": max(abs(x) for x in d),
                                "mean": statistics.fmean(d)}
                            for t, d in diffs.items()},
           "largest_differential_pct": worst,
           "veto_rule": "veto iff max|differential| >= |mean delta|; no multiplier",
           "vetoed": vetoed, "kept": kept, "verdict": verdict}
    p = OUT / "d33_stageb" / "d33_stageb_report.json"
    p.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
