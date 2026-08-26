"""The stop-edit vocabulary, on a network where the right answer is known.

The property that matters most is the one the audit forced: an applied edit
must not grant the route a time saving. Everything else here is guard-rail
behaviour -- what gets rejected, and why every reason is reported rather than
the first one found.
"""
import numpy as np
import pandas as pd
import pytest

from cota_opt.network import PatternSegment, RoutePattern, StopNode, TransitNetwork
from cota_opt.stopedits import (BreakEven, Guard, StopEdit, apply_stop_edits,
                                breakeven, edits_from, guard_reasons, propose,
                                register, stop_flows)


def _pattern(pid, stops, times, route="R", direction=0, n_trips=30):
    segs = [PatternSegment(route, direction, pid, stops[i], stops[i + 1], i,
                           times[i]) for i in range(len(stops) - 1)]
    return RoutePattern(route, direction, pid, list(stops), segs, n_trips)


@pytest.fixture
def net():
    pats = {"P1": _pattern("P1", ["A", "B", "C", "D"], [60.0, 90.0, 120.0]),
            "P2": _pattern("P2", ["A", "B", "D"], [60.0, 210.0])}
    stops = {s: StopNode(s, s, 39.96 + 0.001 * i, -83.0)
             for i, s in enumerate("ABCD")}
    sr, rs = {}, {}
    for p in pats.values():
        for s in p.stops:
            sr.setdefault(s, set()).add(p.route_id)
            rs.setdefault(p.route_id, set()).add(s)
    return TransitNetwork(stops=stops, patterns=pats, stop_routes=sr,
                          route_stops=rs)


def _audit_row(**kw):
    base = dict(stop_id="C", stop_name="C St", routes="R", protected="",
                nearest_stop_id="B", nearest_walk_min=1.2, prev_spacing_m=120.0,
                catchment_flow=40.0, unique_flow=0.0, daily_trips=30.0)
    base.update(kw)
    return base


# -- the property the audit forced ------------------------------------------

def test_dropping_a_stop_does_not_make_the_route_any_faster(net):
    """Runtime is held fixed by construction: this is the whole design."""
    before = {pid: p.total_run_time_min for pid, p in net.patterns.items()}
    out, rep = apply_stop_edits(net, [StopEdit("consolidate", "R", "C",
                                               receiver_id="B")])
    after = {pid: p.total_run_time_min for pid, p in out.patterns.items()}
    assert rep.runtime_delta_min == pytest.approx(0.0, abs=1e-9)
    assert after["P1"] == pytest.approx(before["P1"])
    assert "held fixed" in rep.summary()["runtime_treatment"]


def test_the_merged_segment_carries_the_sum_of_the_two_it_replaced(net):
    out, _ = apply_stop_edits(net, [StopEdit("remove", "R", "C")])
    p = out.patterns["P1"]
    assert p.stops == ["A", "B", "D"]
    bd = [s for s in p.segments if s.from_stop == "B" and s.to_stop == "D"]
    assert len(bd) == 1 and bd[0].run_time_sec == pytest.approx(90.0 + 120.0)


def test_segments_are_renumbered_so_the_pattern_stays_walkable(net):
    out, _ = apply_stop_edits(net, [StopEdit("remove", "R", "C")])
    p = out.patterns["P1"]
    assert [s.seq for s in p.segments] == list(range(len(p.stops) - 1))
    assert [s.from_stop for s in p.segments] == p.stops[:-1]
    assert [s.to_stop for s in p.segments] == p.stops[1:]


def test_a_pattern_that_never_served_the_stop_is_untouched(net):
    out, rep = apply_stop_edits(net, [StopEdit("remove", "R", "C")])
    assert out.patterns["P2"].stops == ["A", "B", "D"]
    assert rep.patterns_changed == 1


def test_a_terminal_is_never_dropped_by_a_consolidation_edit(net):
    out, rep = apply_stop_edits(net, [StopEdit("remove", "R", "A")])
    assert out.patterns["P1"].stops == ["A", "B", "C", "D"]
    assert rep.applied == [] and "no eligible pattern" in rep.skipped[0]


def test_the_edited_network_forgets_the_stop_it_no_longer_serves(net):
    out, _ = apply_stop_edits(net, [StopEdit("remove", "R", "C")])
    assert "C" not in out.route_stops["R"]
    assert "C" not in out.stop_routes


# -- guards ------------------------------------------------------------------

def test_a_protected_stop_is_never_proposed():
    df = pd.DataFrame([_audit_row(protected="terminal")])
    out = propose(df)
    assert not out["eligible"].any()
    assert "terminal" in out.iloc[0]["rejected_for"]


def test_every_failing_rule_is_reported_not_just_the_first():
    """Relaxing one rule must not silently reveal three others."""
    df = pd.DataFrame([_audit_row(protected="terminal", nearest_walk_min=9.0,
                                  prev_spacing_m=800.0)])
    why = propose(df).iloc[0]["rejected_for"]
    assert "terminal" in why and "min" in why and "spacing" in why


def test_a_stop_on_two_routes_is_out_of_scope_for_a_route_scoped_edit():
    df = pd.DataFrame([_audit_row(routes="R;S")])
    assert "serves 2 routes" in propose(df).iloc[0]["rejected_for"]


