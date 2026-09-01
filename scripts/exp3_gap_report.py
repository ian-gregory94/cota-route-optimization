#!/usr/bin/env python3
"""What the optimization-gap benchmark does and does not license.

Four questions, in order, and the fourth is the only one that yields a number
anyone may use as a threshold:

1. the absolute heuristic gap against the exact reference;
2. its distribution across geometries;
3. whether it moves SYSTEMATICALLY between control and treatment;
4. therefore the treatment effect distinguishable from treatment-correlated
   solver error.

A generic mean or maximum gap is not an effect floor. If both arms sit the same
distance from optimum in the same direction, their difference is clean however
large the gap; if one arm is 0.4% off and the other 0.1%, a 0.3% artifact is
available. Only the DIFFERENTIAL matters, so that is what question 4 reports and
nothing else here is offered as a bound.
"""
from __future__ import annotations

import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "exp3"


def main() -> int:
    rows = [json.loads(l) for l in (OUT / "gap_benchmark.jsonl").read_text()
            .splitlines() if l.strip()]
    if not rows:
        print("no cells yet")
        return 1
    nets = sorted({r["network"] for r in rows})
    strata = sorted({r["stratum"] for r in rows})
    print(f"optimization-gap benchmark — {len(rows)} cells, "
          f"{len(nets)} networks, {len(strata)} strata\n")

    # --- Q1/Q2: the gap and how it is distributed --------------------------
    g = [r["gap_pct"] for r in rows]
    nz = [x for x in g if abs(x) > 1e-12]
    print("Q1/Q2 — absolute gap of the DELIVERED answer vs the exact optimum")
    print(f"  cells with any gap : {len(nz)}/{len(g)}")
    print(f"  median             : {st.median(g):+.6f}%")
    print(f"  mean               : {st.mean(g):+.6f}%")
    if len(g) >= 20:
        print(f"  95th percentile    : "
              f"{sorted(g)[int(0.95*(len(g)-1))]:+.6f}%")
    print(f"  maximum            : {max(g):+.6f}%")

    print("\n  by stratum (mean, max, cells with a gap):")
    for s in strata:
        v = [r["gap_pct"] for r in rows if r["stratum"] == s]
        print(f"    {s:18s} n={len(v):3d}  mean {st.mean(v):+.6f}%  "
              f"max {max(v):+.6f}%  nonzero {sum(1 for x in v if abs(x)>1e-12)}")
    print("\n  by size (does a bigger neighbourhood find more?):")
    for n in sorted({r["n_free"] for r in rows}):
        v = [r["gap_pct"] for r in rows if r["n_free"] == n]
        print(f"    N={n:<3d} n={len(v):3d}  mean {st.mean(v):+.6f}%  "
              f"max {max(v):+.6f}%")

    # --- Q3: does the gap move with the treatment? -------------------------
    print("\nQ3 — does the gap move SYSTEMATICALLY with the treatment?")
    by_net = {n: [r["gap_pct"] for r in rows if r["network"] == n] for n in nets}
    for n in nets:
        v = by_net[n]
        print(f"    {n:24s} n={len(v):3d}  mean {st.mean(v):+.6f}%  "
              f"max {max(v):+.6f}%  nonzero {sum(1 for x in v if abs(x)>1e-12)}")

    ctrl = by_net.get("control", [])
    if not ctrl:
        print("\n  no control cells; question 3 unanswerable")
        return 1

    # Paired on (stratum, size): the same subproblem shape in both arms.
    print("\n  paired by (stratum, size) — control gap vs treatment gap:")
    pairs: dict[str, list[float]] = defaultdict(list)
    cmap = {(r["stratum"], r["n_free"]): r["gap_pct"]
            for r in rows if r["network"] == "control"}
    for r in rows:
        if r["network"] == "control":
            continue
        c = cmap.get((r["stratum"], r["n_free"]))
        if c is None:
            continue
        pairs[r["network"]].append(r["gap_pct"] - c)

    worst = 0.0
    for n in sorted(pairs):
        d = pairs[n]
        worst = max(worst, max(abs(x) for x in d))
        print(f"    {n:24s} n={len(d):3d}  mean diff {st.mean(d):+.6f}%  "
              f"max |diff| {max(abs(x) for x in d):.6f}%")

    # --- Q4: what, if anything, this bounds --------------------------------
    print("\nQ4 — effect distinguishable from treatment-correlated solver error")
    print(f"  largest |control gap - treatment gap| over paired subproblems:")
    print(f"      {worst:.6f} percentage points")
    nfree = max(r["n_free"] for r in rows)
    ntotal = max(r.get("n_route_periods", 0) for r in rows) or None
    print("\n  WHAT THIS IS")
    print(f"    A LOCAL optimality check. Each cell varies at most {nfree} "
          f"route-periods")
    print(f"    {('of ~%d' % ntotal) if ntotal else 'out of the full problem'}, "
          "across 3 ladder rungs centred on the delivered")
    print("    plan. It establishes that the delivered answer is (or is not)")
    print("    optimal WITHIN THAT NEIGHBOURHOOD, under the production")
    print("    objective, exactly.")
    print("\n  WHAT THIS IS NOT")
    print("    It is not the heuristic's distance from the global optimum, and")
    print("    the number above must never be quoted as though it were. A")
    print("    plan can be optimal in every neighbourhood this samples and")
    print("    still sit far from the best plan reachable by moving twenty")
    print("    route-periods at once, or by moving any of them more than one")
    print("    rung. Local optimality is necessary for global optimality and")
    print("    nowhere near sufficient.")
    print("\n  HOW TO USE IT")
    print("    As a LOWER bound on the differential-error bound. The")
    print("    full-problem differential can only be larger, never smaller.")
    print("    A census margin below this figure is not distinguishable from")
    print("    treatment-correlated solver error. A margin above it is NOT")
    print("    thereby established -- it is only not excluded by this")
    print("    measurement, which is a much weaker statement and should be")
    print("    written as such wherever the census is reported.")

    doc = {"n_cells": len(rows), "networks": nets, "strata": strata,
           "q1_median_gap_pct": st.median(g), "q1_mean_gap_pct": st.mean(g),
           "q1_max_gap_pct": max(g),
           "q1_cells_with_gap": len(nz),
           "q2_by_stratum": {s: {"mean": st.mean([r["gap_pct"] for r in rows
                                                  if r["stratum"] == s]),
                                 "max": max(r["gap_pct"] for r in rows
                                            if r["stratum"] == s)}
                             for s in strata},
           "q3_by_network": {n: {"mean": st.mean(v), "max": max(v),
                                 "nonzero": sum(1 for x in v if abs(x) > 1e-12)}
                             for n, v in by_net.items()},
           "q3_paired_differences": {n: {"mean": st.mean(v),
                                         "max_abs": max(abs(x) for x in v)}
                                     for n, v in pairs.items()},
           "q4_max_paired_differential_pct": worst,
           "q4_interpretation":
               "A LOCAL optimality check, not a distance from the global "
               "optimum. Each cell varies at most N route-periods across three "
               "ladder rungs centred on the delivered plan, so it establishes "
               "local optimality within that neighbourhood under the "
               "production objective, exactly. A plan can be optimal in every "
               "neighbourhood sampled here and still sit far from the best "
               "plan reachable by moving many route-periods at once. Use the "
               "figure as a LOWER bound on the differential-error bound: the "
               "full-problem differential can only be larger. A census margin "
               "below it is not distinguishable from treatment-correlated "
               "solver error; a margin above it is not thereby established, "
               "only not excluded by this measurement.",
           "q4_is_not": "the heuristic's distance from the global optimum",
           "methodology_generation": "gen1"}
    (OUT / "gap_report.json").write_text(json.dumps(doc, indent=2) + "\n")
    print(f"\nwrote {OUT / 'gap_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
