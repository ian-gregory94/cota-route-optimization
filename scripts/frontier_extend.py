#!/usr/bin/env python3
"""Did the ablation under-explore the frontier, or under-search it?

Two confounds are tested together. Experiment 1 swept the unserved-demand
weight over lambda in {0.25 ... 16} with 400k iterations and 20 restarts; the
ablation swept only {0.5, 1, 2} with 20k iterations and no restarts. Scoring
Experiment 1's own plans under the path model showed them reaching -8.7%
unserved demand, well past where the ablation looked — so the ablation may have
stopped early on BOTH axes.

This extends the sweep to the same lambda range at a materially larger search
budget, and reports the resulting frontier against Experiment 1's plans scored
on the identical model. That is the apples-to-apples comparison the ablation
should have made.
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
from cota_opt.experiment import Experiment
from cota_opt.frequency import FrequencyPlan, optimize_frequencies, pareto_filter
from cota_opt.odmatrix import (_top_k, build_zone_system, filter_to_accessible,
                               from_lodes_od, scale_to)
from cota_opt.raptor import build_raptor_network
from cota_opt.registry import Registry
from cota_opt.routeclass import classify_routes

log = logging.getLogger("frontier")
UPLOADS = Path("/mnt/user-data/uploads/Downloads")
DEMAND_FILES = {"rac": UPLOADS / "oh_rac_S000_JT00_2022.csv.gz",
                "wac": UPLOADS / "oh_wac_S000_JT00_2022.csv.gz",
                "centroids": UPLOADS / "CenPop2020_Mean_BG39.txt"}
CACHE = Path("/tmp/cota_pathsets.pkl")
LAMBDAS = [0.5, 1.0, 2.0, 4.0, 8.0, 16.0]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    seed = 20260825
    exp = Experiment(name="exp4_frontier", seed=seed,
                     algorithm="path model, extended lambda sweep, larger search",
                     config_files=["assumptions.yaml", "cost_weights.yaml",
                                   "constraints.yaml"])
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
    setup = build_setup(b, rn, zs, od, seed=seed, route_classes=classes,
                        with_crowding=True, lock_classes=("peak_express",),
                        pathset_cache=cache)
    model, base = setup.model, setup.baseline_plan
    bf = model.evaluate(base)
    log.info("baseline: gc=%.4e unserved=%.0f vh=%.1f",
             bf.generalized_cost, bf.unserved_demand, bf.revenue_veh_hours)

    rows = [{"source": "baseline (COTA scheduled)", "lambda": None,
             "gc_change_pct": 0.0, "unserved_change_pct": 0.0,
             "veh_hours": bf.revenue_veh_hours}]

    # Experiment 1's plans, scored on this identical model
    e1dir = sorted((ROOT / "outputs" / "experiments")
                   .glob("exp1_frequency_redistribution_*"))[-1]
    for csv in sorted(e1dir.glob("plan_lambda_*.csv")):
        df = pd.read_csv(csv, dtype={"route_id": str})
        h = dict(base.headways)
        for r in df.itertuples():
            k = (r.route_id, r.period)
            if k in h:
                h[k] = float(r.headway_min)
        f = model.evaluate(FrequencyPlan(h))
        rows.append({"source": "Experiment 1 plan (scored here)",
                     "lambda": float(csv.stem.replace("plan_lambda_", "")),
                     "gc_change_pct": (f.generalized_cost / bf.generalized_cost - 1) * 100,
                     "unserved_change_pct": (f.unserved_demand / bf.unserved_demand - 1) * 100,
                     "veh_hours": f.revenue_veh_hours})

    # extended, better-searched sweep on the corrected model
    results = []
    for lam in LAMBDAS:
        t = time.time()
        r = optimize_frequencies(
            model, setup.budget, ladder=[], unserved_multiplier=lam,
            local_search_iterations=120_000, seed=seed, ladders=setup.ladders,
            initial=base, n_restarts=3, candidate_width=48, greedy_start=False)
        results.append(r)
        gc = (r.fitness.generalized_cost / bf.generalized_cost - 1) * 100
        un = (r.fitness.unserved_demand / bf.unserved_demand - 1) * 100
        rows.append({"source": "corrected model (extended sweep)", "lambda": lam,
                     "gc_change_pct": gc, "unserved_change_pct": un,
                     "veh_hours": r.fitness.revenue_veh_hours})
        log.info("  lambda=%-5s %4.0fs gc %+7.2f%% unserved %+7.2f%% vh=%.1f ex=%d",
                 lam, time.time() - t, gc, un, r.fitness.revenue_veh_hours,
                 r.meta["exchanges"])
        r.plan.to_frame().to_csv(
            exp.artifact_path(f"plan_lambda_{lam}.csv"), index=False)
        d = plan_diff(setup, r.plan)
        r10 = d[d.route_id == "010"][["period", "baseline_headway_min",
                                      "optimized_headway_min"]]
        log.info("    route 010: %s",
                 {x.period: round(x.optimized_headway_min, 1) for x in r10.itertuples()})

    tab = pd.DataFrame(rows)
    tab.to_csv(exp.artifact_path("frontier_comparison.csv"), index=False)
    exp.log_metrics(frontier=tab.to_dict(orient="records"),
                    baseline={"gc": bf.generalized_cost,
                              "unserved": bf.unserved_demand,
                              "veh_hours": bf.revenue_veh_hours})
    exp.save()

    print("\n" + "=" * 88)
    print("APPLES-TO-APPLES FRONTIER — every row scored by the same path-based model")
    print("=" * 88)
    print(tab.round(2).to_string(index=False))
    print(f"\nartifacts: {exp.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
