#!/usr/bin/env python3
"""Generate and freeze the Experiment 3 atomic mutation pool.

Run once, before anything is scored. The pool is content-addressed by
`POOL_VERSION`, which is part of every cache key, so a pool regenerated under
different rules cannot be served the old pool's scores.

Two artifacts:

``outputs/exp3/mutation_pool.json``
    Every accepted mutation with its canonical id and the structural evidence
    that produced it, plus every rejected proposal and the rule that removed
    it. The rejection half is the more interesting one: a pool reported as
    "N candidates" cannot be argued with, and a rule nobody can see the effect
    of is a rule nobody can question.

``outputs/exp3/incompatible_pairs.json``
    Pairs that may never share a state, by structure alone — a common route, or
    one removing a stop the other anchors on. Never by measured performance:
    excluding a candidate for scoring badly alone would assume exactly the
    composability Experiment 2B exists to have tested, and 2B's answer was that
    a candidate which hurts alone can substitute for one that helps.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cota_opt import geo                                    # noqa: E402
from cota_opt.candidates import stop_context                # noqa: E402
from cota_opt.contract import ContractLimits                # noqa: E402
from cota_opt.exp3 import POOL_VERSION, config_digest       # noqa: E402
from cota_opt.geometry import SegmentTimeModel              # noqa: E402
from cota_opt.harness import build_harness                  # noqa: E402
from cota_opt.mutate import build_pool, incompatible_pairs  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(message)s")
log = logging.getLogger("exp3_pool")
OUT = ROOT / "outputs" / "exp3"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=20260825)
    ap.add_argument("--common-lines", default="same_route",
                    help="the waiting model, passed explicitly — never left "
                         "to the config default (gate 3-1)")
    args = ap.parse_args()

    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    H = build_harness(seed=args.seed, common_lines=args.common_lines,
                      with_pathsets=False)
    b, a = H.baseline, H.assumptions
    sg = geo.stops_gdf(b.feed, a["crs"]["projected"])
    model = SegmentTimeModel.fit(b.network, sg)

    express = {r for r, c in H.classes.items() if c.klass == "peak_express"}
    log.info("excluding %d peak-express routes: Experiment 1 established their "
             "timetable is a design choice, and their single long non-stop run "
             "reads to a geometry generator as a droppable tail", len(express))

    zone_flow = np.zeros(H.zones.n)
    np.add.at(zone_flow, H.od.origin, H.od.flow)
    np.add.at(zone_flow, H.od.dest, H.od.flow)
    ctx = stop_context(b.network, H.zones, H.raptor.stop_ids, model)
    trips_by_route = b.tstats.groupby("route_id").size().to_dict()

    budget_vh = float(b.tstats["runtime_min"].sum() / 60.0)
    limits = ContractLimits(veh_hour_budget=budget_vh,
                            peak_vehicle_budget=197.0,
                            required_waiting_model=args.common_lines)

    audit = build_pool(b.network, ctx, H.zones, H.raptor.stop_ids, zone_flow,
                       trips_by_route, limits, exclude_routes=express)

    pairs = incompatible_pairs(audit.accepted)
    doc = audit.as_dict()
    doc.update({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seed": args.seed,
        "waiting_model": args.common_lines,
        "config_digest": config_digest(),
        "excluded_routes": sorted(express),
        "excluded_why": "peak-express routes; Experiment 1 established their "
                        "timetable is a design choice rather than neglect",
        "limits": {k: getattr(limits, k) for k in
                   ("terminal_move_m", "max_route_stop_visit_loss",
                    "max_network_edit_distance", "min_split_share",
                    "modelled_share_primary_pct", "min_deviation_circuity",
                    "veh_hour_budget", "peak_vehicle_budget")},
        "incompatible_pairs": len(pairs),
    })
    (OUT / "mutation_pool.json").write_text(json.dumps(doc, indent=2) + "\n")
    (OUT / "incompatible_pairs.json").write_text(json.dumps(
        {"pool_version": POOL_VERSION,
         "pairs": [list(p) for p in pairs],
         "rule": "a common route, or one mutation removing a stop the other "
                 "uses as a terminal or junction. Structure only — never "
                 "measured performance.",
         }, indent=2) + "\n")

    print("=" * 84)
    print(f"EXPERIMENT 3 MUTATION POOL — {POOL_VERSION}")
    print("=" * 84)
    print(f"  proposed            {doc['proposed']}")
    print(f"  accepted            {doc['accepted']}  {doc['accepted_by_kind']}")
    print(f"  rejected            {doc['rejected']}  {doc['rejected_by_rule']}")
    print(f"  incompatible pairs  {len(pairs)}")
    print(f"  excluded routes     {len(express)} peak-express")
    print(f"  built in            {time.time() - t0:.0f}s")
    print(f"\nartifacts: {OUT / 'mutation_pool.json'}")
    print(f"           {OUT / 'incompatible_pairs.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