def test_a_stop_with_no_walking_alternative_is_never_proposed():
    df = pd.DataFrame([_audit_row(nearest_walk_min=np.inf)])
    assert "no walking alternative" in propose(df).iloc[0]["rejected_for"]


def test_widely_spaced_stops_are_not_consolidation_candidates():
    df = pd.DataFrame([_audit_row(prev_spacing_m=450.0)])
    assert "spacing" in propose(df).iloc[0]["rejected_for"]
    ok = propose(df, Guard(max_pair_spacing_m=500.0))
    assert bool(ok.iloc[0]["eligible"])


def test_no_route_loses_more_than_the_cap_allows():
    rows = [_audit_row(stop_id=f"S{i}", nearest_stop_id=f"S{i+1}",
                       catchment_flow=float(i)) for i in range(10)]
    out = propose(pd.DataFrame(rows), Guard(max_removed_per_route=3))
    assert int(out["eligible"].sum()) == 3
    assert out[~out["eligible"]]["rejected_for"].str.contains("cap").any()


def test_rejected_candidates_stay_in_the_frame():
    """A pool that arrives without its rejections cannot be audited."""
    rows = [_audit_row(stop_id="C"), _audit_row(stop_id="D", protected="terminal")]
    out = propose(pd.DataFrame(rows))
    assert len(out) == 2 and int(out["eligible"].sum()) == 1


def test_edits_are_built_only_from_eligible_rows():
    rows = [_audit_row(stop_id="C"), _audit_row(stop_id="D", protected="terminal")]
    edits = edits_from(propose(pd.DataFrame(rows)))
    assert [e.stop_id for e in edits] == ["C"]
    assert all(e.receiver_id for e in edits)


def test_guard_reasons_is_usable_on_its_own():
    row = pd.Series(_audit_row(protected="", nearest_walk_min=1.0,
                               daily_trips=30.0))
    assert guard_reasons(row, "B", Guard()) == []
    assert guard_reasons(row, None, Guard())[0].startswith("no receiver")


# -- the break-even, which is the point --------------------------------------

def test_the_threshold_is_the_penalty_that_exactly_pays_for_the_walking():
    # 100 generalized minutes of extra walking a day, 200 riders passing through
    be = breakeven(100.0, {"through": 200.0}, w_in_vehicle=1.0)
    assert be.seconds_per_stop_required == pytest.approx(30.0)
    assert "NOT counted" in be.basis


def test_a_stop_nobody_rides_past_can_never_pay_for_itself():
    be = breakeven(10.0, {"through": 0.0}, w_in_vehicle=1.0)
    assert not np.isfinite(be.seconds_per_stop_required)
    assert "no stop penalty can pay" in be.verdict(30.0)


def test_the_verdict_reports_the_assumption_it_was_judged_against():
    be = breakeven(100.0, {"through": 200.0}, w_in_vehicle=1.0)
    assert "not justified" in be.verdict(20.0)
    assert "below the 40 s assumed" in be.verdict(40.0)


def test_weighting_in_vehicle_time_higher_lowers_the_bar():
    a = breakeven(100.0, {"through": 200.0}, w_in_vehicle=1.0)
    b = breakeven(100.0, {"through": 200.0}, w_in_vehicle=2.0)
    assert b.seconds_per_stop_required < a.seconds_per_stop_required


# -- bookkeeping -------------------------------------------------------------

def test_unscored_candidates_are_still_counted():
    frame = propose(pd.DataFrame([_audit_row(stop_id="C"),
                                  _audit_row(stop_id="E", nearest_stop_id="F")]))
    out = register(frame, [{"edit_id": frame.iloc[0]["edit_id"],
                            "gc_change_pct": -0.2}])
    assert len(out) == len(frame)
    assert int(out["scored"].sum()) == 1


def test_an_empty_result_list_still_returns_the_pool():
    frame = propose(pd.DataFrame([_audit_row()]))
    out = register(frame, [])
    assert len(out) == 1 and not out["scored"].any()


# -- flows -------------------------------------------------------------------

class _FakePS:
    n_paths = 4
    leg_pattern = np.array([0, 0, 0, 0])
    leg_board_pos = np.array([0, 1, 2, 0])
    leg_alight_pos = np.array([3, 2, 3, 1])
    leg_path = np.array([0, 1, 2, 3])


class _FakeEv:
    ps = _FakePS()

    def path_flows(self, hw):
        return np.array([100.0, 10.0, 20.0, 5.0])


def test_boarders_alighters_and_through_riders_are_counted_separately():
    f = stop_flows(_FakeEv(), np.zeros(1), {"P1": 0}, {"P1": 1})
    assert f["through"] == pytest.approx(100.0)   # path 0 rides 0 -> 3
    assert f["boarding"] == pytest.approx(10.0)   # path 1 boards at 1
    assert f["alighting"] == pytest.approx(5.0)   # path 3 alights at 1


def test_an_empty_path_set_reports_zero_rather_than_failing():
    class Empty:
        class ps:
            n_paths = 0
            leg_pattern = None
    assert stop_flows(Empty(), np.zeros(1), {}, {})["through"] == 0.0
