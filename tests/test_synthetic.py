"""The synthetic representation, and the facts about COTA that constrain it.

Experiment 4 releases route identity, so its representation cannot lean on
legacy route ids for anything — not for pairing directions, not for identity,
not for de-duplication. These pin the properties the search depends on, and one
data fact that broke the first implementation outright.
"""
import json
from pathlib import Path

import pytest

from cota_opt.synthetic import (HEADWAY_LADDER, MAX_ONEWAY_MIN, MIN_ONEWAY_MIN,
                                OFF, SyntheticNetwork, SyntheticRoute)

RECON = (Path(__file__).resolve().parents[1] / "outputs" / "exp4"
         / "reconstruction.json")


def R(ob, ib, **kw):
    kw.setdefault("outbound_sec", 1800.0)
    kw.setdefault("inbound_sec", 1800.0)
    return SyntheticRoute(outbound=tuple(ob), inbound=tuple(ib), **kw)


# -- canonical identity ----------------------------------------------------

def test_identity_is_geometry_not_discovery_order():
    a = R(["A", "B", "C"], ["Cw", "Bw", "Aw"])
    b = R(["A", "B", "C"], ["Cw", "Bw", "Aw"], provenance="found later")
    assert a.rid == b.rid


def test_identity_is_direction_symmetric():
    """The same physical line found from either end is one line, not two."""
    a = R(["A", "B", "C"], ["Cw", "Bw", "Aw"])
    b = R(["Cw", "Bw", "Aw"], ["A", "B", "C"])
    assert a.rid == b.rid


def test_different_geometry_is_a_different_route():
    a = R(["A", "B", "C"], ["Cw", "Bw", "Aw"])
    b = R(["A", "B", "D"], ["Dw", "Bw", "Aw"])
    assert a.rid != b.rid


def test_stop_order_matters():
    a = R(["A", "B", "C"], ["Cw", "Bw", "Aw"])
    b = R(["A", "C", "B"], ["Cw", "Bw", "Aw"])
    assert a.rid != b.rid


# -- network digest --------------------------------------------------------

def _net(routes, headway=30.0, periods=("am_peak", "midday")):
    act = {r.rid: {p: headway for p in periods} for r in routes}
    return SyntheticNetwork(tuple(routes), act)


def test_network_digest_is_permutation_invariant():
    a, b = R(["A", "B"], ["Bw", "Aw"]), R(["C", "D"], ["Dw", "Cw"])
    assert _net([a, b]).digest == _net([b, a]).digest


def test_a_route_switched_off_is_not_in_the_network():
    """OFF is a real state, so an all-OFF network IS the empty network."""
    a = R(["A", "B"], ["Bw", "Aw"])
    off = SyntheticNetwork((a,), {a.rid: {"am_peak": OFF, "midday": OFF}})
    assert off.digest == SyntheticNetwork((), {}).digest
    assert off.active_rids() == ()


def test_an_inactive_candidate_does_not_change_the_network():
    """Two networks running the same service are the same network.

    A search that carries a different pool of unused candidates must not
    thereby produce a different digest, or every cache lookup misses.
    """
    a, b = R(["A", "B"], ["Bw", "Aw"]), R(["C", "D"], ["Dw", "Cw"])
    run = {a.rid: {"am_peak": 30.0}}
    assert (SyntheticNetwork((a,), run).digest
            == SyntheticNetwork((a, b), run).digest)


def test_headway_changes_the_network():
    a = R(["A", "B"], ["Bw", "Aw"])
    assert (SyntheticNetwork((a,), {a.rid: {"am_peak": 30.0}}).digest
            != SyntheticNetwork((a,), {a.rid: {"am_peak": 15.0}}).digest)


def test_off_is_in_the_ladder_and_is_none():
    assert OFF is None
    assert HEADWAY_LADDER[0] is None
    assert None in HEADWAY_LADDER
    assert 5.0 in HEADWAY_LADDER and 60.0 in HEADWAY_LADDER


# -- search bounds ---------------------------------------------------------

