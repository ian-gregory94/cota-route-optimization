"""Every contract limit, at the limit and one step past it.

A limit tested only in the middle of its range is a limit nobody has checked.
Each rule below gets three cases where the arithmetic allows: comfortably
inside, exactly at the boundary, and one step over. The exact-limit case is the
one that catches an off-by-one in a comparison operator, which is the failure
mode that turns a documented 40% cap into an undocumented 41% one.
"""
import math
import re

import pytest

from cota_opt.contract import (ContractLimits, ContractViolation,
                               edit_distance, stop_visits, validate_applied,
                               validate_mutation, validate_state_proposal)
from cota_opt.geometry import (EDIT_KINDS, GeometryEdit, SegmentTimeModel,
                               apply_edits)

from test_raptor import _net, _stops_gdf, _tstats


LIMITS = ContractLimits()


@pytest.fixture
def net():
    return _net()


@pytest.fixture
def ts():
    return _tstats()


@pytest.fixture
def model(net):
    return SegmentTimeModel.fit(net, _stops_gdf())


@pytest.fixture
def coords(model):
    return model.coords


# -- the document and the code agree ---------------------------------------

def test_limits_match_the_committed_contract():
    """The numbers in ContractLimits are the numbers in the contract file."""
    from pathlib import Path
    doc = (Path(__file__).resolve().parents[1]
           / "EXPERIMENT3_CONTRACT.md").read_text(encoding="utf-8")
    assert "1,200 m" in doc
    assert "40% of its baseline stop-visits" in doc
    assert "15%" in doc
    assert "30% of the original stop-visits" in doc
    assert "2.0%" in doc
    assert LIMITS.terminal_move_m == 1200.0
    assert LIMITS.max_route_stop_visit_loss == 0.40
    assert LIMITS.max_network_edit_distance == 0.15
    assert LIMITS.min_split_share == 0.30
    assert LIMITS.modelled_share_primary_pct == 2.0


def test_every_permitted_operation_in_the_doc_is_a_real_kind():
    from pathlib import Path
    doc = (Path(__file__).resolve().parents[1]
           / "EXPERIMENT3_CONTRACT.md").read_text(encoding="utf-8")
    advertised = set(re.findall(r"\| `(\w+)` \| yes", doc))
    assert advertised, "the operation table lost its kind column"
    assert advertised <= set(EDIT_KINDS), (
        f"the contract advertises operations the code cannot build: "
        f"{sorted(advertised - set(EDIT_KINDS))}")


# -- existing stops only ----------------------------------------------------

def test_a_mutation_naming_an_unknown_stop_is_refused(net, coords):
    e = GeometryEdit(kind="add_stop", route_id="A",
                     append_stops=("NOT_A_STOP",), description="invent one")
    with pytest.raises(ContractViolation, match="existing-stops-only"):
        validate_mutation(e, net, coords, LIMITS)


def test_a_mutation_naming_a_known_stop_passes(net, coords):
    e = GeometryEdit(kind="add_stop", route_id="A", append_stops=("S6",),
                     description="add an existing stop")
    validate_mutation(e, net, coords, LIMITS)


def test_a_mutation_naming_a_dead_route_is_refused(net, coords):
    e = GeometryEdit(kind="truncate", route_id="ZZ", drop_stops=("S4",),
                     description="edit a route that is not there")
    with pytest.raises(ContractViolation, match="live-routes"):
        validate_mutation(e, net, coords, LIMITS)


# -- terminal movement: inside, exactly at, and one step over ---------------

def _at(coords, metres):
    """Coordinates placing S4 and S6 exactly `metres` apart."""
    c = dict(coords)
    c["S4"], c["S6"] = (0.0, 0.0), (float(metres), 0.0)
    return c


def test_terminal_move_inside_the_limit_passes(net, coords):
    e = GeometryEdit(kind="change_terminal", route_id="A", junction="S4",
                     append_stops=("S6",), description="move 1199 m")
    validate_mutation(e, net, _at(coords, 1199.0), LIMITS)


def test_terminal_move_exactly_at_the_limit_passes(net, coords):
    c = _at(coords, 1200.0)
    e = GeometryEdit(kind="change_terminal", route_id="A", junction="S4",
                     append_stops=("S6",), description="move exactly 1200 m")
    validate_mutation(e, net, c, LIMITS)   # <= is the documented comparison


def test_terminal_move_one_metre_over_is_refused(net, coords):
    c = _at(coords, 1201.0)
    e = GeometryEdit(kind="change_terminal", route_id="A", junction="S4",
                     append_stops=("S6",), description="move 1201 m")
    with pytest.raises(ContractViolation, match="terminal-move"):
        validate_mutation(e, net, c, LIMITS)


# -- split share: inside, exactly at, and one step under -------------------

def test_split_at_a_terminal_is_refused(net, coords):
    e = GeometryEdit(kind="split", route_id="A", junction="S1",
                     description="cut at the terminal")
    with pytest.raises(ContractViolation, match="split-junction"):
        validate_mutation(e, net, coords, LIMITS)


