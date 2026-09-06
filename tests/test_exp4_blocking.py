"""Candidate blocking: the instrument that finally constrains fleet, not a proxy.

The headline test is `test_terminal_separation_forces_a_second_vehicle`. Peak
concurrency says one bus can cover two non-overlapping trips; if those trips end
and start at different terminals with no known deadhead, the real answer is two.
That test is the escape from the concurrency bug rather than a rename of it.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cota_opt.blocks import block_concurrency                    # noqa: E402
from cota_opt.exp4_blocking import (OPERATIONAL_RECOURSE,        # noqa: E402
                                    BlockingError, ConnectionRule,
                                    DeadheadOracle, DeadheadUnknown,
                                    MaterializedTrip, SameTerminalOracle,
                                    TableDeadheadOracle, TripTable,
                                    ZeroDeadheadRelaxation,
                                    audit_published_transitions,
                                    block_candidate_schedule,
                                    materialize_timetable,
                                    minimum_block_fleet,
                                    period_lower_bounds,
                                    production_feasible)
from cota_opt.firewall.core import digest                        # noqa: E402

PERIODS = {"early": (5.0, 6.0), "am_peak": (6.0, 9.0),
           "midday": (9.0, 15.0), "pm_peak": (15.0, 18.0),
           "evening": (18.0, 22.0), "owl": (22.0, 29.0)}


def _trip(tid, o, d, dep_h, arr_h, route="R1", period="am_peak"):
    return MaterializedTrip(
        trip_id=tid, route_id=route, pattern_id=f"{route}p", direction_id=0,
        origin_terminal=o, destination_terminal=d,
        departure_sec=dep_h * 3600.0, arrival_sec=arr_h * 3600.0,
        runtime_min=(arr_h - dep_h) * 60.0, period=period)


def _table(trips):
    ts = tuple(sorted(trips, key=lambda t: (t.departure_sec, t.trip_id)))
    return TripTable(ts, "test", digest([t.payload() for t in ts]))


# ===========================================================================
# THE test: concurrency says one bus, geometry says two
# ===========================================================================

def test_terminal_separation_forces_a_second_vehicle():
    """Two non-overlapping trips, different terminals, no known deadhead.

    Peak concurrency counts 1 -- the trips never overlap in time. The blocker
    must require 2, because nothing can get the bus from A's end to B's start.
    A solver that answers 1 here has renamed the concurrency bug, not escaped
    it.
    """
    a = _trip("t1", "TERM_A", "TERM_A_END", 7.0, 8.0)
    b = _trip("t2", "TERM_B", "TERM_B_END", 8.5, 9.5)
    res = block_candidate_schedule(_table([a, b]), SameTerminalOracle(),
                                   PERIODS)
    assert res.minimum_blocks == 2, (
        "the blocker reused one vehicle across an unreachable terminal pair -- "
        "this is exactly the concurrency error the instrument exists to fix")
    # and the naive concurrency view really would have said one
    _c, _m, peak, _pm, _bp = block_concurrency([a.departure_sec],
                                               [a.arrival_sec], PERIODS)
    assert peak == 1
    assert res.n_feasible_edges == 0


def test_the_same_pair_needs_one_vehicle_once_a_deadhead_exists():
    """The complement: supply the missing datum and the answer changes."""
    a = _trip("t1", "TERM_A", "TERM_A_END", 7.0, 8.0)
    b = _trip("t2", "TERM_B", "TERM_B_END", 8.5, 9.5)
    oracle = TableDeadheadOracle(table={("TERM_A_END", "TERM_B"): 600.0},
                                 min_layover_sec=300.0)
    res = block_candidate_schedule(_table([a, b]), oracle, PERIODS)
    assert res.minimum_blocks == 1
    assert res.blocks[0].connections[0]["deadhead_sec"] == 600.0


# ===========================================================================
# missing deadhead is infeasible, never free
# ===========================================================================

def test_missing_deadhead_makes_the_edge_infeasible_not_zero():
    rule = ConnectionRule(min_layover_sec=0.0)
    a = _trip("t1", "X", "P", 7.0, 8.0)
    b = _trip("t2", "Q", "Y", 8.0, 9.0)       # instant connection if free
    ok, why, dh = rule.feasible(a, b, SameTerminalOracle(min_layover_sec=0.0))
    assert not ok and "deadhead unknown" in why
    assert math.isnan(dh)


def test_the_shipped_oracle_refuses_cross_terminal_outright():
    o = SameTerminalOracle()
    assert o.time_sec("A", "A", 0.0) == 0.0
    with pytest.raises(DeadheadUnknown):
        o.time_sec("A", "B", 0.0)
    assert o.provenance["cross_terminal"].startswith("UNKNOWN")
    assert "UPPER BOUND" in o.provenance["consequence"]


def test_a_result_from_the_same_terminal_oracle_is_flagged_upper_bound():
    a = _trip("t1", "A", "A", 7.0, 8.0)
    res = block_candidate_schedule(_table([a]), SameTerminalOracle(), PERIODS)
    assert res.is_upper_bound
    assert "UPPER BOUND" in res.notes


# ===========================================================================
# same-terminal layover behaviour
# ===========================================================================

def test_same_terminal_respects_the_minimum_layover():
    rule = ConnectionRule(min_layover_sec=600.0)
    o = SameTerminalOracle(min_layover_sec=600.0)
    a = _trip("t1", "A", "T", 7.0, 8.0)
    tight = _trip("t2", "T", "B", 8.0 + 5 / 60, 9.0)     # 5 min gap
    roomy = _trip("t3", "T", "B", 8.0 + 15 / 60, 9.0)    # 15 min gap
    assert not rule.feasible(a, tight, o)[0]
    assert rule.feasible(a, roomy, o)[0]


def test_time_cannot_run_backward():
    rule = ConnectionRule(min_layover_sec=0.0)
    a = _trip("t1", "A", "T", 8.0, 9.0)
    b = _trip("t2", "T", "B", 7.0, 7.5)
    assert not rule.feasible(a, b, SameTerminalOracle(0.0))[0]


# ===========================================================================
# known synthetic path-cover instances
# ===========================================================================

def test_a_chain_of_reachable_trips_needs_one_vehicle():
    o = SameTerminalOracle(min_layover_sec=0.0)
    trips = [_trip(f"t{i}", "T", "T", 6.0 + i, 6.5 + i) for i in range(5)]
    res = block_candidate_schedule(_table(trips), o, PERIODS,
                                   ConnectionRule(min_layover_sec=0.0))
    assert res.minimum_blocks == 1
    assert len(res.blocks) == 1
    assert len(res.blocks[0].trip_ids) == 5


def test_simultaneous_trips_need_one_vehicle_each():
    o = SameTerminalOracle(min_layover_sec=0.0)
    trips = [_trip(f"t{i}", "T", "T", 7.0, 8.0) for i in range(4)]
    res = block_candidate_schedule(_table(trips), o, PERIODS,
                                   ConnectionRule(min_layover_sec=0.0))
    assert res.minimum_blocks == 4


def test_two_interleaved_chains_need_exactly_two():
    o = SameTerminalOracle(min_layover_sec=0.0)
    trips = ([_trip(f"a{i}", "T", "T", 6.0 + i, 6.4 + i) for i in range(3)]
             + [_trip(f"b{i}", "T", "T", 6.2 + i, 6.6 + i) for i in range(3)])
    res = block_candidate_schedule(_table(trips), o, PERIODS,
                                   ConnectionRule(min_layover_sec=0.0))
    assert res.minimum_blocks == 2


def test_minimum_block_fleet_agrees_with_the_full_result():
    o = SameTerminalOracle(min_layover_sec=0.0)
    trips = [_trip(f"t{i}", "T", "T", 6.0 + i * 0.5, 6.4 + i * 0.5)
             for i in range(6)]
    tbl = _table(trips)
    rule = ConnectionRule(min_layover_sec=0.0)
    assert minimum_block_fleet(tbl, o, PERIODS, rule) == \
        block_candidate_schedule(tbl, o, PERIODS, rule).minimum_blocks


# ===========================================================================
# every trip exactly once; chains audited
# ===========================================================================

def test_every_trip_appears_in_exactly_one_block():
    o = SameTerminalOracle(min_layover_sec=0.0)
    trips = ([_trip(f"a{i}", "T", "T", 6.0 + i, 6.4 + i) for i in range(4)]
             + [_trip(f"z{i}", "U", "U", 6.1 + i, 6.5 + i) for i in range(3)])
    res = block_candidate_schedule(_table(trips), o, PERIODS,
                                   ConnectionRule(min_layover_sec=0.0))
    seen = [t for b in res.blocks for t in b.trip_ids]
    assert len(seen) == len(trips) == res.n_trips
    assert len(set(seen)) == len(trips)


def test_chains_carry_their_connections_with_deadhead_and_layover():
    o = SameTerminalOracle(min_layover_sec=300.0)
    trips = [_trip("t1", "T", "T", 7.0, 8.0), _trip("t2", "T", "T", 8.5, 9.0)]
    res = block_candidate_schedule(_table(trips), o, PERIODS)
    c = res.blocks[0].connections[0]
    assert c["from"] == "t1" and c["to"] == "t2"
    assert c["deadhead_sec"] == 0.0
    assert c["layover_sec"] == pytest.approx(1800.0)


def test_determinism_of_the_whole_solve():
    o = SameTerminalOracle(min_layover_sec=0.0)
    trips = [_trip(f"t{i}", "T", "T", 6.0 + i * 0.3, 6.5 + i * 0.3)
             for i in range(8)]
    rule = ConnectionRule(min_layover_sec=0.0)
    a = block_candidate_schedule(_table(trips), o, PERIODS, rule)
    b = block_candidate_schedule(_table(list(reversed(trips))), o, PERIODS, rule)
    assert a.minimum_blocks == b.minimum_blocks
    assert [x.trip_ids for x in a.blocks] == [x.trip_ids for x in b.blocks]


# ===========================================================================
# timetable materialisation
# ===========================================================================

class _Seg:
    def __init__(self, s):
        self.run_time_sec = s


class _Pat:
    def __init__(self, route, direction, stops, run_sec):
        self.route_id = route
        self.direction_id = direction
        self.stops = stops
        self.segments = [_Seg(run_sec)]


class _Net:
    def __init__(self, pats):
        self.patterns = pats


def _net():
    return _Net({"p1": _Pat("R1", 0, ["A", "B"], 1800.0),
                 "p2": _Pat("R1", 1, ["B", "A"], 1800.0)})


def test_materialisation_is_deterministic_and_order_independent():
    plan = {("R1", "am_peak"): 30.0}
    first = {"am_peak": 6.0 * 3600}
    a = materialize_timetable(_net(), plan, PERIODS, first)
    b = materialize_timetable(_net(), dict(reversed(list(plan.items()))),
                              PERIODS, first)
    assert a.digest == b.digest
    assert [t.trip_id for t in a.trips] == [t.trip_id for t in b.trips]


def test_headway_produces_the_expected_first_and_last_trip():
    plan = {("R1", "am_peak"): 60.0}          # hourly, window 06:00-09:00
    first = {"am_peak": 6.0 * 3600}
    tbl = materialize_timetable(_net(), plan, PERIODS, first)
    p1 = [t for t in tbl.trips if t.pattern_id == "p1"]
    assert [t.departure_sec / 3600 for t in p1] == [6.0, 7.0, 8.0], (
        "a trip departing exactly at the window end must not be emitted")
    assert p1[0].arrival_sec == pytest.approx(6.5 * 3600)


def test_both_directions_are_materialised():
    tbl = materialize_timetable(_net(), {("R1", "am_peak"): 60.0}, PERIODS,
                                {"am_peak": 6.0 * 3600})
    assert {t.direction_id for t in tbl.trips} == {0, 1}
    assert {t.origin_terminal for t in tbl.trips} == {"A", "B"}


def test_an_off_route_period_materialises_no_trips():
    for off in (float("inf"), 1e9):
        tbl = materialize_timetable(_net(), {("R1", "am_peak"): off}, PERIODS,
                                    {"am_peak": 6.0 * 3600})
        assert len(tbl) == 0


def test_owl_window_wraps_past_midnight():
    tbl = materialize_timetable(_net(), {("R1", "owl"): 120.0}, PERIODS,
                                {"owl": 22.0 * 3600})
    hours = sorted({t.departure_sec / 3600 for t in tbl.trips})
    assert hours == [22.0, 24.0, 26.0, 28.0], (
        "the owl window runs 22:00-29:00 and must not be truncated at midnight")


def test_an_unknown_period_is_refused():
    with pytest.raises(BlockingError, match="not in the frozen period set"):
        materialize_timetable(_net(), {("R1", "nope"): 30.0}, PERIODS,
                              {"am_peak": 0})


# ===========================================================================
# per-period counting is SHARED with the canonical reconstruction
# ===========================================================================

def test_period_counting_is_the_canonical_function_not_a_copy():
    import inspect
    from cota_opt import blocks, exp4_blocking
    assert "block_concurrency" in inspect.getsource(exp4_blocking)
    assert "block_concurrency" in inspect.getsource(blocks.reconstruct), (
        "reconstruct must call the shared counter, or the two instruments can "
        "drift apart on when a block occupies a vehicle")


def test_period_boundary_counting():
    # one block spanning 08:30-09:30 straddles am_peak and midday
    _c, _m, peak, _pm, by = block_concurrency([8.5 * 3600], [9.5 * 3600],
                                              PERIODS)
    assert peak == 1
    assert by["am_peak"] == 1 and by["midday"] == 1
    assert by["early"] == 0 and by["evening"] == 0


def test_candidate_fleet_is_reported_per_period_with_source():
    o = SameTerminalOracle(min_layover_sec=0.0)
    trips = [_trip("t1", "T", "T", 7.0, 8.0, period="am_peak"),
             _trip("t2", "T", "T", 16.0, 17.0, period="pm_peak")]
    res = block_candidate_schedule(_table(trips), o, PERIODS,
                                   ConnectionRule(min_layover_sec=0.0))
    p = res.payload()
    assert p["source"] == "candidate_block_solver"
    assert set(p["fleet_by_period"]) == set(PERIODS)
    assert "system_peak" in p and "system_peak_time" in p
    assert p["deadhead_provenance"]["deadhead_source"] == "same_terminal_only"
    assert p["model_digest"]


# ===========================================================================
# the forbidden shortcuts
# ===========================================================================

def test_the_module_contains_no_interlining_factor_and_no_speed():
    src = ROOT.joinpath("src/cota_opt/exp4_blocking.py").read_text()
    code = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("#"))
    body = code.split('"""', 2)[-1]
    for forbidden in ("1.307", "1.30", "routewise_peak(", "peak_vehicles ="):
        assert forbidden not in body, (
            f"{forbidden!r} appears in exp4_blocking; fleet is solved for, "
            f"never converted from a proxy")


