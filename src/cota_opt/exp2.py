"""Experiment 2 — frequency redistribution with path-based passenger assignment.

Same problem as Experiment 1 (route geometry fixed, headways are the decision
variables, resources held at the current scheduled envelope) but passenger cost
is computed on origin-destination *paths* found by RAPTOR, not on route-level
aggregates. That closes the largest gap named in the Experiment 1 write-up:
when a route's frequency is cut, travellers re-route onto whatever alternative
is now cheapest instead of absorbing the full penalty.

What changes from Experiment 1
------------------------------
- demand is real LODES origin-destination commute flow, not a stop-access proxy;
- a trip's cost is its whole journey — access walk, wait, ride, transfer wait,
  transfer penalty, egress walk — over the best available path;
- unserved demand splits into *structural* (no path exists at all, which no
  frequency plan can fix) and *discouraged* (a path exists but costs enough
  that some travellers give up), and only the second responds to frequency.

Resource accounting is unchanged and still ties exactly to the GTFS schedule.

Module naming: these files are numbered by the order the models were built,
not by the write-up's experiment numbers. Despite the name, this is the model
the *first* experiment's headline rests on; Experiment 2's geometry funnel is
``geometry_eval``.

"""
from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .baseline import Baseline
from .configs import load_constraints, load_cost_weights, service_periods
from .cost import CostWeights
from .frequency import (FitnessVector, FrequencyModel, FrequencyPlan,
                        ResourceBudget, RouteService, ServicePeriod,
                        build_ladders)
from .odmatrix import ODTable, ZoneSystem
from .pathset import PathSet, PathSetEvaluator, build_pathset
from .raptor import RaptorNetwork

log = logging.getLogger(__name__)


