"""Frequency model and optimizer tests, including an analytic benchmark.

The key validation is the Mohring square-root rule: minimizing
``Σ D_i · w · h_i/2`` subject to ``Σ c_i/h_i = B`` (equal per-route cost
coefficients) yields ``h_i ∝ 1/sqrt(D_i)``. The solver must reproduce it.
"""
import math

import pytest

from cota_opt.cost import CostWeights
from cota_opt.frequency import (FrequencyModel, FrequencyPlan, PassengerDemand,
                                ResourceBudget, RouteService, ServicePeriod,
                                integer_fleet, optimize_frequencies, pareto_filter)

LADDER = [5, 6, 7.5, 10, 12, 15, 20, 24, 30, 40, 45, 60]

# Assumptions that switch off retention loss, crowding and transfers so the
# analytic optimum is exactly the Mohring result.
CLEAN = {
    "operations": {"layover_ratio": 0.0},
    "waiting": {"random_arrival_threshold_min": 1e9, "schedule_coefficient": 0.25,
                "retention_full_min": 1e9, "retention_zero_min": 1e9 + 1,
                "retention_floor": 1.0},
    "crowding": {"bus_capacity": 1e12, "crowding_penalty_per_excess_load": 0.0},
    "passenger": {"avg_ride_fraction": 0.0, "access_walk_min": 0.0,
                  "transfer_rate": 0.0},
}


def _model(demands: dict[str, float], runtime: float = 30.0,
           assumptions: dict | None = None) -> FrequencyModel:
    periods = {"all": ServicePeriod("all", 6, 18)}
    services = {(r, "all"): RouteService(r, "all", runtime, 2, 30.0, 24)
                for r in demands}
    demand = PassengerDemand({(r, "all"): d for r, d in demands.items()})
    return FrequencyModel(services, periods, demand,
                          CostWeights(waiting=2.0, in_vehicle=1.0, walking=2.0,
                                      unserved=60.0),
                          assumptions or CLEAN)


def test_resource_accounting_is_self_consistent():
    m = _model({"R1": 1000.0}, runtime=30.0)
    svc = m.services[("R1", "all")]
    # 12h period, 2 directions, 30-min headway → 2*720/30 = 48 trips
    assert m.trips(svc, 30.0) == pytest.approx(48.0)
    # 48 trips * 30 min / 60 = 24 revenue vehicle-hours
    assert m.revenue_veh_hours(svc, 30.0) == pytest.approx(24.0)
    # cycle = 2*30*(1+0) = 60 min; at 30-min headway → 2 buses
    assert m.peak_vehicles(svc, 30.0) == pytest.approx(2.0)


def test_halving_headway_doubles_resources():
    m = _model({"R1": 1000.0})
    svc = m.services[("R1", "all")]
    assert m.revenue_veh_hours(svc, 15.0) == pytest.approx(
        2 * m.revenue_veh_hours(svc, 30.0))
    assert m.peak_vehicles(svc, 15.0) == pytest.approx(
        2 * m.peak_vehicles(svc, 30.0))


def test_square_root_rule_two_routes():
    """Route B has 4x the demand of A → its headway should be ~half A's."""
    m = _model({"A": 1000.0, "B": 4000.0})
    base = FrequencyPlan({k: 20.0 for k in m.services})
    b = m.evaluate(base)
    budget = ResourceBudget(b.revenue_veh_hours, dict(b.peak_by_period),
                            tolerance=0.0)
    res = optimize_frequencies(m, budget, LADDER, unserved_multiplier=1.0,
                               local_search_iterations=4000, seed=1)
    hA = res.plan.headways[("A", "all")]
    hB = res.plan.headways[("B", "all")]
    assert hA > hB, "the higher-demand route must get the shorter headway"
    ratio = hA / hB
    assert ratio == pytest.approx(2.0, rel=0.30), f"h_A/h_B = {ratio}, expected ~2"
    assert res.fitness.revenue_veh_hours <= budget.vh_cap() + 1e-9


def test_square_root_rule_three_routes_ordering():
    m = _model({"A": 500.0, "B": 2000.0, "C": 8000.0})
    base = FrequencyPlan({k: 20.0 for k in m.services})
    b = m.evaluate(base)
    budget = ResourceBudget(b.revenue_veh_hours, dict(b.peak_by_period), tolerance=0.0)
    res = optimize_frequencies(m, budget, LADDER, local_search_iterations=6000, seed=2)
    h = {r: res.plan.headways[(r, "all")] for r in ("A", "B", "C")}
    assert h["A"] >= h["B"] >= h["C"]
    # analytic optimum ratios: 1/sqrt(D) normalized
    exp = {r: 1 / math.sqrt(d) for r, d in (("A", 500.), ("B", 2000.), ("C", 8000.))}
    k = h["C"] / exp["C"]
    for r in ("A", "B"):
        assert h[r] == pytest.approx(k * exp[r], rel=0.35)


