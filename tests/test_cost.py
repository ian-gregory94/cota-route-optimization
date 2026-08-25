"""Arithmetic contract for the generalized passenger cost API."""
import pytest

from cota_opt.cost import (CostWeights, TripCostComponents, crowding_excess_min,
                           demand_retention, expected_wait_min, unserved_cost)


def test_expected_wait_random_arrival_regime():
    # below the threshold, E[wait] = h/2 exactly
    assert expected_wait_min(10, 12, 0.25) == pytest.approx(5.0)
    assert expected_wait_min(12, 12, 0.25) == pytest.approx(6.0)


def test_expected_wait_schedule_regime():
    # 12/2 + 0.25*(60-12) = 6 + 12 = 18
    assert expected_wait_min(60, 12, 0.25) == pytest.approx(18.0)
    # monotone increasing and continuous at the threshold
    assert expected_wait_min(12.001, 12, 0.25) > expected_wait_min(12, 12, 0.25)


def test_expected_wait_rejects_nonpositive():
    with pytest.raises(ValueError):
        expected_wait_min(0)


def test_generalized_cost_is_exact_weighted_sum():
    w = CostWeights(walking=2.0, waiting=2.0, in_vehicle=1.0,
                    transfer_wait=2.0, transfer_penalty=10.0, crowding=1.0,
                    reliability=0.0)
    c = TripCostComponents(walk_min=5, wait_min=6, in_vehicle_min=20,
                           transfer_wait_min=4, n_transfers=1, crowding_excess=3)
    # 2*5 + 2*6 + 1*20 + 2*4 + 10*1 + 1*3 = 10+12+20+8+10+3 = 63
    assert c.generalized_cost(w) == pytest.approx(63.0)


def test_demand_retention_endpoints_and_midpoint():
    assert demand_retention(5, 15, 120, 0.25) == 1.0
    assert demand_retention(15, 15, 120, 0.25) == 1.0
    assert demand_retention(120, 15, 120, 0.25) == pytest.approx(0.25)
    assert demand_retention(500, 15, 120, 0.25) == pytest.approx(0.25)
    # halfway (h=67.5): 1 - 0.5*0.75 = 0.625
    assert demand_retention(67.5, 15, 120, 0.25) == pytest.approx(0.625)


def test_demand_retention_is_monotone_decreasing():
    vals = [demand_retention(h) for h in (5, 15, 30, 60, 90, 120)]
    assert all(a >= b for a, b in zip(vals, vals[1:]))


def test_crowding_is_zero_below_capacity_then_linear():
    assert crowding_excess_min(59, 60, 20) == 0.0
    assert crowding_excess_min(60, 60, 20) == 0.0
    assert crowding_excess_min(90, 60, 20, 1.0) == pytest.approx(10.0)
    assert crowding_excess_min(120, 60, 20, 1.0) == pytest.approx(20.0)


def test_unserved_cost_scales_with_multiplier():
    w = CostWeights(unserved=60.0)
    assert unserved_cost(10, w, 1.0) == pytest.approx(600.0)
    assert unserved_cost(10, w, 2.0) == pytest.approx(1200.0)


def test_cost_weights_from_config_ignores_unknown_keys():
    w = CostWeights.from_config({"waiting": 3.0, "nonsense": 1.0})
    assert w.waiting == 3.0 and w.in_vehicle == 1.0
