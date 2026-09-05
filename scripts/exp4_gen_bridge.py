#!/usr/bin/env python3
"""D21b — the Gen1 -> Gen2 generation bridge.

`METHODOLOGY.md`: a generation bridge answers the SAME question with both
generations and compares the answers. Gen2 agreement marks Gen1 "confirmed by
Gen2 bridge"; disagreement retains both and marks Gen1 "superseded by Gen2
because ..." with the reason. Execution is not the test -- agreement is.

The two arms differ in exactly one thing, enforced structurally rather than by
care: both call `solve_on_network` with identical network, tstats, harness,
envelope, seeds, path inputs, waiting model and ladders, and only `solver`
differs -- `"gen1"` (the exchange heuristic with restarts) versus `"exact"`
(exhaustive enumeration of the ladder space, which refuses rather than samples).

Compared: all seven FitnessVector fields, every route-period headway and its OFF
provenance, the active set, envelope usage, and the objective each generation
optimized.

Exactness where the contract requires it. The frequency subproblem is
deterministic given a plan, so the FITNESS OF A GIVEN PLAN must agree bit for
bit; what may legitimately differ is WHICH plan each solver found, and that
difference is the optimization gap this bridge exists to measure.

    python scripts/exp4_gen_bridge.py --json outputs/exp4/gen_bridge.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

FIELDS = ["generalized_cost", "unserved_demand", "served_demand",
          "revenue_veh_hours", "peak_vehicles", "mean_wait_min",
          "gc_per_served_trip"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--max-combinations", type=int, default=10_000_000,
                    help="raised from the 2M default deliberately: the "
                         "one-line bridge network has 6 route-periods x 14 "
                         "rungs = 7,529,536 combinations at 24us each, ~3 min")
    a = ap.parse_args()

    from cota_opt.exp3_score import solve_on_network
    from cota_opt.exp4_assemble import assemble
    from cota_opt.exp4_network import Exp4Selection
    from cota_opt.frequency import is_off
    from exp4_c10_fixtures import (POOL_VERSION, _BY_RID, _boot,
                                   _first_dep_by_period)
    from exp2_treatments import pinned
    from cota_opt.configs import service_periods

    st = _boot()
    H, sg, graph = st["H"], st["sg"], st["graph"]
    periods = sorted(service_periods(H.assumptions))

    # A single line: 6 route-periods, small enough for the ladder space to be
    # enumerated exactly. The bridge needs a question BOTH generations can
    # answer, and Gen2's exact solver refuses anything larger rather than
    # approximating it.
    line = "syn-9a1726e4c4a0670b"
    sel = Exp4Selection.of(POOL_VERSION, [line])
    built = assemble(sel, _BY_RID, graph, H.baseline.network.stops,
                     pool_version=POOL_VERSION,
                     first_dep_sec_by_period=_first_dep_by_period())
    vh, peak = 200.0, 18.0
    cons = pinned(vh, {p: peak for p in periods})
    print(f"network: 1 line, {len(built.network.patterns)} patterns, "
          f"{len(built.tstats)} tstat rows, envelope {vh} vh / {peak} peak")

    common = dict(harness=H, stops_gdf=sg, lam=2.0, seed=20260825,
                  constraints=cons, waiting_model="same_route",
                  starts="greedy", allow_off=True)

    print("\narm 1: Gen1 (exchange heuristic + restarts) ...")
    t = time.time()
    g1 = solve_on_network(built.network, built.tstats, iterations=20_000,
                          restarts=1, width=0, solver="gen1", **common)
    t1 = time.time() - t

    print("arm 2: Gen2 (exhaustive ladder enumeration) ...")
    t = time.time()
    g2 = solve_on_network(built.network, built.tstats, iterations=20_000,
                          restarts=1, width=0, solver="exact",
                          exact_max_combinations=a.max_combinations, **common)
    t2 = time.time() - t

    f1, f2 = g1["fit"], g2["fit"]
    rows, worst_abs, worst_rel = [], 0.0, 0.0
    for f in FIELDS:
        if not (hasattr(f1, f) and hasattr(f2, f)):
            raise KeyError(f"FitnessVector has no field {f!r}")
        v1, v2 = float(getattr(f1, f)), float(getattr(f2, f))
        ad = abs(v2 - v1)
        rd = ad / abs(v1) if v1 else ad
        worst_abs, worst_rel = max(worst_abs, ad), max(worst_rel, rd)
        rows.append({"field": f, "gen1": v1, "gen2": v2,
                     "abs_diff": ad, "rel_diff": rd})

    p1 = {k: float(v) for k, v in g1["plan"].headways.items()}
    p2 = {k: float(v) for k, v in g2["plan"].headways.items()}
    same_keys = set(p1) == set(p2)
    hw_diff = {k: (p1[k], p2.get(k)) for k in sorted(p1)
               if p2.get(k) != p1[k]}
    off1 = {k for k, v in p1.items() if is_off(v)}
    off2 = {k for k, v in p2.items() if is_off(v)}
    active1 = set(p1) - off1
    active2 = set(p2) - off2

    obj1 = f1.scalarized(g1["judge"].model.w.unserved, 2.0)
    obj2 = f2.scalarized(g2["judge"].model.w.unserved, 2.0)
    gap = obj1 - obj2                     # >0 means Gen1 left value on the table

    print(f"\n  {'field':<22} {'gen1':>16} {'gen2':>16} {'rel':>11}")
    for r in rows:
        print(f"  {r['field']:<22} {r['gen1']:>16.6f} {r['gen2']:>16.6f} "
              f"{r['rel_diff']:>11.3e}")
    print(f"\n  route-period key sets identical : {same_keys}")
    print(f"  headways differing              : {len(hw_diff)} of {len(p1)}")
    print(f"  OFF set gen1 / gen2             : {len(off1)} / {len(off2)}")
    print(f"  active set gen1 / gen2          : {len(active1)} / {len(active2)}")
    print(f"  envelope used gen1 / gen2       : {f1.revenue_veh_hours:.3f} / "
          f"{f2.revenue_veh_hours:.3f} of {vh}")
    print(f"  objective gen1 / gen2           : {obj1:,.4f} / {obj2:,.4f}")
    print(f"  OPTIMIZATION GAP (gen1 - exact) : {gap:,.6f}")
    print(f"  combinations enumerated         : "
          f"{g2['solver_meta'].get('n_combinations'):,}"
          f" ({g2['solver_meta'].get('n_feasible'):,} feasible)")
    print(f"  seconds gen1 / gen2             : {t1:.1f} / {t2:.1f}")

    # The verdict. Gen1 is CONFIRMED when it found the exact optimum; it is
    # SUPERSEDED when the exact solver found strictly better, and the gap is
    # the reason. Gen1 finding something BETTER than an exhaustive enumeration
    # is impossible and would mean the two arms are not the same problem.
    if gap < -1e-9:
        verdict = "BROKEN"
        note = ("Gen1 beat an exhaustive enumeration of the same ladder space, "
                "which is impossible if both arms optimize the same objective "
                "over the same feasible set. The bridge is measuring two "
                "different problems and must be diagnosed before use.")
    elif gap <= 1e-9:
        verdict = "CONFIRMED"
        note = ("Gen1's heuristic found the exact optimum of the frequency "
                "subproblem on this network. Optimization gap zero.")
    else:
        verdict = "SUPERSEDED"
        note = (f"the exact solver found a strictly better plan; Gen1's "
                f"optimization gap is {gap:,.6f} on this network.")
    print(f"\n  BRIDGE VERDICT: {verdict}\n    {note}")

    out = {"question": "optimal frequency plan for one assembled Exp 4 network "
                       "under a pinned envelope, lambda=2",
           "network": {"lines": sorted(sel.lines),
                       "state_key": sel.state_key,
                       "n_patterns": len(built.network.patterns),
                       "n_route_periods": len(p1)},
           "envelope": {"veh_hours": vh, "peak_vehicles": peak},
           "arms_differ_only_in": "solver",
           "fields": rows, "worst_abs_diff": worst_abs,
           "worst_rel_diff": worst_rel,
           "route_period_keys_identical": same_keys,
           "headways_differing": {k: list(v) for k, v in hw_diff.items()},
           "off_gen1": sorted(off1), "off_gen2": sorted(off2),
           "active_gen1": sorted(active1), "active_gen2": sorted(active2),
           "objective_gen1": obj1, "objective_gen2": obj2,
           "optimization_gap": gap,
           "exact_combinations": g2["solver_meta"].get("n_combinations"),
           "exact_feasible": g2["solver_meta"].get("n_feasible"),
           "seconds": {"gen1": t1, "gen2": t2},
           "verdict": verdict, "note": note}
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2))
        print(f"\nwrote {a.json}")
    return 0 if verdict in ("CONFIRMED", "SUPERSEDED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
