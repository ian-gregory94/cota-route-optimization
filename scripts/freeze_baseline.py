#!/usr/bin/env python3
"""Freeze the Model B Experiment 1 baseline that Experiment 2 compares against.

Experiment 2's comparator must be the *certified* Model B frontier and nothing
else -- not a Model A result, not an interim fixpoint iteration, and not
whatever the store happens to hold when a later script runs. So it is written
out once, in full, with the evidence attached, and read from that file
thereafter.

What "certified" means here is narrower than "final", and the file says so:
gate 4 certified λ ≥ 2 on both models and failed λ ≤ 1 on both, so the frozen
comparator carries a `certified` flag per λ and the uncertified corner travels
with a warning rather than being dropped. Dropping it would hide that the
frontier has an edge; keeping it unflagged would let someone quote it.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from cota_opt.cache import ResultStore

log = logging.getLogger("freeze")
OUT = ROOT / "outputs"
SEP = "::"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cert = ResultStore(OUT / "certify_modelB.jsonl")
    fixp = ResultStore(OUT / "fixpoint_modelB.jsonl")

    rows, plans, adeq = [], {}, {}
    for r in cert.rows():
        c = r["cell"]
        if c.startswith("certify|lam") and "adequacy" not in c:
            rows.append({k: v for k, v in r.items() if k not in ("plan", "cell")})
            plans[str(r["lambda"])] = r["plan"]
        elif c.startswith("certify|adequacy|lam"):
            adeq[str(r["lambda"])] = {
                k: v for k, v in r["adequacy"].items() if k != "by_period"}
    if not rows:
        log.error("no certified cells in certify_modelB.jsonl")
        return 2

    hist = pd.read_csv(OUT / "fixpoint_history_modelB.csv")
    line = float(hist["worst_flow_share_improvable"].iloc[-1])
    df = pd.DataFrame(rows).sort_values("lambda", ignore_index=True)
    df["improvable_flow_pct"] = df["lambda"].map(
        lambda m: adeq[str(m)]["flow_share_improvable"] * 100)
    df["certified"] = df["improvable_flow_pct"] <= line * 100

    base = next((r for r in fixp.rows() if r["cell"].startswith("final|lam")), {})
    frozen = {
        "model": "same_route (Model B)",
        "what_this_is": (
            "the certified Model B Experiment 1 frontier. Experiment 2 compares "
            "against this and nothing else; it is not replaced during "
            "Experiment 2."),
        "gate4_line_pct": line * 100,
        "n_paths": int(df["n_paths"].iloc[0]),
        "enumeration": "converged fixpoint set, widened once by the gate 4 "
                       "repair step and re-solved at every lambda",
        "effort": {"iterations": 400_000, "restarts": 20, "width": 0,
                   "seed": 20260825},
        "baseline_gc": base.get("baseline_gc"),
        "baseline_unserved": base.get("baseline_unserved"),
        "baseline_served": base.get("baseline_served"),
        "frontier": df.to_dict("records"),
        "adequacy": adeq,
        "plans": plans,
        "uncertified_lambdas": [float(m) for m in df.loc[~df["certified"], "lambda"]],
        "quoting_rule": (
            "quote from lambda = 2 upward. Gate 4 certified lambda >= 2 on both "
            "models and failed lambda <= 1 on both, at different thresholds and "
            "on candidate sets 4% apart -- see D15. The uncertified corner is "
            "kept here so the frontier's edge is visible, not so it can be "
            "quoted."),
        "identification_rule": (
            "the aggregate is measured; the plan is not. Independent seeds "
            "disagree on 19.7% of route-periods while scoring within 0.06 "
            "points -- see D17. Quote totals, never a route headway."),
    }
    p = OUT / "exp1_baseline_modelB.json"
    p.write_text(json.dumps(frozen, indent=2, default=str))
    df.drop(columns=[c for c in ("gc", "unserved", "served") if c in df]) \
      .to_csv(OUT / "exp1_baseline_modelB.csv", index=False)

    print("\n" + "=" * 92)
    print("FROZEN — Model B Experiment 1 baseline")
    print("=" * 92)
    cols = ["lambda", "gc_change_pct", "unserved_change_pct", "served_change_pct",
            "gc_per_trip_change_pct", "revenue_veh_hours", "improvable_flow_pct",
            "certified"]
    print(df[[c for c in cols if c in df]].round(4).to_string(index=False))
    print(f"\n  {int(df['n_paths'].iloc[0]):,} candidate paths · gate 4 line "
          f"{line*100:.3f}% · uncertified {frozen['uncertified_lambdas']}")
    print(f"  written to {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
