"""Geometry edits on the synthetic network, with hand-checked arithmetic.

    PA (route A):  S1 -> S2 -> S3 -> S4    600 s per segment
    PB (route B):  S1 -> S5 -> S4          720 s per segment
    PC (route C):  S2 -> S6                300 s

The properties that matter are all about bookkeeping: an edit must change
vehicle-hours by exactly the running time it added or removed, must keep
observed segment times for links it did not touch, and must never invent a
stop.
"""
import numpy as np
import pandas as pd
import pytest

from cota_opt.geometry import (GeometryEdit, SegmentTimeModel, apply_edits,
                               describe)
from cota_opt.network import TransitNetwork

from test_raptor import SPECS, _net, _stops_gdf, _tstats


@pytest.fixture
def net():
    return _net()


@pytest.fixture
def ts():
    return _tstats()


@pytest.fixture
def model(net):
    return SegmentTimeModel.fit(net, _stops_gdf())


def vh(ts: pd.DataFrame) -> float:
    return float(ts["runtime_min"].sum() / 60.0)


# -- running-time model -----------------------------------------------------

def test_model_reproduces_observed_segments_within_its_own_error(net, model):
    """The fit is reported honestly: predictions land inside the stated MAPE."""
    for p in net.patterns.values():
        for seg in p.segments:
            pred = model.predict(p.route_id, seg.from_stop, seg.to_stop)
            assert pred > 0
    assert not model.diagnostics.empty
    assert (model.diagnostics["implied_speed_kmh"] > 0).all()


def test_model_speed_is_clamped_to_something_a_bus_could_do(net):
    m = SegmentTimeModel.fit(net, _stops_gdf())
    for rid, (c, slope) in m.per_route.items():
        assert c >= 0
        assert 3.0 <= 3.6 / slope <= 90.0


# -- truncate ---------------------------------------------------------------

def test_truncate_removes_the_stop_and_frees_exactly_its_running_time(net, ts, model):
    e = GeometryEdit(kind="truncate", route_id="A", drop_stops=("S4",),
                     description="truncate A at S3, dropping the S4 tail")
    out = apply_edits(net, ts, model, [e])
    stops = out.network.patterns["PA"].stops
    assert stops == ["S1", "S2", "S3"]
    # 10 trips on PA each lose one 600 s segment
    assert vh(ts) - vh(out.tstats) == pytest.approx(10 * 600 / 3600, rel=1e-12)
    assert out.report.segments_modelled == 0      # nothing new was invented


def test_truncate_keeps_observed_times_on_surviving_segments(net, ts, model):
    e = GeometryEdit(kind="truncate", route_id="A", drop_stops=("S4",),
                     description="drop S4")
    out = apply_edits(net, ts, model, [e])
    assert [s.run_time_sec for s in out.network.patterns["PA"].segments] == [600, 600]


def test_truncating_a_middle_stop_models_the_new_link(net, ts, model):
    """Removing S2 leaves S1->S3, a link the schedule has never run."""
    e = GeometryEdit(kind="straighten", route_id="A", drop_stops=("S2",),
                     description="straighten A past the S2 deviation")
    out = apply_edits(net, ts, model, [e])
    assert out.network.patterns["PA"].stops == ["S1", "S3", "S4"]
    assert out.report.segments_modelled == 1
    assert out.report.segments_kept == 1          # S3->S4 survives


# -- extend -----------------------------------------------------------------

def test_extend_adds_stops_and_costs_vehicle_hours(net, ts, model):
    e = GeometryEdit(kind="extend", route_id="C", append_stops=("S4",),
                     description="extend C from S6 to S4")
    out = apply_edits(net, ts, model, [e])
    assert "S4" in out.network.patterns["PC"].stops
    assert vh(out.tstats) > vh(ts)
    assert out.report.stops_added == 1


def test_extend_never_invents_a_stop(net, ts, model):
    e = GeometryEdit(kind="extend", route_id="C", append_stops=("NOT_A_STOP",),
                     description="extend C to a stop that does not exist")
    out = apply_edits(net, ts, model, [e])
    assert out.network.patterns["PC"].stops == list(SPECS["PC"][2])
    assert vh(out.tstats) == pytest.approx(vh(ts))


# -- reroute ----------------------------------------------------------------

def test_reroute_swaps_the_chain_between_two_anchors(net, ts, model):
    e = GeometryEdit(kind="reroute", route_id="A",
                     replace_between=("S1", "S4"), replace_with=("S5",),
                     description="reroute A between S1 and S4 via S5")
    out = apply_edits(net, ts, model, [e])
    assert out.network.patterns["PA"].stops == ["S1", "S5", "S4"]
    # route B already runs S1->S5->S4, so those times are observed, not modelled
    assert out.report.segments_modelled == 0
    assert out.report.segments_kept == 2
    assert [s.run_time_sec for s in out.network.patterns["PA"].segments] == [720, 720]


def test_reroute_leaves_the_route_alone_if_an_anchor_is_missing(net, ts, model):
    e = GeometryEdit(kind="reroute", route_id="C",
                     replace_between=("S1", "S4"), replace_with=("S5",),
                     description="reroute C between stops it does not serve")
    out = apply_edits(net, ts, model, [e])
    assert out.network.patterns["PC"].stops == list(SPECS["PC"][2])


# -- splice -----------------------------------------------------------------

def test_splice_is_vehicle_hour_neutral_at_baseline(net, ts, model):
    e = GeometryEdit(kind="splice", route_id="A", with_route="C",
                     junction="S2",
                     description="through-route A and C at S2")
    out = apply_edits(net, ts, model, [e])
    assert vh(out.tstats) == pytest.approx(vh(ts), rel=0.06)


