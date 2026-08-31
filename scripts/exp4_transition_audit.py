#!/usr/bin/env python3
"""Transition-level evidence for the frozen Experiment 4 route pool.

Corrective plan section 27. `modelled share = 0%` establishes that every
directed link in a proposed line is one COTA already drives. It does not
establish that the LINE is. A line stitched from two observed corridors meets
at a junction, and the turn it makes there may be one no bus has ever made.

Evidence classes:

    0  legacy sequence           the sequence itself is operated today
    1  observed-turn synthesis   new line; every link AND every turn observed
    2  observed-edge synthesis   every link observed; one or more novel turns
    3  modelled geometry         one or more links not directly observed

Class 2 is not rejected here. It is weaker evidence, reported as such, and a
gate may act on it later -- but a gate invented after seeing the numbers is not
a gate.

    python scripts/exp4_transition_audit.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cota_opt import geo                                    # noqa: E402
from cota_opt.harness import build_harness                  # noqa: E402
from cota_opt.linkgraph import build_link_graph             # noqa: E402
from cota_opt.routeclass import classify_routes             # noqa: E402

OUT = ROOT / "outputs" / "exp4"


def main() -> int:
    doc = json.loads((OUT / "route_pool.json").read_text())
    H = build_harness(seed=20260825, with_pathsets=False)
    from cota_opt.configs import period_of_seconds, service_periods
    periods = service_periods(H.assumptions)
    tp = H.baseline.tstats.copy()
    tp["period"] = tp["first_dep_sec"].map(lambda x: period_of_seconds(x, periods))
    rcls = classify_routes(tp.dropna(subset=["period"]), H.baseline.routes)
    express = {r for r, c in rcls.items() if c == "peak_express"}
    g = build_link_graph(H.baseline.network, exclude_routes=express)

    legacy = frozenset(
        tuple(s.from_stop for s in p.segments) + (p.segments[-1].to_stop,)
        for p in H.baseline.network.patterns.values()
        if p.route_id not in express and p.segments)

    classes = collections.Counter()
    by_gen = collections.defaultdict(collections.Counter)
    worst, rows = [], []
    for r in doc["routes"]:
        prov = r.get("provenance") or {}
        gen = (prov.get("generator") if isinstance(prov, dict) else None) or \
            (prov if isinstance(prov, str) else "?")
        # A route is BOTH directions; a turn unobserved on either side is a turn
        # the line asks a bus to make.
        evs = [g.evidence(r[d], legacy=legacy) for d in ("outbound", "inbound")
               if r.get(d)]
        if not evs:
            continue
        cls = max(e.evidence_class for e in evs)
        name = {0: "legacy_sequence", 1: "observed_turn_synthesis",
                2: "observed_edge_synthesis", 3: "modelled_geometry"}[cls]
        bad = sum(len(e.unsupported) for e in evs)
        nt = sum(e.n_transitions for e in evs)
        share = (nt - bad) / nt if nt else 1.0
        classes[name] += 1
        by_gen[gen][name] += 1
        rows.append({"rid": r.get("rid"), "generator": gen,
                     "evidence_class": cls, "class_name": name,
                     "unsupported_transitions": bad, "n_transitions": nt,
                     "observed_transition_share": round(share, 4),
                     "per_direction": [e.as_dict() for e in evs]})
        if bad:
            worst.append((bad, r.get("rid"), gen, share))

    n = sum(classes.values())
    print(f"Experiment 4 route pool — transition-level evidence ({n} lines)\n")
    for name in ("legacy_sequence", "observed_turn_synthesis",
                 "observed_edge_synthesis", "modelled_geometry"):
        c = classes.get(name, 0)
        print(f"  {name:26s} {c:4d}  {100*c/n if n else 0:5.1f}%")
    print("\n  by generator:")
    for gen, cs in sorted(by_gen.items()):
        tot = sum(cs.values())
        parts = "  ".join(f"{k.split('_')[0]}={v}" for k, v in sorted(cs.items()))
        print(f"    {gen:16s} n={tot:4d}  {parts}")

    if worst:
        worst.sort(reverse=True)
        print(f"\n  lines with novel turns: {len(worst)} of {n}")
        print("  worst offenders (unsupported turns, observed-turn share):")
        for k, rid, gen, share in worst[:8]:
            print(f"    {str(rid)[:34]:34s} {gen:14s} {k:3d} turns  "
                  f"{100*share:5.1f}% observed")
    else:
        print("\n  every line in the pool uses only observed turns")

    (OUT / "transition_audit.json").write_text(json.dumps(
        {"n_lines": n, "classes": dict(classes),
         "by_generator": {k: dict(v) for k, v in by_gen.items()},
         "lines": rows}, indent=2) + "\n")
    print(f"\nwrote {OUT / 'transition_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
