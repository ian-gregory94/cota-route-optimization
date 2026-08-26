#!/usr/bin/env python3
"""Is the ablation a fair test of Experiment 1? Three checks that could break it.

The ablation compared Experiment 1 against path-based configurations that
differed in several ways at once — assignment method, demand source, demand
scale, retention model, AND search effort. Only the first of those is the thing
being tested. These checks isolate the confounds.

1. SCORE EXPERIMENT 1'S OWN PLAN under the path-based evaluator. This is the
   decisive test and it needs no re-optimization: if Experiment 1's headways
   really were an artifact, they must look bad when passengers can re-route. If
   they look fine, the ablation's conclusion is wrong.

2. LOCAL OPTIMALITY OF ROUTE 10. The headline claim is that the optimizer leaves
   route 10 alone. That is only meaningful if moving it actually makes things
   worse — otherwise the search simply never looked.

3. SEARCH-EFFORT SENSITIVITY. Experiment 1 was solved with 20 restarts at full
   candidate width; the ablation configs got 0 restarts at width 24. If more
   search finds materially more, the ablation understated the corrected model's
   achievable gain.
"""
from __future__ import annotations

import json
import logging
import pickle
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from cota_opt import geo
from cota_opt.baseline import CENTRAL_OHIO_FIPS, build_baseline
from cota_opt.configs import period_of_seconds, service_periods
from cota_opt.exp2 import build_setup, plan_diff
from cota_opt.frequency import FrequencyPlan, optimize_frequencies
from cota_opt.odmatrix import (_top_k, build_zone_system, filter_to_accessible,
                               from_lodes_od, scale_to)
from cota_opt.raptor import build_raptor_network
from cota_opt.registry import Registry
from cota_opt.routeclass import classify_routes

log = logging.getLogger("fair")
UPLOADS = Path("/mnt/user-data/uploads/Downloads")
DEMAND_FILES = {"rac": UPLOADS / "oh_rac_S000_JT00_2022.csv.gz",
                "wac": UPLOADS / "oh_wac_S000_JT00_2022.csv.gz",
                "centroids": UPLOADS / "CenPop2020_Mean_BG39.txt"}
CACHE = Path("/tmp/cota_pathsets.pkl")


