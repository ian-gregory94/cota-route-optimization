"""Frequency optimization v0 — Experiment 1 data structures and solver.

Problem
-------
Route geometry and stop patterns are **fixed**. The decision variable is the
headway of every (route, service period) that has baseline service. Total
weekday revenue vehicle-hours and per-period peak vehicle requirement are held
at (or below) the baseline envelope. Objectives: minimize passenger generalized
cost and unserved demand.

Resource accounting (documented, self-consistent)
------------------------------------------------
For a route with mean one-way runtime ``R`` minutes, ``k`` directions, in a
period of ``T`` minutes at headway ``h``:

    trips            = k * T / h
    revenue_veh_hours= trips * R / 60
    cycle_time       = 2 * R * (1 + layover_ratio)          [round trip + recovery]
    peak_vehicles    = cycle_time / h                        [continuous approx.]

Peak vehicles is a continuous relaxation of ``ceil(cycle/h)``; it is reported as
a *scheduled* fleet estimate, never as COTA's actual fleet requirement (which
depends on interlining, deadhead, run-cutting and maintenance reserve — all
UNKNOWN here).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd

from .cost import CostWeights, crowding_excess_min, demand_retention, expected_wait_min

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ServicePeriod:
    name: str
    start_hour: float
    end_hour: float

    @property
    def duration_min(self) -> float:
        return (self.end_hour - self.start_hour) * 60.0


@dataclass(frozen=True)
class RouteService:
    """Fixed (non-decision) attributes of one route in one period."""

    route_id: str
    period: str
    runtime_min: float          # mean one-way scheduled runtime
    n_directions: int
    baseline_headway_min: float
    baseline_trips: int


@dataclass
class ResourceBudget:
    """The service resource envelope the plan must respect."""

    revenue_veh_hours: float
    peak_vehicles_by_period: dict[str, float]
    tolerance: float = 0.005

    def vh_cap(self) -> float:
        return self.revenue_veh_hours * (1.0 + self.tolerance)

    def peak_cap(self, period: str) -> float:
        return self.peak_vehicles_by_period[period] * (1.0 + self.tolerance)


@dataclass
class PassengerDemand:
    """Proxy demand by (route, period), in daily passenger trips."""

    by_route_period: dict[tuple[str, str], float]
    source: str = "PROXY"
    notes: str = ""

    def get(self, route_id: str, period: str) -> float:
        return self.by_route_period.get((route_id, period), 0.0)

    def total(self) -> float:
        return float(sum(self.by_route_period.values()))


@dataclass
class FrequencyPlan:
    """A candidate assignment of headways to (route, period)."""

    headways: dict[tuple[str, str], float]

    def copy(self) -> "FrequencyPlan":
        return FrequencyPlan(dict(self.headways))

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [{"route_id": r, "period": p, "headway_min": h}
             for (r, p), h in sorted(self.headways.items())])


@dataclass(frozen=True)
class FitnessVector:
    """Multi-objective evaluation of a plan."""

    generalized_cost: float          # equivalent in-vehicle minutes, served trips
    unserved_demand: float           # daily passenger trips without usable service
    revenue_veh_hours: float
    peak_vehicles: float
    peak_by_period: dict[str, float] = field(default_factory=dict)
    served_demand: float = 0.0
    mean_wait_min: float = 0.0
    gc_per_served_trip: float = 0.0

    def scalarized(self, w_unserved: float, multiplier: float = 1.0) -> float:
        return self.generalized_cost + multiplier * w_unserved * self.unserved_demand

    def dominates(self, other: "FitnessVector") -> bool:
        return ((self.generalized_cost <= other.generalized_cost
                 and self.unserved_demand <= other.unserved_demand)
                and (self.generalized_cost < other.generalized_cost
                     or self.unserved_demand < other.unserved_demand))


@dataclass
class OptimizationResult:
    plan: FrequencyPlan
    fitness: FitnessVector
    label: str = ""
    meta: dict = field(default_factory=dict)


class FrequencyModel:
    """Evaluates frequency plans: resources, passenger cost, unserved demand."""

    def __init__(
        self,
        services: dict[tuple[str, str], RouteService],
        periods: dict[str, ServicePeriod],
        demand: PassengerDemand,
        weights: CostWeights,
        assumptions: dict,
        connections: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self.services = services
        self.periods = periods
        self.demand = demand
        self.w = weights
        self.a = assumptions
        # route -> {connected_route: share of its transfers} (rows sum to 1)
        self.connections = connections or {}
        ops = assumptions["operations"]
        self.layover = float(ops["layover_ratio"])
        wait = assumptions["waiting"]
        self._wait_kw = dict(
            random_arrival_threshold_min=float(wait["random_arrival_threshold_min"]),
            schedule_coefficient=float(wait["schedule_coefficient"]))
        self._ret_kw = dict(full_min=float(wait["retention_full_min"]),
                            zero_min=float(wait["retention_zero_min"]),
                            floor=float(wait["retention_floor"]))
        crowd = assumptions["crowding"]
        self.capacity = float(crowd["bus_capacity"])
        self.crowd_penalty = float(crowd["crowding_penalty_per_excess_load"])
        pax = assumptions.get("passenger", {})
        self.avg_ride_fraction = float(pax.get("avg_ride_fraction", 0.35))
        self.access_walk_min = float(pax.get("access_walk_min", 5.0))
        self.transfer_rate = float(pax.get("transfer_rate", 0.20))

    # -- per route-period physics ----------------------------------------
    def trips(self, svc: RouteService, headway: float) -> float:
        return svc.n_directions * self.periods[svc.period].duration_min / headway

    def revenue_veh_hours(self, svc: RouteService, headway: float) -> float:
        return self.trips(svc, headway) * svc.runtime_min / 60.0

    def peak_vehicles(self, svc: RouteService, headway: float) -> float:
        cycle = 2.0 * svc.runtime_min * (1.0 + self.layover)
        return cycle / headway

    # -- evaluation -------------------------------------------------------
    def evaluate(self, plan: FrequencyPlan) -> FitnessVector:
        vh = 0.0
        peak: dict[str, float] = {p: 0.0 for p in self.periods}
        served_total = unserved_total = 0.0
        wait_weighted = 0.0
        gc_total = 0.0

        # Pass 1: resources, served demand, and per-route mean headway (for transfers)
        served_rp: dict[tuple[str, str], float] = {}
        for key, svc in self.services.items():
            h = plan.headways[key]
            vh += self.revenue_veh_hours(svc, h)
            peak[svc.period] += self.peak_vehicles(svc, h)
            d = self.demand.get(*key)
            rho = demand_retention(h, **self._ret_kw)
            served_rp[key] = d * rho
            served_total += d * rho
            unserved_total += d * (1.0 - rho)

        # Pass 2: passenger cost (transfer term needs connecting headways)
        for key, svc in self.services.items():
            h = plan.headways[key]
            served = served_rp[key]
            if served <= 0:
                continue
            wait = expected_wait_min(h, **self._wait_kw)
            ivt = svc.runtime_min * self.avg_ride_fraction
            n_trips = self.trips(svc, h)
            pax_per_trip = served / n_trips if n_trips > 0 else 0.0
            crowd = crowding_excess_min(pax_per_trip, self.capacity, ivt,
                                        self.crowd_penalty)
            t_wait = self._transfer_wait(key[0], key[1], plan)
            per_trip = (
                self.w.walking * self.access_walk_min
                + self.w.waiting * wait
                + self.w.in_vehicle * ivt
                + self.w.crowding * crowd
                + self.transfer_rate * (self.w.transfer_wait * t_wait
                                        + self.w.transfer_penalty)
            )
            gc_total += served * per_trip
            wait_weighted += served * wait

        peak_system = max(peak.values()) if peak else 0.0
        return FitnessVector(
            generalized_cost=gc_total,
            unserved_demand=unserved_total,
            revenue_veh_hours=vh,
            peak_vehicles=peak_system,
            peak_by_period=peak,
            served_demand=served_total,
            mean_wait_min=(wait_weighted / served_total) if served_total else 0.0,
            gc_per_served_trip=(gc_total / served_total) if served_total else 0.0,
        )

    def _transfer_wait(self, route_id: str, period: str, plan: FrequencyPlan) -> float:
        """Expected wait for the second leg, over routes this route connects to."""
        conn = self.connections.get(route_id)
        if not conn:
            return expected_wait_min(plan.headways[(route_id, period)], **self._wait_kw)
        tot = 0.0
        wsum = 0.0
        for other, share in conn.items():
            k = (other, period)
            if k not in plan.headways:
                continue
            tot += share * expected_wait_min(plan.headways[k], **self._wait_kw)
            wsum += share
        if wsum <= 0:
            return expected_wait_min(plan.headways[(route_id, period)], **self._wait_kw)
        return tot / wsum


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------

def _feasible(model: FrequencyModel, fit: FitnessVector,
              budget: ResourceBudget) -> bool:
    if fit.revenue_veh_hours > budget.vh_cap():
        return False
    for p, v in fit.peak_by_period.items():
        if p in budget.peak_vehicles_by_period and v > budget.peak_cap(p):
            return False
    return True


def optimize_frequencies(
    model: FrequencyModel,
    budget: ResourceBudget,
    ladder: Iterable[float],
    unserved_multiplier: float = 1.0,
    max_headway: float = 60.0,
    min_headway: float = 5.0,
    local_search_iterations: int = 3000,
    seed: int = 0,
) -> OptimizationResult:
    """Greedy marginal allocation + randomized pairwise local search.

    Phase A starts every route-period at the policy maximum headway (minimum
    service preserved everywhere it exists today) and spends the vehicle-hour
    budget on whichever single ladder step buys the largest objective reduction
    per vehicle-hour. Phase B then tries budget-neutral pairwise swaps.
    """
    rng = np.random.default_rng(seed)
    lad = sorted(h for h in ladder if min_headway <= h <= max_headway)
    if not lad:
        raise ValueError("empty headway ladder after applying policy bounds")
    keys = list(model.services)

    plan = FrequencyPlan({k: lad[-1] for k in keys})
    fit = model.evaluate(plan)
    if not _feasible(model, fit, budget):
        raise ValueError(
            "minimum-service plan already exceeds the budget; the policy maximum "
            "headway is infeasible under this envelope")

    def obj(f: FitnessVector) -> float:
        return f.scalarized(model.w.unserved, unserved_multiplier)

    idx_of = {k: len(lad) - 1 for k in keys}
    cur_obj = obj(fit)

    # -- Phase A: greedy marginal allocation ------------------------------
    improved = True
    n_steps = 0
    while improved:
        improved = False
        best = None  # (ratio, key, new_idx, new_fit, new_obj)
        for k in keys:
            i = idx_of[k]
            if i == 0:
                continue
            trial = plan.copy()
            trial.headways[k] = lad[i - 1]
            tf = model.evaluate(trial)
            if not _feasible(model, tf, budget):
                continue
            d_vh = tf.revenue_veh_hours - fit.revenue_veh_hours
            d_obj = cur_obj - obj(tf)
            if d_obj <= 0 or d_vh <= 0:
                continue
            ratio = d_obj / d_vh
            if best is None or ratio > best[0]:
                best = (ratio, k, i - 1, tf, obj(tf))
        if best is not None:
            _, k, new_i, tf, new_obj = best
            plan.headways[k] = lad[new_i]
            idx_of[k] = new_i
            fit, cur_obj = tf, new_obj
            improved = True
            n_steps += 1

    log.info("phase A: %d ladder steps, obj=%.1f, vh=%.1f/%.1f",
             n_steps, cur_obj, fit.revenue_veh_hours, budget.revenue_veh_hours)

    # -- Phase B: randomized budget-neutral pairwise swaps -----------------
    n_accept = 0
    for _ in range(local_search_iterations):
        if len(keys) < 2:
            break
        a, b = rng.choice(len(keys), size=2, replace=False)
        ka, kb = keys[a], keys[b]
        ia, ib = idx_of[ka], idx_of[kb]
        if ia == len(lad) - 1 or ib == 0:
            continue
        trial = plan.copy()
        trial.headways[ka] = lad[ia + 1]   # worse service on a (frees hours)
        trial.headways[kb] = lad[ib - 1]   # better service on b (spends them)
        tf = model.evaluate(trial)
        if not _feasible(model, tf, budget):
            continue
        to = obj(tf)
        if to < cur_obj - 1e-9:
            plan = trial
            idx_of[ka], idx_of[kb] = ia + 1, ib - 1
            fit, cur_obj = tf, to
            n_accept += 1

    # -- Phase C: final single-step sweep to spend any freed budget --------
    improved = True
    while improved:
        improved = False
        for k in keys:
            i = idx_of[k]
            if i == 0:
                continue
            trial = plan.copy()
            trial.headways[k] = lad[i - 1]
            tf = model.evaluate(trial)
            if _feasible(model, tf, budget) and obj(tf) < cur_obj - 1e-9:
                plan, idx_of[k] = trial, i - 1
                fit, cur_obj = tf, obj(tf)
                improved = True

    log.info("phase B/C: %d swaps accepted, obj=%.1f, vh=%.1f",
             n_accept, cur_obj, fit.revenue_veh_hours)
    return OptimizationResult(
        plan=plan, fitness=fit,
        label=f"lambda={unserved_multiplier}",
        meta={"phase_a_steps": n_steps, "swaps_accepted": n_accept,
              "unserved_multiplier": unserved_multiplier, "seed": seed})


def pareto_filter(results: list[OptimizationResult]) -> list[OptimizationResult]:
    """Keep only non-dominated (generalized_cost, unserved_demand) solutions."""
    out = []
    for r in results:
        if not any(o.fitness.dominates(r.fitness) for o in results if o is not r):
            out.append(r)
    # de-duplicate identical objective pairs
    seen: set[tuple[float, float]] = set()
    uniq = []
    for r in sorted(out, key=lambda x: x.fitness.generalized_cost):
        key = (round(r.fitness.generalized_cost, 3), round(r.fitness.unserved_demand, 3))
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    return uniq


def snap_to_ladder(headway: float, ladder: Iterable[float]) -> float:
    """Nearest ladder value (used to make the baseline plan comparable)."""
    lad = sorted(ladder)
    return min(lad, key=lambda x: abs(x - headway))


def integer_fleet(model: FrequencyModel, plan: FrequencyPlan) -> dict[str, int]:
    """Per-period fleet with per-route integer rounding (ceil of cycle/headway)."""
    out: dict[str, int] = {p: 0 for p in model.periods}
    for key, svc in model.services.items():
        h = plan.headways[key]
        cycle = 2.0 * svc.runtime_min * (1.0 + model.layover)
        out[svc.period] += int(math.ceil(cycle / h))
    return out
