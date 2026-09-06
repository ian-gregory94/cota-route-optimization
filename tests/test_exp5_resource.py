"""Experiment 5 resource semantics, and the envelope errors that got us here.

Every negative test below corresponds to a mistake actually made or actually
available. A cap was read off an evaluated plan's usage; a scalar stood in for a
six-period vector; a concurrency proxy was mistaken for a fleet count. These
fail loudly now.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cota_opt.exp5_resource import (FLEET_ROUNDING, LEVELS,     # noqa: E402
                                    REJECTED_AS_CAP,
                                    Exp5Feasibility, ResourceCell,
                                    ResourceEnvelope, ResourceError,
                                    ResourceUsage, cell_id, grid_digest,
                                    load_canonical, nested, stage_a_grid,
                                    stage_b_grid)

CANON = ROOT / "outputs" / "CANONICAL_ENVELOPE.json"
CANON_HOURS = 2517.183333
CANON_FLEET = {"early": 135, "am_peak": 187, "midday": 173,
               "pm_peak": 197, "evening": 178, "owl": 149}


def _canon() -> ResourceEnvelope:
    return ResourceEnvelope(revenue_veh_hours=CANON_HOURS,
                            fleet_by_period=dict(CANON_FLEET),
                            source="canonical_artifact",
                            canonical_digest="test")


# ---------------------------------------------------------------------------
# the positive test: 100% reconstructs exactly
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not CANON.exists(), reason="envelope not frozen here")
def test_the_100_percent_cell_reconstructs_the_canonical_envelope_exactly():
    canon = load_canonical()
    before = canon.digest
    r100 = next(c for c in stage_a_grid(canon) if c.id == "R100")
    assert r100.envelope.revenue_veh_hours == pytest.approx(
        CANON_HOURS, abs=1e-6)
    assert dict(r100.envelope.fleet_by_period) == CANON_FLEET
    assert canon.digest == before, "reading the grid mutated the canonical envelope"
    assert r100.envelope.canonical_digest == canon.canonical_digest


@pytest.mark.skipif(not CANON.exists(), reason="envelope not frozen here")
def test_canonical_is_loaded_from_the_artifact_not_recomputed():
    d = json.loads(CANON.read_text())
    canon = load_canonical()
    assert canon.revenue_veh_hours == float(d["weekday_revenue_vehicle_hours"])
    assert dict(canon.fleet_by_period) == {k: int(v) for k, v in
                                           d["peak_vehicles_by_period"].items()}
    assert canon.canonical_digest == d["envelope_digest"]


def test_there_is_no_second_path_to_the_canonical_constants():
    """A module that hard-codes them is a module that will disagree later."""
    src = ROOT.joinpath("src/cota_opt/exp5_resource.py").read_text()
    code = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("#"))
    body = code.split('"""', 2)[-1]           # drop the module docstring
    for forbidden in ("2517.183", "2517.18", "= 197", "=197"):
        assert forbidden not in body, (
            f"{forbidden!r} is hard-coded in exp5_resource; the canonical "
            f"constants come from CANONICAL_ENVELOPE.json only")


# ---------------------------------------------------------------------------
# the numbers that are NOT caps
# ---------------------------------------------------------------------------

def test_the_rejected_cap_list_names_every_near_miss():
    for k in ("FitnessVector.peak_vehicles", "routewise_peak", "ntd_voms_198",
              "optimized_plan_realized_veh_hours", "scalar_fleet_cap",
              "concurrency_times_interlining_factor"):
        assert k in REJECTED_AS_CAP


def test_a_scalar_fleet_cap_is_refused():
    with pytest.raises(ResourceError, match="per period"):
        ResourceEnvelope(revenue_veh_hours=CANON_HOURS, fleet_by_period={})


def test_a_fractional_fleet_cap_is_refused():
    """Block-derived fleet is a count of buses. 176.49 is not a bus count."""
    with pytest.raises(ResourceError, match="count of vehicles"):
        ResourceEnvelope(revenue_veh_hours=CANON_HOURS,
                         fleet_by_period={**CANON_FLEET, "pm_peak": 176.49})