def test_split_at_the_middle_passes(net, coords):
    e = GeometryEdit(kind="split", route_id="A", junction="S2",
                     description="cut A at S2")
    validate_mutation(e, net, coords, LIMITS)


def test_split_share_exactly_at_the_floor_passes(net, coords):
    """Route A is S1-S2-S3-S4 (4 stop-visits); cutting at S2 gives 2 and 3.

    Setting the floor to exactly the smaller half's share must PASS: the
    documented rule is "at least 30%", so equality is inside it. This is the
    case that catches a `>` written where `>=` was meant.
    """
    e = GeometryEdit(kind="split", route_id="A", junction="S2",
                     description="cut A at S2")
    lim = ContractLimits(min_split_share=0.5)   # exactly the smaller half
    validate_mutation(e, net, coords, lim)


def test_split_share_a_hair_above_the_smaller_half_is_refused(net, coords):
    e = GeometryEdit(kind="split", route_id="A", junction="S2",
                     description="cut A at S2")
    lim = ContractLimits(min_split_share=0.5 + 1e-9)
    with pytest.raises(ContractViolation, match="split-share"):
        validate_mutation(e, net, coords, lim)


def test_split_share_one_step_under_the_floor_is_refused(net, coords):
    lim = ContractLimits(min_split_share=0.75)   # forces the shorter half under
    e = GeometryEdit(kind="split", route_id="A", junction="S2",
                     description="cut A at S2")
    with pytest.raises(ContractViolation, match="split-share"):
        validate_mutation(e, net, coords, lim)


# -- pairwise incompatibility ----------------------------------------------

def test_two_mutations_on_one_route_are_refused(net, coords):
    a = GeometryEdit(kind="truncate", route_id="A", drop_stops=("S4",),
                     description="a")
    b = GeometryEdit(kind="add_stop", route_id="A", append_stops=("S6",),
                     description="b")
    with pytest.raises(ContractViolation, match="incompatible-pair"):
        validate_state_proposal([a, b], net, coords, LIMITS)


def test_a_splice_and_an_edit_sharing_one_route_are_refused(net, coords):
    a = GeometryEdit(kind="splice", route_id="A", with_route="C",
                     junction="S2", description="a")
    b = GeometryEdit(kind="truncate", route_id="C", drop_stops=("S6",),
                     description="b")
    with pytest.raises(ContractViolation, match="incompatible-pair"):
        validate_state_proposal([a, b], net, coords, LIMITS)


def test_route_disjoint_mutations_are_accepted(net, coords):
    a = GeometryEdit(kind="truncate", route_id="A", drop_stops=("S4",),
                     description="a")
    b = GeometryEdit(kind="truncate", route_id="B", drop_stops=("S5",),
                     description="b")
    validate_state_proposal([a, b], net, coords, LIMITS)


def test_removing_a_stop_another_mutation_anchors_on_is_refused(net, coords):
    a = GeometryEdit(kind="truncate", route_id="A", drop_stops=("S2",),
                     description="drops S2")
    b = GeometryEdit(kind="splice", route_id="B", with_route="C",
                     junction="S2", description="joins at S2")
    with pytest.raises(ContractViolation, match="incompatible-pair"):
        validate_state_proposal([a, b], net, coords, LIMITS)


# -- outcome checks: only the resulting network knows -----------------------

def test_a_state_that_strands_a_stop_is_refused(net, ts, model):
    """C's only stop-visit at S6 removed leaves S6 served by nobody."""
    e = GeometryEdit(kind="truncate", route_id="C", drop_stops=("S6",),
                     description="strand S6")
    out = apply_edits(net, ts, model, [e])
    chk = validate_applied(net, out.network, [e], LIMITS)
    assert not chk.ok
    assert any("served by no route" in v for v in chk.violations)
    with pytest.raises(ContractViolation):
        chk.raise_if_bad()


def test_a_sole_access_stop_may_not_be_stranded(net, ts, model):
    e = GeometryEdit(kind="truncate", route_id="C", drop_stops=("S6",),
                     description="strand S6")
    out = apply_edits(net, ts, model, [e])
    chk = validate_applied(net, out.network, [e], LIMITS,
                           sole_access_stops={"S6"})
    assert any("sole-access" in v for v in chk.violations)


def test_a_clean_state_passes_every_rule(net, ts, model):
    e = GeometryEdit(kind="add_stop", route_id="C", append_stops=("S3",),
                     description="add S3 to C")
    out = apply_edits(net, ts, model, [e])
    chk = validate_applied(net, out.network, [e], LIMITS)
    assert chk.ok, chk.violations
    assert "no-stop-removed" in chk.rules_checked
    assert "network-edit-distance" in chk.rules_checked


def test_edit_distance_is_zero_for_no_change(net, ts, model):
    out = apply_edits(net, ts, model, [])
    assert edit_distance(net, out.network) == pytest.approx(0.0)


