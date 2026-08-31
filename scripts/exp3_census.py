#!/usr/bin/env python3
"""The corrected Phase A1 census — DESCRIPTIVE ONLY.

Every effect here comes from `firewall.compare()`, so each one rests on a
comparison whose two arms were shown to differ only in the geometry. A state
with no receipt, or whose comparison the firewall refuses, does not appear as a
number; it appears in the refusals.

**There is no significance column, and that is deliberate.** See
`decisions/2026-08-31-replicate-spread-is-not-a-materiality-floor.md`. Under
`starts="both"` at 60000/2/32 the pipeline is deterministic — `_greedy_build`
takes no RNG, `both` selects greedy on every state measured, and two restarts
never escape greedy's basin — so three replicates at three seeds return
bit-identical objectives and 3σ of that spread is exactly zero.

A zero spread is not precision. Determinism is not accuracy: a heuristic sitting
0.5% from optimum on one geometry and 0.1% on another produces a 0.4% "effect"
that is pure solver artifact and reproduces perfectly at every seed. Replicate
spread bounds solver VARIANCE; materiality needs a bound on solver ERROR.

So the discovery same-run floor is reported as **undefined for materiality
purposes** — never as 0% — the observed zero spread is labelled solver variance
only, and no threshold is borrowed from certification effort. Classifications
will be added retrospectively once an optimization-gap benchmark supplies a
differential-error bound, in a derived artifact, leaving this one intact.

    python scripts/exp3_census.py
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cota_opt.firewall import (EXP3_STAGE_A, ObservationStore,  # noqa: E402
                               compare)

OUT = ROOT / "outputs" / "exp3"
NULL = "<none>"

FLOOR_NOTE = (
    "UNDEFINED for materiality purposes. Under starts='both' at 60000/2/32 the "
    "pipeline is deterministic, so same-run replicate spread is exactly zero. "
    "That measures solver VARIANCE and places no bound on solver ERROR, which "
    "is what materiality requires. Not 0%. Not substituted from certification "
    "effort. See decisions/2026-08-31-replicate-spread-is-not-a-materiality-"
    "floor.md.")


def kind_of(state_key: str) -> str:
    return state_key.split("-")[0] if state_key not in ("", NULL) else "control"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default="observations")
    ap.add_argument("--out", default="stageA_census.json")
    args = ap.parse_args()

    base = EXP3_STAGE_A.solver.seeds[0]
    store = ObservationStore(OUT / args.store)
    all_receipts = store.all()
    at_base = {r.spec.state_key: r for r in all_receipts if r.spec.seed == base}
    control = at_base.get(NULL)
    if control is None:
        print("no zero-edit control receipt at the base seed; nothing to build")
        return 1

    # Replicates: preserved as an OBSERVATION about the solver, not a threshold.
    reps = sorted((r for r in all_receipts if r.spec.state_key == NULL),
                  key=lambda r: r.spec.seed)
    rep_objs = [r.objective for r in reps]
    spread = (max(rep_objs) - min(rep_objs)) if len(rep_objs) > 1 else None
    variance_note = {
        "n_replicates": len(reps),
        "seeds": [r.spec.seed for r in reps],
        "objectives": rep_objs,
        "spread_absolute": spread,
        "spread_pct_of_mean": (100.0 * spread / st.mean(rep_objs)
                               if spread is not None and rep_objs else None),
        "what_this_is": "SOLVER VARIANCE ONLY — how far the answer moves when "
                        "the seed moves. Zero here because the discovery "
                        "pipeline is deterministic (D32). It is not a "
                        "materiality floor and not a statement about accuracy.",
    }

    rows, refused = [], []
    for key, rec in sorted(at_base.items()):
        if rec is control:
            continue
        res = compare(control, rec, EXP3_STAGE_A)
        if not res:
            refused.append({"state": key,
                            "dimensions": sorted({d.dimension for d in
                                                  getattr(res, "undeclared", ())}),
                            "notes": list(getattr(res, "notes", ()))})
            continue
        m, cm = rec.metrics, control.metrics
        rows.append({
            "state": key, "cardinality": rec.spec.cardinality,
            "kind": kind_of(key), "comparison_id": res.id,
            "objective": rec.objective, "effect": res.effect,
            "effect_pct": res.effect_pct,
            "unserved_demand": m.get("unserved_demand"),
            "unserved_pct": (100.0 * (m["unserved_demand"] - cm["unserved_demand"])
                             / cm["unserved_demand"]
                             if cm.get("unserved_demand") else None),
            "generalized_cost": m.get("generalized_cost"),
            "revenue_veh_hours": m.get("revenue_veh_hours"),
            "winning_start": rec.winning_start,
            "evaluations": rec.evaluations_performed,
            "receipt": rec.digest,
        })
    rows.sort(key=lambda r: r["effect_pct"])

    doc = {
        "census": "Experiment 3 Phase A1, corrected",
        "methodology_generation": EXP3_STAGE_A.methodology_generation,
        "contract": EXP3_STAGE_A.digest,
        "effort": f"{EXP3_STAGE_A.solver.evaluation_ceiling}/"
                  f"{EXP3_STAGE_A.solver.restarts}/"
                  f"{EXP3_STAGE_A.solver.candidate_width}",
        "start_policy": EXP3_STAGE_A.solver.start_policy.value,
        "control_objective": control.objective,
        "control_receipt": control.digest,
        "interpretation": "DESCRIPTIVE ONLY. Signed effects and rankings, no "
                          "significance or materiality classification.",
        "discovery_same_run_floor": FLOOR_NOTE,
        "solver_variance_observation": variance_note,
        "n_states": len(rows), "n_refused": len(refused),
        "refused": refused, "states": rows,
    }

    by_kind = defaultdict(list)
    for r in rows:
        by_kind[r["kind"]].append(r["effect_pct"])
    doc["per_kind"] = {
        k: {"n": len(v), "best": min(v), "median": st.median(v), "worst": max(v),
            "mean": st.mean(v)}
        for k, v in sorted(by_kind.items())}

    (OUT / args.out).write_text(json.dumps(doc, indent=2) + "\n")

    print(f"Experiment 3 Phase A1 — corrected census (DESCRIPTIVE ONLY)")
    print(f"  contract {EXP3_STAGE_A.digest}   generation "
          f"{EXP3_STAGE_A.methodology_generation}   "
          f"starts={EXP3_STAGE_A.solver.start_policy.value}")
    print(f"  control  {control.objective:.4f}")
    print(f"  states   {len(rows)} compared, {len(refused)} refused\n")
    print(f"  discovery same-run floor: UNDEFINED for materiality purposes")
    print(f"      replicate spread {spread if spread is not None else 'n/a'} "
          f"-- solver variance only, not a threshold\n")
    print(f"  {'state':46s} {'k':>2s} {'objective %':>12s} {'unserved %':>11s}")
    for r in rows[:25]:
        print(f"  {r['state'][:46]:46s} {r['cardinality']:2d} "
              f"{r['effect_pct']:+12.4f} "
              f"{r['unserved_pct']:+11.4f}" if r["unserved_pct"] is not None
              else f"  {r['state'][:46]:46s}")
    if len(rows) > 25:
        print(f"  ... {len(rows)-25} more")
    print(f"\n  per kind (mean signed effect, no classification):")
    for k, v in doc["per_kind"].items():
        print(f"      {k:16s} n={v['n']:3d}  best {v['best']:+8.4f}  "
              f"median {v['median']:+8.4f}  mean {v['mean']:+8.4f}")
    if refused:
        print(f"\n  {len(refused)} refused comparisons:")
        for r in refused[:8]:
            print(f"      {r['state'][:44]:44s} {','.join(r['dimensions'])[:40]}")
    print(f"\nwrote {OUT / args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