def test_optimizer_never_exceeds_the_budget():
    m = _model({"A": 1000.0, "B": 2000.0, "C": 300.0})
    base = FrequencyPlan({k: 30.0 for k in m.services})
    b = m.evaluate(base)
    budget = ResourceBudget(b.revenue_veh_hours, dict(b.peak_by_period), tolerance=0.0)
    for mult in (0.25, 1.0, 8.0):
        res = optimize_frequencies(m, budget, LADDER, unserved_multiplier=mult,
                                   local_search_iterations=500, seed=3)
        assert res.fitness.revenue_veh_hours <= budget.vh_cap() + 1e-9
        for p, v in res.fitness.peak_by_period.items():
            assert v <= budget.peak_cap(p) + 1e-9


def test_optimizer_is_deterministic_for_a_fixed_seed():
    m = _model({"A": 1000.0, "B": 2500.0, "C": 700.0})
    base = FrequencyPlan({k: 30.0 for k in m.services})
    b = m.evaluate(base)
    budget = ResourceBudget(b.revenue_veh_hours, dict(b.peak_by_period), tolerance=0.0)
    r1 = optimize_frequencies(m, budget, LADDER, local_search_iterations=800, seed=42)
    r2 = optimize_frequencies(m, budget, LADDER, local_search_iterations=800, seed=42)
    assert r1.plan.headways == r2.plan.headways
    assert r1.fitness.generalized_cost == pytest.approx(r2.fitness.generalized_cost)


def test_optimizer_beats_the_uniform_baseline():
    m = _model({"A": 200.0, "B": 6000.0})
    base = FrequencyPlan({k: 20.0 for k in m.services})
    b = m.evaluate(base)
    budget = ResourceBudget(b.revenue_veh_hours, dict(b.peak_by_period), tolerance=0.0)
    res = optimize_frequencies(m, budget, LADDER, local_search_iterations=3000, seed=7)
    assert res.fitness.generalized_cost < b.generalized_cost


def test_retention_creates_an_unserved_demand_tradeoff():
    """With retention on, a tighter unserved penalty must not increase unserved."""
    a = {**CLEAN, "waiting": {"random_arrival_threshold_min": 12.0,
                              "schedule_coefficient": 0.25,
                              "retention_full_min": 15.0,
                              "retention_zero_min": 120.0,
                              "retention_floor": 0.25}}
    m = _model({"A": 1000.0, "B": 4000.0, "C": 200.0}, assumptions=a)
    base = FrequencyPlan({k: 30.0 for k in m.services})
    b = m.evaluate(base)
    assert b.unserved_demand > 0
    budget = ResourceBudget(b.revenue_veh_hours, dict(b.peak_by_period), tolerance=0.0)
    lo = optimize_frequencies(m, budget, LADDER, unserved_multiplier=0.25,
                              local_search_iterations=2000, seed=5)
    hi = optimize_frequencies(m, budget, LADDER, unserved_multiplier=16.0,
                              local_search_iterations=2000, seed=5)
    assert hi.fitness.unserved_demand <= lo.fitness.unserved_demand + 1e-6


def test_pareto_filter_removes_dominated_points():
    m = _model({"A": 1000.0})
    base = FrequencyPlan({("A", "all"): 20.0})
    b = m.evaluate(base)
    budget = ResourceBudget(b.revenue_veh_hours, dict(b.peak_by_period))
    from cota_opt.frequency import FitnessVector, OptimizationResult
    pts = [
        OptimizationResult(base, FitnessVector(100.0, 10.0, 1, 1), "good"),
        OptimizationResult(base, FitnessVector(200.0, 20.0, 1, 1), "dominated"),
        OptimizationResult(base, FitnessVector(90.0, 30.0, 1, 1), "other-end"),
    ]
    keep = {r.label for r in pareto_filter(pts)}
    assert "dominated" not in keep
    assert keep == {"good", "other-end"}


def test_minimum_service_infeasible_budget_raises():
    m = _model({"A": 1000.0})
    tiny = ResourceBudget(0.001, {"all": 0.001}, tolerance=0.0)
    with pytest.raises(ValueError):
        optimize_frequencies(m, tiny, LADDER)


def test_integer_fleet_rounds_up_per_route():
    m = _model({"A": 1000.0, "B": 1000.0}, runtime=30.0)
    plan = FrequencyPlan({("A", "all"): 25.0, ("B", "all"): 25.0})
    # cycle = 60 min; 60/25 = 2.4 → ceil 3 per route → 6 total
    assert integer_fleet(m, plan)["all"] == 6