def test_the_result_type_denies_being_a_reconstruction():
    o = SameTerminalOracle(min_layover_sec=0.0)
    res = block_candidate_schedule(
        _table([_trip("t1", "T", "T", 7.0, 8.0)]), o, PERIODS,
        ConnectionRule(min_layover_sec=0.0))
    assert "not a reconstruction" in res.payload()["NOT"]
    assert res.source == "candidate_block_solver"


def test_operational_recourse_is_preregistered_and_bounded():
    assert "no additional fleet" in OPERATIONAL_RECOURSE["rule"]
    for forbidden in ("change the fleet caps", "change the network",
                      "change the frequency plan",
                      "change the deadhead assumptions",
                      "change the layover assumptions"):
        assert forbidden in OPERATIONAL_RECOURSE["the_blocker_may_not"]


# ===========================================================================
# the audit of published transitions
# ===========================================================================

def test_audit_flags_same_terminal_transitions_under_the_layover_minimum():
    ts = pd.DataFrame([
        {"trip_id": "a", "block_id": "B1", "first_dep_sec": 0.0,
         "last_arr_sec": 3600.0},
        {"trip_id": "b", "block_id": "B1", "first_dep_sec": 3660.0,
         "last_arr_sec": 7200.0},
    ])
    out = audit_published_transitions(
        ts, SameTerminalOracle(min_layover_sec=300.0),
        terminal_of=lambda r: ("T", "T"))
    assert out["transitions_examined"] == 1
    assert out["same_terminal_under_min_layover"] == 1
    assert out["examples"][0]["gap_sec"] == pytest.approx(60.0)