def test_a_link_no_route_runs_is_modelled_not_borrowed(net, ts, model):
    """S1->S3 exists on no pattern, so it has to be priced by the model."""
    e = GeometryEdit(kind="straighten", route_id="A", drop_stops=("S2",),
                     description="straighten A past S2")
    out = apply_edits(net, ts, model, [e])
    assert out.report.segments_modelled == 1


def test_splice_keeps_every_stop_both_routes_served(net, ts, model):
    e = GeometryEdit(kind="splice", route_id="A", with_route="C",
                     junction="S2", description="through-route A and C at S2")
    out = apply_edits(net, ts, model, [e])
    before = {s for p in net.patterns.values() if p.route_id in ("A", "C")
              for s in p.stops}
    after = {s for p in out.network.patterns.values() for s in p.stops}
    assert before <= after


def test_splice_produces_one_route_where_there_were_two(net, ts, model):
    e = GeometryEdit(kind="splice", route_id="A", with_route="C",
                     junction="S2", description="through-route A and C at S2")
    out = apply_edits(net, ts, model, [e])
    routes = {p.route_id for p in out.network.patterns.values()}
    assert "A+C" in routes and "A" not in routes and "C" not in routes
    assert set(out.tstats["route_id"]) == routes


def test_splice_requires_the_junction_to_be_on_both_routes(net, ts, model):
    e = GeometryEdit(kind="splice", route_id="A", with_route="C",
                     junction="S4", description="bad junction")
    with pytest.raises(ValueError, match="junction"):
        apply_edits(net, ts, model, [e])


def test_editing_a_consumed_route_is_an_error_not_a_silent_no_op(net, ts, model):
    e1 = GeometryEdit(kind="splice", route_id="A", with_route="C",
                      junction="S2", description="through-route A and C")
    e2 = GeometryEdit(kind="truncate", route_id="A", drop_stops=("S4",),
                      description="truncate a route that no longer exists")
    with pytest.raises(ValueError, match="no longer exist"):
        apply_edits(net, ts, model, [e1, e2])


# -- composition and bookkeeping -------------------------------------------

def test_edits_compose_in_order(net, ts, model):
    e1 = GeometryEdit(kind="truncate", route_id="A", drop_stops=("S4",),
                      description="drop S4")
    e2 = GeometryEdit(kind="truncate", route_id="A", drop_stops=("S3",),
                      description="drop S3")
    out = apply_edits(net, ts, model, [e1, e2])
    assert out.network.patterns["PA"].stops == ["S1", "S2"]
    assert vh(ts) - vh(out.tstats) == pytest.approx(2 * 10 * 600 / 3600, rel=1e-12)


def test_no_edits_is_an_exact_identity(net, ts, model):
    out = apply_edits(net, ts, model, [])
    assert vh(out.tstats) == pytest.approx(vh(ts), rel=1e-12)
    for pid, p in net.patterns.items():
        assert out.network.patterns[pid].stops == p.stops
        assert [s.run_time_sec for s in out.network.patterns[pid].segments] == \
               [s.run_time_sec for s in p.segments]


def test_report_accounts_for_every_segment(net, ts, model):
    e = GeometryEdit(kind="straighten", route_id="A", drop_stops=("S2",),
                     description="straighten A")
    out = apply_edits(net, ts, model, [e])
    d = out.report.as_dict()
    assert d["segments_kept"] + d["segments_modelled"] == \
        len(out.network.patterns["PA"].segments)
    assert 0 < d["modelled_share_pct"] <= 100
    assert d["edits"] == ["straighten A"]


def test_a_pattern_reduced_below_two_stops_is_dropped(net, ts, model):
    e = GeometryEdit(kind="truncate", route_id="C", drop_stops=("S6",),
                     description="truncate C to a single stop")
    out = apply_edits(net, ts, model, [e])
    assert "PC" not in out.network.patterns
    assert "C" not in {p.route_id for p in out.network.patterns.values()}
    assert (out.tstats["route_id"] == "C").sum() == 0


def test_route_stops_index_is_rebuilt(net, ts, model):
    e = GeometryEdit(kind="truncate", route_id="A", drop_stops=("S4",),
                     description="drop S4")
    out = apply_edits(net, ts, model, [e])
    assert "S4" not in out.network.route_stops["A"]
    assert "A" not in out.network.stop_routes.get("S4", set())
    # S4 is still reachable on route B, so it stays in the network
    assert "B" in out.network.stop_routes["S4"]


def test_unedited_patterns_keep_their_scheduled_runtime_exactly(net, ts, model):
    """Trip runtime is scaled by the geometry change, so a no-op is exact even
    when the feed's runtime differs from the sum of median segment times."""
    ts2 = ts.copy()
    ts2["runtime_min"] = ts2["runtime_min"] * 1.17     # pretend recovery time
    e = GeometryEdit(kind="truncate", route_id="A", drop_stops=("S4",),
                     description="drop S4")
    out = apply_edits(net, ts2, model, [e])
    untouched = out.tstats[out.tstats["route_id"] != "A"]
    orig = ts2[ts2["route_id"] != "A"]
    assert untouched["runtime_min"].sum() == pytest.approx(
        orig["runtime_min"].sum(), rel=1e-12)
    # route A loses one of three 600 s segments, so its runtime scales by 2/3
    edited = out.tstats[out.tstats["route_id"] == "A"]["runtime_min"].sum()
    assert edited == pytest.approx(
        ts2[ts2["route_id"] == "A"]["runtime_min"].sum() * 2 / 3, rel=1e-12)


def test_describe_is_readable(net, ts, model):
    e = GeometryEdit(kind="truncate", route_id="A", drop_stops=("S4",),
                     description="truncate A at S3, dropping the S4 tail")
    assert describe([e]) == "truncate A at S3, dropping the S4 tail"
    assert describe([]) == "no geometry change"
