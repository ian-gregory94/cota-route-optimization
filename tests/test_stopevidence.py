"""Natural stop-skipping experiments, on a schedule with a known answer.

Route R, direction 0, three patterns over the same corridor X..Y:

    P_all   X a b c Y   every segment 60 s plus 20 s per intermediate stop
    P_semi  X a   c Y
    P_exp   X       Y

Built so the true scheduled penalty is exactly 20 s per extra stop, and the
estimator has to recover it from the running times alone.
"""
import numpy as np
import pandas as pd
import pytest

from cota_opt.network import PatternSegment, RoutePattern, StopNode, TransitNetwork
from cota_opt.stopevidence import (estimate, find_comparisons, validate,
                                   verdict)

BASE_SEC = 60.0          # travel between adjacent points, before stopping
STOP_SEC = 20.0          # the penalty the tests must recover


def _pattern(route, direction, pid, stops, n_trips, hop_sec):
    segs = [PatternSegment(route, direction, pid, stops[i], stops[i + 1], i,
                           hop_sec[i]) for i in range(len(stops) - 1)]
    return RoutePattern(route, direction, pid, list(stops), segs, n_trips)


def _corridor(route="R", direction=0, prefix=""):
    """X-a-b-c-Y with intermediate stops costing STOP_SEC each."""
    pats = {}
    # every hop covers the same ground; a hop that ends at a served stop pays
    # the stop penalty, so total time = 4*BASE + (#intermediate)*STOP
    specs = {
        f"{prefix}P_all": (["X", "a", "b", "c", "Y"], 3),
        f"{prefix}P_semi": (["X", "a", "c", "Y"], 2),
        f"{prefix}P_exp": (["X", "Y"], 0),
    }
    for pid, (stops, n_int) in specs.items():
        n_hops = len(stops) - 1
        total = 4 * BASE_SEC + n_int * STOP_SEC
        hop = [total / n_hops] * n_hops
        pats[pid] = _pattern(route, direction, pid, stops, 10, hop)
    return pats


def _net(patterns):
    coords = {"X": 0, "a": 1, "b": 2, "c": 3, "Y": 4}
    stops = {s: StopNode(s, s, 39.96, -83.0 - 0.01 * i)
             for s, i in coords.items()}
    sr, rs = {}, {}
    for p in patterns.values():
        for s in p.stops:
            sr.setdefault(s, set()).add(p.route_id)
            rs.setdefault(p.route_id, set()).add(s)
    return TransitNetwork(stops=stops, patterns=patterns, stop_routes=sr,
                          route_stops=rs)


def _tstats(patterns):
    rows = []
    for pid, p in patterns.items():
        for t in range(p.n_trips):
            rows.append({"trip_id": f"{pid}_{t}", "route_id": p.route_id,
                         "direction_id": p.direction_id, "pattern_id": pid,
                         "first_dep_sec": 8 * 3600 + t * 600,
                         "runtime_min": sum(s.run_time_sec
                                            for s in p.segments) / 60.0})
    return pd.DataFrame(rows)


@pytest.fixture
def corridor():
    pats = _corridor()
    return _net(pats), _tstats(pats)


# -- finding the comparisons -------------------------------------------------

def test_it_finds_the_pairs_that_differ_only_in_stops_served(corridor):
    net, ts = corridor
    c = find_comparisons(net, ts, min_segment_sec=0.0)
    assert not c.empty
    pairs = set(zip(c["pattern_more"], c["pattern_fewer"]))
    assert ("P_all", "P_exp") in pairs
    assert ("P_all", "P_semi") in pairs
    assert ("P_semi", "P_exp") in pairs


def test_each_pair_is_recorded_once_in_the_informative_direction(corridor):
    net, ts = corridor
    c = find_comparisons(net, ts, min_segment_sec=0.0)
    assert (c["n_stops_more"] > c["n_stops_fewer"]).all()
    assert len(c) == len(set(zip(c["pattern_more"], c["pattern_fewer"])))


def test_the_recovered_penalty_is_the_one_that_was_built_in(corridor):
    net, ts = corridor
    c = find_comparisons(net, ts, min_segment_sec=0.0)
    assert c["seconds_per_extra_stop"].round(6).eq(STOP_SEC).all()
    assert estimate(c).summary["pooled_sec_per_stop"] == pytest.approx(STOP_SEC)


def test_a_pattern_that_adds_stops_of_its_own_is_not_a_clean_comparison():
    """B must skip a subset of A's stops, not visit somewhere A never goes."""
    pats = _corridor()
    pats["P_odd"] = _pattern("R", 0, "P_odd", ["X", "z", "Y"], 5, [90.0, 90.0])
    net, ts = _net(pats), _tstats(pats)
    c = find_comparisons(net, ts, min_segment_sec=0.0)
    assert not ((c["pattern_more"] == "P_all") & (c["pattern_fewer"] == "P_odd")).any()