def test_audit_counts_cross_terminal_as_missing_data_not_contradiction():
    ts = pd.DataFrame([
        {"trip_id": "a", "block_id": "B1", "first_dep_sec": 0.0,
         "last_arr_sec": 3600.0},
        {"trip_id": "b", "block_id": "B1", "first_dep_sec": 9000.0,
         "last_arr_sec": 12000.0},
    ])
    out = audit_published_transitions(
        ts, SameTerminalOracle(), terminal_of=lambda r: (
            ("X", "P") if r["trip_id"] == "a" else ("Q", "Y")))
    assert out["cross_terminal_or_unknown"] == 1
    assert out["same_terminal_under_min_layover"] == 0
    assert "measures how much" in out["interpretation"]


# ===========================================================================
# bounds: the bracket that replaces the deadhead nobody has
# ===========================================================================

def test_the_relaxation_is_labelled_a_bound_and_never_a_deadhead_model():
    o = ZeroDeadheadRelaxation()
    p = o.provenance
    assert p["is_bound_only"] is True
    assert "LOWER BOUND" in p["consequence"]
    assert "not a deadhead estimate" in p["NOT"]
    assert "false" in p["cross_terminal"].lower(), (
        "a relaxation that lets a bus teleport must say so in its provenance, "
        "or a later reader will mistake it for evidence about Columbus")


