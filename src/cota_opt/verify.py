"""Independent verification of optimization results (the Skeptic pass).

Nothing here calls the vectorized evaluator. Every quantity is recomputed from
first principles with plain Python loops so that a bug in the fast path cannot
hide behind itself.
"""
from __future__ import annotations

import math
from typing import Any

from .cost import CostWeights
from .frequency import FrequencyModel, FrequencyPlan, ResourceBudget


def _wait(h: float, t: float, c: float) -> float:
    return h / 2.0 if h <= t else t / 2.0 + c * (h - t)


def _retention(h: float, full: float, zero: float, floor: float) -> float:
    if h <= full:
        return 1.0
    if h >= zero:
        return floor
    return 1.0 - (h - full) / (zero - full) * (1.0 - floor)


def recompute(model: FrequencyModel, plan: FrequencyPlan) -> dict[str, Any]:
    """Scalar re-implementation of the fitness calculation."""
    a = model.a
    t = float(a["waiting"]["random_arrival_threshold_min"])
    c = float(a["waiting"]["schedule_coefficient"])
    full = float(a["waiting"]["retention_full_min"])
    zero = float(a["waiting"]["retention_zero_min"])
    floor = float(a["waiting"]["retention_floor"])
    lay = float(a["operations"]["layover_ratio"])
    cap = float(a["crowding"]["bus_capacity"])
    cpen = float(a["crowding"]["crowding_penalty_per_excess_load"])
    pax = a.get("passenger", {})
    ride = float(pax.get("avg_ride_fraction", 0.35))
    walk = float(pax.get("access_walk_min", 5.0))
    trate = float(pax.get("transfer_rate", 0.20))
    w: CostWeights = model.w

    vh = 0.0
    peak: dict[str, float] = {}
    served_tot = unserved_tot = gc = wait_w = 0.0

    waits: dict[tuple[str, str], float] = {}
    for key, svc in model.services.items():
        waits[key] = _wait(plan.headways[key], t, c)

    for key, svc in model.services.items():
        h = plan.headways[key]
        T = model.periods[svc.period].duration_min
        trips = svc.n_directions * T / h
        vh += trips * svc.runtime_min / 60.0
        peak[svc.period] = peak.get(svc.period, 0.0) + \
            2.0 * svc.runtime_min * (1.0 + lay) / h
        d = model.demand.get(*key)
        rho = _retention(h, full, zero, floor)
        served = d * rho
        served_tot += served
        unserved_tot += d - served
        if served <= 0:
            continue
        ivt = svc.runtime_min * ride
        load = (served / trips) / cap
        crowd = cpen * max(load - 1.0, 0.0) * ivt

        conn = model.connections.get(key[0]) or {}
        num = den = 0.0
        for other, share in conn.items():
            k2 = (other, key[1])
            if k2 in waits:
                num += share * waits[k2]
                den += share
        twait = num / den if den > 0 else waits[key]

        per_trip = (w.walking * walk + w.waiting * waits[key]
                    + w.in_vehicle * ivt + w.crowding * crowd
                    + trate * (w.transfer_wait * twait + w.transfer_penalty))
        gc += served * per_trip
        wait_w += served * waits[key]

    return {
        "generalized_cost": gc,
        "unserved_demand": unserved_tot,
        "served_demand": served_tot,
        "revenue_veh_hours": vh,
        "peak_by_period": peak,
        "peak_vehicles": max(peak.values()) if peak else 0.0,
        "mean_wait_min": wait_w / served_tot if served_tot else 0.0,
        "gc_per_served_trip": gc / served_tot if served_tot else 0.0,
    }


def verify_result(model: FrequencyModel, plan: FrequencyPlan,
                  budget: ResourceBudget, ladders: dict, tol: float = 1e-6,
                  ) -> dict[str, Any]:
    """Cross-check a plan: arithmetic, budget, policy constraints."""
    fast = model.evaluate(plan)
    slow = recompute(model, plan)
    checks: dict[str, Any] = {}

    def rel(a_: float, b_: float) -> float:
        return abs(a_ - b_) / max(abs(b_), 1e-12)

    checks["gc_relative_error"] = rel(fast.generalized_cost, slow["generalized_cost"])
    checks["unserved_relative_error"] = rel(fast.unserved_demand, slow["unserved_demand"])
    checks["vh_relative_error"] = rel(fast.revenue_veh_hours, slow["revenue_veh_hours"])
    checks["peak_relative_error"] = max(
        rel(fast.peak_by_period[p], v) for p, v in slow["peak_by_period"].items())
    checks["vectorized_matches_scalar"] = all(
        checks[k] < 1e-9 for k in
        ("gc_relative_error", "unserved_relative_error", "vh_relative_error",
         "peak_relative_error"))

    checks["veh_hours"] = slow["revenue_veh_hours"]
    checks["veh_hours_budget"] = budget.revenue_veh_hours
    checks["veh_hours_cap"] = budget.vh_cap()
    checks["within_veh_hour_budget"] = slow["revenue_veh_hours"] <= budget.vh_cap() + tol
    checks["veh_hours_headroom_pct"] = (
        slow["revenue_veh_hours"] / budget.revenue_veh_hours - 1) * 100

    peak_ok = True
    peak_detail = {}
    for p, v in slow["peak_by_period"].items():
        capv = budget.peak_cap(p)
        peak_detail[p] = {"used": v, "cap": capv, "ok": v <= capv + tol}
        peak_ok &= v <= capv + tol
    checks["within_peak_budget"] = peak_ok
    checks["peak_detail"] = peak_detail

    off_ladder = [k for k, h in plan.headways.items()
                  if not any(math.isclose(h, x, rel_tol=1e-9) for x in ladders[k])]
    checks["all_headways_on_ladder"] = not off_ladder
    checks["off_ladder_keys"] = off_ladder[:10]

    worst_violations = [
        (k, plan.headways[k], max(ladders[k]))
        for k in plan.headways if plan.headways[k] > max(ladders[k]) + tol]
    checks["minimum_service_preserved"] = not worst_violations
    checks["service_violations"] = worst_violations[:10]
    checks["all_route_periods_served"] = all(
        h < float("inf") for h in plan.headways.values())
    checks["n_route_periods"] = len(plan.headways)
    return checks