def load_plan(csv: Path, baseline: FrequencyPlan) -> FrequencyPlan:
    df = pd.read_csv(csv, dtype={"route_id": str})
    h = dict(baseline.headways)
    col = "headway_min" if "headway_min" in df.columns else "optimized_headway_min"
    for r in df.itertuples():
        k = (r.route_id, r.period)
        if k in h:
            h[k] = float(getattr(r, col))
    return FrequencyPlan(h)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    seed = 20260825
    b = build_baseline(demand_files=DEMAND_FILES, write=False)
    a = b.assumptions
    pa = a["path_assignment"]
    periods = service_periods(a)
    sg = geo.stops_gdf(b.feed, a["crs"]["projected"])
    rn = build_raptor_network(b.feed, b.network, b.tstats, sg,
                              walk_radius_m=float(pa["walk_radius_m"]),
                              walk_speed_m_per_min=float(pa["walk_speed_m_per_min"]),
                              periods=periods, with_timetable=False)
    zs = build_zone_system(b.demand["bg_frame"], sg,
                           radius_m=float(pa["access_radius_m"]),
                           walk_speed_m_per_min=float(pa["walk_speed_m_per_min"]),
                           stop_index=rn.stop_index)
    reg = Registry()
    od = _top_k(filter_to_accessible(
        from_lodes_od(reg.path_for("lodes_od_oh"), zs,
                      county_fips=CENTRAL_OHIO_FIPS), zs), int(pa["od_top_k"]))
    od = scale_to(od, float(a["demand_proxy"]["assumed_weekday_linked_trips"]))

    ts = b.tstats.copy()
    ts["period"] = ts["first_dep_sec"].map(lambda s: period_of_seconds(s, periods))
    classes = classify_routes(ts.dropna(subset=["period"]), b.feed.routes)

    cache = pickle.load(open(CACHE, "rb")) if CACHE.exists() else {}
    log.info("path sets from cache: %d", len(cache))
    setup = build_setup(b, rn, zs, od, seed=seed, route_classes=classes,
                        with_crowding=True, lock_classes=("peak_express",),
                        pathset_cache=cache)
    model, base = setup.model, setup.baseline_plan
    bf = model.evaluate(base)
    out: dict = {"baseline": {"gc": bf.generalized_cost,
                              "unserved": bf.unserved_demand,
                              "served": bf.served_demand,
                              "veh_hours": bf.revenue_veh_hours}}
    log.info("baseline under path model: gc=%.4e unserved=%.0f vh=%.1f",
             bf.generalized_cost, bf.unserved_demand, bf.revenue_veh_hours)

    # ---- CHECK 1: Experiment 1's own plans, scored honestly -------------
    e1dir = sorted((ROOT / "outputs" / "experiments")
                   .glob("exp1_frequency_redistribution_*"))[-1]
    rows = []
    for csv in sorted(e1dir.glob("plan_lambda_*.csv")):
        lam = csv.stem.replace("plan_lambda_", "")
        plan = load_plan(csv, base)
        f = model.evaluate(plan)
        rows.append({
            "experiment_1_plan": f"lambda={lam}",
            "gc_change_pct": (f.generalized_cost / bf.generalized_cost - 1) * 100,
            "unserved_change_pct": (f.unserved_demand / bf.unserved_demand - 1) * 100,
            "served_change_pct": (f.served_demand / bf.served_demand - 1) * 100,
            "veh_hours": f.revenue_veh_hours,
            "within_budget": f.revenue_veh_hours <= setup.budget.vh_cap() * (1 + 1e-9),
        })
        log.info("  exp1 plan lambda=%-5s scored honestly: gc %+.2f%% unserved %+.2f%%",
                 lam, rows[-1]["gc_change_pct"], rows[-1]["unserved_change_pct"])
    out["check1_exp1_plans_scored_by_path_model"] = rows

    # ---- CHECK 2: is leaving route 10 alone actually optimal? ------------
    obj = lambda f: f.scalarized(model.w.unserved, 1.0)
    base_obj = obj(bf)
    probe = []
    ladder = [10.0, 12.0, 15.0, 20.0, 24.0, 30.0, 40.0, 60.0]
    for per in ("am_peak", "midday", "pm_peak"):
        k = ("010", per)
        if k not in model.services:
            continue
        h0 = base.headways[k]
        for h in ladder:
            if abs(h - h0) < 1e-6:
                continue
            p2 = base.copy()
            p2.headways[k] = h
            f2 = model.evaluate(p2)
            feasible = (f2.revenue_veh_hours <= setup.budget.vh_cap() * (1 + 1e-9)
                        and all(v <= setup.budget.peak_cap(pp) * (1 + 1e-9)
                                for pp, v in f2.peak_by_period.items()))
            probe.append({"period": per, "baseline_headway": h0, "trial_headway": h,
                          "objective_change_pct": (obj(f2) / base_obj - 1) * 100,
                          "gc_change_pct": (f2.generalized_cost / bf.generalized_cost - 1) * 100,
                          "veh_hours_change": f2.revenue_veh_hours - bf.revenue_veh_hours,
                          "feasible": feasible})
    pr = pd.DataFrame(probe)
    pr.to_csv(ROOT / "outputs" / "route010_probe.csv", index=False)
    improving = pr[(pr.objective_change_pct < -1e-9) & pr.feasible]
    out["check2_route010"] = {
        "trials": len(pr),
        "feasible_trials": int(pr.feasible.sum()),
        "improving_moves": len(improving),
        "best_improvement_pct": float(improving.objective_change_pct.min())
        if len(improving) else 0.0,
        "cheapest_worsening_pct": float(
            pr[pr.feasible & (pr.objective_change_pct > 0)].objective_change_pct.min())
        if (pr.feasible & (pr.objective_change_pct > 0)).any() else None,
    }
    log.info("route 010 probe: %d/%d feasible single moves improve the objective",
             len(improving), int(pr.feasible.sum()))

    # ---- CHECK 3: does more search effort find more? --------------------
    effort = []
    for label, iters, restarts, width in (
            ("ablation setting (20k / 0 / 24)", 20_000, 0, 24),
            ("exp1-matched (400k / 20 / full)", 400_000, 20, 0)):
        t = time.time()
        r = optimize_frequencies(
            model, setup.budget, ladder=[], unserved_multiplier=1.0,
            local_search_iterations=iters, seed=seed, ladders=setup.ladders,
            initial=base, n_restarts=restarts, candidate_width=width,
            greedy_start=False)
        effort.append({
            "setting": label, "seconds": time.time() - t,
            "gc_change_pct": (r.fitness.generalized_cost / bf.generalized_cost - 1) * 100,
            "unserved_change_pct": (r.fitness.unserved_demand / bf.unserved_demand - 1) * 100,
            "objective_change_pct": (obj(r.fitness) / base_obj - 1) * 100,
            "exchanges": r.meta["exchanges"],
        })
        log.info("  %s: %4.0fs obj %+.3f%% gc %+.2f%% unserved %+.2f%%",
                 label, effort[-1]["seconds"], effort[-1]["objective_change_pct"],
                 effort[-1]["gc_change_pct"], effort[-1]["unserved_change_pct"])
        r.plan.to_frame().to_csv(
            ROOT / "outputs" / f"plan_effort_{label.split()[0]}.csv", index=False)
    out["check3_search_effort"] = effort

    (ROOT / "outputs" / "fairness_checks.json").write_text(
        json.dumps(out, indent=2, default=str))

    print("\n" + "=" * 90)
    print("CHECK 1 — Experiment 1's own plans, scored by the path-based model")
    print("=" * 90)
    print(pd.DataFrame(rows).round(2).to_string(index=False))
    print("\nCHECK 2 — route 10: is leaving it alone actually optimal?")
    print(json.dumps(out["check2_route010"], indent=2))
    print("\n  sample of single-move probes:")
    print(pr[pr.feasible].sort_values("objective_change_pct").head(8).round(3).to_string(index=False))
    print("\nCHECK 3 — search effort")
    print(pd.DataFrame(effort).round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
