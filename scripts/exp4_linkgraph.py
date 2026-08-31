#!/usr/bin/env python3
"""Build and audit the Experiment 4 observed-link graph.

Item 6 of the definition of ready, and the foundation the rest sits on. The
audit's load-bearing assertion is that **every pattern of every included route
is a serviceable path through the graph** — if the graph has lost a movement
COTA operates, a route pool built on it could not contain the current network,
which the contract makes mandatory.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cota_opt.harness import build_harness              # noqa: E402
from cota_opt.linkgraph import audit, build_link_graph  # noqa: E402

OUT = ROOT / "outputs" / "exp4"


def main() -> int:
    H = build_harness(seed=20260825, common_lines="same_route",
                      with_pathsets=False)
    express = {r for r, c in H.classes.items() if c.klass == "peak_express"}
    g = build_link_graph(H.baseline.network, H.baseline.tstats,
                         exclude_routes=express)
    res = audit(g, H.baseline.network, exclude_routes=express)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "linkgraph_audit.json").write_text(json.dumps(res, indent=2) + "\n")

    print("=" * 84)
    print("EXPERIMENT 4 — OBSERVED-LINK GRAPH")
    print("=" * 84)
    print(f"  stops                        {res['n_stops']}")
    print(f"  directed links               {res['n_directed_links']}")
    print(f"  links >1 route serves        "
          f"{res['n_links_served_by_more_than_one_route']}")
    print(f"  out-degree                   mean {res['mean_out_degree']}, "
          f"max {res['max_out_degree']}")
    print(f"  run time (s)                 {res['run_time_sec']}")
    print(f"  observations per link        {res['observations_per_link']}")
    print(f"  excluded (peak express)      {len(res['excluded_routes'])} routes")
    print()
    print(f"  patterns checked             {res['patterns_checked']}")
    print(f"  not serviceable              {res['patterns_not_serviceable']} "
          f"{res['not_serviceable_examples']}")
    print(f"  EVERY PATTERN IS A PATH      {res['every_pattern_is_a_path']}")
    print(f"  strongly connected           {res['is_strongly_connected']} "
          f"({res['strongly_connected_components']} component(s), largest "
          f"{res['largest_component_stops']})")
    print()
    print(f"  branch points (choice)       {res['branch_points']} "
          f"({100 * res['branch_point_share']:.1f}% of stops)")
    print(f"  merge points                 {res['merge_points']}")
    print(f"  true junctions               {res['true_junctions']}")
    print(f"  links w/ ONE observation     {res['links_with_one_observation']} "
          f"({100 * res['single_observation_share']:.1f}%)")
    print()
    if not res["every_pattern_is_a_path"]:
        print("  FAIL — the graph has lost a movement COTA operates, so a route")
        print("  pool built on it could not contain the current network.")
    print(f"artifacts: {OUT / 'linkgraph_audit.json'}")
    return 0 if res["every_pattern_is_a_path"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
