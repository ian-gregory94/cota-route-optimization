"""Transfer nodes, weighted by riders rather than by adjacency.

Two routes crossing at a stop makes it a transfer point on a map. It makes it
a transfer *node* only if somebody changes there. 645 of COTA's stops satisfy
the first and the protection rules should rest on the second, so the audit is
built on the transfer legs in the chosen paths.
"""
import numpy as np
import pandas as pd
import pytest

from cota_opt.cost import CostWeights
from cota_opt.network import PatternSegment, RoutePattern, StopNode, TransitNetwork
from cota_opt.stops import transfer_audit, transfer_summary


def _pattern(pid, route, stops):
    segs = [PatternSegment(route, 0, pid, stops[i], stops[i + 1], i, 60.0)
            for i in range(len(stops) - 1)]
    return RoutePattern(route, 0, pid, list(stops), segs, 20)


@pytest.fixture
def net():
    pats = {"PA": _pattern("PA", "A", ["s1", "hub", "s3"]),
            "PB": _pattern("PB", "B", ["hub", "s4", "s5"]),
            "PC": _pattern("PC", "C", ["s6", "quiet", "s7"])}
    stops = {s: StopNode(s, s, 39.9, -83.0)
             for s in ["s1", "hub", "s3", "s4", "s5", "s6", "quiet", "s7"]}
    return TransitNetwork(stops=stops, patterns=pats, stop_routes={},
                          route_stops={})


class _PS:
    """Two paths: one straight ride, one that transfers at 'hub'."""
    period = "am_peak"
    n_paths = 2
    n_legs = 3
    leg_path = np.array([0, 1, 1])
    leg_rp = np.array([0, 0, 1])
    leg_pattern = np.array([0, 0, 1])       # PA, PA, PB
    leg_board_pos = np.array([0, 0, 0])     # PB boards at position 0 = 'hub'
    leg_alight_pos = np.array([2, 1, 2])
    leg_is_transfer = np.array([False, False, True])
    leg_headway_mult = np.array([1.0, 1.0, 1.0])


class _Ev:
    ps = _PS()
    w = CostWeights(transfer_wait=2.0, transfer_penalty=10.0)
    ride_mask = np.array([True, True, True])
    ride_rp = np.array([0, 0, 1])
    ride_mult = np.array([1.0, 1.0, 1.0])

    def _wait(self, h):
        return h / 2.0

    def path_flows(self, hw):
        return np.array([500.0, 80.0])


PIX = {"PA": 0, "PB": 1, "PC": 2}


def test_only_stops_where_someone_changes_appear(net):
    df = transfer_audit(_Ev(), np.array([10.0, 20.0]), net, PIX)
    assert list(df["stop_id"]) == ["hub"]
    assert "quiet" not in set(df["stop_id"])


def test_the_flow_is_the_flow_of_the_transferring_path(net):
    df = transfer_audit(_Ev(), np.array([10.0, 20.0]), net, PIX)
    assert df.iloc[0]["transfer_flow"] == pytest.approx(80.0)
    assert df.iloc[0]["n_transfer_legs"] == 1


def test_the_cost_is_what_would_have_to_be_paid_again_elsewhere(net):
    # boarding route B at headway 20 -> 10 min wait, weighted 2.0, plus a
    # 10-minute penalty, over 80 daily riders
    df = transfer_audit(_Ev(), np.array([10.0, 20.0]), net, PIX)
    r = df.iloc[0]
    assert r["transfer_wait_min"] == pytest.approx(80 * 10.0 * 2.0)
    assert r["penalty_min"] == pytest.approx(80 * 10.0)
    assert r["generalized_min"] == pytest.approx(r["transfer_wait_min"]
                                                 + r["penalty_min"])


def test_both_sides_of_the_connection_are_recorded(net):
    df = transfer_audit(_Ev(), np.array([10.0, 20.0]), net, PIX)
    assert df.iloc[0]["routes_departing"] == "B"
    assert df.iloc[0]["routes_arriving"] == "A"


def test_a_shorter_headway_lowers_the_cost_of_the_same_connection(net):
    a = transfer_audit(_Ev(), np.array([10.0, 20.0]), net, PIX)
    b = transfer_audit(_Ev(), np.array([10.0, 5.0]), net, PIX)
    assert b.iloc[0]["generalized_min"] < a.iloc[0]["generalized_min"]
    assert b.iloc[0]["transfer_flow"] == pytest.approx(a.iloc[0]["transfer_flow"])


def test_an_empty_path_set_returns_the_right_columns_not_an_error(net):
    class Empty:
        class ps:
            n_paths = 0
            leg_pattern = None
    df = transfer_audit(Empty(), np.zeros(2), net, PIX)
    assert df.empty and "transfer_flow" in df.columns
    assert transfer_summary(df)["n_transfer_nodes_used"] == 0


def test_the_summary_says_how_concentrated_transferring_is():
    df = pd.DataFrame({"stop_id": list("abcd"),
                       "transfer_flow": [100.0, 50.0, 30.0, 20.0],
                       "generalized_min": [1000.0, 500.0, 300.0, 200.0]})
    s = transfer_summary(df, n_geometric=645)
    assert s["nodes_for_half_the_transfers"] == 1
    assert s["nodes_for_ninety_pct"] == 3
    assert s["busiest"] == "a"
    assert s["share_of_geometric_points_used"] == pytest.approx(4 / 645)


def test_geometric_transfer_points_are_reported_as_a_denominator():
    """The gap between 'routes touch here' and 'riders change here' is the point."""
    df = pd.DataFrame({"stop_id": ["a"], "transfer_flow": [10.0],
                       "generalized_min": [100.0]})
    s = transfer_summary(df, n_geometric=645)
    assert s["geometric_transfer_points"] == 645
    assert s["share_of_geometric_points_used"] < 0.01
