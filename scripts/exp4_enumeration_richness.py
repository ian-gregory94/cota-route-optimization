#!/usr/bin/env python3
"""Enumeration richness, as its own diagnostic. NOT gate 4-7.

Gate 4-7 asks one question: does reusing a frozen supernetwork master path set
pick the same network as rebuilding paths per candidate? `exp4_gate47.py`
answers it with both arms enumerating under identical settings, so the only
thing that varies is reuse.

This script measures the OTHER thing the first benchmark accidentally varied:
what changes when the path enumeration itself is made richer. It is informational.
It has no gate, it cannot close one, and its numbers may not be used to argue
that reuse is better or worse than it measured.

WHY IT IS SEPARATE
------------------
The original gate 4-7 benchmark built the master with `n_random_scenarios=6` and
the exact arm with `0`. At survival fraction 1.000 -- where filtering keeps every
path and is therefore the identity -- the two arms still differed, and the
master-fed arm was *better* in 4 of 5 cases. A difference that survives the
identity transformation was never caused by that transformation. Both factors
moved, so neither was identified.

Richness has a real effect and deserves to be measured. It just is not the
question gate 4-7 asks, and mixing the two makes both unanswerable.

WHAT IT MEASURES
----------------
Per case, the same canonical candidate universe scored at two enumeration
settings, with NO reuse in either arm -- every candidate rebuilds its own paths
both times:

    BASE   n_random_scenarios = 0   (what the exact-rebuild path uses today)
    RICH   n_random_scenarios = R   (--scenarios, default 6)

and reports candidate-count differences, per-candidate score differences, leader
changes, ranking inversions and promoted-set changes between the two.

A large effect here is a finding about the PATH MODEL, not about reuse: it would
mean the production enumeration setting materially changes which network wins,
which is a question for gate 4-9 (path-model adequacy) and for whatever setting
certification is eventually frozen at. It is recorded here so that the choice is
made on evidence rather than inherited.

    python scripts/exp4_enumeration_richness.py --json outputs/exp4/enumeration_richness.json
"""
from __future__ import annotations

import argparse
import itertools
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
PROMOTED_K = 3


