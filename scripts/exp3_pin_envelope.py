#!/usr/bin/env python3
"""Compute the pinned envelope once and write it down.

The envelope every Experiment 3 state is judged against: the unedited network's
weekday revenue vehicle-hours and its per-period peak fleet. Both are constants
of the baseline, so computing them inside every run is waste — and expensive
waste, because the peak needs a full model build. Doing it per slice cost about
five minutes of startup and left a 520-second slice with no time to score
anything.

Written to disk so every slice, every shard and every later stage reads the
same object. That is the point: 2B pins it once and hands the same constraint to
every state, and the alternative — resolving `constraints.yaml`'s `baseline`
sentinel per state — gives a mutation that lengthens its routes a larger budget
to spend.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cota_opt.harness import build_harness      # noqa: E402
from exp2_treatments import pinned              # noqa: E402

OUT = ROOT / "outputs" / "exp3"
DEST = OUT / "pinned_envelope.json"


def load() -> dict:
    """The pinned constraints, or a clear refusal to guess."""
    if not DEST.exists():
        raise SystemExit(
            f"{DEST} is missing. Run scripts/exp3_pin_envelope.py first — "
            f"Experiment 3 may not fall back to config/constraints.yaml, whose "
            f"budget is the sentinel 'baseline' and resolves against whichever "
            f"network is being scored.")
    return json.loads(DEST.read_text())["constraints"]


def main() -> int:
    H = build_harness(seed=20260825, common_lines="same_route")
    vh = float(H.baseline.tstats["runtime_min"].sum() / 60.0)
    ctrl = H.setup(with_crowding=False, lock_classes=("peak_express",))
    fit = ctrl.model.evaluate(ctrl.baseline_plan)
    peak = dict(fit.peak_by_period)
    cons = pinned(vh, peak)
    OUT.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps({
        "weekday_revenue_veh_hours": vh,
        "peak_fleet_by_period": peak,
        "constraints": cons,
        "waiting_model": "same_route",
        "note": "Computed once from the UNEDITED network and handed to every "
                "Experiment 3 state. Experiment 2B does the same. Resolving "
                "the config's 'baseline' sentinel per state instead gives a "
                "mutation that lengthens its routes a larger budget to spend, "
                "so every state would be judged against a different envelope.",
    }, indent=2) + "\n")
    print(f"pinned envelope: {vh:.1f} veh-hours, peak {peak}")
    print(f"artifacts: {DEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