def test_concurrency_semantics_are_refused_at_construction():
    with pytest.raises(ResourceError, match="block-derived"):
        ResourceEnvelope(revenue_veh_hours=CANON_HOURS,
                         fleet_by_period=dict(CANON_FLEET),
                         fleet_semantics="peak_concurrency")


def test_feasibility_refuses_a_non_block_fleet_source():
    """§7: concurrency may be stored alongside; it may not decide the boolean."""
    with pytest.raises(ResourceError, match="not a block-derived"):
        Exp5Feasibility(cell_id="R100", feasible=True, reasons=[],
                        hours_used=1.0, fleet_used_by_period={"pm_peak": 1},
                        fleet_source="FitnessVector.peak_vehicles")


def test_concurrency_rides_along_as_a_diagnostic_only():
    f = Exp5Feasibility(cell_id="R100", feasible=True, reasons=[],
                        hours_used=1.0, fleet_used_by_period={"pm_peak": 190},
                        fleet_source="blocks.reconstruct",
                        concurrency_diagnostic={"pm_peak": 176.49})
    pay = f.payload()
    assert pay["feasible"] is True
    assert "concurrency_diagnostic_NOT_A_CAP" in pay
    assert pay["fleet_source"].startswith("block")


# ---------------------------------------------------------------------------
# scaling: floor, never upward, hours exact
# ---------------------------------------------------------------------------

def test_fleet_scales_by_floor_and_never_grants_more_than_nominal():
    canon = _canon()
    for m in LEVELS:
        env = canon.scale(m, m)
        for p, base in CANON_FLEET.items():
            got = env.fleet_by_period[p]
            assert got == math.floor(m * base)
            assert got <= m * base + 1e-9, (
                f"{p} at {m:.0%} granted {got} against a nominal "
                f"{m * base:.3f} -- rounding up hands out resources the level "
                f"does not authorise")


def test_the_rounding_rule_is_floor_and_is_pinned():
    assert FLEET_ROUNDING == "floor"
    canon = _canon()
    env = canon.scale(1.10, 1.10)
    # pm_peak: floor(216.7) = 216, emphatically not 217
    assert env.fleet_by_period["pm_peak"] == 216


def test_hours_scale_exactly_and_are_not_rounded():
    canon = _canon()
    env = canon.scale(1.25, 1.25)
    assert env.revenue_veh_hours == pytest.approx(CANON_HOURS * 1.25, abs=1e-9)
    assert env.revenue_veh_hours != math.floor(env.revenue_veh_hours)


def test_scaling_a_scaled_envelope_is_refused():
    canon = _canon()
    with pytest.raises(ResourceError, match="canonical envelope only"):
        canon.scale(1.10, 1.10).scale(1.10, 1.10)


def test_hours_and_fleet_never_collapse_into_one_scalar():
    canon = _canon()
    env = canon.scale(1.50, 0.75)
    assert env.hours_pct == 1.50 and env.fleet_pct == 0.75
    pay = env.payload()
    assert "revenue_veh_hours_cap" in pay and "fleet_by_period_cap" in pay
    assert not any("resources" == k for k in pay)


# ---------------------------------------------------------------------------
# cell identity is the envelope, not the label
# ---------------------------------------------------------------------------

def test_cell_identity_depends_on_the_envelope_not_the_label():
    canon = _canon()
    a = ResourceCell("100%", "diagonal", canon.scale(1.0, 1.0))
    b = ResourceCell("100%", "diagonal", canon.scale(1.10, 1.10))
    assert a != b and hash(a) != hash(b), (
        "two different envelopes displayed with the same label compared equal")
    c = ResourceCell("something else", "diagonal", canon.scale(1.0, 1.0))
    assert a == c, "relabelling changed a cell's identity"


def test_cell_payload_carries_everything_section_6_requires():
    canon = _canon()
    cell = stage_a_grid(canon)[0]
    p = cell.payload()
    for k in ("hours_multiplier", "fleet_multiplier", "revenue_veh_hours_cap",
              "fleet_by_period_cap", "canonical_envelope_digest",
              "scaling_rule"):
        assert k in p, f"cell payload is missing {k}"
    assert len(p["fleet_by_period_cap"]) == 6


# ---------------------------------------------------------------------------
# feasibility: both dimensions, all six periods
# ---------------------------------------------------------------------------