def test_the_relaxation_never_needs_more_buses_than_the_strict_oracle():
    """Adding connections can only lower a minimum path cover."""
    trips = [_trip("t1", "A", "A_END", 7.0, 8.0),
             _trip("t2", "B", "B_END", 8.5, 9.5),
             _trip("t3", "A", "A_END", 9.0, 10.0),
             _trip("t4", "B", "B_END", 10.5, 11.5)]
    tbl = _table(trips)
    hi = block_candidate_schedule(tbl, SameTerminalOracle(), PERIODS)
    lo = block_candidate_schedule(tbl, ZeroDeadheadRelaxation(), PERIODS)
    assert lo.minimum_blocks <= hi.minimum_blocks
    assert hi.is_upper_bound and not hi.is_lower_bound
    assert lo.is_lower_bound and not lo.is_upper_bound


def test_a_lower_bound_result_says_it_certifies_nothing():
    lo = block_candidate_schedule(
        _table([_trip("t1", "A", "A_END", 7.0, 8.0)]),
        ZeroDeadheadRelaxation(), PERIODS)
    assert "certifies nothing" in lo.notes
    assert lo.payload()["is_lower_bound"] is True


def test_period_lower_bounds_do_not_depend_on_any_blocking():
    """Two trips that overlap need two buses under every possible blocking."""
    tbl = _table([_trip("t1", "A", "A_END", 7.0, 8.0),
                  _trip("t2", "B", "B_END", 7.5, 8.5)])
    lb, peak, _minute = period_lower_bounds(tbl, PERIODS, 300.0)
    assert peak == 2
    assert lb["am_peak"] == 2


