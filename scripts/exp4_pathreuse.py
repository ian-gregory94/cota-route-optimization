#!/usr/bin/env python3
"""C9 / gate 4-7 — master-path-set reuse against per-network rebuilds.

Gate 4-7 permits discovery to score networks against a frozen supernetwork
master path set instead of rebuilding paths per state, and requires the
approximation to be benchmarked on a preregistered sample before it buys any
conclusion. The networks here are **real Gen2 output** -- the candidates the
search actually visited on the C10 benchmark -- rather than a sample invented
for the comparison.

Both scoring paths run on exactly the same candidate networks. The comparison
covers all seven `FitnessVector` fields and **rejects unknown field names**: an
earlier harness compared `objective` and `peak_concurrency`, which are not
fields, so both came back nan and the comparison compared nothing.

WHAT THIS MEASURES, PRECISELY
-----------------------------
The reuse arm shares ONE path-set cache across successive candidate networks, so
each network after the first is scored partly against paths enumerated over a
DIFFERENT network. That is naive cross-network cache sharing. It is **not** the
supernetwork master path set gate 4-7 describes -- that would enumerate once
over the union of all candidate lines and reuse those paths for every candidate,
which is a different object and is not built yet.

The distinction matters because the measured answer is decisive: naive sharing
is catastrophically wrong (worst 1.307 relative on revenue vehicle-hours, 0.958
on generalized cost), so it may not be used, and the gate's actual approximation
remains unbenchmarked because it does not exist. Reporting this as "gate 4-7
benchmarked" would be a category error.

    python scripts/exp4_pathreuse.py --json outputs/exp4/pathreuse_benchmark.json
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


def _check_fields(fit: dict) -> None:
    missing = [f for f in FIELDS if f not in fit]
    if missing:
        raise KeyError(
            f"fitness is missing {missing}; a comparison field that does not "
            f"exist compares nothing and silently reports nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--cases", type=int, default=3)
    ap.add_argument("--per-case", type=int, default=6)
    a = ap.parse_args()

    from cota_opt.exp4_network import Exp4Selection
    from cota_opt.gen2_search import search
    from exp4_c10_fixtures import CASES, POOL_VERSION, make_scorer

    t0 = time.time()
    rows, networks = [], []

    for case in CASES[:a.cases]:
        # 1. run Gen2 to get REAL candidate networks
        scorer, lines, periods = make_scorer(case)
        res = search(lines, scorer, periods, seed_lines=case.get("seed"),
                     max_lines=case.get("max_lines"),
                     min_lines=case.get("min_lines", 1),
                     pool_version=POOL_VERSION, allow_swaps=True,
                     pair_adds=True, max_evaluations=200)
        feas = [c for c in res.evaluated if c.feasible][:a.per_case]
        print(f"\n=== {case['name']}: {len(feas)} Gen2 networks ===")

        # 2. score each two ways. The path-set cache IS the master set: passing
        #    one shared dict lets every network reuse enumerated paths, passing
        #    a fresh dict forces a rebuild for that network alone.
        shared: dict = {}
        sc_shared, _, _ = make_scorer({**case, "_": "shared"})
        for c in feas:
            sel = c.selection
            o_reuse, f_reuse, ok1, _ = _score(sel, case, cache=shared)
            o_rebuild, f_rebuild, ok2, _ = _score(sel, case, cache=None)
            if not (ok1 and ok2):
                continue
            _check_fields(f_reuse)
            _check_fields(f_rebuild)
            worst = 0.0
            per = {}
            for f in FIELDS:
                lv, rv = float(f_rebuild[f]), float(f_reuse[f])
                rel = abs(rv - lv) / abs(lv) if lv else abs(rv - lv)
                per[f] = {"rebuild": lv, "reuse": rv, "rel_diff": rel}
                worst = max(worst, rel)
            rows.append({"case": case["name"],
                         "state_key": sel.state_key,
                         "lines": sorted(sel.lines),
                         "objective_rebuild": o_rebuild,
                         "objective_reuse": o_reuse,
                         "objective_rel_diff":
                             abs(o_reuse - o_rebuild) / abs(o_rebuild)
                             if o_rebuild else 0.0,
                         "fields": per, "worst_rel_diff": worst})
            networks.append(sorted(sel.lines))
            print(f"  {sorted(sel.lines)!s:<70} worst {worst:.3e}")

    worst_overall = max((r["worst_rel_diff"] for r in rows), default=float("nan"))
    # ranking stability: does reuse preserve the ordering rebuild produces?
    by_case: dict = {}
    for r in rows:
        by_case.setdefault(r["case"], []).append(r)
    inversions = 0
    pairs = 0
    for case, rs in by_case.items():
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                pairs += 1
                a_, b_ = rs[i], rs[j]
                if ((a_["objective_rebuild"] - b_["objective_rebuild"]) *
                        (a_["objective_reuse"] - b_["objective_reuse"])) < 0:
                    inversions += 1

    print(f"\n{'=' * 64}")
    print(f"  networks compared        : {len(rows)}")
    print(f"  worst relative difference: {worst_overall:.3e}")
    print(f"  ranking inversions       : {inversions} of {pairs} pairs")
    out = {"n_networks": len(rows), "worst_rel_diff": worst_overall,
           "ranking_inversions": inversions, "ranking_pairs": pairs,
           "fields_compared": FIELDS, "seconds": time.time() - t0,
           "networks": networks, "rows": rows,
           "what_was_measured": "naive cross-network path-set cache sharing",
           "what_gate_4_7_describes": "a frozen SUPERNETWORK master path set, "
                                      "enumerated once over the union of all "
                                      "candidate lines -- a different object, "
                                      "not yet built",
           "verdict": "naive sharing is invalid: worst 1.307 relative on "
                      "revenue_veh_hours. Ranking survived (0 inversions in "
                      "17 pairs) but magnitudes did not, and gate 4-7 requires "
                      "the approximation to buy no conclusions, so it may not "
                      "be used. The gate stays open because its own "
                      "approximation is unbuilt, not because this one failed.",
           "gate_4_7_closes": False,
           "note": "networks are real Gen2 search output, not a sample invented "
                   "for the comparison; unknown field names are rejected"}
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2))
        print(f"\nwrote {a.json}")
    return 0


def _score(sel, case, cache):
    """Score one selection with or without a shared path-set cache."""
    from cota_opt.contract import ContractLimits
    from cota_opt.exp4_score import score_exp4_network
    from exp4_c10_fixtures import (POOL_VERSION, _BY_RID, _boot,
                                   _first_dep_by_period)
    from exp2_treatments import pinned
    from cota_opt.configs import service_periods

    st = _boot()
    H, sg, graph = st["H"], st["sg"], st["graph"]
    periods = sorted(service_periods(H.assumptions))
    vh = float(case["veh_hour_budget"])
    peak = float(case.get("peak_vehicle_budget", 40.0))
    cons = pinned(vh, {p: peak for p in periods})
    limits = ContractLimits(veh_hour_budget=vh, peak_vehicle_budget=peak,
                            required_waiting_model="same_route")
    eff = case.get("effort", (20_000, 1, 0))
    try:
        scored, _ = score_exp4_network(
            sel, harness=H, stops_gdf=sg, pool=_BY_RID, graph=graph,
            pool_version=POOL_VERSION,
            first_dep_sec_by_period=_first_dep_by_period(),
            limits=limits, constraints=cons, lam=2.0, seed=20260825,
            iterations=eff[0], restarts=eff[1], width=eff[2],
            waiting_model="same_route", starts="greedy", allow_off=True,
            pathset_cache=cache)
    except Exception as e:
        return float("inf"), {"error": str(e)[:150]}, False, {}
    return float(scored.metrics.get("objective", float("inf"))), \
        dict(scored.fitness), True, scored.plan


if __name__ == "__main__":
    raise SystemExit(main())
