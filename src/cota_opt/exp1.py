"""Experiment 1 — Pareto-optimal weekday frequency redistribution.

Route geometry and stop patterns are held fixed. The decision variable is the
headway of every (route, service period) with baseline weekday service. The
plan must fit inside COTA's *current scheduled* resource envelope: weekday
revenue vehicle-hours and per-period peak vehicle requirement.

Calibration guarantee
---------------------
Baseline headways are derived so the model reproduces the observed trip count
exactly:  ``h = k · T / n_trips``.  Because revenue vehicle-hours are
``n_trips · mean_runtime / 60`` and ``mean_runtime · n_trips = Σ runtime``, the
model's baseline vehicle-hours are *identically* the GTFS scheduled
vehicle-hours. There is no calibration gap to explain away — this is asserted
at run time.

Module naming: these files are numbered by the order the models were built,
not by the write-up's experiment numbers. This is the route-level frequency
model; the path-based model in ``exp2`` is what the *first* experiment's
headline rests on, and Experiment 2's geometry funnel lives in
``geometry_eval``.

"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .baseline import Baseline
from .configs import load_constraints, load_cost_weights, period_of_seconds
from .cost import CostWeights
from .frequency import (FrequencyModel, FrequencyPlan, OptimizationResult,
                        PassengerDemand, ResourceBudget, RouteService,
                        ServicePeriod, build_ladders, integer_fleet,
                        optimize_frequencies, pareto_filter)

log = logging.getLogger(__name__)


@dataclass
class Exp1Setup:
    model: FrequencyModel
    baseline_plan: FrequencyPlan
    budget: ResourceBudget
    ladders: dict[tuple[str, str], list[float]]
    services_frame: pd.DataFrame
    checks: dict[str, Any]


def build_setup(b: Baseline, constraints: dict | None = None,
                weights: CostWeights | None = None) -> Exp1Setup:
    a = b.assumptions
    cons = constraints or load_constraints()
    w = weights or CostWeights.from_config(load_cost_weights())
    periods_cfg = a["service_periods"]
    periods = {name: ServicePeriod(name, float(v[0]), float(v[1]))
               for name, v in periods_cfg.items()}

    # --- route × period supply, aggregated over directions -----------------
    ts = b.tstats.copy()
    ts["period"] = ts["first_dep_sec"].map(
        lambda s: period_of_seconds(s, {k: (v.start_hour, v.end_hour)
                                        for k, v in periods.items()}))
    ts = ts.dropna(subset=["period"])

    services: dict[tuple[str, str], RouteService] = {}
    rows = []
    for (rid, per), grp in ts.groupby(["route_id", "period"]):
        n_trips = len(grp)
        k = int(grp["direction_id"].nunique())
        T = periods[per].duration_min
        runtime = float(grp["runtime_min"].mean())
        headway = k * T / n_trips          # calibration-preserving definition
        services[(rid, per)] = RouteService(rid, per, runtime, k, headway, n_trips)
        rows.append({"route_id": rid, "period": per, "n_trips": n_trips,
                     "n_directions": k, "mean_runtime_min": runtime,
                     "baseline_headway_min": headway,
                     "revenue_veh_hours": n_trips * runtime / 60.0})
    services_frame = pd.DataFrame(rows)

    # --- demand ------------------------------------------------------------
    if b.demand.get("status") != "PROXY":
        raise ValueError("Experiment 1 requires the demand proxy to be built")
    dp = b.demand["route_demand_period"]
    raw = {(r.route_id, r.period): float(r.demand_potential)
           for r in dp.itertuples() if (r.route_id, r.period) in services}
    raw_total = sum(raw.values())
    target = a["demand_proxy"].get("assumed_weekday_linked_trips")
    if target and raw_total > 0:
        scale = float(target) / raw_total
        raw = {k: v * scale for k, v in raw.items()}
    else:
        scale = 1.0
    demand = PassengerDemand(
        raw,
        source="LODES-derived stop-access proxy",
        notes=("Relative daily boarding potential from LEHD LODES workers/jobs "
               "within a 600 m stop catchment, split across periods by assumed "
               "shares, then rescaled so the system total equals the assumed "
               f"weekday linked-trip count ({target:,} trips; scale factor "
               f"{scale:.6g}). NOT observed COTA ridership."))

    # --- transfer coupling from shared stops -------------------------------
    conn_counts = b.network.route_connections()
    conn: dict[str, dict[str, float]] = {}
    for (ra, rb), n in conn_counts.items():
        conn.setdefault(ra, {})[rb] = float(n)
        conn.setdefault(rb, {})[ra] = float(n)
    for r, d in conn.items():
        tot = sum(d.values())
        if tot:
            conn[r] = {k: v / tot for k, v in d.items()}

    model = FrequencyModel(services, periods, demand, w, a, conn)
    baseline_plan = FrequencyPlan(
        {k: v.baseline_headway_min for k, v in services.items()})
    fit = model.evaluate(baseline_plan)

    # --- calibration assertions (skeptic pass) -----------------------------
    gtfs_vh = float(ts["runtime_min"].sum() / 60.0)
    checks: dict[str, Any] = {
        "gtfs_scheduled_revenue_veh_hours": gtfs_vh,
        "model_baseline_revenue_veh_hours": fit.revenue_veh_hours,
        "vh_relative_error": abs(fit.revenue_veh_hours - gtfs_vh) / gtfs_vh,
        "model_baseline_peak_by_period": dict(fit.peak_by_period),
        "schedule_sweep_peak_concurrent_buses": b.system.peak_concurrent_buses,
        "model_peak_system": fit.peak_vehicles,
        "n_route_periods": len(services),
        "n_routes": int(ts["route_id"].nunique()),
        "baseline_generalized_cost": fit.generalized_cost,
        "baseline_unserved_demand": fit.unserved_demand,
        "baseline_served_demand": fit.served_demand,
        "baseline_mean_wait_min": fit.mean_wait_min,
        "demand_raw_total": raw_total,
        "demand_scale_factor": scale,
        "demand_assumed_weekday_trips": target,
        "baseline_mean_pax_per_trip": (
            fit.served_demand / sum(v.baseline_trips for v in services.values())),
    }
    if checks["vh_relative_error"] > 1e-9:
        raise AssertionError(
            f"model baseline vehicle-hours ({fit.revenue_veh_hours:.4f}) do not "
            f"reproduce GTFS scheduled vehicle-hours ({gtfs_vh:.4f})")

    # --- budget ------------------------------------------------------------
    res = cons["resource"]
    vh_budget = (fit.revenue_veh_hours if res["weekday_revenue_vehicle_hours"] == "baseline"
                 else float(res["weekday_revenue_vehicle_hours"]))
    peak_budget = (dict(fit.peak_by_period)
                   if res["peak_fleet_by_period"] == "baseline"
                   else {k: float(v) for k, v in res["peak_fleet_by_period"].items()})
    budget = ResourceBudget(vh_budget, peak_budget,
                            tolerance=float(res.get("budget_tolerance", 0.005)))

    svc_cons = cons["service"]
    ladders = build_ladders(model, svc_cons["headway_ladder_min"],
                            float(svc_cons["policy_max_headway_min"]),
                            float(svc_cons["policy_min_headway_min"]))
    return Exp1Setup(model, baseline_plan, budget, ladders, services_frame, checks)


def run_pareto(setup: Exp1Setup, multipliers: list[float], seed: int,
               iterations: int) -> tuple[list[OptimizationResult], list[OptimizationResult]]:
    """Sweep the unserved-demand weight to trace the frontier."""
    results = []
    for m in multipliers:
        r = optimize_frequencies(
            setup.model, setup.budget, ladder=[],
            unserved_multiplier=m, local_search_iterations=iterations,
            seed=seed, ladders=setup.ladders)
        log.info("lambda=%-5s gc=%.3e unserved=%.1f vh=%.1f",
                 m, r.fitness.generalized_cost, r.fitness.unserved_demand,
                 r.fitness.revenue_veh_hours)
        results.append(r)
    return results, pareto_filter(results)


def compare_to_baseline(setup: Exp1Setup, res: OptimizationResult) -> dict[str, Any]:
    m, base = setup.model, setup.baseline_plan
    bf = m.evaluate(base)
    f = res.fitness
    return {
        "label": res.label,
        "generalized_cost": f.generalized_cost,
        "gc_change_pct": (f.generalized_cost / bf.generalized_cost - 1) * 100,
        "unserved_demand": f.unserved_demand,
        "unserved_change_pct": ((f.unserved_demand / bf.unserved_demand - 1) * 100
                                if bf.unserved_demand else float("nan")),
        "served_demand": f.served_demand,
        "served_change_pct": (f.served_demand / bf.served_demand - 1) * 100,
        "mean_wait_min": f.mean_wait_min,
        "wait_change_pct": (f.mean_wait_min / bf.mean_wait_min - 1) * 100,
        "gc_per_served_trip": f.gc_per_served_trip,
        "gc_per_trip_change_pct": (f.gc_per_served_trip / bf.gc_per_served_trip - 1) * 100,
        "revenue_veh_hours": f.revenue_veh_hours,
        "vh_vs_budget_pct": (f.revenue_veh_hours / setup.budget.revenue_veh_hours - 1) * 100,
        "peak_vehicles_continuous": f.peak_vehicles,
        "integer_fleet_by_period": integer_fleet(m, res.plan),
        "baseline_integer_fleet_by_period": integer_fleet(m, base),
    }


def plan_diff(setup: Exp1Setup, res: OptimizationResult) -> pd.DataFrame:
    """Route-period level change table: baseline vs optimized."""
    m = setup.model
    rows = []
    for key, svc in m.services.items():
        hb = setup.baseline_plan.headways[key]
        ho = res.plan.headways[key]
        rows.append({
            "route_id": key[0], "period": key[1],
            "baseline_headway_min": hb, "optimized_headway_min": ho,
            "headway_change_min": ho - hb,
            "baseline_trips": m.trips(svc, hb), "optimized_trips": m.trips(svc, ho),
            "baseline_veh_hours": m.revenue_veh_hours(svc, hb),
            "optimized_veh_hours": m.revenue_veh_hours(svc, ho),
            "veh_hours_change": m.revenue_veh_hours(svc, ho) - m.revenue_veh_hours(svc, hb),
            "demand_potential": m.demand.get(*key),
            "runtime_min": svc.runtime_min,
        })
    df = pd.DataFrame(rows)
    df["direction"] = np.where(df["headway_change_min"] < -0.01, "more service",
                      np.where(df["headway_change_min"] > 0.01, "less service", "unchanged"))
    return df.sort_values("veh_hours_change")
