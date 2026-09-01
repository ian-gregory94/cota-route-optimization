#!/usr/bin/env python3
"""Stage health report from the observation store — corrective plan section 23.

The point is to make systematic patterns visible without a human grepping logs.
This is the report whose absence let a treatment-correlated optimizer run for
four experiments: every individual number looked fine, and nobody was asking
whether execution behaviour was ASSOCIATED with the treatment.

    python scripts/exp3_health.py [--store observations]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cota_opt.firewall import (EXP3_STAGE_A, ObservationStore,  # noqa: E402
                               compare, health_report)

OUT = ROOT / "outputs" / "exp3"
NULL = "<none>"


def treatment_class(rec) -> str:
    """The experimental class of an arm, for the association sweep."""
    k = rec.spec.state_key
    if k in ("", NULL):
        return "control"
    if rec.spec.cardinality > 1:
        return f"k={rec.spec.cardinality}"
    return k.split("-")[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default="observations")
    ap.add_argument("--threshold", type=float, default=0.10)
    ap.add_argument("--out", default="health.json")
    args = ap.parse_args()

    store = ObservationStore(OUT / args.store)
    receipts = store.all()
    if not receipts:
        print(f"no observations in {store.root}")
        return 1

    base = EXP3_STAGE_A.solver.seeds[0]
    by_key = {r.spec.state_key: r for r in receipts if r.spec.seed == base}
    control = by_key.get(NULL)
    comps = ([compare(control, t, EXP3_STAGE_A)
              for k, t in by_key.items() if t is not control]
             if control is not None else [])

    rep = health_report(receipts, EXP3_STAGE_A, treatment_class, comps,
                        threshold=args.threshold)
    print(rep.text())
    if control is None:
        print("\n  NOTE: no zero-edit control receipt at the base seed, so no "
              "comparison was attempted.")
    (OUT / args.out).write_text(json.dumps(rep.as_dict(), indent=2) + "\n")
    print(f"\nwrote {OUT / args.out}")
    # Fail closed: a stage with treatment-correlated execution is not a stage
    # whose results may be promoted, however clean each pair looked.
    return 0 if rep.healthy else 2


if __name__ == "__main__":
    raise SystemExit(main())