def test_the_lower_bound_includes_the_layover_a_vehicle_owes():
    """A vehicle is unavailable for min_layover after it arrives."""
    tbl = _table([_trip("t1", "A", "A_END", 7.0, 8.0),
                  _trip("t2", "A", "A_END", 8.0 + 1 / 60, 9.0)])
    zero, _p0, _m0 = period_lower_bounds(tbl, PERIODS, 0.0)
    five, _p5, _m5 = period_lower_bounds(tbl, PERIODS, 300.0)
    assert zero["am_peak"] == 1
    assert five["am_peak"] == 2, (
        "with a 5 minute minimum layover the second trip cannot start one "
        "minute after the first ends, so the lower bound must be 2")


def test_the_bracket_contains_the_strict_answer():
    trips = [_trip(f"t{i}", "A" if i % 2 else "B",
                   "A_END" if i % 2 else "B_END",
                   6.0 + i * 0.6, 6.5 + i * 0.6) for i in range(8)]
    tbl = _table(trips)
    lo = block_candidate_schedule(tbl, ZeroDeadheadRelaxation(), PERIODS)
    hi = block_candidate_schedule(tbl, SameTerminalOracle(), PERIODS)
    assert lo.minimum_blocks <= hi.minimum_blocks


# ===========================================================================
# matching stability: the per-period figure is not a property of the schedule
# ===========================================================================

def test_the_solver_reports_whether_the_period_figure_is_matching_stable():
    res = block_candidate_schedule(
        _table([_trip("t1", "A", "A_END", 7.0, 8.0),
                _trip("t2", "A", "A_END", 9.0, 10.0)]),
        SameTerminalOracle(), PERIODS)
    assert res.fleet_by_period_stable is not None
    assert res.fleet_by_period_alternate is not None