def test_all_six_fleet_periods_must_pass_independently():
    canon = _canon()
    used = {p: v - 1 for p, v in CANON_FLEET.items()}
    ok, why = canon.feasible(CANON_HOURS - 1, used)
    assert ok, why
    used["owl"] = CANON_FLEET["owl"] + 1        # one period over
    ok, why = canon.feasible(CANON_HOURS - 1, used)
    assert not ok and any("owl" in w for w in why)


def test_a_missing_period_is_a_failure_not_a_pass():
    canon = _canon()
    used = {p: 1 for p in CANON_FLEET if p != "midday"}
    ok, why = canon.feasible(1.0, used)
    assert not ok and any("midday" in w for w in why)


def test_hours_and_fleet_are_tested_separately():
    canon = _canon()
    ok, why = canon.feasible(CANON_HOURS + 1, {p: 0 for p in CANON_FLEET})
    assert not ok and any("hours" in w for w in why)


# ---------------------------------------------------------------------------
# nesting (E5-4) and the grids
# ---------------------------------------------------------------------------

def test_nesting_holds_across_the_whole_preregistered_grid():
    canon = _canon()
    cells = stage_a_grid(canon) + stage_b_grid(canon)
    ok, problems = nested(cells)
    assert ok, problems


def test_a_dominating_cell_admits_every_schedule_the_dominated_one_admits():
    """The property §8 asks to be tested explicitly."""
    canon = _canon()
    lo = canon.scale(0.90, 0.90)
    hi = canon.scale(1.25, 1.25)
    assert hi.dominates(lo)
    # any usage feasible under lo must be feasible under hi
    used_hours = lo.revenue_veh_hours
    used_fleet = dict(lo.fleet_by_period)
    assert lo.feasible(used_hours, used_fleet)[0]
    assert hi.feasible(used_hours, used_fleet)[0]


def test_stage_b_does_not_re_emit_the_shared_100_cell():
    canon = _canon()
    b = stage_b_grid(canon)
    assert not any(c.id == "R100" for c in b)
    assert len({c.id for c in b}) == len(b)


def test_grids_are_deterministic():
    canon = _canon()
    assert grid_digest(stage_a_grid(canon)) == grid_digest(stage_a_grid(canon))


def test_cell_ids_distinguish_the_axes():
    assert cell_id(1.0, 1.0) == "R100"
    assert cell_id(1.25, 1.0) == "H125"
    assert cell_id(1.0, 1.25) == "F125"


# ---------------------------------------------------------------------------
# usage accounting keeps allowed and used apart (§12)
# ---------------------------------------------------------------------------

def test_usage_separates_allowed_from_used_and_reports_binding():
    u = ResourceUsage(hours_cap=1000.0, hours_used=900.0,
                      fleet_cap_by_period={"pm_peak": 197, "owl": 149},
                      fleet_used_by_period={"pm_peak": 197, "owl": 100})
    assert u.hours_slack == pytest.approx(100.0)
    assert not u.hours_binding
    assert u.fleet_binding()["pm_peak"] is True
    assert u.fleet_binding()["owl"] is False
    assert u.any_fleet_binding


# ---------------------------------------------------------------------------
# the specific wrong numbers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("wrong", [2507.0, 2507.763673])
def test_the_wrong_hours_figures_are_not_the_canonical_cap(wrong):
    assert abs(wrong - CANON_HOURS) > 1.0
    if CANON.exists():
        assert load_canonical().revenue_veh_hours != pytest.approx(wrong,
                                                                   abs=1e-6)


@pytest.mark.parametrize("wrong", [197, 198, 200, 176, 150])
def test_no_single_number_is_the_fleet_envelope(wrong):
    """Even 197 alone is not the envelope: the envelope is six numbers.

    The first version of this test passed a one-entry dict and expected a
    refusal that did not come -- ResourceEnvelope accepted {"all": 197}, a
    scalar cap in a dict costume that satisfies every "is it a mapping?" check.
    The class now refuses it, which is the real fix; this is the test that
    found it.
    """
    with pytest.raises(ResourceError, match="dict costume"):
        ResourceEnvelope(revenue_veh_hours=CANON_HOURS,
                         fleet_by_period={"all": wrong})