def test_patterns_of_different_routes_are_never_compared():
    a = _corridor(route="R")
    b = _corridor(route="S", prefix="S_")
    pats = {**a, **b}
    net, ts = _net(pats), _tstats(pats)
    c = find_comparisons(net, ts, min_segment_sec=0.0)
    assert (c["route_id"].isin(["R", "S"])).all()
    for r in c.itertuples():
        assert net.patterns[r.pattern_more].route_id == \
               net.patterns[r.pattern_fewer].route_id


def test_a_short_segment_is_excluded_as_too_noisy(corridor):
    net, ts = corridor
    assert find_comparisons(net, ts, min_segment_sec=1e6).empty


def test_too_few_shared_stops_is_excluded():
    pats = {"P_a": _pattern("R", 0, "P_a", ["X", "a"], 5, [100.0])}
    net, ts = _net(pats), _tstats(pats)
    assert find_comparisons(net, ts, min_shared_stops=2,
                            min_segment_sec=0.0).empty


# -- the estimate ------------------------------------------------------------

def test_negative_observations_are_kept_by_default():
    """A faster pattern that serves MORE stops is real and must not be dropped:
    discarding it biases the penalty upward, which flatters consolidation."""
    pats = _corridor()
    # make the all-stops pattern implausibly quick
    fast = pats["P_all"]
    for i, s in enumerate(fast.segments):
        fast.segments[i] = PatternSegment(s.route_id, s.direction_id,
                                          s.pattern_id, s.from_stop, s.to_stop,
                                          s.seq, 30.0)
    net, ts = _net(pats), _tstats(pats)
    c = find_comparisons(net, ts, min_segment_sec=0.0)
    kept = estimate(c)
    dropped = estimate(c, drop_negative=True)
    assert kept.summary["share_negative"] > 0
    assert kept.summary["negatives_kept"] is True
    assert dropped.summary["pooled_sec_per_stop"] > \
        kept.summary["pooled_sec_per_stop"]


def test_the_estimate_says_what_it_is_not(corridor):
    net, ts = corridor
    s = estimate(find_comparisons(net, ts, min_segment_sec=0.0)).summary
    assert "NOT a passenger dwell estimate" in s["interpretation"]


def test_an_empty_feed_reports_insufficient_rather_than_guessing():
    e = estimate(pd.DataFrame())
    assert e.summary["n_comparisons"] == 0
    label, why = verdict(e.summary, {"n_folds": 0})
    assert label == "insufficient"
    assert "assumed" in why


# -- validation --------------------------------------------------------------

def test_validation_holds_out_by_route_not_by_row():
    """Many routes, each with the same built-in penalty: it must transfer."""
    pats = {}
    for k in range(8):
        pats.update(_corridor(route=f"R{k}", prefix=f"R{k}_"))
    net, ts = _net(pats), _tstats(pats)
    c = find_comparisons(net, ts, min_segment_sec=0.0)
    v = validate(c, n_folds=4)
    assert v["n_folds"] == 4
    assert v["n_routes"] == 8
    assert v["bias_sec"] == pytest.approx(0.0, abs=1e-6)
    label, _ = verdict(estimate(c).summary, v)
    assert label == "usable"


def test_too_few_routes_is_reported_as_unvalidated(corridor):
    net, ts = corridor
    c = find_comparisons(net, ts, min_segment_sec=0.0)
    v = validate(c, n_folds=5)
    assert v["n_folds"] == 0
    label, _ = verdict(estimate(c).summary, v)
    assert label == "unvalidated"


def test_a_penalty_that_does_not_transfer_between_routes_is_called_biased():
    """One route with a wildly different penalty breaks the pooled figure."""
    pats = {}
    for k in range(6):
        pats.update(_corridor(route=f"R{k}", prefix=f"R{k}_"))
    net = _net(pats)
    # give R0 a ten-times penalty by stretching every one of its segments
    for pid, p in net.patterns.items():
        if p.route_id != "R0":
            continue
        for i, s in enumerate(p.segments):
            p.segments[i] = PatternSegment(
                s.route_id, s.direction_id, s.pattern_id, s.from_stop,
                s.to_stop, s.seq, s.run_time_sec * 10)
    ts = _tstats(net.patterns)
    c = find_comparisons(net, ts, min_segment_sec=0.0)
    v = validate(c, n_folds=3, seed=7)
    assert abs(v["aggregate_bias_pct"]) > 0
    assert "over-prediction" in v["exploitable_direction"]