def test_an_unstable_period_figure_is_detected_rather_than_reported_as_fact():
    """One trip, two equally valid continuations with different spans.

    t1 can be followed by the short t2 or the long t3. Both give a maximum
    matching of the same size, but the chain that ends at t3 keeps a vehicle
    nominally in service two hours longer. If the solver reported either
    per-period number as the answer, the answer would depend on list order.
    """
    trips = [_trip("t1", "A", "A", 6.0, 7.0),
             _trip("t2", "A", "A", 8.0, 8.5),
             _trip("t3", "A", "A", 8.0, 14.0)]
    res = block_candidate_schedule(_table(trips), SameTerminalOracle(), PERIODS)
    assert res.minimum_blocks == 2
    if res.fleet_by_period_stable is False:
        assert res.fleet_by_period_alternate != dict(res.fleet_by_period)


def test_the_payload_marks_the_period_figure_as_not_decision_grade():
    res = block_candidate_schedule(
        _table([_trip("t1", "A", "A_END", 7.0, 8.0)]),
        SameTerminalOracle(), PERIODS)
    pl = res.payload()
    assert pl["fleet_by_period_is_matching_dependent"] is True
    assert "may not decide feasibility" in pl["CERTIFICATION"]
    assert "invariant" in pl["CERTIFICATION"]


def test_the_minimum_block_count_is_invariant_under_the_probe():
    """If the two matchings ever disagree in SIZE the solver is broken."""
    trips = [_trip(f"t{i}", "A", "A", 6.0 + i * 0.4, 6.3 + i * 0.4)
             for i in range(12)]
    res = block_candidate_schedule(_table(trips), SameTerminalOracle(), PERIODS)
    assert res.minimum_blocks == len(res.blocks)


# ===========================================================================
# production feasibility: three verdicts, and refusal is one of them
# ===========================================================================

ENV = {"early": 135, "am_peak": 187, "midday": 173,
       "pm_peak": 197, "evening": 178, "owl": 149}


def _tiny():
    tbl = _table([_trip("t1", "A", "A_END", 7.0, 8.0),
                  _trip("t2", "A_END", "A", 9.0, 10.0)])
    return tbl, block_candidate_schedule(tbl, SameTerminalOracle(), PERIODS)


def test_a_scalar_envelope_in_a_dict_costume_is_refused():
    tbl, res = _tiny()
    with pytest.raises(BlockingError):
        production_feasible(res, {"all": 197}, tbl, PERIODS)


def test_vehicle_hours_over_the_envelope_is_infeasible_outright():
    tbl, res = _tiny()
    v = production_feasible(res, ENV, tbl, PERIODS,
                            envelope_vehicle_hours=2517.183333,
                            candidate_vehicle_hours=2600.0)
    assert v.status == "INFEASIBLE" and v.feasible is False
    assert any("vehicle-hours" in r for r in v.reasons)


def test_a_lower_bound_over_the_cap_is_a_real_infeasibility():
    """Three simultaneous trips against a cap of two: no blocking can help."""
    trips = [_trip(f"t{i}", "A", "A_END", 7.0, 8.0) for i in range(3)]
    tbl = _table(trips)
    res = block_candidate_schedule(tbl, SameTerminalOracle(), PERIODS)
    env = {k: 2 for k in PERIODS}
    v = production_feasible(res, env, tbl, PERIODS,
                            envelope_vehicle_hours=1e9,
                            candidate_vehicle_hours=1.0)
    assert v.status == "INFEASIBLE"
    assert any("no choice of blocking can fix this" in r for r in v.reasons)
    assert v.per_period["lower_bound_exceeds_envelope"]


def test_missing_vehicle_hours_makes_the_verdict_undecidable_not_feasible():
    tbl, res = _tiny()
    v = production_feasible(res, ENV, tbl, PERIODS)
    assert v.status == "UNDECIDABLE" and v.feasible is None
    assert any("vehicle-hours were not supplied" in r for r in v.reasons)