def test_edit_distance_exactly_at_the_limit_passes(net, ts, model):
    """Set the limit to the distance the edit actually produces; equality passes.

    The documented rule is "edit distance <= 15%", so a state landing exactly on
    the line is inside it. Measuring the real distance first and then setting
    the limit to it tests the comparison rather than the arithmetic.
    """
    e = GeometryEdit(kind="truncate", route_id="A", drop_stops=("S4",),
                     description="shorten A")
    out = apply_edits(net, ts, model, [e])
    exact = edit_distance(net, out.network)
    assert exact > 0, "the fixture edit must actually move stop-visits"
    chk = validate_applied(net, out.network, [e],
                           ContractLimits(max_network_edit_distance=exact))
    assert not any("edit distance" in v for v in chk.violations)

    over = validate_applied(
        net, out.network, [e],
        ContractLimits(max_network_edit_distance=exact - 1e-12))
    assert any("edit distance" in v for v in over.violations)


def test_edit_distance_one_step_over_is_refused(net, ts, model):
    lim = ContractLimits(max_network_edit_distance=0.0)
    e = GeometryEdit(kind="truncate", route_id="A", drop_stops=("S4",),
                     description="any change at all")
    out = apply_edits(net, ts, model, [e])
    chk = validate_applied(net, out.network, [e], lim)
    assert any("edit distance" in v for v in chk.violations)


# -- gate 3-8, both halves of the envelope ---------------------------------

def test_vehicle_hours_over_budget_is_refused(net, ts, model):
    lim = ContractLimits(veh_hour_budget=100.0)
    out = apply_edits(net, ts, model, [])
    chk = validate_applied(net, out.network, [], lim, veh_hours=100.0)
    assert chk.ok
    chk = validate_applied(net, out.network, [], lim, veh_hours=100.001)
    assert any("vehicle-hours exceeds" in v for v in chk.violations)


def test_peak_vehicles_over_baseline_is_refused_even_within_the_hour_budget(
        net, ts, model):
    lim = ContractLimits(veh_hour_budget=1e9, peak_vehicle_budget=197.0)
    out = apply_edits(net, ts, model, [])
    chk = validate_applied(net, out.network, [], lim, veh_hours=1.0,
                           peak_vehicles=197.0)
    assert chk.ok
    chk = validate_applied(net, out.network, [], lim, veh_hours=1.0,
                           peak_vehicles=198.0)
    assert any("peak vehicles exceeds" in v for v in chk.violations)


# -- gate 3-1, the evaluator states its model ------------------------------

def test_a_model_a_evaluator_is_refused(net, ts, model):
    out = apply_edits(net, ts, model, [])
    chk = validate_applied(net, out.network, [], LIMITS,
                           waiting_model="pattern")
    assert any("Model B" in v for v in chk.violations)


def test_model_b_passes(net, ts, model):
    out = apply_edits(net, ts, model, [])
    chk = validate_applied(net, out.network, [], LIMITS,
                           waiting_model="same_route")
    assert chk.ok, chk.violations


# -- gate 3-4, the disguised consolidation ---------------------------------

def test_dropping_interior_stops_while_keeping_the_alignment_is_refused(
        net, ts, model):
    """A `straighten` that keeps both ends is exactly the forbidden shape."""
    e = GeometryEdit(kind="straighten", route_id="A", drop_stops=("S2",),
                     description="drop an interior stop, same ends")
    out = apply_edits(net, ts, model, [e])
    chk = validate_applied(net, out.network, [e], LIMITS)
    assert any("alignment end to end" in v for v in chk.violations), \
        chk.violations


def test_truncating_a_route_is_not_a_skip_stop_violation(net, ts, model):
    """Shortening a route moves its terminal, so it is a real geometry change."""
    e = GeometryEdit(kind="truncate", route_id="A", drop_stops=("S4",),
                     description="shorten A")
    out = apply_edits(net, ts, model, [e])
    chk = validate_applied(net, out.network, [e], LIMITS)
    assert not any("alignment end to end" in v for v in chk.violations)


# -- gate 3-9, the evidence class ------------------------------------------

def test_modelled_share_sets_the_evidence_class(net, ts, model):
    e = GeometryEdit(kind="add_stop", route_id="C", append_stops=("S3",),
                     description="add S3 to C")
    out = apply_edits(net, ts, model, [e])
    chk = validate_applied(net, out.network, [e], LIMITS, report=out.report)
    assert chk.facts["evidence_class"] in ("primary", "secondary")
    share = chk.facts["modelled_share_pct"]
    assert (chk.facts["evidence_class"] == "primary") == (share <= 2.0)


# -- invalid mutations raise, never no-op ----------------------------------

def test_an_unknown_kind_cannot_even_be_constructed():
    with pytest.raises(ValueError, match="unknown edit kind"):
        GeometryEdit(kind="teleport", route_id="A", description="nope")


def test_an_incomplete_split_cannot_be_constructed():
    with pytest.raises(ValueError, match="junction"):
        GeometryEdit(kind="split", route_id="A", description="cut where?")


def test_an_incomplete_change_terminal_cannot_be_constructed():
    with pytest.raises(ValueError, match="change_terminal needs"):
        GeometryEdit(kind="change_terminal", route_id="A", junction="S4",
                     description="move to where?")
