#!/usr/bin/env python3
"""Rebuild COTA's current local network in the synthetic representation.

Item 4 of Experiment 4's definition of ready, and the one the contract calls
most likely to fail quietly. It is the Experiment 4 form of OPERATIONS.md rule
15: **do not trust a new representation until it reproduces a number the old one
already produced.**

If the current network cannot be expressed as paths through the observed-link
graph, then the frozen route pool cannot contain it — and a poor Experiment 4
result would be indistinguishable from a generator that simply failed to propose
what COTA already runs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cota_opt.harness import build_harness                    # noqa: E402
from cota_opt.linkgraph import build_link_graph               # noqa: E402
from cota_opt.synthetic import (SyntheticNetwork,             # noqa: E402
                                reconstruct_current)

OUT = ROOT / "outputs" / "exp4"


def main() -> int:
    H = build_harness(seed=20260825, common_lines="same_route",
                      with_pathsets=False)
    express = {r for r, c in H.classes.items() if c.klass == "peak_express"}
    g = build_link_graph(H.baseline.network, H.baseline.tstats,
                         exclude_routes=express)
    routes, rep = reconstruct_current(g, H.baseline.network,
                                      exclude_routes=express)

    # Identity checks the representation has to satisfy before anything is
    # built on it.
    rids = [r.rid for r in routes]
    rep["unique_rids"] = len(set(rids))
    rep["rid_collisions"] = len(rids) - len(set(rids))

    periods = list(H.assumptions["demand_proxy"]["period_shares"])
    act = {r.rid: {p: 30.0 for p in periods} for r in routes}
    n1 = SyntheticNetwork(tuple(routes), act)
    n2 = SyntheticNetwork(tuple(reversed(routes)), dict(act))
    rep["digest_is_order_free"] = (n1.digest == n2.digest)

    off = {r.rid: {p: None for p in periods} for r in routes}
    rep["all_off_is_the_empty_network"] = (
        SyntheticNetwork(tuple(routes), off).digest
        == SyntheticNetwork((), {}).digest)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "reconstruction.json").write_text(json.dumps(
        {**rep, "routes": [r.as_dict() for r in routes]}, indent=2) + "\n")

    print("=" * 84)
    print("EXPERIMENT 4 — RECONSTRUCTING THE CURRENT NETWORK SYNTHETICALLY")
    print("=" * 84)
    print(f"  legacy local routes          {rep['legacy_routes_seen']}")
    print(f"  reconstructed                {rep['reconstructed']}")
    print(f"  failed                       {rep['failed']}")
    for f in rep["failures"][:6]:
        print(f"      route {f['route_id']}: {f['why'][:110]}")
    print(f"  EVERY ROUTE RECONSTRUCTED    {rep['every_route_reconstructed']}")
    print()
    print(f"  stops covered                {rep['stops_covered']} of "
          f"{rep['stops_in_legacy_network']}")
    print(f"  stop coverage complete       {rep['stop_coverage_complete']}")
    if rep["stops_missed"]:
        print(f"      missed: {rep['stops_missed']}")
    print()
    print(f"  one-way minutes              {rep['oneway_minutes']}")
    print(f"  outside the 10-120 bound     {len(rep['outside_search_bounds'])}")
    print()
    print(f"  unique canonical ids         {rep['unique_rids']} "
          f"(collisions {rep['rid_collisions']})")
    print(f"  digest is order-free         {rep['digest_is_order_free']}")
    print(f"  all-OFF == empty network     "
          f"{rep['all_off_is_the_empty_network']}")

    ok = (rep["every_route_reconstructed"] and rep["rid_collisions"] == 0
          and rep["digest_is_order_free"]
          and rep["all_off_is_the_empty_network"])
    print()
    print(f"  VERDICT: {'PASS' if ok else 'FAIL'}")
    if not ok:
        print("  The route pool cannot be built until this passes: a pool that")
        print("  cannot contain the current network cannot tell 'greenfield is")
        print("  not better' from 'the generator missed what COTA runs'.")
    print(f"\nartifacts: {OUT / 'reconstruction.json'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
