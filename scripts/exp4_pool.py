#!/usr/bin/env python3
"""Generate and freeze the Experiment 4 route pool — contract item 10.

Legacy inclusion is checked, not assumed: the pool must contain every current
local route, or a poor Experiment 4 result cannot be distinguished from a
generator that failed to propose what COTA already runs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cota_opt import geo                                     # noqa: E402
from cota_opt.harness import build_harness                   # noqa: E402
from cota_opt.linkgraph import build_link_graph              # noqa: E402
from cota_opt.routepool import generate_pool                 # noqa: E402
from cota_opt.synthetic import reconstruct_current           # noqa: E402

OUT = ROOT / "outputs" / "exp4"
POOL_VERSION = "exp4-pool-v1"


def main() -> int:
    H = build_harness(seed=20260825, common_lines="same_route",
                      with_pathsets=False)
    express = {r for r, c in H.classes.items() if c.klass == "peak_express"}
    g = build_link_graph(H.baseline.network, H.baseline.tstats,
                         exclude_routes=express)
    sg = geo.stops_gdf(H.baseline.feed, H.assumptions["crs"]["projected"])
    coords = {r.stop_id: (r.geometry.x, r.geometry.y) for r in sg.itertuples()}

    legacy, recon = reconstruct_current(g, H.baseline.network,
                                        exclude_routes=express)

    # Demand reaching each stop, via the zone system: the ranking the OD,
    # crosstown and trunk generators use to choose endpoints.
    zone_flow = np.zeros(H.zones.n)
    np.add.at(zone_flow, H.od.origin, H.od.flow)
    np.add.at(zone_flow, H.od.dest, H.od.flow)
    stop_demand: dict[str, float] = {}
    for zi in range(H.zones.n):
        f = float(zone_flow[zi])
        if f <= 0:
            continue
        stops, walks = H.zones.access_of(zi)
        if not len(stops):
            continue
        # A zone's flow is shared among the stops that can reach it, weighted
        # against walking time. Spreading it evenly would make a stop next to a
        # dense block group look identical to one ten minutes away from it.
        w = 1.0 / (1.0 + np.asarray(walks, dtype=float))
        w = w / w.sum()
        for sidx, wi in zip(stops, w):
            s = H.raptor.stop_ids[int(sidx)]
            stop_demand[s] = stop_demand.get(s, 0.0) + f * float(wi)

    terminals = {r.outbound[0] for r in legacy} | {r.outbound[-1] for r in legacy}

    audit = generate_pool(g, coords, legacy, stop_demand=stop_demand,
                          terminals=terminals)
    doc = audit.as_dict()

    legacy_rids = {r.rid for r in legacy}
    pool_rids = {r.rid for r in audit.accepted}
    doc.update({
        "pool_version": POOL_VERSION,
        "legacy_lines": len(legacy),
        "legacy_in_pool": len(legacy_rids & pool_rids),
        "legacy_inclusion_complete": legacy_rids <= pool_rids,
        "stops_reachable_by_pool": len({s for r in audit.accepted
                                        for s in r.stops}),
        "stops_in_network": recon["stops_in_legacy_network"],
        "routes": [r.as_dict() for r in audit.accepted],
        "rejections": audit.rejected[:200],
    })

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "route_pool.json").write_text(json.dumps(doc, indent=2) + "\n")

    print("=" * 84)
    print(f"EXPERIMENT 4 ROUTE POOL — {POOL_VERSION}")
    print("=" * 84)
    print(f"  proposed                 {doc['proposed']}")
    print(f"  accepted                 {doc['accepted']}  "
          f"{doc['accepted_by_generator']}")
    print(f"  rejected                 {doc['rejected']}  "
          f"{doc['rejected_by_reason']}")
    print()
    print(f"  legacy lines in pool     {doc['legacy_in_pool']}/"
          f"{doc['legacy_lines']}")
    print(f"  LEGACY INCLUSION         {doc['legacy_inclusion_complete']}")
    print(f"  stops reachable by pool  {doc['stops_reachable_by_pool']} of "
          f"{doc['stops_in_network']}")
    print()
    print(f"  one-way minutes          {doc['oneway_minutes']}")
    print(f"  sitting on the bound     {doc['on_length_bound']}")
    print(f"  max modelled share       {doc['modelled_share_max']}")
    ok = doc["legacy_inclusion_complete"]
    print(f"\n  VERDICT: {'PASS' if ok else 'FAIL'}")
    if not ok:
        print("  The pool does not contain the current network, so Experiment 4")
        print("  could not tell a null result from a generator failure.")
    print(f"\nartifacts: {OUT / 'route_pool.json'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