class PathBasedModel(FrequencyModel):
    """A :class:`FrequencyModel` whose passenger cost comes from path sets.

    Resource physics (vehicle-hours, peak vehicles) are inherited unchanged.
    Only the passenger side is replaced. Evaluations are cached per period: a
    change to one (route, period) can only move that period's passenger cost,
    so the other five periods are reused.
    """

    def __init__(self, services, periods, demand, weights, assumptions,
                 evaluators: dict[str, PathSetEvaluator],
                 connections=None, crowding=None, locked: set | None = None) -> None:
        super().__init__(services, periods, demand, weights, assumptions,
                         connections)
        self.evaluators = evaluators
        # crowding: {period: CrowdingModel}; priced at the peak load point
        self.crowding = crowding or {}
        self.locked = locked or set()
        # map this model's key order onto each period's rp_keys order
        self._sel: dict[str, np.ndarray] = {}
        # A period's path set is indexed against the FULL route-period key list,
        # so _sel[per] spans every key in the network. Using that for the cache
        # key would mean any single-key change invalidates all six periods. The
        # cache key therefore uses only the keys that period's rides actually
        # reference, which is what its cost can possibly depend on.
        self._cachesel: dict[str, np.ndarray] = {}
        idx = {k: i for i, k in enumerate(self.keys)}
        for per, ev in evaluators.items():
            self._sel[per] = np.array([idx[k] for k in ev.ps.rp_keys], dtype=np.int64)
            used = np.unique(ev.ps.leg_rp[ev.ps.leg_rp >= 0])
            keys_used = [ev.ps.rp_keys[i] for i in used]
            self._cachesel[per] = np.array(
                sorted(idx[k] for k in keys_used if k in idx), dtype=np.int64)
        # A single cache slot per period is useless here: the optimizer scans
        # keys one at a time, so each period's slot is evicted by the next key
        # that happens to live in it. A tiny keyed cache instead means the five
        # periods a trial does NOT touch are always hits.
        self._cache: dict[str, "OrderedDict[bytes, dict]"] = {
            per: OrderedDict() for per in evaluators}
        self._cache_max = 8
        self.n_evals = 0
        self.n_period_evals = 0
        self.n_cache_hits = 0

    def _period_result(self, per: str, h: np.ndarray) -> dict:
        sub = h[self._sel[per]]
        slot = self._cache[per]
        key = h[self._cachesel[per]].tobytes()
        hit = slot.get(key)
        if hit is not None:
            slot.move_to_end(key)
            self.n_cache_hits += 1
            return hit
        ev = self.evaluators[per]
        res = dict(ev.evaluate(sub))
        cm = self.crowding.get(per)
        if cm is not None:
            pf = ev.path_flows(sub)   # shares path_costs internally
            boardings = ev.boardings_by_rp(sub, pf)
            sel = self._sel[per]
            trips = self._ndir[sel] * self._T[sel] / sub
            crowd = float(cm.excess_cost(boardings, trips).sum())
            res["crowding_cost"] = crowd
            res["generalized_cost_served_only"] += crowd
            res["generalized_cost"] += crowd
            res["peak_load_over_capacity"] = float(np.max(
                boardings * cm.profile.peak_load_factor
                / np.where(trips > 0, trips, np.inf) / cm.capacity)) if len(trips) else 0.0
        slot[key] = res
        if len(slot) > self._cache_max:
            slot.popitem(last=False)
        self.n_period_evals += 1
        return res

    def evaluate_array(self, h: np.ndarray) -> FitnessVector:
        self.n_evals += 1
        # resources: unchanged physics
        trips = self._ndir * self._T / h
        vh = float((trips * self._runtime / 60.0).sum())
        peak_arr = np.bincount(self._pi, weights=self._cycle / h,
                               minlength=len(self.period_names))
        peak = {p: float(peak_arr[i]) for i, p in enumerate(self.period_names)}

        gc = served = unserved = struct = disc = 0.0
        for per in self.evaluators:
            r = self._period_result(per, h)
            gc += r["generalized_cost_served_only"]
            served += r["served_demand"]
            unserved += r["unserved_demand"]
            struct += r["unserved_structural"]
            disc += r["unserved_discouraged"]

        return FitnessVector(
            generalized_cost=gc,
            unserved_demand=unserved,
            revenue_veh_hours=vh,
            peak_vehicles=float(peak_arr.max()) if len(peak_arr) else 0.0,
            peak_by_period=peak,
            served_demand=served,
            mean_wait_min=0.0,
            gc_per_served_trip=(gc / served) if served else 0.0,
        )

    def detail(self, plan: FrequencyPlan) -> dict[str, Any]:
        """Per-period breakdown for reporting."""
        h = self.headway_array(plan)
        out: dict[str, Any] = {"periods": {}}
        for per in self.evaluators:
            out["periods"][per] = dict(self._period_result(per, h))
        f = self.evaluate_array(h)
        out["total"] = {
            "generalized_cost": f.generalized_cost,
            "unserved_demand": f.unserved_demand,
            "served_demand": f.served_demand,
            "gc_per_served_trip": f.gc_per_served_trip,
            "revenue_veh_hours": f.revenue_veh_hours,
            "peak_by_period": dict(f.peak_by_period),
        }
        out["total"]["unserved_structural"] = sum(
            v["unserved_structural"] for v in out["periods"].values())
        out["total"]["unserved_discouraged"] = sum(
            v["unserved_discouraged"] for v in out["periods"].values())
        return out


@dataclass
class Exp2Setup:
    model: PathBasedModel
    baseline_plan: FrequencyPlan
    budget: ResourceBudget
    ladders: dict[tuple[str, str], list[float]]
    pathsets: dict[str, PathSet]
    checks: dict[str, Any]


