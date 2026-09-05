#!/usr/bin/env python3
"""Search the pool for a space that genuinely defeats greedy.

Gate 4-14 asks for "a space that can defeat it". Three hand-built spaces did
not, so this looks for one instead of tuning until something passes. Each
candidate space is a small set of pool lines under a binding envelope; for each,
the oracle enumerates every feasible selection with the PRODUCTION evaluator and
add-only greedy is run against it. A space is kept only when greedy misses the
enumerated optimum.

Being unable to find one would itself be a result, and would be reported as one.

    python scripts/exp4_find_deceptive.py --spaces 40 --json outputs/exp4/deceptive_search.json
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cota_opt.gen2_search import enumerate_exact, search            # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spaces", type=int, default=40)
    ap.add_argument("--seed", type=int, default=414)
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    from exp4_c10_fixtures import POOL_VERSION, _BY_RID, make_scorer

    rng = random.Random(a.seed)
    # short lines keep enumeration cheap; overlap is what creates transfers
    short = sorted((r for r in _BY_RID.values() if r["oneway_min"] < 45),
                   key=lambda r: r["oneway_min"])[:24]
    rids = [r["rid"] for r in short]
    stops = {r["rid"]: set(r["outbound"]) | set(r["inbound"]) for r in short}

    found, tried = [], []
    t0 = time.time()
    for i in range(a.spaces):
        lines = rng.sample(rids, 5)
        overlap = max(len(stops[x] & stops[y])
                      for x, y in itertools.combinations(lines, 2))
        vh = rng.choice([90.0, 120.0, 160.0, 200.0])
        case = {"name": f"scan{i}", "lines": lines, "max_lines": 3,
                "min_lines": 1, "effort": (20_000, 1, 0),
                "veh_hour_budget": vh,
                "peak_vehicle_budget": rng.choice([10.0, 14.0, 18.0])}
        scorer, ls, periods = make_scorer(case)
        try:
            oracle = enumerate_exact(ls, scorer, periods, max_lines=3,
                                     min_lines=1, pool_version=POOL_VERSION,
                                     max_networks=64)
        except Exception as e:
            tried.append({"space": i, "error": str(e)[:120]})
            continue
        if oracle.best is None:
            tried.append({"space": i, "note": "no feasible network"})
            continue
        g = search(ls, scorer, periods, seed_lines=[lines[0]], max_lines=3,
                   min_lines=1, pool_version=POOL_VERSION, allow_swaps=False,
                   max_evaluations=200)
        opt = sorted(oracle.best.selection.lines)
        got = sorted(g.best.selection.lines) if g.best else None
        missed = got != opt
        rec = {"space": i, "lines": lines, "veh_hour_budget": vh,
               "peak_vehicle_budget": case["peak_vehicle_budget"],
               "max_stop_overlap": overlap,
               "n_enumerated": oracle.n_evaluations,
               "optimum": opt, "optimum_objective": oracle.best.objective,
               "greedy": got,
               "greedy_objective": g.best.objective if g.best else None,
               "greedy_missed": missed}
        tried.append(rec)
        flag = "DECEPTIVE" if missed else "greedy finds it"
        print(f"  space {i:2d}  vh {vh:5.0f}  overlap {overlap:3d}  "
              f"opt {len(opt)} lines  {flag}")
        if missed:
            found.append(rec)

    print(f"\n  scanned {len(tried)} spaces in {time.time() - t0:.0f}s")
    print(f"  deceptive spaces found: {len(found)}")
    out = {"n_scanned": len(tried), "n_deceptive": len(found),
           "seconds": time.time() - t0, "deceptive": found, "all": tried}
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2))
        print(f"  wrote {a.json}")
    return 0 if found else 1


if __name__ == "__main__":
    raise SystemExit(main())