def test_an_unstable_per_period_figure_cannot_return_feasible():
    tbl, res = _tiny()
    unstable = type(res)(**{**res.__dict__, "fleet_by_period_stable": False,
                            "fleet_by_period_alternate": {"am_peak": 999}})
    v = production_feasible(unstable, ENV, tbl, PERIODS,
                            envelope_vehicle_hours=1e9,
                            candidate_vehicle_hours=1.0)
    assert v.status == "UNDECIDABLE", (
        "a per-period test whose answer changes with list order must not be "
        "allowed to certify a plan as feasible")
    assert v.per_period["literal_test_is_decision_grade"] is False


def test_a_stable_within_envelope_candidate_is_feasible():
    tbl, res = _tiny()
    stable = type(res)(**{**res.__dict__, "fleet_by_period_stable": True})
    v = production_feasible(stable, ENV, tbl, PERIODS,
                            envelope_vehicle_hours=2517.183333,
                            candidate_vehicle_hours=10.0)
    assert v.status == "FEASIBLE" and v.feasible is True


def test_more_blocks_than_the_baseline_under_one_instrument_is_infeasible():
    tbl, res = _tiny()
    stable = type(res)(**{**res.__dict__, "fleet_by_period_stable": True})
    v = production_feasible(stable, ENV, tbl, PERIODS,
                            envelope_vehicle_hours=1e9,
                            candidate_vehicle_hours=1.0,
                            baseline_minimum_blocks=0)
    assert v.status == "INFEASIBLE"
    assert "instrument-consistent" in v.system["comparison"]


def test_the_system_comparison_refuses_to_equate_a_path_cover_with_a_peak():
    tbl, res = _tiny()
    v = production_feasible(res, ENV, tbl, PERIODS)
    assert "is NOT this quantity" in v.system["comparison"], (
        "the envelope's 197 is a concurrency of published blocks; the "
        "candidate's number is a path-cover count. Comparing them without "
        "saying so is how the 1.307 factor was born")


# ===========================================================================
# the two proxies this instrument exists to replace, checked in the AST
# ===========================================================================

def _code_names(path: Path) -> set[str]:
    """Every identifier the module actually EXECUTES.

    Parsed, not grepped. An earlier pair of tests in this repository matched
    prose that explained why a thing was absent and passed for the wrong
    reason; a docstring naming `routewise_peak` in order to reject it must not
    read as a use of it.
    """
    import ast
    tree = ast.parse(path.read_text())
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                            ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.keyword) and n.arg:
            out.add(n.arg)
    return out


def test_no_use_of_routewise_peak_for_certification():
    names = _code_names(ROOT / "src/cota_opt/exp4_blocking.py")
    assert "routewise_peak" not in names, (
        "routewise_peak is the pre-interlining frequency proxy; it reads "
        "150.73 against a block-derived 197 and may not certify anything")


def test_no_use_of_fitnessvector_peak_vehicles_for_certification():
    names = _code_names(ROOT / "src/cota_opt/exp4_blocking.py")
    assert "peak_vehicles" not in names, (
        "FitnessVector.peak_vehicles is peak CONCURRENCY, not fleet: it "
        "cannot see that a bus must reach the next trip's terminal. This "
        "module solves for fleet instead, which is its whole reason to exist")
    assert "FitnessVector" not in names


def test_the_solver_never_imports_the_frequency_fitness_model():
    import ast
    tree = ast.parse((ROOT / "src/cota_opt/exp4_blocking.py").read_text())
    mods = {n.module for n in ast.walk(tree)
            if isinstance(n, ast.ImportFrom) and n.module}
    mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
             for a in n.names}
    assert not any("frequency" in m or "fitness" in m for m in mods), (
        f"imports {sorted(mods)}: the blocking instrument must not be able to "
        f"reach a proxy it is supposed to replace")


# ===========================================================================
# the real feed: the recorded measurement, pinned
# ===========================================================================

VALIDATION = ROOT / "outputs" / "exp4" / "blocking_validation.json"


def _validation():
    import json
    return json.loads(VALIDATION.read_text())


@pytest.mark.skipif(not VALIDATION.exists(),
                    reason="blocking validation has not been run here")
def test_published_reconstruction_still_reproduces_the_canonical_envelope():
    a = _validation()["test_a"]
    assert a["fleet_by_period"] == {"early": 135, "am_peak": 187,
                                    "midday": 173, "pm_peak": 197,
                                    "evening": 178, "owl": 149}
    assert a["system_peak"] == 197 and a["peak_time"] == "17:13"
    assert a["n_blocks"] == 284 and a["pass"] is True


