"""One retention definition, shared by the screen and the production evaluator.

The bug this file exists to prevent: two implementations of "unserved" with the
same name and different meanings, one counting only unreachable demand and the
other applying the retention curve, ranking geometry candidates on a concept
the authoritative model does not use.
"""
import numpy as np
import pytest

from cota_opt.cost import CostWeights
from cota_opt.pathset import PathSet, PathSetEvaluator
from cota_opt.retention import Retention, score

R = Retention(full_min=60.0, zero_min=210.0, floor=0.10)


def test_a_cheap_trip_is_fully_retained():
    assert R.keep(np.array([10.0]))[0] == pytest.approx(1.0)
    assert R.keep(np.array([60.0]))[0] == pytest.approx(1.0)


def test_an_impossible_trip_falls_to_the_floor():
    assert R.keep(np.array([210.0]))[0] == pytest.approx(0.10)
    assert R.keep(np.array([1e6]))[0] == pytest.approx(0.10)


def test_the_curve_is_linear_between_the_endpoints():
    mid = R.keep(np.array([135.0]))[0]           # halfway from 60 to 210
    assert mid == pytest.approx(1.0 - 0.5 * 0.9)


def test_unreachable_and_discouraged_are_reported_separately():
    cost = np.array([30.0, np.inf, 210.0])
    flow = np.array([100.0, 50.0, 200.0])
    s = score(cost, flow, R)
    assert s["unreachable_demand"] == pytest.approx(50.0)
    # the 210-minute pair keeps only its floor
    assert s["discouraged_demand"] == pytest.approx(200.0 * 0.9)
    assert s["unserved_demand"] == pytest.approx(50.0 + 180.0)
    assert s["served_demand"] == pytest.approx(100.0 + 20.0)


def test_unserved_is_not_the_same_as_unreachable():
    """The whole point: a fully reachable network can have large unserved demand."""
    cost = np.array([200.0, 200.0])
    flow = np.array([100.0, 100.0])
    s = score(cost, flow, R)
    assert s["unreachable_demand"] == 0.0
    assert s["unserved_demand"] > 100.0


def test_generalized_cost_counts_only_the_travellers_who_go():
    cost = np.array([100.0])
    flow = np.array([100.0])
    s = score(cost, flow, R)
    keep = R.keep(np.array([100.0]))[0]
    assert s["generalized_cost"] == pytest.approx(100.0 * 100.0 * keep)
    assert s["gc_per_served_trip"] == pytest.approx(100.0)


def test_the_evaluator_uses_the_shared_curve():
    """PathSetEvaluator must not carry its own copy of the arithmetic."""
    W = CostWeights(walking=2.0, waiting=2.0, in_vehicle=1.0,
                    transfer_wait=2.0, transfer_penalty=10.0)
    ps = PathSet(period="p", n_od=1,
                 leg_path=np.array([0]), leg_rp=np.array([0]),
                 leg_ivt=np.array([10.0]), leg_walk=np.array([0.0]),
                 leg_is_boarding=np.array([True]),
                 leg_is_transfer=np.array([False]),
                 path_od=np.array([0]), path_offsets=np.array([0, 1]),
                 od_offsets=np.array([0, 1]), od_flow=np.array([1.0]),
                 od_walk_only=np.array([np.inf]), rp_keys=[("A", "p")])
    ev = PathSetEvaluator(ps, W, dict(random_arrival_threshold_min=12.0,
                                      schedule_coefficient=0.25), 200.0,
                          retention_full_min=60.0, retention_zero_min=210.0,
                          retention_floor=0.10)
    probe = np.array([30.0, 135.0, 300.0])
    assert np.allclose(ev.retention(probe), R.keep(probe))
    assert ev.retention_curve == R


def test_from_assumptions_reads_the_config_keys():
    a = {"path_assignment": {"cost_retention_full_min": 45.0,
                             "cost_retention_zero_min": 180.0,
                             "cost_retention_floor": 0.2}}
    r = Retention.from_assumptions(a)
    assert (r.full_min, r.zero_min, r.floor) == (45.0, 180.0, 0.2)


def test_empty_input_does_not_divide_by_zero():
    s = score(np.array([]), np.array([]), R)
    assert s["served_demand"] == 0.0
    assert not np.isfinite(s["gc_per_served_trip"])