def test_length_bounds_are_a_search_bound_that_can_be_detected():
    """The contract requires proving the winner does not live on the bound."""
    short = R(["A", "B"], ["Bw", "Aw"], outbound_sec=60 * (MIN_ONEWAY_MIN - 1),
              inbound_sec=60 * (MIN_ONEWAY_MIN - 1))
    ok = R(["A", "B"], ["Bw", "Aw"], outbound_sec=60 * 60.0,
           inbound_sec=60 * 60.0)
    long = R(["A", "B"], ["Bw", "Aw"], outbound_sec=60 * (MAX_ONEWAY_MIN + 1),
             inbound_sec=60 * (MAX_ONEWAY_MIN + 1))
    assert not short.within_length_bounds()
    assert ok.within_length_bounds() and not ok.touches_length_bound()
    assert not long.within_length_bounds()
    on_bound = R(["A", "B"], ["Bw", "Aw"],
                 outbound_sec=60 * MAX_ONEWAY_MIN, inbound_sec=60 * 10)
    assert on_bound.touches_length_bound()


# -- the reconstruction, as committed --------------------------------------

def _recon():
    if not RECON.exists():
        pytest.skip("reconstruction has not been run in this working copy")
    return json.loads(RECON.read_text())


def test_the_current_network_is_representable():
    """Definition-of-ready item 4. Without it Experiment 4 cannot conclude.

    A pool that cannot contain the current network cannot distinguish
    'greenfield is not better' from 'the generator failed to propose what COTA
    already runs'.
    """
    r = _recon()
    assert r["every_route_reconstructed"], r["failures"][:3]
    assert r["stop_coverage_complete"], r["stops_missed"]
    assert r["rid_collisions"] == 0


def test_every_legacy_stop_is_still_served():
    r = _recon()
    assert r["stops_covered"] == r["stops_in_legacy_network"]


def test_short_turn_variants_became_their_own_lines():
    """Taking only the longest pattern per direction missed 101 stops.

    In a representation where route identity has no privileged status, a
    short-turn is just another line; keeping only the 'main' pattern would
    reintroduce the legacy notion of a route having one true shape.
    """
    r = _recon()
    assert r["reconstructed"] > r["legacy_routes_seen"], (
        "variants collapsed back into one line per route")


def test_reconstructed_routes_are_inside_the_search_bounds():
    """If today's routes fall outside them, the bounds are wrong."""
    r = _recon()
    assert r["outside_search_bounds"] == [], (
        f"the search bounds exclude routes COTA runs today: "
        f"{r['outside_search_bounds']}")


# -- structural distance ---------------------------------------------------

def test_a_network_is_identical_to_itself():
    from cota_opt.synthetic import structural_distance
    a = _net([R(["A", "B", "C"], ["Cw", "Bw", "Aw"])])
    d = structural_distance(a, a)
    assert d["edge_jaccard"] == 1.0
    assert d["service_weighted_cosine"] == pytest.approx(1.0)
    assert d["one_seat_jaccard"] == 1.0
    assert d["distance"] == 0.0


def test_disjoint_networks_are_maximally_distant():
    from cota_opt.synthetic import structural_distance
    a = _net([R(["A", "B"], ["Bw", "Aw"])])
    b = _net([R(["X", "Y"], ["Yw", "Xw"])])
    d = structural_distance(a, b)
    assert d["edge_jaccard"] == 0.0
    assert d["distance"] == 1.0


def test_same_streets_different_service_is_not_called_identical():
    """Unweighted overlap would miss the difference that matters most."""
    from cota_opt.synthetic import structural_distance
    r = R(["A", "B", "C"], ["Cw", "Bw", "Aw"])
    often = SyntheticNetwork((r,), {r.rid: {"am_peak": 5.0}})
    rarely = SyntheticNetwork((r,), {r.rid: {"am_peak": 60.0}})
    d = structural_distance(often, rarely)
    assert d["edge_jaccard"] == 1.0, "the same streets are driven"
    assert d["service_weighted_cosine"] == pytest.approx(1.0), (
        "cosine is scale-free, so it agrees they are the same shape")
    ea = __import__("cota_opt.synthetic", fromlist=["service_edges"]).service_edges
    assert sum(ea(often.routes, often.activation).values()) > \
        sum(ea(rarely.routes, rarely.activation).values())


def test_one_seat_overlap_catches_a_split_that_edges_do_not():
    """Two networks can drive the same streets and join different journeys."""
    from cota_opt.synthetic import structural_distance
    through = _net([R(["A", "B", "C"], ["Cw", "Bw", "Aw"])])
    cut = _net([R(["A", "B"], ["Bw", "Aw"]), R(["B", "C"], ["Cw", "Bw"])])
    d = structural_distance(through, cut)
    assert d["edge_jaccard"] == 1.0, "identical streets driven"
    assert d["one_seat_jaccard"] < 1.0, (
        "but A->C is a one-seat ride in one network and a transfer in the "
        "other, which is the difference Experiments 6-7 care about")
