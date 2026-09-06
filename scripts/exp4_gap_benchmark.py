#!/usr/bin/env python3
"""D18 — the optimization-gap benchmark, on Experiment 4 networks.

EXPERIMENT4_DESIGN section 9 item 18, verbatim:

    The gap benchmark has been run on Experiment 4 networks, its four questions
    answered in order, and question 3's answer recorded -- including the branch
    where it forbids discovery-effort comparison.

Section 3 fixes the method: it is D33's, "run on Experiment 4 networks BEFORE
the search, and answering the same four questions in the same order", with
strata that "must include high-branching networks, sparse networks, networks
with many OFF routes, and networks whose lines overlap heavily". D33's number
does NOT transfer -- section 3 says so explicitly -- so this measures its own.

WHY EXHAUSTIVE ENUMERATION OF A REDUCED NEIGHBOURHOOD
----------------------------------------------------
Ported unchanged from `exp3_gap_benchmark.py`, because the reason is unchanged.
The Gen1 objective resists linearization honestly: under Model B a path's
waiting cost depends on the COMBINED frequency of every same-route pattern
serving its boarding stop then its alighting stop, in that order, so a path's
cost is a joint function of several route-period headways and does not separate.
A MILP would have to linearize that coupling or drop it, and would then be
measuring a different objective than the one under test.

So the PROBLEM is reduced instead of the objective. All but N route-periods are
frozen at the delivered plan by a one-rung ladder; the free ones keep K rungs
around theirs. Every one of the K^N combinations is priced by the REAL
evaluator, and the best feasible one is the exact optimum OF THAT REDUCED
PROBLEM, under the production objective. Benchmark objective and production
objective are therefore the same function; the approximation is confined
entirely to the size of the decision space, which is stated and not hidden.

Full ladder enumeration is not an alternative at this scale. Measured: 336.6 us
per combination, so one line (6 route-periods, 14 rungs) is 7.53e6 combinations
and 42 minutes, and two lines is 5.67e13 -- about 600 years. The reduced
neighbourhood at K=3, N=10 is 59,049.

The enumerator is `gen2_frequency.solve_exact`, driven through
`solve_on_network(solver="exact", ladder_override=...)`, so the exact reference
and the heuristic answer are produced by the same setup, the same evaluator, the
same feasibility predicate and the same scalarization. Nothing about the
comparison is reimplemented.

WHAT THE FOUR QUESTIONS ARE, AND WHICH ONE YIELDS A NUMBER
----------------------------------------------------------
1. absolute gap of the delivered plan against the exact reference;
2. its distribution across network STRUCTURES (section 3's strata);
3. whether the gap moves SYSTEMATICALLY with network structure;
4. therefore the network-level effect distinguishable from structure-correlated
   solver error.

Only (4) yields a usable number. A generic mean or maximum gap is not an effect
floor: if two networks sit the same distance from optimum in the same direction
their difference is clean however large the gap, and if one is 0.4% off and the
other 0.1% then a 0.3% artifact is available. Only the DIFFERENTIAL bounds
anything, and it is the only thing offered here as the promotion band.

QUESTION 3'S FORBIDDING BRANCH
------------------------------
Section 3: "If (3) says the gap tracks structure, Experiment 4 cannot compare
networks at discovery effort at all, and the search must select on something
else." That branch is implemented, not just described: if the structure-paired
differential fails the declared test below, this script records
`discovery_effort_comparison_permitted: false` and emits NO band.

    python scripts/exp4_gap_benchmark.py --json outputs/exp4/gap_benchmark.json
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

LAM = 2.0
SEED = 20260825
K_RUNGS = 3                    # ladder rungs kept per free route-period
SIZES = (6, 8, 10)             # free route-periods: 3^N = 729 / 6561 / 59049

#: How the free route-periods are chosen within a network. Declared before any
#: gap is measured, and deliberately not all easy: a benchmark that samples only
#: well-behaved subproblems reports a gap that means nothing about the ones
#: under test.
STRATA = ("peak", "offpeak", "seeded_random")

#: Q3's declared test, fixed BEFORE the numbers exist so it cannot be chosen to
#: fit them. The gap "tracks structure" -- and discovery-effort comparison is
#: forbidden -- if the structure-paired differential is not a small fraction of
#: the gaps themselves: i.e. if knowing a network's structure tells you much
#: about its gap. Concretely: forbidden when the largest paired |differential|
#: exceeds HALF the median absolute gap, because at that point the
#: structure-correlated component is the same order as the thing being measured.
Q3_FORBID_RATIO = 0.5


def restricted_ladders(full: dict, keys, free: set, k_rungs: int,
                       anchor: dict) -> dict:
    """One rung for every frozen route-period, k around the anchor for free.

    The anchor is the plan Gen1 actually DELIVERED on the full problem, so the
    reduced problem is a neighbourhood of the answer the experiment would
    report. Exhaustive enumeration then asks the question that matters: is
    anything better sitting next to what we shipped? That is the optimization
    ERROR of the delivered result, not a capability test on a fresh small
    problem.
    """
    import math
    out = {}
    for key in keys:
        lad = sorted(full[key])
        cur = float(anchor.get(key, lad[len(lad) // 2]))

        def dist(v: float) -> float:
            if math.isinf(v) and math.isinf(cur):
                return 0.0
            if math.isinf(v) or math.isinf(cur):
                return float("inf")
            return abs(v - cur)

        i = min(range(len(lad)), key=lambda j: dist(lad[j]))
        if key not in free:
            out[key] = [lad[i]]
            continue
        lo = max(0, min(i - k_rungs // 2, len(lad) - k_rungs))
        out[key] = lad[lo:lo + k_rungs] or [lad[i]]
    return out


def pick_free(keys, stratum: str, n: int) -> set:
    """Which route-periods are freed, deterministically."""
    import random
    ks = sorted(keys)
    if stratum == "peak":
        pref = [k for k in ks if k[1] in ("am_peak", "pm_peak")]
    elif stratum == "offpeak":
        pref = [k for k in ks if k[1] not in ("am_peak", "pm_peak")]
    else:
        pref = list(ks)
    rng = random.Random(f"{stratum}:{n}:{SEED}")
    pool = pref if len(pref) >= n else ks
    return set(rng.sample(sorted(pool), min(n, len(pool))))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--sizes", default=",".join(map(str, SIZES)))
    ap.add_argument("--max-combos", type=int, default=200_000)
    a = ap.parse_args()
    sizes = tuple(int(x) for x in a.sizes.split(","))

    from cota_opt.configs import service_periods
    from cota_opt.exp3_score import solve_on_network
    from cota_opt.exp4_assemble import assemble
    from cota_opt.exp4_network import Exp4Selection
    from cota_opt.firewall.core import digest
    from cota_opt.frequency import is_off
    from exp2_treatments import pinned
    from exp4_c10_fixtures import (CASES, POOL_VERSION, _BY_RID, _boot,
                                   _first_dep_by_period)

    st_ = _boot()
    H, sg, graph = st_["H"], st_["sg"], st_["graph"]
    periods = sorted(service_periods(H.assumptions))
    first_dep = _first_dep_by_period()
    t_all = time.time()

    # ---- the structural strata section 3 requires --------------------------
    #
    # Built from the frozen C10 pools, which are real Experiment 4 geometry.
    # Each stratum is a NETWORK STRUCTURE, and the whole point of question 3 is
    # whether the gap moves between them.
    def ok(sel):
        try:
            assemble(sel, _BY_RID, graph, H.baseline.network.stops,
                     pool_version=POOL_VERSION,
                     first_dep_sec_by_period=first_dep)
            return True
        except Exception:
            return False

    pool_a = sorted(CASES[1]["lines"])          # large_gap: all five assemble
    pool_a = [l for l in pool_a
              if ok(Exp4Selection(POOL_VERSION, frozenset([l]), frozenset()))]
    pool_b = sorted(CASES[3]["lines"])          # greedy_overbuilds
    pool_b = [l for l in pool_b
              if ok(Exp4Selection(POOL_VERSION, frozenset([l]), frozenset()))]

    NETWORKS = {
        # high-branching: every line in the pool active together
        "dense": (Exp4Selection(POOL_VERSION, frozenset(pool_a), frozenset()),
                  160.0, 40.0),
        # sparse: the smallest structure that still has decisions to make
        "sparse": (Exp4Selection(POOL_VERSION, frozenset(pool_a[:2]),
                                 frozenset()), 160.0, 40.0),
        # many OFF routes: a whole line pinned off across every period
        "many_off": (Exp4Selection(
            POOL_VERSION, frozenset(pool_a),
            frozenset((pool_a[0], p) for p in periods)), 160.0, 40.0),
        # a different pool entirely, so "structure" is not one pool's quirk
        "other_pool": (Exp4Selection(POOL_VERSION, frozenset(pool_b),
                                     frozenset()), 200.0, 40.0),
    }

    rows = []
    for netname, (sel, vh, peak) in NETWORKS.items():
        built = assemble(sel, _BY_RID, graph, H.baseline.network.stops,
                         pool_version=POOL_VERSION,
                         first_dep_sec_by_period=first_dep)
        cons = pinned(vh, {p: peak for p in periods})
        common = dict(harness=H, stops_gdf=sg, lam=LAM, seed=SEED,
                      constraints=cons, waiting_model="same_route",
                      starts="greedy", allow_off=True,
                      pinned_off=frozenset(sel.pinned_off))

        # 1. what Gen1 DELIVERS on the whole problem -- the thing under test
        t0 = time.time()
        deliv = solve_on_network(built.network, built.tstats,
                                 iterations=20_000, restarts=1, width=0,
                                 solver="gen1", include_setup=True, **common)
        t_deliv = time.time() - t0
        judge = deliv["judge"]
        keys = list(judge.model.keys)
        full_lads = {k: list(judge.ladders[k]) for k in keys}
        plan = dict(deliv["plan"].headways)
        w_uns = judge.model.w.unserved
        obj_deliv = deliv["fit"].scalarized(w_uns, LAM)
        n_off = sum(1 for k in keys if is_off(plan.get(k, 1.0)))
        print(f"\n=== {netname}: {len(sel.lines)} lines, {len(keys)} "
              f"route-periods, {n_off} OFF, delivered {obj_deliv:,.4f} "
              f"({t_deliv:.1f}s) ===")

        for stratum in STRATA:
            for n in sizes:
                if n > len(keys):
                    continue
                if K_RUNGS ** n > a.max_combos:
                    print(f"  skip {stratum}/{n}: {K_RUNGS**n:,} > "
                          f"{a.max_combos:,}")
                    continue
                free = pick_free(keys, stratum, n)
                lads = restricted_ladders(full_lads, keys, free, K_RUNGS, plan)
                combos = 1
                for k in keys:
                    combos *= len(lads[k])

                # 2. the EXACT optimum of that reduced problem, by the existing
                #    enumerator, against the same frozen evaluator
                t0 = time.time()
                ex = solve_on_network(
                    built.network, built.tstats, iterations=20_000,
                    restarts=1, width=0, solver="exact",
                    exact_max_combinations=max(combos * 2, 1000),
                    ladder_override=lads, **common)
                t_ex = time.time() - t0
                obj_ex = ex["fit"].scalarized(w_uns, LAM)

                # The delivered plan is IN the reduced space by construction
                # (its own rung is always kept), so the exact optimum can never
                # be worse. If it is, the two arms are not the same problem.
                gap = obj_deliv - obj_ex
                if gap < -1e-6:
                    raise AssertionError(
                        f"{netname}/{stratum}/{n}: the exact optimum of a space "
                        f"CONTAINING the delivered plan is worse than it "
                        f"({obj_ex:,.6f} vs {obj_deliv:,.6f}). The reduced "
                        f"problem is not a neighbourhood of the answer.")
                gap_pct = 100.0 * gap / abs(obj_deliv) if obj_deliv else 0.0
                rows.append({
                    "network": netname, "stratum": stratum, "n_free": n,
                    "n_route_periods": len(keys), "n_lines": len(sel.lines),
                    "n_off_in_delivered": n_off,
                    "combinations": combos,
                    "objective_delivered": float(obj_deliv),
                    "objective_exact": float(obj_ex),
                    "gap": float(gap), "gap_pct": float(gap_pct),
                    "seconds_exact": t_ex,
                    "free_keys": sorted(f"{r}|{p}" for r, p in free),
                })
                print(f"  {stratum:<14} N={n:<3} {combos:>7,} combos  "
                      f"gap {gap_pct:+.6f}%  ({t_ex:.1f}s)")

    if not rows:
        print("no cells ran")
        return 1

    # ---------------------------------------------------------------- Q1/Q2 --
    g = [r["gap_pct"] for r in rows]
    nets = sorted({r["network"] for r in rows})
    print(f"\n{'=' * 74}")
    print("Q1/Q2 - absolute gap of the delivered answer vs the exact optimum")
    print(f"  cells {len(rows)}   median {st.median(g):+.6f}%   "
          f"mean {st.mean(g):+.6f}%   max {max(g):+.6f}%")
    print(f"  nonzero gaps: {sum(1 for x in g if abs(x) > 1e-12)}/{len(g)}")
    print("\n  by network structure:")
    by_net = {n: [r["gap_pct"] for r in rows if r["network"] == n] for n in nets}
    for n in nets:
        v = by_net[n]
        print(f"    {n:<14} n={len(v):3d}  mean {st.mean(v):+.6f}%  "
              f"max {max(v):+.6f}%  nonzero "
              f"{sum(1 for x in v if abs(x) > 1e-12)}")

    # ------------------------------------------------------------------ Q3 --
    #
    # Paired on (stratum, n_free): the SAME subproblem shape in two different
    # network structures. That is what isolates structure from subproblem.
    print("\nQ3 - does the gap move SYSTEMATICALLY with network structure?")
    ref = "dense" if "dense" in by_net else nets[0]
    rmap = {(r["stratum"], r["n_free"]): r["gap_pct"]
            for r in rows if r["network"] == ref}
    pairs: dict[str, list[float]] = {}
    worst = 0.0
    for r in rows:
        if r["network"] == ref:
            continue
        c = rmap.get((r["stratum"], r["n_free"]))
        if c is None:
            continue
        pairs.setdefault(r["network"], []).append(r["gap_pct"] - c)
    print(f"  reference structure: {ref}")
    for n in sorted(pairs):
        d = pairs[n]
        worst = max(worst, max(abs(x) for x in d))
        print(f"    {n:<14} n={len(d):3d}  mean diff {st.mean(d):+.6f}%  "
              f"max |diff| {max(abs(x) for x in d):.6f}%")

    med_abs = st.median([abs(x) for x in g])
    ratio = (worst / med_abs) if med_abs > 0 else (0.0 if worst == 0 else
                                                  float("inf"))
    forbids = ratio > Q3_FORBID_RATIO
    print(f"\n  largest paired |differential| : {worst:.6f} pp")
    print(f"  median absolute gap           : {med_abs:.6f} pp")
    print(f"  ratio                         : {ratio:.3f} "
          f"(declared limit {Q3_FORBID_RATIO})")
    print(f"  Q3 ANSWER: the gap {'TRACKS' if forbids else 'does NOT track'} "
          f"network structure")

    # ------------------------------------------------------------------ Q4 --
    print("\nQ4 - network effect distinguishable from structure-correlated "
          "solver error")
    if forbids:
        band = None
        print("  NO BAND IS EMITTED.")
        print("  Section 3's forbidding branch is taken: the gap tracks "
              "structure, so")
        print("  Experiment 4 MAY NOT compare networks at discovery effort, "
              "and the")
        print("  search must select on something else -- rank stability across "
              "efforts,")
        print("  or certification of a wider frontier.")
    else:
        band = worst
        print(f"  PROMOTION BAND = {band:.6f} percentage points")
        print("  This is the largest structure-paired differential over "
              "subproblems of")
        print("  identical shape. A margin below it is not distinguishable "
              "from")
        print("  structure-correlated solver error. A margin above it is NOT "
              "thereby")
        print("  established -- it is only not excluded by this measurement, "
              "which is")
        print("  a much weaker statement and must be written as such wherever "
              "it is used.")
        print("\n  WHAT THIS IS NOT: a distance from the global optimum. Each "
              "cell varies")
        print(f"  at most {max(r['n_free'] for r in rows)} of "
              f"{max(r['n_route_periods'] for r in rows)} route-periods across "
              f"{K_RUNGS} rungs. Local optimality is")
        print("  necessary for global optimality and nowhere near sufficient.")

    src = digest({"strata": list(STRATA), "sizes": list(sizes),
                  "k_rungs": K_RUNGS, "lam": LAM, "seed": SEED,
                  "networks": {k: [sorted(v[0].lines),
                                   sorted(map(list, v[0].pinned_off)),
                                   v[1], v[2]]
                               for k, v in sorted(NETWORKS.items())},
                  "q3_forbid_ratio": Q3_FORBID_RATIO})
    out = {
        "item": "D18",
        "criterion": ("The gap benchmark has been run on Experiment 4 "
                      "networks, its four questions answered in order, and "
                      "question 3's answer recorded -- including the branch "
                      "where it forbids discovery-effort comparison."),
        "method": ("D33's, per EXPERIMENT4_DESIGN section 3: exhaustive "
                   "enumeration of a reduced neighbourhood under the "
                   "production objective, by gen2_frequency.solve_exact "
                   "through solve_on_network(solver='exact', "
                   "ladder_override=...)"),
        "k_rungs": K_RUNGS, "sizes": list(sizes), "strata": list(STRATA),
        "anchor": "delivered Gen1 plan on the full problem",
        "lam": LAM, "seed": SEED,
        "design_digest": src,
        "networks": {k: {"lines": sorted(v[0].lines),
                         "pinned_off": sorted(map(list, v[0].pinned_off)),
                         "state_key": v[0].state_key,
                         "state_digest": v[0].state_digest,
                         "veh_hour_budget": v[1], "peak_vehicle_budget": v[2]}
                     for k, v in NETWORKS.items()},
        "n_cells": len(rows),
        "q1_median_gap_pct": st.median(g),
        "q1_mean_gap_pct": st.mean(g),
        "q1_max_gap_pct": max(g),
        "q1_nonzero_cells": sum(1 for x in g if abs(x) > 1e-12),
        "q2_by_structure": {n: {"n": len(by_net[n]),
                                "mean_gap_pct": st.mean(by_net[n]),
                                "max_gap_pct": max(by_net[n])} for n in nets},
        "q3_reference_structure": ref,
        "q3_paired_differentials": {n: {"n": len(v), "mean": st.mean(v),
                                        "max_abs": max(abs(x) for x in v)}
                                    for n, v in sorted(pairs.items())},
        "q3_largest_paired_differential_pp": worst,
        "q3_median_absolute_gap_pp": med_abs,
        "q3_ratio": ratio,
        "q3_forbid_ratio_declared": Q3_FORBID_RATIO,
        "q3_gap_tracks_structure": forbids,
        "q3_answer": ("the gap TRACKS network structure; section 3 forbids "
                      "discovery-effort comparison"
                      if forbids else
                      "the gap does NOT track network structure; "
                      "discovery-effort comparison is permitted"),
        "discovery_effort_comparison_permitted": not forbids,
        "q4_promotion_band_pp": band,
        "q4_note": ("the largest structure-paired differential; a generic mean "
                    "or maximum gap is NOT an effect floor and none is offered"),
        "seconds": time.time() - t_all,
        "rows": rows,
    }
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(out, indent=2))
        print(f"\nwrote {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
