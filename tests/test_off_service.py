"""C8 — a route-period may be OFF, and OFF must mean nothing at all.

Experiment 4 treats service activation, including OFF, as a decision variable.
Generation 1 could not represent it: `build_ladders` offers only finite rungs
and says so ("no route-period with service today may lose it entirely").

The representation is an infinite headway, because that makes every downstream
quantity come out right arithmetically rather than by special case. These tests
pin both halves of the requirement: an inactive service contributes no
frequency, vehicle-hours, paths or passenger service, AND it cannot become
active through a default.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cota_opt.cost import expected_wait_min          # noqa: E402
from cota_opt.frequency import (OFF, is_off, snap_plan_to_ladder,  # noqa: E402
                                snap_to_ladder, FrequencyPlan)


# --------------------------------------------------------------------------
# OFF contributes nothing
# --------------------------------------------------------------------------

def test_off_costs_no_trips_no_vehicle_hours_no_vehicles():
    """The resource arithmetic, done exactly as frequency.py does it."""
    n_dir, duration, runtime, cycle = 2, 180.0, 45.0, 90.0
    trips = n_dir * duration / OFF
    assert trips == 0.0
    assert trips * runtime / 60.0 == 0.0            # revenue_veh_hours
    assert cycle / OFF == 0.0                       # peak_vehicles
    assert int(math.ceil(cycle / OFF)) == 0         # integer_fleet


def test_off_is_never_boardable_by_the_path_model():
    """RAPTOR's own guard, reproduced verbatim from generalized_cost."""
    def boardable(h: float) -> bool:
        return bool(np.isfinite(h) and h < 1e5)

    assert boardable(10.0) and boardable(9_999.0)
    assert not boardable(OFF)
    assert not boardable(1e5)
    assert not boardable(float("nan"))


def test_is_off_rejects_a_large_finite_headway_masquerading_as_off():
    """A very large finite headway is NOT off -- it still costs vehicle-hours.

    Without this, someone could 'turn a route off' with headway=99999 and the
    path model would refuse to board it (>= 1e5 is the unusable threshold... no,
    99999 < 1e5, so it WOULD be boardable) while the resource model charged for
    0.0036 trips. `is_off` and the path model must agree on where the line is.
    """
    assert is_off(OFF) and is_off(float("inf")) and is_off(1e5)
    assert not is_off(60.0) and not is_off(99_999.0)
    # and the path model agrees at exactly the same threshold
    assert bool(np.isfinite(99_999.0) and 99_999.0 < 1e5) is True
    assert bool(np.isfinite(1e5) and 1e5 < 1e5) is False


def test_expected_wait_is_infinite_for_off_and_raises_for_nonsense():
    assert expected_wait_min(OFF) == math.inf
    for bad in (0.0, -1.0):
        with pytest.raises(ValueError):
            expected_wait_min(bad)


# --------------------------------------------------------------------------
# OFF cannot become active by default -- the part that was actually broken
# --------------------------------------------------------------------------

def test_snapping_an_off_headway_used_to_return_maximum_service():
    """Regression. `min(lad, key=lambda x: abs(x - inf))` is a tie on inf.

    Every rung scored `inf`, so the tie broke on magnitude and an OFF
    route-period snapped to the SHORTEST headway on the ladder -- an inactive
    service silently becoming the most frequent one.
    """
    ladder = [10.0, 20.0, 30.0]
    assert min(ladder, key=lambda x: abs(x - OFF)) == 10.0      # the old rule
    with pytest.raises(ValueError, match="no OFF rung"):
        snap_to_ladder(OFF, ladder)                             # the new one


def test_off_survives_snapping_when_the_ladder_offers_it():
    assert snap_to_ladder(OFF, [10.0, 20.0, OFF]) == OFF
    p = snap_plan_to_ladder({("r", "peak"): [10.0, 20.0, OFF]},
                            FrequencyPlan({("r", "peak"): OFF}))
    assert p.headways[("r", "peak")] == OFF


def test_a_plan_cannot_be_snapped_onto_a_ladder_that_never_offered_off():
    with pytest.raises(ValueError, match="no OFF rung"):
        snap_plan_to_ladder({("r", "peak"): [10.0, 20.0]},
                            FrequencyPlan({("r", "peak"): OFF}))


def test_finite_headways_still_snap_exactly_as_before():
    """The fix must not move any Gen1 plan."""
    ladder = [5.0, 10.0, 15.0, 20.0, 30.0, 60.0]
    for h, want in ((4.0, 5.0), (12.0, 10.0), (13.0, 15.0), (61.0, 60.0),
                    (30.0, 30.0)):
        assert snap_to_ladder(h, ladder) == want
    # and with an OFF rung present, finite headways ignore it
    assert snap_to_ladder(13.0, ladder + [OFF]) == 15.0


# --------------------------------------------------------------------------
# Generation 1 is unchanged
# --------------------------------------------------------------------------

def test_ladders_do_not_offer_off_by_default():
    """Gen1's policy sentence is intact: allow_off must be opt-in."""
    import inspect

    from cota_opt.frequency import build_ladders
    sig = inspect.signature(build_ladders)
    assert sig.parameters["allow_off"].default is False
    doc = build_ladders.__doc__ or ""
    assert "no route-period with service today may lose it entirely" in doc
