"""Synthetic passenger assignment on a network where the answer is obvious.

Network geometry (all cases use subsets of this):

    Route A:  A1 -- A2 -- A3 -- A4     (10 min per segment)
    Route B:  A1 -- B1 -- A4           (12 min per segment, fewer stops)
    Route C:  A2 -- C1                 (feeder)
    Walk:     A3 <-> C1 (4 min)

Every expected value below is computed by hand in the test.
"""
import pytest

from cota_opt.assignment import RouteSpec, SmallNetwork, WalkLink, assign
from cota_opt.cost import CostWeights, expected_wait_min

W = CostWeights(walking=2.0, waiting=2.0, in_vehicle=1.0, transfer_wait=2.0,
                transfer_penalty=10.0)
WK = dict(random_arrival_threshold_min=12.0, schedule_coefficient=0.25)


def test_direct_route_cost_is_wait_plus_in_vehicle():
    net = SmallNetwork([RouteSpec("A", ["A1", "A2", "A3", "A4"], [10, 10, 10], 10.0)])
    r = assign(net, "A1", "A4", W, WK)
    # wait = 10/2 = 5 → weighted 2*5 = 10; ivt = 30 → 30. Total 40.
    assert r.reachable
    assert r.wait_min == pytest.approx(5.0)
    assert r.in_vehicle_min == pytest.approx(30.0)
    assert r.n_transfers == 0
    assert r.generalized_cost == pytest.approx(40.0)
    assert r.routes_used == ["A"]


def test_faster_route_wins_even_with_longer_headway():
    """B is 24 min in-vehicle at 20-min headway; A is 30 min at 10-min headway."""
    net = SmallNetwork([
        RouteSpec("A", ["A1", "A2", "A3", "A4"], [10, 10, 10], 10.0),
        RouteSpec("B", ["A1", "B1", "A4"], [12, 12], 20.0),
    ])
    # A: 2*5 + 30 = 40.  B: wait = 6 + 0.25*8 = 8 → 2*8 + 24 = 40.  Tie at h=20.
    r = assign(net, "A1", "A4", W, WK)
    assert r.generalized_cost == pytest.approx(40.0)

    # Tighten B's headway to 12 → wait 6 → 2*6 + 24 = 36 < 40. B must win.
    net.routes[1] = RouteSpec("B", ["A1", "B1", "A4"], [12, 12], 12.0)
    r2 = assign(net, "A1", "A4", W, WK)
    assert r2.generalized_cost == pytest.approx(36.0)
    assert r2.routes_used == ["B"]


def test_wait_time_difference_changes_the_chosen_route():
    """Same in-vehicle time both ways; the more frequent route must win."""
    net = SmallNetwork([
        RouteSpec("A", ["A1", "A2", "A3", "A4"], [10, 10, 10], 30.0),
        RouteSpec("B", ["A1", "B1", "A4"], [15, 15], 10.0),
    ])
    # A: wait = 6 + 0.25*18 = 10.5 → 21 + 30 = 51.  B: 2*5 + 30 = 40.
    r = assign(net, "A1", "A4", W, WK)
    assert r.routes_used == ["B"]
    assert r.generalized_cost == pytest.approx(40.0)


def test_one_transfer_route_pays_the_transfer_penalty():
    net = SmallNetwork([
        RouteSpec("A", ["A1", "A2", "A3", "A4"], [10, 10, 10], 10.0),
        RouteSpec("C", ["A2", "C1"], [5], 20.0),
    ])
    r = assign(net, "A1", "C1", W, WK)
    # board A: 2*5=10; ride A1→A2: 10; transfer to C: wait=6+0.25*8=8
    #   → 2*8 = 16, plus penalty 10; ride A2→C1: 5.  Total = 10+10+16+10+5 = 51
    assert r.reachable
    assert r.n_transfers == 1
    assert r.routes_used == ["A", "C"]
    assert r.generalized_cost == pytest.approx(51.0)
    assert r.in_vehicle_min == pytest.approx(15.0)


def test_faster_path_with_longer_walk_is_chosen_when_it_is_cheaper():
    """Walking A3→C1 (4 min) beats transferring to route C."""
    net = SmallNetwork(
        [RouteSpec("A", ["A1", "A2", "A3", "A4"], [10, 10, 10], 10.0),
         RouteSpec("C", ["A2", "C1"], [5], 60.0)],
        [WalkLink("A3", "C1", 4.0)])
    r = assign(net, "A1", "C1", W, WK)
    # via walk: board A 10 + ride A1→A3 20 + walk 2*4=8 → 38
    # via C:    10 + 10 + (wait 6+0.25*48=18 → 36) + 10 + 5 = 71
    assert r.generalized_cost == pytest.approx(38.0)
    assert r.walk_min == pytest.approx(4.0)
    assert r.n_transfers == 0


def test_walking_loses_when_it_is_long_enough():
    net = SmallNetwork(
        [RouteSpec("A", ["A1", "A2", "A3", "A4"], [10, 10, 10], 10.0),
         RouteSpec("C", ["A2", "C1"], [5], 20.0)],
        [WalkLink("A3", "C1", 20.0)])
    r = assign(net, "A1", "C1", W, WK)
    # walk path: 10 + 20 + 2*20 = 70 ; transfer path = 51 (previous test)
    assert r.generalized_cost == pytest.approx(51.0)
    assert r.routes_used == ["A", "C"]


def test_unserved_od_is_unreachable():
    net = SmallNetwork([RouteSpec("A", ["A1", "A2", "A3", "A4"], [10, 10, 10], 10.0)])
    r = assign(net, "A1", "ZZZ", W, WK)
    assert not r.reachable
    assert r.generalized_cost == float("inf")


def test_route_direction_is_respected():
    """Route A is one-way in the model: A4 → A1 must not be free."""
    net = SmallNetwork([RouteSpec("A", ["A1", "A2", "A3", "A4"], [10, 10, 10], 10.0)])
    assert not assign(net, "A4", "A1", W, WK).reachable


def test_segment_length_validation():
    with pytest.raises(ValueError):
        RouteSpec("bad", ["A", "B", "C"], [5], 10.0)


def test_halving_headway_reduces_cost_by_exactly_the_wait_delta():
    net10 = SmallNetwork([RouteSpec("A", ["A1", "A2"], [10], 10.0)])
    net5 = SmallNetwork([RouteSpec("A", ["A1", "A2"], [10], 5.0)])
    c10 = assign(net10, "A1", "A2", W, WK).generalized_cost
    c5 = assign(net5, "A1", "A2", W, WK).generalized_cost
    delta = W.waiting * (expected_wait_min(10, **WK) - expected_wait_min(5, **WK))
    assert c10 - c5 == pytest.approx(delta)
