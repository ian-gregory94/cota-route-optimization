"""Adversarial tests for the Experiment 4 assembly/scoring substrate.

The substrate's whole claim is that a greenfield network is scored on Gen1's
yardstick. These pin the parts that could quietly stop being true.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cota_opt.exp4_assemble import (_pattern_id, assemble,        # noqa: E402
                                    rebuild_like_assembler)
from cota_opt.exp4_network import Exp4Selection, Exp4SelectionError  # noqa: E402
from cota_opt.frequency import (OFF, FrequencyPlan, RouteService,  # noqa: E402
                                build_ladders, is_off,
                                snap_plan_to_ladder)
from cota_opt.linkgraph import LinkGraph, ObservedLink            # noqa: E402
from cota_opt.network import StopNode                             # noqa: E402


# ---------------------------------------------------------------- fixtures
def _graph(links):
    return LinkGraph(links={(a, b): ObservedLink(a, b, t, 1, (), 0.0)
                            for a, b, t in links},
                     out={}, stops=tuple(sorted({s for a, b, _ in links
                                                 for s in (a, b)})))


def _stops(ids):
    return {s: StopNode(s, s, 39.96 + i * 1e-3, -83.0 + i * 1e-3)
            for i, s in enumerate(sorted(ids))}


@pytest.fixture
def tiny():
    links = [("A", "B", 300.0), ("B", "C", 240.0),
             ("C", "B", 250.0), ("B", "A", 310.0),
             ("A", "D", 200.0), ("D", "A", 210.0)]
    pool = {
        "L1": {"outbound": ["A", "B", "C"], "inbound": ["C", "B", "A"]},
        "L2": {"outbound": ["A", "D"], "inbound": ["D", "A"]},
    }
    return pool, _graph(links), _stops(["A", "B", "C", "D"])


PERIODS = {"am_peak": 25_200.0, "midday": 36_000.0}


# ------------------------------------------------- assembly & determinism
def test_assembly_is_deterministic(tiny):
    pool, g, stops = tiny
    sel = Exp4Selection.of("v1", ["L1", "L2"])
    a = assemble(sel, pool, g, stops, pool_version="v1",
                 first_dep_sec_by_period=PERIODS)
    b = assemble(sel, pool, g, stops, pool_version="v1",
                 first_dep_sec_by_period=PERIODS)
    assert sorted(a.network.patterns) == sorted(b.network.patterns)
    assert a.report.as_dict() == b.report.as_dict()
    pd.testing.assert_frame_equal(a.tstats, b.tstats)


def test_pattern_ids_are_content_derived_not_positional(tiny):
    pool, g, stops = tiny
    one = assemble(Exp4Selection.of("v1", ["L1", "L2"]), pool, g, stops,
                   pool_version="v1", first_dep_sec_by_period=PERIODS)
    # the same line assembled in a different company keeps its pattern ids
    two = assemble(Exp4Selection.of("v1", ["L1"]), pool, g, stops,
                   pool_version="v1", first_dep_sec_by_period=PERIODS)
    l1 = {p for p in one.network.patterns if p.startswith("L1.")}
    assert l1 == set(two.network.patterns)


def test_assembled_accounting_trips_vehicle_hours_peak_and_fleet(tiny):
    pool, g, stops = tiny
    a = assemble(Exp4Selection.of("v1", ["L1"]), pool, g, stops,
                 pool_version="v1", first_dep_sec_by_period=PERIODS)
    # runtimes come from the graph, per segment, not from a total
    out = a.network.patterns[_pattern_id("L1", 0, ["A", "B", "C"])]
    assert [s.run_time_sec for s in out.segments] == [300.0, 240.0]
    assert out.total_run_time_min == pytest.approx((300 + 240) / 60.0)

    # and the accounting a FrequencyModel would do on it
    svc = RouteService("L1", "am_peak", runtime_min=out.total_run_time_min,
                       n_directions=2, baseline_headway_min=OFF,
                       baseline_trips=0)
    duration = 180.0
    for h, want_trips in ((10.0, 2 * duration / 10.0), (OFF, 0.0)):
        trips = svc.n_directions * duration / h
        assert trips == pytest.approx(want_trips)
        assert trips * svc.runtime_min / 60.0 == pytest.approx(
            want_trips * svc.runtime_min / 60.0)
    cycle = 2.0 * svc.runtime_min * 1.1
    assert cycle / OFF == 0.0
    assert int(math.ceil(cycle / OFF)) == 0


# ---------------------------------------------------------------- OFF
def test_a_synthetic_route_gets_no_baseline_headway(tiny):
    """Gate 4-5: inventing a baseline invents a service commitment."""
    svc = RouteService("L1", "am_peak", runtime_min=9.0, n_directions=2,
                       baseline_headway_min=OFF, baseline_trips=0)
    assert is_off(svc.baseline_headway_min)


def test_off_is_a_rung_only_when_allowed_and_survives_snapping():
    class _M:
        services = {("L1", "am_peak"): RouteService(
            "L1", "am_peak", 9.0, 2, OFF, 0)}
    k = ("L1", "am_peak")
    lad_on = build_ladders(_M(), [10.0, 20.0, 30.0], allow_off=True)
    assert any(is_off(v) for v in lad_on[k])

    # A route-period with NO baseline cannot be laddered without an OFF rung.
    # Regression: build_ladders used to append svc.baseline_headway_min
    # unconditionally, so an OFF baseline leaked an OFF rung into a ladder
    # built with allow_off=False -- silently permitting exactly what the flag
    # exists to forbid. It now refuses instead.
    with pytest.raises(ValueError, match="no baseline service"):
        build_ladders(_M(), [10.0, 20.0, 30.0], allow_off=False)

    # a route-period that DOES have a baseline ladders normally, with no OFF
    class _M2:
        services = {k: RouteService("L1", "am_peak", 9.0, 2, 20.0, 40)}
    lad_plain = build_ladders(_M2(), [10.0, 20.0, 30.0], allow_off=False)
    assert not any(is_off(v) for v in lad_plain[k])

    snapped = snap_plan_to_ladder(lad_on, FrequencyPlan({k: OFF}))
    assert is_off(snapped.headways[k])
    with pytest.raises(ValueError, match="no OFF rung"):
        snap_plan_to_ladder(lad_plain, FrequencyPlan({k: OFF}))


def test_off_and_non_finite_patterns_are_never_boarded():
    import numpy as np
    for h in (OFF, float("inf"), float("nan"), 1e5):
        assert not (np.isfinite(h) and h < 1e5)


# ------------------------------------------------------- failing closed
def test_unknown_line_is_refused_not_dropped(tiny):
    pool, g, stops = tiny
    with pytest.raises(Exp4SelectionError, match="not in the pool"):
        assemble(Exp4Selection.of("v1", ["L1", "NOPE"]), pool, g, stops,
                 pool_version="v1", first_dep_sec_by_period=PERIODS)


def test_pool_version_mismatch_is_refused(tiny):
    pool, g, stops = tiny
    with pytest.raises(Exp4SelectionError, match="pool"):
        assemble(Exp4Selection.of("v2", ["L1"]), pool, g, stops,
                 pool_version="v1", first_dep_sec_by_period=PERIODS)


def test_an_unobserved_link_is_refused(tiny):
    pool, g, stops = tiny
    pool = {**pool, "BAD": {"outbound": ["A", "C"], "inbound": ["C", "A"]}}
    with pytest.raises(Exp4SelectionError, match="unobserved link"):
        assemble(Exp4Selection.of("v1", ["BAD"]), pool, g, stops,
                 pool_version="v1", first_dep_sec_by_period=PERIODS)


def test_a_stop_outside_the_fixed_universe_is_refused(tiny):
    pool, g, stops = tiny
    pool = {**pool, "X": {"outbound": ["A", "B", "Z"], "inbound": ["Z", "B", "A"]}}
    g2 = _graph([("A", "B", 300.0), ("B", "Z", 100.0),
                 ("Z", "B", 100.0), ("B", "A", 310.0)])
    with pytest.raises(Exp4SelectionError, match="fixed stop universe"):
        assemble(Exp4Selection.of("v1", ["X"]), pool, g2, stops,
                 pool_version="v1", first_dep_sec_by_period=PERIODS)


def test_a_one_stop_direction_is_refused(tiny):
    pool, g, stops = tiny
    pool = {**pool, "S": {"outbound": ["A"], "inbound": ["A"]}}
    with pytest.raises(Exp4SelectionError, match="at least two"):
        assemble(Exp4Selection.of("v1", ["S"]), pool, g, stops,
                 pool_version="v1", first_dep_sec_by_period=PERIODS)


def test_nothing_is_silently_repaired(tiny):
    """Every malformed input above raises. None returns a partial network."""
    pool, g, stops = tiny
    bad = {**pool, "BAD": {"outbound": ["A", "C"], "inbound": ["C", "A"]}}
    try:
        assemble(Exp4Selection.of("v1", ["L1", "BAD"]), bad, g, stops,
                 pool_version="v1", first_dep_sec_by_period=PERIODS)
    except Exp4SelectionError:
        pass
    else:
        pytest.fail("a network containing an unobserved link was assembled")


# ------------------------------------------------------ interface shape
def test_exp4_does_not_masquerade_as_geometry_edits():
    """The abstraction change is explicit in the type, not smuggled."""
    import inspect

    from cota_opt.exp4_score import score_exp4_network
    sig = inspect.signature(score_exp4_network)
    assert "selection" in sig.parameters
    ann = sig.parameters["selection"].annotation
    assert "Exp4Selection" in str(ann)
    assert "edits" not in sig.parameters


def test_gen1_default_is_unchanged_everywhere():
    import inspect

    from cota_opt.exp2 import build_setup
    from cota_opt.exp3_score import solve_on_network
    assert inspect.signature(build_setup).parameters["allow_off"].default is False
    assert (inspect.signature(solve_on_network)
            .parameters["allow_off"].default is False)
    assert (inspect.signature(build_ladders)
            .parameters["allow_off"].default is False)


# --------------------------------------------------------------------------
# D35: PINNED_OFF was a label, not a constraint.
#
# `Exp4Selection.pinned_off` was validated at construction and hashed into the
# state digest, and then reached nothing that scores: `assemble` recorded it in
# the assembly report, `score_exp4_network` did not forward it, and
# `solve_on_network` forwarded it on the "exact" solver branch alone. Two
# selections differing only in pinned_off therefore produced IDENTICAL scores
# under different state digests -- which the firewall admits as a declared
# treatment difference and reports a zero effect for a treatment that was never
# applied.
#
# These tests pin the wiring rather than the numbers, so they run without a
# harness. The end-to-end effect is measured in
# `scripts/exp4_masterpath_benchmark.py`, whose pinned_off rows were byte-
# identical to its supernetwork rows and are what exposed this.
# --------------------------------------------------------------------------

def test_score_exp4_network_forwards_pinned_off_to_the_solver():
    """The passthrough itself. Its absence is the whole of D35."""
    import inspect

    from cota_opt.exp4_score import score_exp4_network
    src = inspect.getsource(score_exp4_network)
    assert "pinned_off=" in src, (
        "score_exp4_network must forward the selection's pins to "
        "solve_on_network; without this a PINNED_OFF fate cannot change a score")
    assert "selection.pinned_off" in src


def test_solve_on_network_pins_the_setup_not_one_solver():
    """Pinning must bind Gen1 and Gen2 alike.

    The mechanism is the one `locked` already uses -- a single-rung ladder
    cannot be moved by any optimizer -- so it is applied to the setup above the
    solver switch. Pinning inside `solve_exact` alone leaves the Gen1 branch
    unconstrained, which is how this shipped.
    """
    import inspect

    from cota_opt.exp3_score import solve_on_network
    src = inspect.getsource(solve_on_network)
    pin_at = src.index("if pinned_off:")
    switch_at = src.index('if solver == "exact":')
    assert pin_at < switch_at, (
        "the pin is applied after the solver switch, so it binds one "
        "generation and not the other")
    assert "judge.ladders[k] = [off[0]]" in src
    # snap_to_ladder REFUSES a finite headway against an OFF-only ladder, so
    # pinning the ladder without pinning the baseline plan crashes rather
    # than pins.
    assert "judge.baseline_plan.headways[k] = OFF" in src


def test_pinned_off_is_asserted_on_the_result():
    """A constraint enforced only by construction is one nobody has watched fail."""
    import inspect

    from cota_opt.exp3_score import solve_on_network
    src = inspect.getsource(solve_on_network)
    assert "came back with service" in src
    assert src.index("came back with service") > src.index('if solver == "exact":')


def test_pinned_off_refuses_a_pin_that_matches_nothing():
    import inspect

    from cota_opt.exp3_score import solve_on_network
    src = inspect.getsource(solve_on_network)
    assert "names route-periods this network does not have" in src
    assert "pinned_off requires allow_off=True" in src


def test_snap_refuses_finite_headway_against_an_off_only_ladder():
    """Why the baseline plan has to be pinned too -- the failure is a crash."""
    from cota_opt.frequency import snap_to_ladder
    assert snap_to_ladder(OFF, [OFF]) == OFF
    with pytest.raises(ValueError, match="offers no service at all"):
        snap_to_ladder(20.0, [OFF])