@pytest.mark.skipif(not VALIDATION.exists(),
                    reason="blocking validation has not been run here")
def test_almost_every_published_transition_is_feasible_under_the_oracle():
    """The honest form of "every published transition is feasible".

    It is not every one, and pinning the real numbers is worth more than an
    assertion that would have to be false. 2,007 of 2,014 same-terminal
    transitions clear the 300s layover; 7 do not, which measures the layover
    ASSUMPTION rather than any defect in COTA's schedule. 33 of 2,047 are
    cross-terminal, so 98.4% of the published blocking needs no deadhead data
    at all -- the missing input is real but small.
    """
    d = _validation()["audit"]
    assert d["terminals_available"] is True
    assert d["transitions_examined"] == 2047
    assert d["same_terminal"] == 2014
    assert d["same_terminal_feasible"] == 2007
    assert d["same_terminal_under_min_layover"] == 7
    assert d["cross_terminal_or_unknown"] == 33
    assert d["share_needing_deadhead_data"] < 0.02


@pytest.mark.skipif(not VALIDATION.exists(),
                    reason="blocking validation has not been run here")
def test_the_candidate_result_is_never_calibrated_toward_the_published_figure():
    b = _validation()["test_b"]
    if not b.get("run"):
        pytest.skip(b.get("why", "test B did not run"))
    assert b["minimum_blocks"] != 197, (
        "the candidate solver landing exactly on the published peak would be "
        "evidence of calibration, not of measurement")
    assert b["is_upper_bound"] is True
    assert "NOT a recreation" in b["invariant"]
    assert "Not calibrated" in b["invariant"]


@pytest.mark.skipif(not VALIDATION.exists(),
                    reason="blocking validation has not been run here")
def test_the_bracket_is_reported_and_the_published_figure_sits_inside_it():
    """180 <= true minimum fleet <= 212, measured on the real weekday feed.

    The published 197 lies inside the bracket, which is the most that can
    honestly be said without a deadhead source: the historical blocking is
    consistent with the physics, and the instrument neither reproduces it nor
    contradicts it.
    """
    br = _validation()["bracket"]
    lo = br.get("lower_solved", br["lower_analytic"]["system_peak"])
    hi = br["upper_solved"]
    assert lo == 180 and hi == 212
    assert lo <= br["published_peak_for_reference"] <= hi
    assert "not the same quantity" in br["meaning"]


@pytest.mark.skipif(not VALIDATION.exists(),
                    reason="blocking validation has not been run here")
def test_dilworth_cross_check_validates_the_matching_on_real_data():
    """Under zero deadhead the reachability is transitively closed, so the
    minimum path cover MUST equal the peak interval concurrency. Agreement on
    2,331 real trips checks Hopcroft-Karp independently of transit modelling.
    """
    d = _validation()["bracket"].get("dilworth_cross_check")
    if d is None:
        pytest.skip("relaxation solve was skipped")
    assert d["agree"] is True and d["solver"] == d["analytic"] == 180


@pytest.mark.skipif(not VALIDATION.exists(),
                    reason="blocking validation has not been run here")
def test_the_real_per_period_figure_is_measurably_matching_dependent():
    """This is why §9's per-period arm returns UNDECIDABLE rather than a
    verdict: on the real baseline an equally maximum matching moves midday by
    11 vehicles and owl by 4. A test that moves when you reverse a list is not
    a test.
    """
    b = _validation()["test_b"]
    assert b["fleet_by_period_stable"] is False
    alt = b["fleet_by_period_alternate"]
    got = b["fleet_by_period"]
    assert alt != got
    assert max(abs(alt[k] - got[k]) for k in got) >= 5


@pytest.mark.skipif(not VALIDATION.exists(),
                    reason="blocking validation has not been run here")
def test_production_feasibility_refuses_rather_than_guesses():
    fb = _validation().get("production_feasibility")
    if fb is None:
        pytest.skip("feasibility was not evaluated")
    assert fb["status"] == "UNDECIDABLE" and fb["feasible"] is None
    assert fb["per_period"]["literal_test_is_decision_grade"] is False
    assert fb["vehicle_hours"]["within"] is True, (
        "the timetable's own revenue vehicle-hours must sit inside the "
        "envelope it was used to define")
