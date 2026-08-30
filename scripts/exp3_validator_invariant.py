#!/usr/bin/env python3
"""The validator must accept everything Experiment 2B actually evaluated.

The strongest check available, because it does not rest on my judgement about
what the contract means. Experiment 2B applied twelve splice candidates to the
real network, rebuilt path sets, re-optimized frequency and reported the
results. Those states are, by construction, states this project considers
evaluable. **If the Experiment 3 validator refuses one of them, the validator
is wrong** — not the candidate.

It was wrong. On its first run against the real pool it refused 60 of 84
mutations, every kind included:

* **42 on vehicle-hours** — it was handed the EDITED BASELINE's hours, before
  frequency re-optimization, so any mutation that lengthened the network at all
  was over budget by a fraction of a percent. The method is mutate then
  re-optimize INSIDE the envelope; the constraint belongs on the optimized plan.
* **11 on stranded stops** — it refused any state leaving a stop served by no
  route. That is what a truncation does, truncation is explicitly permitted
  under a 40% cap, and the cost is priced by the evaluator as unserved demand.
  The contract forbids changing which stops EXIST, which is a different rule.
* **7 on edit distance** — measured by matching route ids, so a splice read as
  deleting two routes and creating a third even though nearly every stop-visit
  survived. That made the contract contradict itself, since it lists `splice`
  as permitted and quotas twelve.

Left alone, Experiment 3 would have evaluated the 24 cheapest mutations and
reported the validator's bugs as a finding about COTA's network.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cota_opt import geo                                       # noqa: E402
from cota_opt.contract import (ContractLimits, ContractViolation,  # noqa: E402
                               validate_applied, validate_mutation)
from cota_opt.exp3 import mutation_id                          # noqa: E402
from cota_opt.geometry import GeometryEdit, SegmentTimeModel, apply_edits  # noqa: E402
from cota_opt.harness import build_harness                     # noqa: E402
from cota_opt.mutate import edit_from_record                   # noqa: E402

OUT = ROOT / "outputs"


def main() -> int:
    H = build_harness(seed=20260825, common_lines="same_route",
                      with_pathsets=False)
    sg = geo.stops_gdf(H.baseline.feed, H.assumptions["crs"]["projected"])
    stm = SegmentTimeModel.fit(H.baseline.network, sg)
    budget = float(H.baseline.tstats["runtime_min"].sum() / 60.0)
    limits = ContractLimits(veh_hour_budget=budget, peak_vehicle_budget=197.0)
    net, ts = H.baseline.network, H.baseline.tstats

    # --- part 1: the twelve 2B candidates -------------------------------
    classes = json.loads((OUT / "exp2_candidate_classes.json").read_text())
    keys = sorted(classes["rule"]["eligible_for_2B"])
    treat = {}
    tf = OUT / "exp2_treatments.jsonl"
    edits_by_key: dict[str, GeometryEdit] = {}
    for k in keys:
        kind, a, b, jx = k.split("|")
        edits_by_key[k] = GeometryEdit(kind=kind, route_id=a, with_route=b,
                                       junction=jx, description=k)

    rows = []
    for k in keys:
        e = edits_by_key[k]
        try:
            validate_mutation(e, net, stm.coords, limits)
            ed = apply_edits(net, ts, stm, [e])
            chk = validate_applied(net, ed.network, [e], limits,
                                   coords=stm.coords, report=ed.report,
                                   edited_baseline_veh_hours=float(
                                       ed.tstats["runtime_min"].sum() / 60.0),
                                   waiting_model="same_route")
            rows.append({"candidate": k, "accepted": chk.ok,
                         "violations": chk.violations,
                         "edit_distance_pct":
                             chk.facts.get("network_edit_distance_pct"),
                         "route_churn_pct": chk.facts.get("route_churn_pct"),
                         "stops_left_unserved":
                             chk.facts.get("stops_left_unserved")})
        except ContractViolation as v:
            rows.append({"candidate": k, "accepted": False,
                         "violations": [f"[{v.rule}] {v.detail}"]})

    print("=" * 88)
    print("VALIDATOR INVARIANT — the 12 candidates Experiment 2B evaluated")
    print("=" * 88)
    for r in rows:
        mark = "ok  " if r["accepted"] else "FAIL"
        print(f"  {mark} {r['candidate']:<26.26s} "
              f"edit {r.get('edit_distance_pct', float('nan')):5.1f}%  "
              f"churn {r.get('route_churn_pct', float('nan')):5.1f}%  "
              f"unserved-stops {r.get('stops_left_unserved', '-')}")
        for v in r["violations"]:
            print(f"       {v[:150]}")
    n_ok = sum(r["accepted"] for r in rows)

    # --- part 2: the Experiment 3 pool ----------------------------------
    pool_doc = json.loads((OUT / "exp3" / "mutation_pool.json").read_text())
    pool_rows = []
    for m in pool_doc["mutations"]:
        e = edit_from_record(m)
        try:
            validate_mutation(e, net, stm.coords, limits)
            ed = apply_edits(net, ts, stm, [e])
            chk = validate_applied(net, ed.network, [e], limits,
                                   coords=stm.coords, report=ed.report,
                                   edited_baseline_veh_hours=float(
                                       ed.tstats["runtime_min"].sum() / 60.0),
                                   waiting_model="same_route")
            pool_rows.append({"id": m["id"], "kind": m["kind"],
                              "accepted": chk.ok,
                              "violations": chk.violations})
        except (ContractViolation, ValueError) as v:
            pool_rows.append({"id": m["id"], "kind": m["kind"],
                              "accepted": False, "violations": [str(v)]})

    from collections import Counter
    acc = Counter(r["kind"] for r in pool_rows if r["accepted"])
    rej = Counter(r["kind"] for r in pool_rows if not r["accepted"])
    print()
    print("=" * 88)
    print("THE EXPERIMENT 3 POOL, structurally")
    print("=" * 88)
    print(f"  accepted  {sum(acc.values())}/{len(pool_rows)}  {dict(acc)}")
    if rej:
        print(f"  refused   {sum(rej.values())}  {dict(rej)}")
        why = Counter(v.split(".")[0][:60]
                      for r in pool_rows if not r["accepted"]
                      for v in r["violations"][:1])
        for k, v in why.most_common(6):
            print(f"      {v:3d}  {k}")

    ok = n_ok == len(rows)
    res = {"pass": ok, "twelve_2b_candidates": rows,
           "accepted_of_12": n_ok,
           "pool_accepted": sum(acc.values()), "pool_size": len(pool_rows),
           "pool_accepted_by_kind": dict(acc),
           "pool_refused_by_kind": dict(rej),
           "pool": pool_rows,
           "why_this_exists":
               "Experiment 2B applied these twelve to the real network, "
               "rebuilt path sets, re-optimized frequency and reported the "
               "results. If the Experiment 3 validator refuses one, the "
               "validator is wrong, not the candidate."}
    (OUT / "exp3" / "validator_invariant.json").write_text(
        json.dumps(res, indent=2) + "\n")
    print()
    print(f"  VERDICT: {'PASS' if ok else 'FAIL'} — {n_ok}/12 of 2B's "
          f"candidates accepted")
    print(f"\nartifacts: {OUT / 'exp3' / 'validator_invariant.json'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
