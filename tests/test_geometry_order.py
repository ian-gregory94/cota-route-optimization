"""A network state is a SET of mutations, and this is what makes that true.

Experiment 3 caches, compares and de-duplicates network states by a content
digest. That digest is only sound if two searches reaching the same set of
mutations by different paths produce the same network — which is a property of
`apply_edits`, not of the digest function. So it is asserted here on the real
transform rather than assumed in the hashing code.

The property holds because at most one mutation may name a given route. Remove
that rule and these tests fail, which is the point of having them.
"""
import itertools

import pytest

from cota_opt.geometry import (GeometryEdit, SegmentTimeModel, apply_edits,
                               EDIT_KINDS, CONSUMING_KINDS)

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


def _shape(out):
    """Everything about the result a comparison could depend on."""
    return (
        sorted((p.route_id, p.direction_id, tuple(p.stops),
                tuple(round(s.run_time_sec, 6) for s in p.segments))
               for p in out.network.patterns.values()),
        round(float(out.tstats["runtime_min"].sum()), 6),
        len(out.tstats),
    )


def test_disjoint_edits_are_order_free(net, ts, model):
    a = GeometryEdit(kind="truncate", route_id="A", drop_stops=("S4",),
                     description="drop S4 from A")
    b = GeometryEdit(kind="truncate", route_id="B", drop_stops=("S5",),
                     description="drop S5 from B")
    c = GeometryEdit(kind="add_stop", route_id="C", append_stops=("S3",),
                     description="add S3 to C")

    shapes = [(tuple(e.key for e in order),
               _shape(apply_edits(net, ts, model, list(order))))
              for order in itertools.permutations([a, b, c])]
    first = shapes[0][1]
    for keys, shape in shapes:
        assert shape == first, (
            "applying the same set of route-disjoint mutations in a different "
            f"order changed the network: {list(keys)}")


def test_order_freedom_survives_a_consuming_edit(net, ts, model):
    """A splice consumes two routes; it still may not depend on when it ran."""
    sp = GeometryEdit(kind="splice", route_id="A", with_route="C",
                      junction="S2", description="through-route A and C")
    tr = GeometryEdit(kind="truncate", route_id="B", drop_stops=("S5",),
                      description="drop S5 from B")
    one = _shape(apply_edits(net, ts, model, [sp, tr]))
    two = _shape(apply_edits(net, ts, model, [tr, sp]))
    assert one == two


def test_every_declared_kind_is_constructible(net, ts, model):
    """The contract may not advertise an operation the code cannot build.

    One instance of every kind in EDIT_KINDS, applied for real. A kind that
    only exists in the table would let a reader budget search freedom that does
    not exist.
    """
    built = {
        "truncate": GeometryEdit(kind="truncate", route_id="A",
                                 drop_stops=("S4",), description="t"),
        "straighten": GeometryEdit(kind="straighten", route_id="A",
                                   drop_stops=("S2",), description="s"),
        "extend": GeometryEdit(kind="extend", route_id="C",
                               append_stops=("S4",), description="e"),
        "reroute": GeometryEdit(kind="reroute", route_id="A",
                                replace_between=("S1", "S3"),
                                replace_with=("S5",), description="r"),
        "splice": GeometryEdit(kind="splice", route_id="A", with_route="C",
                               junction="S2", description="p"),
        "add_stop": GeometryEdit(kind="add_stop", route_id="A",
                                 append_stops=("S6",), description="a"),
        "change_terminal": GeometryEdit(kind="change_terminal", route_id="A",
                                        junction="S4", append_stops=("S6",),
                                        description="c"),
        "split": GeometryEdit(kind="split", route_id="A", junction="S2",
                              description="x"),
    }
    assert set(built) == set(EDIT_KINDS), (
        "EDIT_KINDS and the constructible set disagree: "
        f"{set(EDIT_KINDS) ^ set(built)}")
    for kind, e in built.items():
        out = apply_edits(net, ts, model, [e])
        assert out.network.patterns, f"{kind} produced an empty network"


def test_split_raises_route_count_and_holds_vehicle_hours(net, ts, model):
    before_routes = {p.route_id for p in net.patterns.values()}
    before_vh = float(ts["runtime_min"].sum() / 60.0)
    e = GeometryEdit(kind="split", route_id="A", junction="S2",
                     description="cut A at S2")
    out = apply_edits(net, ts, model, [e])
    after_routes = {p.route_id for p in out.network.patterns.values()}

    assert "A" not in after_routes
    assert {"Aa", "Ab"} <= after_routes
    assert len(after_routes) == len(before_routes) + 1
    # Each original trip becomes one trip on each half, splitting the original
    # running time between them — so the pair costs what the whole cost.
    after_vh = float(out.tstats["runtime_min"].sum() / 60.0)
    assert after_vh == pytest.approx(before_vh, rel=1e-9)


def test_split_at_a_terminal_is_refused(net, ts, model):
    e = GeometryEdit(kind="split", route_id="A", junction="S1",
                     description="cut A at its own terminal")
    with pytest.raises(ValueError, match="terminal"):
        apply_edits(net, ts, model, [e])


def test_splitting_keeps_the_junction_on_both_halves(net, ts, model):
    e = GeometryEdit(kind="split", route_id="A", junction="S2",
                     description="cut A at S2")
    out = apply_edits(net, ts, model, [e])
    halves = {}
    for p in out.network.patterns.values():
        if p.route_id in ("Aa", "Ab"):
            halves.setdefault(p.route_id, set()).update(p.stops)
    assert "S2" in halves["Aa"] and "S2" in halves["Ab"], (
        "a rider who used to stay aboard must still be able to transfer")


def test_add_stop_is_deterministic(net, ts, model):
    e = GeometryEdit(kind="add_stop", route_id="A", append_stops=("S6",),
                     description="add S6 to A")
    runs = [_shape(apply_edits(net, ts, model, [e])) for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]


def test_change_terminal_moves_the_end_and_nothing_else(net, ts, model):
    e = GeometryEdit(kind="change_terminal", route_id="A", junction="S4",
                     append_stops=("S6",), description="move A's terminal")
    out = apply_edits(net, ts, model, [e])
    stops = out.network.patterns["PA"].stops
    assert stops[-1] == "S6"
    assert stops[:-1] == ["S1", "S2", "S3"]


def test_consuming_kinds_are_the_ones_that_replace_route_ids(net, ts, model):
    """CONSUMING_KINDS is a claim about behaviour; check it against behaviour."""
    cases = {
        "splice": GeometryEdit(kind="splice", route_id="A", with_route="C",
                               junction="S2", description="p"),
        "split": GeometryEdit(kind="split", route_id="A", junction="S2",
                              description="x"),
        "truncate": GeometryEdit(kind="truncate", route_id="A",
                                 drop_stops=("S4",), description="t"),
    }
    for kind, e in cases.items():
        out = apply_edits(net, ts, model, [e])
        gone = "A" not in {p.route_id for p in out.network.patterns.values()}
        assert gone == (kind in CONSUMING_KINDS), (
            f"{kind}: consumed={gone} but CONSUMING_KINDS says "
            f"{kind in CONSUMING_KINDS}")
