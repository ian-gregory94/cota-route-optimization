"""Block reconstruction, with concurrency worked out by hand.

Two blocks:
  B1  08:00-09:00 and 09:30-10:30   (route A, then route B: interlined)
  B2  08:30-09:30                   (route A)

So two vehicles are out from 08:30 to 09:00, one otherwise, and the peak is 2.
"""
import numpy as np
import pandas as pd
import pytest

from cota_opt.blocks import (fleet_estimate, interlining_factor, reconstruct,
                             routewise_peak)

H = 3600.0


def _frames():
    rows = [
        ("t1", "A", "B1", 8 * H, 9 * H, 60.0),
        ("t2", "B", "B1", 9.5 * H, 10.5 * H, 60.0),
        ("t3", "A", "B2", 8.5 * H, 9.5 * H, 60.0),
    ]
    tstats = pd.DataFrame(rows, columns=["trip_id", "route_id", "block_id",
                                         "first_dep_sec", "last_arr_sec",
                                         "runtime_min"])
    trips = tstats[["trip_id", "block_id"]].copy()
    return trips, tstats.drop(columns=["block_id"])


def test_peak_is_the_largest_number_of_blocks_in_service():
    trips, tstats = _frames()
    p = reconstruct(trips, tstats)
    assert p.peak_vehicles == 2
    assert 8 * 60 + 30 <= p.peak_minute < 9 * 60


def test_block_span_includes_layover_between_trips():
    trips, tstats = _frames()
    p = reconstruct(trips, tstats)
    b1 = p.blocks.set_index("block_id").loc["B1"]
    assert b1["span_hours"] == pytest.approx(2.5)
    assert b1["run_minutes"] == pytest.approx(120.0)
    assert b1["layover_minutes"] == pytest.approx(30.0)


def test_interlining_is_detected():
    trips, tstats = _frames()
    p = reconstruct(trips, tstats)
    assert p.interline_share == pytest.approx(0.5)      # B1 of {B1, B2}
    assert p.blocks.set_index("block_id").loc["B1", "routes"] == "A+B"


def test_layover_share_is_the_idle_fraction_of_all_block_spans():
    trips, tstats = _frames()
    p = reconstruct(trips, tstats)
    # spans 150 + 60 = 210 min, running 120 + 60 = 180, so 30/210
    assert p.layover_share == pytest.approx(30 / 210)


def test_period_peaks_use_their_own_windows():
    trips, tstats = _frames()
    p = reconstruct(trips, tstats,
                    periods={"am": (8.0, 9.0), "late": (10.0, 11.0)})
    assert p.peak_by_period["am"] == 2
    assert p.peak_by_period["late"] == 1


def test_a_feed_without_block_id_says_so():
    trips, tstats = _frames()
    with pytest.raises(ValueError, match="no block_id"):
        reconstruct(trips.drop(columns=["block_id"]), tstats)


class _Svc:
    def __init__(self, runtime, ndir):
        self.runtime_min = runtime
        self.n_directions = ndir


def test_routewise_peak_is_cycle_over_headway_summed():
    services = {("A", "am"): _Svc(30.0, 2), ("B", "am"): _Svc(20.0, 2)}
    hw = {("A", "am"): 15.0, ("B", "am"): 10.0}
    rw = routewise_peak(services, hw, {"am": None})
    # A: 60/15 = 4 buses, B: 40/10 = 4 buses
    assert rw["am"] == pytest.approx(8.0)


def test_interlining_factor_is_below_one_when_blocking_helps():
    assert interlining_factor(6, {"am": 8.0}) == pytest.approx(0.75)


def test_fleet_estimate_attributes_the_peak_to_routes():
    services = {("A", "am"): _Svc(30.0, 2), ("B", "am"): _Svc(20.0, 2)}
    hw = {("A", "am"): 15.0, ("B", "am"): 10.0}
    est = fleet_estimate(services, hw, {"am": None}, factor=0.75)
    assert est["routewise_peak"] == pytest.approx(8.0)
    assert est["blocked_peak_proxy"] == pytest.approx(6.0)
    assert est["per_route_at_peak"] == {"A": pytest.approx(4.0),
                                        "B": pytest.approx(4.0)}