def build_setup(b: Baseline, rn: RaptorNetwork, zs: ZoneSystem, od: ODTable,
                weights: CostWeights | None = None,
                constraints: dict | None = None,
                periods_to_model: list[str] | None = None,
                seed: int = 0,
                with_crowding: bool = False,
                lock_classes: tuple[str, ...] = (),
                route_classes: dict | None = None,
                pathset_cache: dict | None = None,
                extra_scenarios: list[tuple[str, dict]] | None = None,
                max_paths_per_od: int | None = None,
                n_random_scenarios: int | None = None,
                common_lines: str | None = None) -> Exp2Setup:
    from .exp1 import build_setup as exp1_setup

    a = b.assumptions
    pa = a["path_assignment"]
    cons = constraints or load_constraints()
    w = weights or CostWeights.from_config(load_cost_weights())
    wk = dict(random_arrival_threshold_min=float(a["waiting"]["random_arrival_threshold_min"]),
              schedule_coefficient=float(a["waiting"]["schedule_coefficient"]))

    # reuse Experiment 1's service construction: it is the same supply model and
    # it asserts that baseline vehicle-hours reproduce the GTFS schedule exactly
    e1 = exp1_setup(b, constraints=cons, weights=w)
    services = e1.model.services
    baseline_plan = e1.baseline_plan
    base_hw = {k: v.baseline_headway_min for k, v in services.items()}

    # The evaluator's leg pricing is the single most consequential choice in
    # this setup -- it is the difference between Model A and Model B -- and it
    # used to be decided silently by a config default that four call sites
    # never overrode. A run could therefore be launched with
    # --common-lines same_route, log "waiting model: same_route" from the
    # harness, and score every plan under Model A anyway. It is now decided
    # once, here, and stated.
    cl = str(common_lines if common_lines is not None
             else pa.get("common_lines", "pattern"))
    if common_lines is None:
        log.warning(
            "evaluator pricing: common_lines=%s from the CONFIG DEFAULT"
            " -- the caller did not specify. If this run is meant to be"
            " Model B, it is not.", cl)
    else:
        log.info("evaluator pricing: common_lines=%s (explicit)", cl)

    periods_cfg = service_periods(a)
    periods = {n: ServicePeriod(n, s, e) for n, (s, e) in periods_cfg.items()}
    modelled = periods_to_model or list(periods)

    shares = a["demand_proxy"]["period_shares"]
    unserved_w = float(load_cost_weights()["unserved"])
    pathsets: dict[str, PathSet] = {}
    evaluators: dict[str, PathSetEvaluator] = {}
    for per in modelled:
        # path sets depend only on the network, zones, OD and baseline headways,
        # none of which vary between model configurations — so they are built
        # once and reused across an ablation.
        if pathset_cache is not None and per in pathset_cache:
            ps = pathset_cache[per]
        else:
            share = float(shares[per])
            od_p = ODTable(od.origin, od.dest, od.flow * share, od.source, od.notes)
            ps = build_pathset(rn, zs, od_p, per, base_hw, w, wk,
                               max_rounds=int(pa["max_rounds"]),
                               max_paths_per_od=int(max_paths_per_od
                                                    or pa["max_paths_per_od"]),
                               n_random_scenarios=int(
                                   pa["n_random_scenarios"]
                                   if n_random_scenarios is None
                                   else n_random_scenarios),
                               seed=seed,
                               extra_scenarios=extra_scenarios,
                               common_lines=cl)
            if pathset_cache is not None:
                pathset_cache[per] = ps
        pathsets[per] = ps
        evaluators[per] = PathSetEvaluator(
            ps, w, wk, unserved_w,
            retention_full_min=float(pa["cost_retention_full_min"]),
            retention_zero_min=float(pa["cost_retention_zero_min"]),
            retention_floor=float(pa["cost_retention_floor"]))
        log.info("period %-8s: %d paths, %d OD pairs", per, ps.n_paths, ps.n_od)

    # crowding priced at each route-period's peak load point, with the load
    # factor derived from the baseline assignment (see cota_opt.crowding)
    crowd_models: dict[str, Any] = {}
    load_profiles: dict[str, Any] = {}
    if with_crowding:
        from .crowding import CrowdingModel, build_load_profile
        cap = float(a["crowding"]["bus_capacity"])
        pen = float(a["crowding"]["crowding_penalty_per_excess_load"])
        ride_frac = float(a["passenger"]["avg_ride_fraction"])
        for per, ev in evaluators.items():
            sub = np.array([base_hw[k] for k in ev.ps.rp_keys])
            pf = ev.path_flows(sub)
            lp = build_load_profile(ev.ps, rn, pf)
            load_profiles[per] = lp
            ivt = np.array([services[k].runtime_min * ride_frac
                            for k in ev.ps.rp_keys])
            trips = np.array([services[k].n_directions
                              * periods[k[1]].duration_min / base_hw[k]
                              for k in ev.ps.rp_keys])
            crowd_models[per] = CrowdingModel(lp, cap, pen, trips, ivt)

    locked = set()
    if lock_classes and route_classes:
        from .routeclass import locked_keys
        locked = locked_keys(route_classes, services, lock_classes)

    model = PathBasedModel(services, periods, e1.model.demand, w, a, evaluators,
                           e1.model.connections, crowding=crowd_models,
                           locked=locked)
    fit = model.evaluate(baseline_plan)

    gtfs_vh = float(e1.checks["gtfs_scheduled_revenue_veh_hours"])
    checks = {
        "gtfs_scheduled_revenue_veh_hours": gtfs_vh,
        "model_baseline_revenue_veh_hours": fit.revenue_veh_hours,
        "vh_relative_error": abs(fit.revenue_veh_hours - gtfs_vh) / gtfs_vh,
        "n_route_periods": len(services),
        "periods_modelled": modelled,
        "od_pairs": len(od),
        "od_total_trips": od.total(),
        "od_source": od.source,
        "baseline_generalized_cost": fit.generalized_cost,
        "baseline_unserved_demand": fit.unserved_demand,
        "baseline_served_demand": fit.served_demand,
        "baseline_gc_per_served_trip": fit.gc_per_served_trip,
        "total_paths": sum(p.n_paths for p in pathsets.values()),
    }
    if checks["vh_relative_error"] > 1e-9:
        raise AssertionError("baseline vehicle-hours do not reproduce the schedule")

    res = cons["resource"]
    vh_budget = (fit.revenue_veh_hours
                 if res["weekday_revenue_vehicle_hours"] == "baseline"
                 else float(res["weekday_revenue_vehicle_hours"]))
    peak_budget = (dict(fit.peak_by_period)
                   if res["peak_fleet_by_period"] == "baseline"
                   else {k: float(v) for k, v in res["peak_fleet_by_period"].items()})
    budget = ResourceBudget(vh_budget, peak_budget,
                            tolerance=float(res.get("budget_tolerance", 0.0)))
    svc = cons["service"]
    ladders = build_ladders(model, svc["headway_ladder_min"],
                            float(svc["policy_max_headway_min"]),
                            float(svc["policy_min_headway_min"]))
    # a locked route-period has exactly one option: today's headway
    for k in locked:
        ladders[k] = [baseline_plan.headways[k]]
    checks["locked_route_periods"] = len(locked)
    checks["locked_routes"] = sorted({k[0] for k in locked})
    checks["with_crowding"] = bool(with_crowding)
    checks["common_lines"] = cl
    checks["common_lines_source"] = ("explicit" if common_lines is not None
                                     else "config default")
    if load_profiles:
        checks["peak_load_factor_median"] = float(np.median(np.concatenate(
            [lp.peak_load_factor[lp.boardings > 0] for lp in load_profiles.values()])))
    return Exp2Setup(model, baseline_plan, budget, ladders, pathsets, checks)


def plan_diff(setup: Exp2Setup, plan: FrequencyPlan) -> pd.DataFrame:
    m = setup.model
    rows = []
    for key, svc in m.services.items():
        hb = setup.baseline_plan.headways[key]
        ho = plan.headways[key]
        rows.append({
            "route_id": key[0], "period": key[1],
            "baseline_headway_min": hb, "optimized_headway_min": ho,
            "headway_change_min": ho - hb,
            "baseline_veh_hours": m.revenue_veh_hours(svc, hb),
            "optimized_veh_hours": m.revenue_veh_hours(svc, ho),
            "veh_hours_change": m.revenue_veh_hours(svc, ho) - m.revenue_veh_hours(svc, hb),
            "runtime_min": svc.runtime_min,
        })
    df = pd.DataFrame(rows)
    df["direction"] = np.where(df["headway_change_min"] < -0.01, "more service",
                      np.where(df["headway_change_min"] > 0.01, "less service", "unchanged"))
    return df.sort_values("veh_hours_change")
