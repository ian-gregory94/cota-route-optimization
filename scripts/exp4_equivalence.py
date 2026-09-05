#!/usr/bin/env python3
"""Does an assembled network reproduce the legacy scoring path exactly?

The Experiment 4 substrate claims to reuse Generation 1's evaluation semantics
rather than fork them. That claim is worth exactly as much as a measurement of
it, so this builds the SAME network two ways and scores both:

    legacy   H.baseline.network / H.baseline.tstats  -> solve_on_network
    assembled  the same patterns, rebuilt through exp4_assemble's own
               construction path                     -> solve_on_network

The contract's own rule for a new representation (item 4, "the one to build
first and the one most likely to fail quietly"): **do not trust a new
representation until it reproduces a number the old one already produced.**

This is deliberately NOT run through `assemble()` from the pool, because the
pool's synthetic lines are not the legacy network. It exercises the same
TransitNetwork/tstats construction the assembler performs -- content-derived
pattern ids, sorted iteration, per-segment times, one trip per pattern-period --
on the legacy geometry, which is the only geometry with a known answer.

    python scripts/exp4_equivalence.py --json outputs/exp4/equivalence.json
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

import pandas as pd                                            # noqa: E402

from cota_opt import geo                                       # noqa: E402
from cota_opt.contract import ContractLimits                   # noqa: E402
from cota_opt.exp3_score import solve_on_network               # noqa: E402
from cota_opt.geometry import SegmentTimeModel                 # noqa: E402
from cota_opt.harness import build_harness                     # noqa: E402
from exp3_pin_envelope import load as pin_load                    # noqa: E402

SEED = 20260825


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--restarts", type=int, default=2)
    ap.add_argument("--iterations", type=int, default=60_000)
    ap.add_argument("--width", type=int, default=32)
    a = ap.parse_args()

    t0 = time.time()
    H = build_harness(seed=SEED, common_lines="same_route", with_pathsets=False)
    sg = geo.stops_gdf(H.baseline.feed, H.assumptions["crs"]["projected"])
    SegmentTimeModel.fit(H.baseline.network, sg)
    limits = ContractLimits(
        veh_hour_budget=float(H.baseline.tstats["runtime_min"].sum() / 60.0),
        peak_vehicle_budget=197.0, required_waiting_model="same_route")
    CONS = pin_load()
    print(f"harness ready in {time.time() - t0:.0f}s")

    kw = dict(harness=H, stops_gdf=sg, lam=2.0, seed=SEED,
              iterations=a.iterations, restarts=a.restarts, width=a.width,
              constraints=CONS, waiting_model="same_route", starts="incumbent")

    print("scoring the LEGACY network through solve_on_network ...")
    t = time.time()
    legacy = solve_on_network(H.baseline.network, H.baseline.tstats, **kw)
    t_legacy = time.time() - t

    # Rebuild the identical network through the assembler's own construction
    # rules, then score it the same way.
    from cota_opt.exp4_assemble import rebuild_like_assembler
    net2, ts2 = rebuild_like_assembler(H.baseline.network, H.baseline.tstats)
    print(f"rebuilt: {len(net2.patterns)} patterns, {len(net2.stops)} stops, "
          f"{len(ts2)} tstat rows")

    print("scoring the ASSEMBLED network ...")
    t = time.time()
    asm = solve_on_network(net2, ts2, **kw)
    t_asm = time.time() - t

    lf, af = legacy["fit"], asm["fit"]
    fields = ["objective", "generalized_cost", "unserved_demand",
              "served_demand", "revenue_veh_hours", "peak_concurrency"]
    rows = []
    worst = 0.0
    for f in fields:
        lv = float(getattr(lf, f, float("nan")))
        av = float(getattr(af, f, float("nan")))
        rel = abs(av - lv) / abs(lv) if lv else abs(av - lv)
        worst = max(worst, rel)
        rows.append({"field": f, "legacy": lv, "assembled": av,
                     "abs_diff": av - lv, "rel_diff": rel})
    print(f"\n  {'field':<22} {'legacy':>18} {'assembled':>18} {'rel':>12}")
    for r in rows:
        print(f"  {r['field']:<22} {r['legacy']:>18.6f} "
              f"{r['assembled']:>18.6f} {r['rel_diff']:>12.3e}")
    print(f"\n  worst relative difference: {worst:.3e}")
    print(f"  legacy {t_legacy:.0f}s | assembled {t_asm:.0f}s")

    out = {"seed": SEED, "effort": f"{a.iterations}/{a.restarts}/{a.width}",
           "fields": rows, "worst_rel_diff": worst,
           "seconds": {"legacy": t_legacy, "assembled": t_asm},
           "n_patterns": {"legacy": len(H.baseline.network.patterns),
                          "assembled": len(net2.patterns)},
           "n_stops": {"legacy": len(H.baseline.network.stops),
                       "assembled": len(net2.stops)}}
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2))
        print(f"\nwrote {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