def test_transfer_coupling_rewards_frequent_connections():
    """Improving a connecting route's headway must lower the other route's cost."""
    a = dict(CLEAN)
    a["passenger"] = {"avg_ride_fraction": 0.0, "access_walk_min": 0.0,
                      "transfer_rate": 0.5}
    m = _model({"A": 1000.0, "B": 1000.0}, assumptions=a)
    m.connections = {"A": {"B": 1.0}, "B": {"A": 1.0}}
    slow = m.evaluate(FrequencyPlan({("A", "all"): 20.0, ("B", "all"): 60.0}))
    fast = m.evaluate(FrequencyPlan({("A", "all"): 20.0, ("B", "all"): 10.0}))
    assert fast.generalized_cost < slow.generalized_cost


# --- the ladder snap that silently discarded the incumbent -------------------
#
# `optimize_frequencies` accepts an `initial` plan only if that plan, once
# snapped to the ladder, still fits the envelope. Nearest-rung snapping moves
# roughly half the route-periods to a SHORTER headway, which costs
# vehicle-hours, so a plan fitted to the envelope in continuous space lands
# back outside it and the optimizer falls back to the greedy build the caller
# disabled. In Stage A that fallback fired on 99 of 156 solves, and on 46 of 46
# multi-edit states, while never firing on the unedited control -- an optimizer
# chosen by the treatment.

def _ladders(m, ladder=LADDER):
    return {k: sorted(float(h) for h in ladder) for k in m.keys}


def test_snap_to_ladder_returns_ladder_values():
    from cota_opt.frequency import snap_to_ladder
    m = _model({"R1": 1000.0, "R2": 500.0})
    lads = _ladders(m)
    snapped = snap_to_ladder(lads, FrequencyPlan({k: 11.3 for k in m.keys}))
    for k in m.keys:
        assert snapped.headways[k] in lads[k]
        assert snapped.headways[k] == 12          # nearest rung to 11.3


def test_snapping_can_push_a_fitting_plan_out_of_the_envelope():
    """The defect itself, in miniature: fits before the snap, not after."""
    from cota_opt.frequency import _feasible, snap_to_ladder
    m = _model({"R1": 1000.0, "R2": 1000.0})
    lads = _ladders(m)
    plan = FrequencyPlan({k: 11.0 for k in m.keys})          # between rungs
    budget = ResourceBudget(m.evaluate(plan).revenue_veh_hours, {})
    assert _feasible(m, m.evaluate(plan), budget)             # fits as given
    snapped = snap_to_ladder(lads, plan)                      # 11.0 -> 10
    assert not _feasible(m, m.evaluate(snapped), budget)      # no longer fits


def test_repair_returns_a_feasible_on_ladder_plan():
    from cota_opt.frequency import _feasible, repair_to_ladder
    m = _model({"R1": 1000.0, "R2": 1000.0})
    lads = _ladders(m)
    plan = FrequencyPlan({k: 11.0 for k in m.keys})
    budget = ResourceBudget(m.evaluate(plan).revenue_veh_hours, {})
    fixed, audit = repair_to_ladder(m, budget, lads, plan)
    assert fixed is not None
    assert audit["snapped_feasible"] is False and audit["steps"] >= 1
    for k in m.keys:
        assert fixed.headways[k] in lads[k]
    assert _feasible(m, m.evaluate(fixed), budget)


def test_repair_is_a_no_op_when_the_snapped_plan_already_fits():
    from cota_opt.frequency import repair_to_ladder
    m = _model({"R1": 1000.0, "R2": 1000.0})
    lads = _ladders(m)
    plan = FrequencyPlan({k: 12.0 for k in m.keys})           # already a rung
    budget = ResourceBudget(m.evaluate(plan).revenue_veh_hours, {})
    fixed, audit = repair_to_ladder(m, budget, lads, plan)
    assert audit["snapped_feasible"] is True and audit["steps"] == 0
    assert fixed is not None
    assert all(fixed.headways[k] == 12.0 for k in m.keys)


def test_repaired_incumbent_is_actually_taken_as_a_start():
    """With the repair the optimizer uses the incumbent branch, not greedy."""
    from cota_opt.frequency import repair_to_ladder
    m = _model({"R1": 1000.0, "R2": 1000.0})
    lads = _ladders(m)
    plan = FrequencyPlan({k: 11.0 for k in m.keys})
    budget = ResourceBudget(m.evaluate(plan).revenue_veh_hours, {})
    fixed, _ = repair_to_ladder(m, budget, lads, plan)
    r = optimize_frequencies(m, budget, ladder=[], ladders=lads, initial=fixed,
                             local_search_iterations=200, n_restarts=0,
                             seed=1, greedy_start=False)
    assert r.meta["n_starts"] == 1          # the incumbent, not a greedy fallback
