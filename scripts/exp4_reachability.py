#!/usr/bin/env python3
"""Neighbourhood reachability and basin structure. The prior question to C9.

If the certified winner is unreachable from every preregistered start under the
production move set, then no number of starts fixes C9 and the blocker is the
NEIGHBOURHOOD DEFINITION, not basin coverage. That is a different problem with a
different fix, and it must be reported separately rather than absorbed into a
recall number.

WHAT THIS BUILDS
----------------
For each C9 cell, the graph whose nodes are candidate networks and whose edges
are legal Gen2 moves -- add(1), drop(1), swap(1-for-1), add2(2) -- subject to
the cell's cardinality bounds. Then:

  * connected components of that graph;
  * whether each certified winner shares a component with at least one
    preregistered start;
  * basin structure: from EVERY candidate, run deterministic steepest descent
    under the production move set and record which local optimum it reaches.

The basin measurement is the one that says whether revision 1's two misses were
unlucky starts or a structurally tiny winning basin. A winner whose basin is one
or two nodes out of twenty-five will be missed by most seeds however many there
are, and that is a fact about the objective landscape rather than about the
search budget.

Descent here uses the CERTIFIED objective, not the discovery objective. The
question is which local optimum the landscape leads to; using discovery scores
would measure the landscape plus the discovery bias at once, and D18 already
established those are different surfaces. Ground truth is read from the C9
certification cache.

    python scripts/exp4_reachability.py --json outputs/exp4/reachability.json
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


def _subsets(lines, lo, hi):
    for n in range(lo, hi + 1):
        for c in itertools.combinations(sorted(lines), n):
            yield frozenset(c)


def moves_from(cl: tuple, pool: list, lo: int, hi: int):
    """Exactly the move set `gen2_search.search` generates, bounds applied."""
    out = set()
    cur = tuple(sorted(cl))
    for x in pool:                                        # add
        if x not in cur:
            out.add(tuple(sorted(cur + (x,))))
    for x in cur:                                         # drop
        out.add(tuple(sorted(y for y in cur if y != x)))
    for x in cur:                                         # swap
        for y in pool:
            if y not in cur:
                out.add(tuple(sorted(tuple(z for z in cur if z != x) + (y,))))
    outside = [x for x in pool if x not in cur]           # add two at once
    for i, x in enumerate(outside):
        for y in outside[i + 1:]:
            out.add(tuple(sorted(cur + (x, y))))
    return {m for m in out if lo <= len(m) <= hi and m}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    from cota_opt.configs import service_periods
    from cota_opt.exp4_assemble import assemble
    from cota_opt.exp4_network import Exp4Selection
    from cota_opt.exp4_proposal import (N_DIVERSIFIED, build_seed_family,
                                        diversified_starts)
    from cota_opt.firewall.core import digest
    from exp4_c10_fixtures import (CASES, POOL_VERSION, _BY_RID, _boot,
                                   _first_dep_by_period)

    st = _boot()
    H, graph = st["H"], st["graph"]
    periods = sorted(service_periods(H.assumptions))
    first_dep = _first_dep_by_period()

    def assembles(sel):
        try:
            assemble(sel, _BY_RID, graph, H.baseline.network.stops,
                     pool_version=POOL_VERSION,
                     first_dep_sec_by_period=first_dep)
            return True
        except Exception:
            return False

    def solo(pool):
        return [l for l in pool
                if assembles(Exp4Selection(POOL_VERSION, frozenset([l]),
                                           frozenset()))]

    poolA = solo(sorted(CASES[1]["lines"]))
    poolB = solo(sorted(CASES[3]["lines"]))
    poolC = solo(sorted(set(CASES[0]["lines"]) | set(CASES[2]["lines"])))

    CELLS = [
        ("sparse_wide_pool", poolC, 1, 2, ()),
        ("sparse_to_mid", poolA, 1, 3, ()),
        ("dense", poolA, 3, 5, ()),
        ("many_off", poolA, 2, 4, "first"),
        ("other_pool", poolB, 1, 3, ()),
    ]

    cache_dir = ROOT / "outputs" / "exp4" / "c9_cache"
    reports = []
    unreachable_any = False

    for name, pool, lo, hi, pinmode in CELLS:
        pins = (frozenset((pool[0], p) for p in periods)
                if pinmode == "first" else frozenset())
        hi_eff = min(hi, len(pool))
        universe = []
        for s in _subsets(pool, lo, hi_eff):
            sel = Exp4Selection(POOL_VERSION, s,
                                pins if (pins and pool[0] in s) else frozenset())
            if assembles(sel):
                universe.append(sel)
        keys = {tuple(sorted(s.lines)): s.state_key for s in universe}
        nodes = sorted(keys)
        udig = digest({"cell": name, "pool": sorted(pool), "lo": lo,
                       "hi": hi, "pins": sorted(map(list, pins)),
                       "candidates": [keys[n] for n in nodes]})

        # ---- the graph -------------------------------------------------
        nodeset = set(nodes)
        adj = {n: sorted(moves_from(n, pool, lo, hi_eff) & nodeset)
               for n in nodes}
        n_edges = sum(len(v) for v in adj.values()) // 2

        seen, comps = set(), []
        for n in nodes:
            if n in seen:
                continue
            stack, comp = [n], []
            seen.add(n)
            while stack:
                u = stack.pop()
                comp.append(u)
                for v in adj[u]:
                    if v not in seen:
                        seen.add(v)
                        stack.append(v)
            comps.append(sorted(comp))
        comp_of = {n: i for i, c in enumerate(comps) for n in c}

        # ---- the preregistered starts ----------------------------------
        fam = build_seed_family(pool, lo, hi_eff,
                                pinned_lines=[pool[0]] if pins else [])
        fam += diversified_starts(pool, lo, hi_eff, N_DIVERSIFIED)
        start_nodes = [s.lines for s in fam if s.lines in nodeset]
        start_comps = {comp_of[s] for s in start_nodes}

        # ---- ground truth from the certification cache ------------------
        hits = sorted(cache_dir.glob(f"{name}-*.json"))
        cert = {}
        if hits:
            raw = json.loads(hits[-1].read_text())
            key_of = {v: k for k, v in keys.items()}
            for sk, rec in raw.items():
                if sk in key_of:
                    cert[key_of[sk]] = float(rec["objective"])

        winner = min(cert, key=lambda n: (cert[n], len(n), n)) if cert else None
        reach = (winner is not None and comp_of[winner] in start_comps)
        if winner is not None and not reach:
            unreachable_any = True

        # ---- basins, by deterministic steepest descent on CERTIFIED cost -
        basins, opt_of = {}, {}
        if cert:
            for n in nodes:
                if n not in cert:
                    continue
                cur = n
                guard = 0
                while guard < 200:
                    guard += 1
                    nbrs = [m for m in adj[cur] if m in cert]
                    if not nbrs:
                        break
                    best = min(nbrs, key=lambda m: (cert[m], len(m), m))
                    if cert[best] < cert[cur] - 1e-9:
                        cur = best
                    else:
                        break
                opt_of[n] = cur
                basins.setdefault(cur, []).append(n)

        wb = len(basins.get(winner, [])) if winner else 0
        n_scored = len(cert)
        print(f"\n=== {name} ===")
        print(f"  nodes {len(nodes)}  edges {n_edges}  components "
              f"{len(comps)} (sizes {[len(c) for c in comps]})")
        print(f"  preregistered starts in-space: {len(start_nodes)}/{len(fam)}"
              f"  spanning components {sorted(start_comps)}")
        if winner:
            print(f"  certified winner {keys[winner]}  "
                  f"({len(winner)} lines, obj {cert[winner]:,.4f})")
            print(f"  winner reachable from a start: "
                  f"{'YES' if reach else 'NO -- NEIGHBOURHOOD BLOCKER'}")
            print(f"  local optima under certified descent: {len(basins)}")
            print(f"  winner basin size: {wb}/{n_scored} "
                  f"({wb / n_scored:.0%} of the space descends to it)")
            sizes = sorted((len(v) for v in basins.values()), reverse=True)
            print(f"  basin sizes: {sizes}")
        else:
            print("  no certification cache for this cell; "
                  "reachability only")

        reports.append({
            "cell": name, "universe_digest": udig,
            "nodes": len(nodes), "edges": n_edges,
            "n_components": len(comps),
            "component_sizes": [len(c) for c in comps],
            "n_preregistered_starts": len(fam),
            "starts_in_space": len(start_nodes),
            "start_components": sorted(start_comps),
            "certified_winner": keys[winner] if winner else None,
            "winner_lines": list(winner) if winner else None,
            "winner_reachable_from_a_start": reach,
            "n_local_optima": len(basins),
            "winner_basin_size": wb,
            "n_scored": n_scored,
            "winner_basin_fraction": (wb / n_scored) if n_scored else None,
            "basin_sizes": sorted((len(v) for v in basins.values()),
                                  reverse=True),
            "local_optima": [keys[k] for k in sorted(basins)],
        })

    print(f"\n{'=' * 74}")
    print(f"  cells                              : {len(reports)}")
    print(f"  every graph connected              : "
          f"{all(r['n_components'] == 1 for r in reports)}")
    print(f"  every winner reachable from a start: {not unreachable_any}")
    tiny = [r for r in reports if r["winner_basin_fraction"] is not None
            and r["winner_basin_fraction"] < 0.15]
    print(f"  winners with a basin below 15%     : "
          f"{len(tiny)}  {[r['cell'] for r in tiny]}")
    if unreachable_any:
        print("\n  NEIGHBOURHOOD BLOCKER: at least one certified winner is in "
              "no component\n  reachable from any preregistered start. More "
              "starts cannot fix that.")
    else:
        print("\n  No neighbourhood blocker: every certified winner is "
              "reachable under the\n  production move set, so the revision 1 "
              "misses were basin coverage, which is\n  what multi-start "
              "addresses.")

    out = {"diagnostic": "neighbourhood reachability and basin structure",
           "move_set": "add(1), drop(1), swap(1-for-1), add2(2), within bounds",
           "descent_objective": ("CERTIFIED, from the C9 certification cache -- "
                                 "using discovery scores would measure the "
                                 "landscape and the discovery bias at once"),
           "n_cells": len(reports),
           "all_graphs_connected": all(r["n_components"] == 1
                                       for r in reports),
           "all_winners_reachable": not unreachable_any,
           "neighbourhood_blocker": unreachable_any,
           "cells": reports}
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(out, indent=2))
        print(f"\nwrote {a.json}")
    return 2 if unreachable_any else 0


if __name__ == "__main__":
    raise SystemExit(main())
