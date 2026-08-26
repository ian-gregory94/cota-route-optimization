#!/usr/bin/env python3
"""Out-of-sample validation of the novel-link running-time estimator.

Runs independently of any optimization. Its verdict gates which Experiment 2
candidates may define the headline frontier (see ACCEPTANCE.md).
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from cota_opt import geo
from cota_opt.experiment import Experiment
from cota_opt.harness import build_harness
from cota_opt.runtime_validation import validate, verdict

log = logging.getLogger("runtimeval")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    exp = Experiment(name="exp2_runtime_validation", seed=20260825,
                     algorithm="5-fold link-held-out validation of the "
                               "segment running-time estimator",
                     config_files=["assumptions.yaml", "sources.yaml"])
    H = build_harness()
    sg = geo.stops_gdf(H.baseline.feed, H.assumptions["crs"]["projected"])
    v = validate(H.baseline.network, sg, n_folds=5)

    v.table.drop(columns=["fold"]).to_csv(
        exp.artifact_path("held_out_predictions.csv"), index=False)
    v.by_distance.to_csv(exp.artifact_path("by_distance.csv"), index=False)
    v.by_route.to_csv(exp.artifact_path("by_route.csv"), index=False)
    v.by_distance.to_csv(ROOT / "outputs" / "runtime_val_by_distance.csv",
                         index=False)
    label, why = verdict(v.summary)
    out = {"summary": v.summary, "verdict": label, "explanation": why,
           "calibration": v.calibration}
    (ROOT / "outputs" / "runtime_validation.json").write_text(
        json.dumps(out, indent=2))
    exp.log_metrics(**out)
    exp.save()

    pd.set_option("display.width", 200)
    print("\n" + "=" * 88)
    print("NOVEL-LINK RUNNING-TIME ESTIMATOR — held out, 5 folds split by link")
    print("=" * 88)
    for k, val in v.summary.items():
        print(f"  {k:28s} {val:,.4f}" if isinstance(val, float) else
              f"  {k:28s} {val}")
    print(f"\n  VERDICT: {label.upper()} — {why}")
    print(f"\n  multiplier that would zero the aggregate bias: "
          f"{v.calibration['multiplier_to_zero_aggregate_bias']:.4f}")
    print("\nBY LINK LENGTH")
    print(v.by_distance.round(2).to_string(index=False))
    print("\nWORST 5 ROUTES BY DIRECTIONAL BIAS (estimator too fast)")
    print(v.by_route.head(5).round(2).to_string(index=False))
    print("\nWORST 5 THE OTHER WAY (estimator too slow)")
    print(v.by_route.tail(5).round(2).to_string(index=False))
    print(f"\nartifacts: {exp.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