def _subsets(lines, lo, hi):
    for n in range(lo, hi + 1):
        for c in itertools.combinations(sorted(lines), n):
            yield frozenset(c)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--cases", type=int, default=5)
    ap.add_argument("--max-candidates", type=int, default=16)
    ap.add_argument("--scenarios", type=int, default=6,
                    help="the RICH arm's n_random_scenarios; BASE is always 0")
    a = ap.parse_args()

    from cota_opt.contract import ContractLimits
    from cota_opt.exp4_assemble import assemble
    from cota_opt.exp4_network import Exp4Selection
    from cota_opt.exp4_score import score_exp4_network
    from cota_opt.configs import service_periods
    from cota_opt.firewall.core import digest
    from exp2_treatments import pinned
    from exp4_c10_fixtures import (CASES, POOL_VERSION, _BY_RID, _boot,
                                   _first_dep_by_period)

    st = _boot()
    H, sg, graph = st["H"], st["sg"], st["graph"]
    periods = sorted(service_periods(H.assumptions))
    first_dep = _first_dep_by_period()
    t_all = time.time()

    def assembles(sel):
        try:
            assemble(sel, _BY_RID, graph, H.baseline.network.stops,
                     pool_version=POOL_VERSION,
                     first_dep_sec_by_period=first_dep)
            return True
        except Exception:
            return False

    def score(sel, case, scen):
        vh = float(case["veh_hour_budget"])
        peak = float(case.get("peak_vehicle_budget", 40.0))
        cons = pinned(vh, {p: peak for p in periods})
        limits = ContractLimits(veh_hour_budget=vh, peak_vehicle_budget=peak,
                                required_waiting_model="same_route")
        eff = case.get("effort", (20_000, 1, 0))
        cache: dict = {}
        try:
            scored, _ = score_exp4_network(
                sel, harness=H, stops_gdf=sg, pool=_BY_RID, graph=graph,
                pool_version=POOL_VERSION, first_dep_sec_by_period=first_dep,
                limits=limits, constraints=cons, lam=2.0, seed=20260825,
                iterations=eff[0], restarts=eff[1], width=eff[2],
                waiting_model="same_route", starts="greedy", allow_off=True,
                # a FRESH dict, never shared between candidates: this script
                # measures enumeration richness with reuse held OFF in both arms
                pathset_cache=cache, n_random_scenarios=scen)
        except Exception as e:
            return None, {}
        return ({"objective": float(scored.metrics.get("objective", float("inf"))),
                 "fitness": dict(scored.fitness)},
                {p: int(ps.n_paths) for p, ps in cache.items()})

    reports = []
    for case in CASES[:a.cases]:
        name = case["name"]
        pool_lines = sorted(case["lines"])
        lo = int(case.get("min_lines", 1))
        hi = int(case.get("max_lines", len(pool_lines)))
        solo = [ln for ln in pool_lines
                if assembles(Exp4Selection(POOL_VERSION, frozenset([ln]),
                                           frozenset()))]
        if not solo:
            continue
        sup = Exp4Selection(POOL_VERSION, frozenset(solo), frozenset())
        if not assembles(sup):
            continue
        pin = sorted(sup.lines)[0]
        proposed = [("supernetwork", sup),
                    ("pinned_off", Exp4Selection(
                        POOL_VERSION, frozenset(sup.lines),
                        frozenset((pin, p) for p in periods)))]
        for s in _subsets(sorted(sup.lines), lo, hi):
            proposed.append(("subset",
                             Exp4Selection(POOL_VERSION, s, frozenset())))
        universe = [(k, s) for k, s in proposed if assembles(s)][:a.max_candidates]
        udig = digest({"case": name,
                       "candidates": [[k, s.state_key] for k, s in universe]})
        print(f"\n=== {name}: {len(universe)} candidates, digest {udig} ===")

        rows = []
        for kind, sel in universe:
            base, np_base = score(sel, case, 0)
            rich, np_rich = score(sel, case, a.scenarios)
            if base is None or rich is None:
                continue
            per = {}
            worst = 0.0
            for f in FIELDS:
                lv, rv = float(base["fitness"][f]), float(rich["fitness"][f])
                rd = abs(rv - lv) / abs(lv) if lv else abs(rv - lv)
                per[f] = {"base": lv, "rich": rv, "rel_diff": rd}
                worst = max(worst, rd)
            rows.append({
                "kind": kind, "id": sel.state_key,
                "lines": sorted(sel.lines),
                "objective_base": base["objective"],
                "objective_rich": rich["objective"],
                "objective_rel_gap": (abs(rich["objective"] - base["objective"])
                                      / abs(base["objective"])
                                      if base["objective"] else 0.0),
                "rich_is_better": rich["objective"] < base["objective"],
                "paths_base": np_base, "paths_rich": np_rich,
                "path_count_delta": {p: np_rich.get(p, 0) - np_base.get(p, 0)
                                     for p in sorted(np_base)},
                "fields": per, "worst_rel_diff": worst})
            print(f"  {kind:<13} base {base['objective']:.4f}  "
                  f"rich {rich['objective']:.4f}  "
                  f"{'RICH better' if rows[-1]['rich_is_better'] else 'base better/equal'}"
                  f"  rel {rows[-1]['objective_rel_gap']:.3e}")

        inv, prs = 0, 0
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                prs += 1
                if ((rows[i]["objective_base"] - rows[j]["objective_base"]) *
                        (rows[i]["objective_rich"] - rows[j]["objective_rich"])) < 0:
                    inv += 1
        lb = min(rows, key=lambda r: r["objective_base"])["id"] if rows else None
        lr = min(rows, key=lambda r: r["objective_rich"])["id"] if rows else None
        k = min(PROMOTED_K, len(rows))
        tb = {r["id"] for r in sorted(rows, key=lambda r: r["objective_base"])[:k]}
        tr = {r["id"] for r in sorted(rows, key=lambda r: r["objective_rich"])[:k]}
        rep = {"case": name, "universe_digest": udig, "n": len(rows),
               "leader_base": lb, "leader_rich": lr, "leader_changes": lb != lr,
               "ranking_inversions": inv, "ranking_pairs": prs,
               "promoted_changes": tb != tr,
               "promoted_base": sorted(tb), "promoted_rich": sorted(tr),
               "n_rich_better": sum(r["rich_is_better"] for r in rows),
               "worst_objective_rel_gap":
                   max((r["objective_rel_gap"] for r in rows), default=0.0),
               "worst_field_rel_diff":
                   max((r["worst_rel_diff"] for r in rows), default=0.0),
               "rows": rows}
        reports.append(rep)
        print(f"  -> leader {'CHANGES' if rep['leader_changes'] else 'unchanged'}, "
              f"{inv}/{prs} inversions, promoted set "
              f"{'CHANGES' if rep['promoted_changes'] else 'unchanged'}, "
              f"rich better in {rep['n_rich_better']}/{len(rows)}")

    tot_inv = sum(r["ranking_inversions"] for r in reports)
    tot_prs = sum(r["ranking_pairs"] for r in reports)
    print(f"\n{'=' * 72}")
    print(f"  cases                    : {len(reports)}")
    print(f"  leader changes           : "
          f"{sum(r['leader_changes'] for r in reports)}/{len(reports)}")
    print(f"  promoted set changes     : "
          f"{sum(r['promoted_changes'] for r in reports)}/{len(reports)}")
    print(f"  ranking inversions       : {tot_inv}/{tot_prs}")
    print(f"  worst objective rel gap  : "
          f"{max((r['worst_objective_rel_gap'] for r in reports), default=0.0):.3e}")
    print("\n  INFORMATIONAL. This is not gate 4-7 and closes nothing.")

    out = {"diagnostic": "enumeration richness (NOT gate 4-7)",
           "gate": None,
           "base_scenarios": 0, "rich_scenarios": a.scenarios,
           "reuse": "OFF in both arms -- every candidate rebuilds its own paths",
           "n_cases": len(reports),
           "leader_changes": sum(r["leader_changes"] for r in reports),
           "promoted_changes": sum(r["promoted_changes"] for r in reports),
           "ranking_inversions": tot_inv, "ranking_pairs": tot_prs,
           "worst_objective_rel_gap":
               max((r["worst_objective_rel_gap"] for r in reports), default=0.0),
           "worst_field_rel_diff":
               max((r["worst_field_rel_diff"] for r in reports), default=0.0),
           "note": ("informational unless the preregistration separately gives "
                    "it a gate; a large effect here is a finding about the PATH "
                    "MODEL and belongs to gate 4-9, not to gate 4-7"),
           "seconds": time.time() - t_all,
           "cases": reports}
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(out, indent=2))
        print(f"\nwrote {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
