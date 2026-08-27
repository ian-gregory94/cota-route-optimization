#!/usr/bin/env python3
"""Two standing questions about the model's simplifications, answered with data.

1. **Peak fleet.** Equal service hours do not mean equal buses. COTA's feed has
   complete block data, so the real peak vehicle requirement is read from it and
   compared against the cycle-time-over-headway formula the optimizer's budget
   uses. The ratio between them is the interlining factor a candidate plan's
   fleet proxy has to carry.

2. **Hyperpath behaviour.** Riders board the first acceptable bus; the model
   puts them on one chosen line. An upper bound on what that omission is worth
   decides whether proper optimal-strategy assignment is required work or
   follow-on work.

Both share one harness load, deliberately: running them as separate processes
alongside the long jobs is what put this container into the OOM killer once
already.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from cota_opt.blocks import fleet_estimate, interlining_factor, reconstruct, routewise_peak
from cota_opt.configs import load_cost_weights, service_periods
from cota_opt.cost import CostWeights
from cota_opt.experiment import Experiment
from cota_opt.harness import build_harness
from cota_opt.hyperpath import bound, summarize

log = logging.getLogger("diagnostics")
OUT = ROOT / "outputs"


def wait_for_memory(min_free_mb: int = 2200, tries: int = 60) -> None:
    """Yield to the authoritative Experiment 1 run rather than race it.

    Running a second harness-loading job next to the long one is what put this
    container into the OOM killer once already. This job is not on anyone's
    critical path minute to minute, so it waits.
    """
    for _ in range(tries):
        try:
            free = int([l for l in Path("/proc/meminfo").read_text().splitlines()
                        if l.startswith("MemAvailable")][0].split()[1]) // 1024
        except Exception:
            return
        if free >= min_free_mb:
            return
        log.warning("only %d MB available, waiting", free)
        time.sleep(30)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--periods", type=str, default="am_peak,midday",
                    help="periods to run the hyperpath bound over")
    ap.add_argument("--exp1-effect-pct", type=float, default=2.0,
                    help="size of the Experiment 1 generalized-cost effect the "
                         "bound is judged against")
    ap.add_argument("--skip-hyperpath", action="store_true")
    ap.add_argument("--common-lines", type=str, default=None,
                    choices=[None, "pattern", "same_route"])
    ap.add_argument("--plan", type=str, default="matrix_plans/C_lam2.0_seed20260825.csv",
                    help="plan to apply the block-derived fleet proxy to, "
                         "relative to outputs/. The point of the check is "
                         "whether a RECOMMENDED plan needs more buses than "
                         "COTA runs today, so it should be pointed at the "
                         "certified balanced plan, not at an old matrix cell")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    wait_for_memory()

    suffix = "" if args.common_lines in (None, "pattern") else "_modelB"
    exp = Experiment(name=f"model_diagnostics{suffix}", seed=20260825,
                     algorithm="GTFS block reconstruction; combined-frequency "
                               "upper bound on hyperpath behaviour",
                     config_files=["assumptions.yaml", "cost_weights.yaml",
                                   "constraints.yaml", "sources.yaml"])
    H = build_harness(common_lines=args.common_lines)
    b, a = H.baseline, H.assumptions
    periods = service_periods(a)
    out: dict = {}

    # ------------------------------------------------------------------
    # 1. peak fleet from blocks
    # ------------------------------------------------------------------
    prof = reconstruct(b.feed.trips, b.tstats, periods)
    prof.blocks.to_csv(exp.artifact_path("blocks.csv"), index=False)
    prof.concurrency.to_csv(exp.artifact_path("concurrency.csv"), index=False)

    setup = H.setup(with_crowding=False, lock_classes=())
    base_hw = dict(setup.baseline_plan.headways)
    rw = routewise_peak(setup.model.services, base_hw, periods)
    factor = interlining_factor(prof.peak_vehicles, rw)
    ntd_voms = next((v.get("ntd_voms") for v in a.values()
                     if isinstance(v, dict) and "ntd_voms" in v), None)

    out["peak_fleet"] = {
        **prof.summary(),
        "routewise_peak_by_period": rw,
        "routewise_peak": max(rw.values()) if rw else None,
        "interlining_factor": factor,
        "ntd_reported_voms": ntd_voms,
        "block_peak_vs_ntd_voms_pct": (100.0 * prof.peak_vehicles / ntd_voms - 100.0)
        if ntd_voms else None,
    }

    print("\n" + "=" * 88)
    print("PEAK VEHICLE REQUIREMENT — read from blocks, not approximated")
    print("=" * 88)
    print(f"  {len(prof.blocks)} blocks, median {prof.blocks['n_trips'].median():.0f} "
          f"trips and {prof.blocks['span_hours'].median():.1f} h span each")
    print(f"  peak vehicles in service      {prof.peak_vehicles} at {out['peak_fleet']['peak_time']}")
    print(f"  cycle-over-headway formula    {max(rw.values()):.1f}")
    print(f"  interlining factor            {factor:.3f}  "
          f"({'blocking beats the formula' if factor < 1 else 'formula is optimistic'})")
    if ntd_voms:
        print(f"  NTD reported VOMS             {ntd_voms}  "
              f"({out['peak_fleet']['block_peak_vs_ntd_voms_pct']:+.1f}% vs blocks)")
    print(f"  blocks serving >1 route       {100 * prof.interline_share:.1f}%")
    print(f"  share of block span on layover {100 * prof.layover_share:.1f}%")
    print("\n  peak by period (from blocks):")
    for k, v in prof.peak_by_period.items():
        print(f"    {k:9s} {v:4d}   formula {rw.get(k, float('nan')):6.1f}")

    # the same proxy applied to a saved optimized plan, if one exists
    plan_csv = OUT / args.plan
    if plan_csv.exists():
        d = pd.read_csv(plan_csv, dtype={"route_id": str})
        hw = dict(base_hw)
        for r in d.itertuples():
            hw[(r.route_id, r.period)] = float(r.headway_min)
        est = fleet_estimate(setup.model.services, hw, periods, factor)
        base_est = fleet_estimate(setup.model.services, base_hw, periods, factor)
        delta = est["blocked_peak_proxy"] - base_est["blocked_peak_proxy"]
        worst = sorted(
            ((rid, est["per_route_at_peak"].get(rid, 0.0)
              - base_est["per_route_at_peak"].get(rid, 0.0))
             for rid in set(est["per_route_at_peak"]) | set(base_est["per_route_at_peak"])),
            key=lambda t: -t[1])[:6]
        out["candidate_fleet"] = {
            "plan": plan_csv.name,
            "baseline_peak_proxy": base_est["blocked_peak_proxy"],
            "candidate_peak_proxy": est["blocked_peak_proxy"],
            "change": delta,
            "change_pct": 100.0 * delta / base_est["blocked_peak_proxy"]
            if base_est["blocked_peak_proxy"] else None,
            "peak_period": est["peak_period"],
            "largest_increases_by_route": [{"route_id": r, "buses": v}
                                           for r, v in worst],
        }
        print(f"\n  BALANCED PLAN ({plan_csv.name})")
        print(f"    baseline peak proxy  {base_est['blocked_peak_proxy']:.1f}")
        print(f"    candidate peak proxy {est['blocked_peak_proxy']:.1f}  "
              f"({delta:+.1f}, {out['candidate_fleet']['change_pct']:+.1f}%)")
        print("    largest per-route increases at the peak period:")
        for r, v in worst:
            print(f"      route {r}: {v:+.2f} buses")

    # ------------------------------------------------------------------
    # 2. hyperpath upper bound
    # ------------------------------------------------------------------
    if not args.skip_hyperpath:
        w = CostWeights.from_config(load_cost_weights())
        wk = dict(random_arrival_threshold_min=float(
            a["waiting"]["random_arrival_threshold_min"]),
            schedule_coefficient=float(a["waiting"]["schedule_coefficient"]))
        frames = []
        for per in args.periods.split(","):
            ev = setup.model.evaluators.get(per)
            if ev is None:
                continue
            log.info("hyperpath bound for %s", per)
            frames.append(bound(ev.ps, ev, H.raptor, base_hw, per, w, wk))
        per_leg = pd.concat([f for f in frames if not f.empty], ignore_index=True) \
            if any(not f.empty for f in frames) else pd.DataFrame()

        baseline_gc = float(setup.model.evaluate(setup.baseline_plan).generalized_cost)
        hb = summarize(per_leg, baseline_gc, args.exp1_effect_pct)
        if not per_leg.empty:
            per_leg.to_csv(exp.artifact_path("hyperpath_legs.csv"), index=False)
            hb.by_route.to_csv(exp.artifact_path("hyperpath_by_route.csv"),
                               index=False)
            hb.by_route.to_csv(OUT / f"hyperpath_by_route{suffix}.csv",
                               index=False)
        out["hyperpath"] = {**hb.summary, "verdict": hb.verdict,
                            "explanation": hb.explanation,
                            "periods": args.periods.split(",")}

        print("\n" + "=" * 88)
        print("HYPERPATH — upper bound on 'board whichever bus comes first'")
        print("=" * 88)
        for k, v in hb.summary.items():
            print(f"  {k:44s} {v:,.4f}" if isinstance(v, float)
                  else f"  {k:44s} {v}")
        print(f"\n  VERDICT: {hb.verdict.upper()}")
        print(f"  {hb.explanation}")
        if not hb.by_route.empty:
            print("\n  where it concentrates:")
            print(hb.by_route.head(8).round(3).to_string(index=False))

    out["common_lines"] = H.common_lines
    (OUT / f"model_diagnostics{suffix}.json").write_text(
        json.dumps(out, indent=2, default=str))
    exp.log_metrics(**out)
    exp.save()
    print(f"\nartifacts: {exp.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
