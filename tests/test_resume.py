"""A solve killed mid-flight must resume to exactly the same answer.

This sandbox reaps long-running processes, and a full-effort solve is twenty
restarts over forty minutes, so "resumable" is not a convenience here -- without
it a kill at minute thirty-nine costs the whole cell. The property under test is
equality, not similarity: an interrupted-and-resumed solve returns bit-identical
results to one that ran straight through, because each restart draws from its
own generator seeded on (seed, restart index).
"""
import numpy as np
import pytest

from cota_opt.frequency import (FitnessVector, FrequencyModel, FrequencyPlan,
                                PassengerDemand, ResourceBudget, RouteService,
                                ServicePeriod, build_ladders,
                                optimize_frequencies)
from cota_opt.cost import CostWeights


def _model(n_routes: int = 12):
    periods = {"am": ServicePeriod("am", 6.0, 9.0),
               "md": ServicePeriod("md", 9.0, 15.0)}
    services, demand = {}, {}
    rng = np.random.default_rng(0)
    for i in range(n_routes):
        rid = f"R{i:02d}"
        for per in periods:
            services[(rid, per)] = RouteService(
                rid, per, runtime_min=20.0 + 5 * (i % 4), n_directions=2,
                baseline_headway_min=15.0 + 5 * (i % 3), baseline_trips=40)
            demand[(rid, per)] = float(rng.integers(200, 2000))
    w = CostWeights(walking=2.0, waiting=2.0, in_vehicle=1.0,
                    transfer_wait=2.0, transfer_penalty=10.0)
    a = {"operations": {"layover_ratio": 0.15,
                        "min_terminal_layover_min": 3},
         "waiting": {"random_arrival_threshold_min": 12.0,
                     "schedule_coefficient": 0.25,
                     "retention_full_min": 15.0,
                     "retention_zero_min": 120.0,
                     "retention_floor": 0.25},
         "crowding": {"bus_capacity": 60.0,
                      "crowding_penalty_per_excess_load": 1.0},
         "passenger": {"avg_ride_fraction": 0.35, "access_walk_min": 5.0,
                       "transfer_rate": 0.20}}
    m = FrequencyModel(services, periods,
                       PassengerDemand(demand, "test", ""), w, a, {})
    plan = FrequencyPlan({k: v.baseline_headway_min for k, v in services.items()})
    fit = m.evaluate(plan)
    budget = ResourceBudget(fit.revenue_veh_hours, dict(fit.peak_by_period),
                            tolerance=0.0)
    ladders = build_ladders(m, [5, 10, 15, 20, 30, 45, 60], 60.0, 5.0)
    return m, budget, plan, ladders


def _solve(m, budget, plan, ladders, n_restarts, progress=None, resume=None):
    return optimize_frequencies(
        m, budget, ladder=[], unserved_multiplier=2.0,
        local_search_iterations=2000, seed=11, ladders=ladders, initial=plan,
        n_restarts=n_restarts, candidate_width=8, greedy_start=False,
        progress=progress, resume=resume)


@pytest.fixture
def setup():
    return _model()


def test_resuming_midway_returns_the_same_plan_as_running_straight_through(setup):
    m, budget, plan, ladders = setup
    whole = _solve(m, budget, plan, ladders, n_restarts=8)

    saved = {}

    def record(k, idx, o, moves):
        saved[k] = {"next_restart": k, "best_idx": list(map(int, idx)),
                    "best_obj": float(o), "moves": int(moves)}

    _solve(m, budget, plan, ladders, n_restarts=8, progress=record)
    assert set(saved) >= {0, 4, 8}

    # rejoin as if the process had been killed after restart 4
    resumed = _solve(m, budget, plan, ladders, n_restarts=8, resume=saved[4])
    assert resumed.plan.headways == whole.plan.headways
    assert resumed.fitness.generalized_cost == pytest.approx(
        whole.fitness.generalized_cost, rel=1e-12)
    assert resumed.fitness.unserved_demand == pytest.approx(
        whole.fitness.unserved_demand, rel=1e-12)


def test_resuming_at_every_restart_point_gives_the_same_answer(setup):
    m, budget, plan, ladders = setup
    whole = _solve(m, budget, plan, ladders, n_restarts=6)
    saved = {}
    _solve(m, budget, plan, ladders, n_restarts=6,
           progress=lambda k, idx, o, mv: saved.__setitem__(
               k, {"next_restart": k, "best_idx": list(map(int, idx)),
                   "best_obj": float(o), "moves": int(mv)}))
    for k in sorted(saved):
        r = _solve(m, budget, plan, ladders, n_restarts=6, resume=saved[k])
        assert r.plan.headways == whole.plan.headways, f"resume at {k} diverged"


def test_progress_is_reported_for_every_restart(setup):
    m, budget, plan, ladders = setup
    seen = []
    _solve(m, budget, plan, ladders, n_restarts=5,
           progress=lambda k, idx, o, mv: seen.append(k))
    # one for the starting point, then one per restart, even when a kick is
    # rejected as infeasible and the restart is skipped
    assert seen == [0, 1, 2, 3, 4, 5]


def test_the_objective_is_recomputed_on_resume_not_trusted(setup):
    """A stored objective from a different model must not survive into a result."""
    m, budget, plan, ladders = setup
    saved = {}
    _solve(m, budget, plan, ladders, n_restarts=4,
           progress=lambda k, idx, o, mv: saved.__setitem__(
               k, {"next_restart": k, "best_idx": list(map(int, idx)),
                   "best_obj": float(o), "moves": int(mv)}))
    poisoned = dict(saved[2])
    poisoned["best_obj"] = -1e18          # a number no plan could achieve
    r = _solve(m, budget, plan, ladders, n_restarts=4, resume=poisoned)
    assert r.fitness.generalized_cost > 0
    # the returned fitness is the model's own evaluation of the returned plan
    assert r.fitness.generalized_cost == pytest.approx(
        m.evaluate(r.plan).generalized_cost, rel=1e-12)


def test_a_resumed_solve_is_never_worse_than_the_state_it_resumed_from(setup):
    m, budget, plan, ladders = setup
    saved = {}
    _solve(m, budget, plan, ladders, n_restarts=6,
           progress=lambda k, idx, o, mv: saved.__setitem__(
               k, {"next_restart": k, "best_idx": list(map(int, idx)),
                   "best_obj": float(o), "moves": int(mv)}))
    for k in sorted(saved):
        r = _solve(m, budget, plan, ladders, n_restarts=6, resume=saved[k])
        obj = r.fitness.scalarized(m.w.unserved, 2.0)
        assert obj <= saved[k]["best_obj"] + 1e-9


def test_each_restart_is_reproducible_on_its_own(setup):
    """Per-restart seeding: restart k must not depend on restarts before it."""
    m, budget, plan, ladders = setup
    saved = {}
    _solve(m, budget, plan, ladders, n_restarts=5,
           progress=lambda k, idx, o, mv: saved.__setitem__(
               k, {"next_restart": k, "best_idx": list(map(int, idx)),
                   "best_obj": float(o), "moves": int(mv)}))
    a = _solve(m, budget, plan, ladders, n_restarts=5, resume=saved[3])
    b = _solve(m, budget, plan, ladders, n_restarts=5, resume=saved[3])
    assert a.plan.headways == b.plan.headways
