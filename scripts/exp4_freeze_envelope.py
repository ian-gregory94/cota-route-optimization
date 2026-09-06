#!/usr/bin/env python3
"""Freeze the canonical resource envelope as a machine-readable artifact.

This exists because it did not, and the absence let a production run launch on
invented numbers. `EXPERIMENT4_CONTRACT.md` §3 states the envelope in prose --
"2,517.183 weekday revenue vehicle-hours · 197 peak vehicles" -- and the code
resolved it at runtime from a `baseline` sentinel. Nothing held the two
together, so nothing objected when a launcher hard-coded 2507.0 hours and a
uniform 200.0 peak.

WHAT THIS DOES NOT DO
---------------------
It does not compute the envelope. Computing it would make this a fourth
opinion. It READS the two committed sources, cross-checks them against the
contract's prose, and refuses to write anything if they disagree:

  hours  outputs/experiments/exp1_*/experiment.json and every exp3 receipt:
         `gtfs_scheduled_revenue_veh_hours`, which `exp2.build_setup` asserts
         the model reproduces to better than 1e-9 or raises.

  fleet  outputs/fleet_check_modelB.json: the BLOCK-DERIVED peak, from
         reconstructing COTA's vehicle blocks out of the feed. 197 at 17:13,
         against NTD's independently reported VOMS of 198 -- a 0.51% match
         nothing was fitted to.

THE THREE FLEET NUMBERS, AND WHY ONLY ONE IS A CAP
--------------------------------------------------
    197.0    block-derived peak vehicles, pm_peak.  THE CAP.
    176.5    the frequency model's `peak_vehicles`: peak CONCURRENCY, the
             max over periods of sum(cycle/headway). An evaluation OUTPUT,
             systematically ~10% below the block-derived figure at the same
             period, because it does not model interlining (measured factor
             1.307). `contract.py` already says comparing it to a
             block-derived budget "would pass every plan while appearing to
             check something", and makes the fleet check record NOT RUN
             rather than run wrong.
    150.7    `routewise_peak`: the same proxy before interlining. Also an
             output.

A cap may never be read off an evaluated plan's resource usage. Both numbers a
production launcher needs are frozen here so that reading them wrong requires
ignoring an artifact rather than merely not knowing one exists.

    python scripts/exp4_freeze_envelope.py --write
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "outputs" / "CANONICAL_ENVELOPE.json"

#: What EXPERIMENT4_CONTRACT.md section 3 states in prose. Used only to
#: CROSS-CHECK the committed receipts, never as the value itself.
CONTRACT_HOURS = 2517.183
CONTRACT_PEAK = 197.0
CONTRACT_TEXT = ("2,517.183 weekday revenue vehicle-hours . 197 peak vehicles")


def find_hours() -> tuple[float, str]:
    for pat in ("outputs/experiments/exp1_*/experiment.json",
                "outputs/experiments/exp3_*/experiment.json",
                "outputs/experiments/exp2*/experiment.json"):
        for f in sorted(glob.glob(str(ROOT / pat)), reverse=True):
            try:
                d = json.loads(Path(f).read_text())
            except Exception:
                continue
            hit = _dig(d, "gtfs_scheduled_revenue_veh_hours")
            if hit is not None:
                return float(hit), str(Path(f).relative_to(ROOT))
    raise SystemExit("no receipt carries gtfs_scheduled_revenue_veh_hours")


def _dig(o, key):
    if isinstance(o, dict):
        if key in o and not isinstance(o[key], (dict, list)):
            return o[key]
        for v in o.values():
            r = _dig(v, key)
            if r is not None:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _dig(v, key)
            if r is not None:
                return r
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    from cota_opt.firewall.core import digest

    hours, hours_src = find_hours()
    fleet_path = ROOT / "outputs" / "fleet_check_modelB.json"
    fleet = json.loads(fleet_path.read_text())["peak_fleet"]
    peak_by_period = {k: float(v) for k, v in
                      sorted(fleet["peak_by_period"].items())}
    peak_system = float(fleet["peak_vehicles"])

    print("CANONICAL RESOURCE ENVELOPE\n")
    print(f"  weekday revenue vehicle-hours : {hours:.6f}")
    print(f"    source                      : {hours_src}")
    print(f"    model reproduces to <1e-9   : asserted by exp2.build_setup")
    print(f"  peak vehicles (block-derived) : {peak_system:.1f} at "
          f"{fleet['peak_time']}")
    print(f"    source                      : outputs/fleet_check_modelB.json")
    print(f"    per period                  : {peak_by_period}")
    print(f"    NTD reported VOMS           : {fleet['ntd_reported_voms']} "
          f"({fleet['block_peak_vs_ntd_voms_pct']:+.2f}%)")

    bad = []
    if abs(hours - CONTRACT_HOURS) > 0.001:
        bad.append(f"hours {hours:.6f} disagrees with EXPERIMENT4_CONTRACT "
                   f"section 3's {CONTRACT_HOURS}")
    if abs(peak_system - CONTRACT_PEAK) > 1e-9:
        bad.append(f"peak {peak_system} disagrees with EXPERIMENT4_CONTRACT "
                   f"section 3's {CONTRACT_PEAK}")
    print(f"\n  cross-check against the contract's prose: "
          f"{'OK' if not bad else 'MISMATCH'}")
    for b in bad:
        print(f"    {b}")
    if bad:
        print("\n  refusing to freeze an envelope the contract does not agree "
              "with.")
        return 1

    doc = {
        "artifact": "CANONICAL_ENVELOPE",
        "version": 1,
        "why": ("the envelope existed only in prose and in a runtime sentinel, "
                "so nothing objected when a launcher hard-coded 2507.0 hours "
                "and a uniform 200.0 peak"),
        "weekday_revenue_vehicle_hours": hours,
        "weekday_revenue_vehicle_hours_source": hours_src,
        "weekday_revenue_vehicle_hours_semantics": (
            "GTFS scheduled weekday revenue vehicle-hours; exp2.build_setup "
            "raises unless the model reproduces this to better than 1e-9"),
        "peak_vehicles": peak_system,
        "peak_vehicles_by_period": peak_by_period,
        "peak_vehicles_source": "outputs/fleet_check_modelB.json",
        "peak_vehicles_semantics": (
            "BLOCK-DERIVED peak vehicles: COTA's vehicle blocks reconstructed "
            "from the feed, including interlining. This is the fleet CAP."),
        "peak_time": fleet["peak_time"],
        "n_blocks": fleet["n_blocks"],
        "ntd_reported_voms": fleet["ntd_reported_voms"],
        "ntd_agreement_pct": fleet["block_peak_vs_ntd_voms_pct"],
        "contract_reference": "EXPERIMENT4_CONTRACT.md section 3",
        "contract_text": CONTRACT_TEXT,
        "NOT_THE_CAP": {
            "frequency_model_peak_concurrency": {
                "value_on_baseline_pm_peak": 176.49,
                "what": ("FitnessVector.peak_vehicles = max over periods of "
                         "sum(cycle/headway); an evaluation OUTPUT"),
                "why_not": ("it does not model interlining and is ~10% below "
                            "the block-derived figure at the same period. "
                            "contract.py refuses to compare it to a "
                            "block-derived budget and records the fleet check "
                            "as NOT RUN rather than running wrong")},
            "routewise_peak": {
                "value_on_baseline_pm_peak": 150.73,
                "what": "the same proxy before interlining (factor 1.307)",
                "why_not": "also an output, and further from the real fleet"},
            "optimized_plan_usage": {
                "example": 2507.763673,
                "what": ("an optimized plan's realised revenue vehicle-hours, "
                         "99.63% of the cap"),
                "why_not": "a cap may never be read off a plan's usage"},
        },
        "rule": ("a resource cap is read from this artifact or from the "
                 "production `baseline` sentinel. It is never read off an "
                 "evaluated plan, and never retyped into a script."),
    }
    doc["envelope_digest"] = digest({
        "vh": round(hours, 9),
        "peak": {k: round(v, 9) for k, v in peak_by_period.items()},
        "peak_system": peak_system})
    print(f"\n  envelope digest: {doc['envelope_digest']}")

    if a.write:
        OUT.write_text(json.dumps(doc, indent=1) + "\n")
        print(f"  wrote {OUT.relative_to(ROOT)}")
    else:
        print("  (dry run; pass --write to freeze)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
