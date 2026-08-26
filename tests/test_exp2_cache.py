"""The per-period cache must be a pure speedup, never a change in answer."""
import numpy as np
import pytest

from cota_opt.cost import CostWeights
from cota_opt.exp2 import PathBasedModel
from cota_opt.frequency import PassengerDemand, RouteService, ServicePeriod
from cota_opt.pathset import PathSetEvaluator
from tests.test_pathset import _ps, W, WK


ASSUMPTIONS = {
    "operations": {"layover_ratio": 0.15},
    "waiting": {"random_arrival_threshold_min": 12.0, "schedule_coefficient": 0.25,
                "retention_full_min": 1e9, "retention_zero_min": 1e9 + 1,
                "retention_floor": 1.0},
    "crowding": {"bus_capacity": 60.0, "crowding_penalty_per_excess_load": 1.0},
    "passenger": {"avg_ride_fraction": 0.35, "access_walk_min": 5.0,
                  "transfer_rate": 0.2},
}


def _model():
    """Two periods, each with its own route; keys span both periods."""
    keys = [("R0", "am"), ("R1", "pm")]
    periods = {"am": ServicePeriod("am", 6, 9), "pm": ServicePeriod("pm", 15, 18)}
    services = {("R0", "am"): RouteService("R0", "am", 30.0, 2, 20.0, 18),
                ("R1", "pm"): RouteService("R1", "pm", 30.0, 2, 20.0, 18)}
    evs = {}
    for per, rp in (("am", 0), ("pm", 1)):
        ps = _ps([(0, [(rp, 20.0, 0.0, False)])], [100.0], keys)
        evs[per] = PathSetEvaluator(ps, W, WK, 60.0, retention_full_min=1e9,
                                    retention_zero_min=1e9 + 1,
                                    retention_floor=1.0)
    demand = PassengerDemand({k: 100.0 for k in services})
    return PathBasedModel(services, periods, demand, W, ASSUMPTIONS, evs)


def test_cache_key_covers_only_the_keys_a_period_uses():
    m = _model()
    # each period's path set references exactly one route-period
    assert [len(v) for v in m._cachesel.values()] == [1, 1]


def test_changing_one_period_leaves_the_other_cached():
    m = _model()
    from cota_opt.frequency import FrequencyPlan
    h = m.headway_array(FrequencyPlan({("R0", "am"): 20.0, ("R1", "pm"): 20.0}))
    m.evaluate_array(h)
    before = m.n_period_evals
    h2 = h.copy()
    h2[m.keys.index(("R0", "am"))] = 15.0
    m.evaluate_array(h2)
    # only the touched period may recompute
    assert m.n_period_evals - before == 1
    assert m.n_cache_hits >= 1


def test_cached_and_uncached_evaluations_agree():
    from cota_opt.frequency import FrequencyPlan
    m = _model()
    fresh = _model()
    rng = np.random.default_rng(0)
    for _ in range(12):
        hw = {k: float(rng.choice([10.0, 15.0, 20.0, 30.0, 60.0])) for k in m.keys}
        plan = FrequencyPlan(hw)
        a = m.evaluate(plan)                      # reuses whatever is cached
        fresh._cache = {p: type(v)() for p, v in fresh._cache.items()}
        b = fresh.evaluate(plan)                  # always cold
        assert a.generalized_cost == pytest.approx(b.generalized_cost)
        assert a.unserved_demand == pytest.approx(b.unserved_demand)
        assert a.revenue_veh_hours == pytest.approx(b.revenue_veh_hours)


def test_cache_is_bounded():
    from cota_opt.frequency import FrequencyPlan
    m = _model()
    rng = np.random.default_rng(1)
    for _ in range(60):
        m.evaluate(FrequencyPlan({k: float(rng.uniform(5, 60)) for k in m.keys}))
    assert all(len(v) <= m._cache_max for v in m._cache.values())
