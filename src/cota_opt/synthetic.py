"""Synthetic routes and networks: route identity without legacy route ids.

Experiment 4 releases route structure, so an Exp 4 line cannot be "route 8 with
73% of its stops changed" — that phrasing smuggles in exactly the identity the
experiment is releasing. A `SyntheticRoute` is a path through the observed-link
graph and nothing else, and a `SyntheticNetwork` is an unordered set of those
lines plus their service activation.

**Canonical identity comes from geometry, never from discovery order.** Two
searches that arrive at the same network by different routes must hash
identically, or the same network caches, compares and de-duplicates as two —
the same requirement Experiment 3 met by refusing two mutations on one route,
and for the same reason.

The representation is not trusted until `reconstruct_current()` rebuilds COTA's
existing local network through it and reproduces that network's own score and
resources. Experiment 3 lost three defects to a fresh implementation of a
validated chain that merely looked right.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from .linkgraph import LinkGraph
from .network import PatternSegment, RoutePattern, TransitNetwork

log = logging.getLogger(__name__)

#: The headway ladder a synthetic route-period may take. **OFF is a real
#: option**, not a formality: a route that did not exist yesterday has no
#: baseline headway, and giving every synthetic line a copied one would invent
#: a service commitment nobody made. OFF consumes zero vehicle-hours and zero
#: peak vehicles and contributes no frequency.
HEADWAY_LADDER: tuple[float | None, ...] = (
    None, 60.0, 45.0, 40.0, 30.0, 24.0, 20.0, 15.0, 12.0, 10.0, 7.5, 6.0, 5.0)

OFF = None

#: Search bounds on one-way running time, in minutes. Today's local routes run
#: roughly 21-99 minutes one way (5th-95th percentile about 27-95), so this is
#: deliberately wider. It is a COMPUTATIONAL BOUND, not a claim about ideal
#: route length, and the contract requires testing whether the winner touches
#: it — a network full of 120-minute routes means the bound is active and the
#: result is censored.
MIN_ONEWAY_MIN = 10.0
MAX_ONEWAY_MIN = 120.0


@dataclass(frozen=True)
class SyntheticRoute:
    """A line defined by the stops it serves, in order, in each direction."""

    outbound: tuple[str, ...]
    inbound: tuple[str, ...]
    outbound_sec: float
    inbound_sec: float
    modelled_links: int = 0
    observed_links: int = 0
    provenance: str = ""

    @property
    def rid(self) -> str:
        """Canonical id: a hash of the geometry, direction-symmetric.

        Symmetric because a line is the same line whichever direction is called
        outbound. Without that, the same physical route discovered from either
        end would be two different routes in the pool and in every cache key.
        """
        a = "|".join(self.outbound)
        b = "|".join(self.inbound)
        payload = "||".join(sorted((a, b)))
        return "syn-" + hashlib.sha256(payload.encode()).hexdigest()[:16]

    @property
    def stops(self) -> frozenset[str]:
        return frozenset(self.outbound) | frozenset(self.inbound)

    @property
    def cycle_sec(self) -> float:
        return self.outbound_sec + self.inbound_sec

    @property
    def modelled_share(self) -> float:
        tot = self.modelled_links + self.observed_links
        return (self.modelled_links / tot) if tot else 0.0

    @property
    def terminals(self) -> tuple[str, str]:
        return (self.outbound[0], self.outbound[-1])

    def within_length_bounds(self) -> bool:
        m = max(self.outbound_sec, self.inbound_sec) / 60.0
        return MIN_ONEWAY_MIN <= m <= MAX_ONEWAY_MIN

    def touches_length_bound(self, tol_min: float = 1.0) -> bool:
        """Is this route sitting ON the search bound rather than inside it?"""
        m = max(self.outbound_sec, self.inbound_sec) / 60.0
        return (m <= MIN_ONEWAY_MIN + tol_min) or (m >= MAX_ONEWAY_MIN - tol_min)

    def as_dict(self) -> dict[str, Any]:
        return {"rid": self.rid, "outbound": list(self.outbound),
                "inbound": list(self.inbound),
                "outbound_sec": round(self.outbound_sec, 1),
                "inbound_sec": round(self.inbound_sec, 1),
                "oneway_min": round(max(self.outbound_sec,
                                        self.inbound_sec) / 60.0, 1),
                "n_stops": len(self.stops),
                "terminals": list(self.terminals),
                "observed_links": self.observed_links,
                "modelled_links": self.modelled_links,
                "modelled_share": round(self.modelled_share, 4),
                "provenance": self.provenance}


def route_from_path(g: LinkGraph, outbound: Sequence[str],
                    inbound: Sequence[str],
                    provenance: str = "") -> SyntheticRoute:
    """Build a route from two paths through the observed-link graph.

    **The inbound path must be supplied, and it is never the reverse of the
    outbound.** COTA's stops are DIRECTIONAL — `11T4THE` is the eastbound stop
    at 11th and 4th, `11T4THW` the westbound one — so the return trip runs
    through a different set of stop ids on the opposite side of the street.
    Reversing an outbound stop list produces a sequence with no observed links
    at all; every one of the 77 legacy patterns failed that way when this
    function defaulted to a reversal.

    That is a hard constraint on route generation, not a quirk of the
    reconstruction: any Experiment 4 generator that proposes a line by picking
    a path and mirroring it will produce nothing drivable. Inbound geometry has
    to be found in the graph, the same as outbound.
    """
    ob = tuple(outbound)
    ot = g.path_time(list(ob))
    if ot is None:
        raise ValueError(f"outbound path is not serviceable: {ob[:4]}...")
    ib = tuple(inbound)
    it_ = g.path_time(list(ib))
    if it_ is None:
        raise ValueError(
            f"inbound path is not serviceable: {ib[:4]}... (note that stops "
            f"are directional here, so the reverse of an outbound path is "
            f"never the inbound path)")
    n_obs = (len(ob) - 1) + (len(ib) - 1)
    return SyntheticRoute(outbound=ob, inbound=ib, outbound_sec=float(ot),
                          inbound_sec=float(it_), observed_links=n_obs,
                          modelled_links=0, provenance=provenance)


@dataclass(frozen=True)
class SyntheticNetwork:
    """An unordered set of lines plus per-period service activation.

    `activation` maps rid -> {period: headway_min or OFF}. A rid absent from
    activation, or OFF in every period, is a route the network does not run —
    which is the same thing as not containing it, and hashes that way.
    """

    routes: tuple[SyntheticRoute, ...]
    activation: dict[str, dict[str, float | None]] = field(default_factory=dict)

    def active_rids(self) -> tuple[str, ...]:
        out = []
        for r in self.routes:
            per = self.activation.get(r.rid, {})
            if any(h is not None for h in per.values()):
                out.append(r.rid)
        return tuple(sorted(out))

    @property
    def digest(self) -> str:
        """Permutation-invariant content digest.

        Over the ACTIVE routes and their service only. Two networks that run
        the same lines at the same headways are the same network, whatever
        order a search found them in and whatever inactive candidates each
        happens to be carrying.
        """
        payload = []
        for rid in self.active_rids():
            per = self.activation.get(rid, {})
            payload.append([rid, sorted((k, v) for k, v in per.items()
                                        if v is not None)])
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True,
                       separators=(",", ":")).encode()).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        act = self.active_rids()
        return {"digest": self.digest, "n_routes_in_pool": len(self.routes),
                "n_active_routes": len(act), "active": list(act),
                "activation": {k: v for k, v in self.activation.items()
                               if k in set(act)}}


# ---------------------------------------------------------------------------
# the reconstruction test — item 4 of the definition of ready
# ---------------------------------------------------------------------------

def reconstruct_current(g: LinkGraph, net: TransitNetwork,
                        exclude_routes: Iterable[str] = ()
                        ) -> tuple[list[SyntheticRoute], dict[str, Any]]:
    """Rebuild COTA's existing local network as synthetic routes.

    The check the contract puts first and calls most likely to fail quietly. If
    the current network cannot be expressed in this representation, then the
    frozen route pool cannot contain it, and a poor Experiment 4 result could
    mean nothing more than that the generator failed to propose what COTA
    already runs.

    Every distinct pattern becomes its own line. Patterns whose reverse is not
    serviceable are reported rather than silently dropped — that is a finding
    about the feed, not a nuisance.
    """
    skip = set(exclude_routes)

    # EVERY distinct pattern becomes its own line, not just the longest one per
    # direction. Taking only the longest missed 101 stops that short-turn and
    # branch variants serve — and in a representation where route identity has
    # no privileged status, a short-turn IS just another line. Keeping only the
    # "main" pattern would have quietly reintroduced the legacy notion of a
    # route having one true shape, which is the thing Experiment 4 releases.
    #
    # The canonical id is direction-symmetric, so a pattern and its reverse
    # collapse to one route rather than two.
    # Group by route and direction, then pair each direction-0 pattern with a
    # direction-1 one, longest with longest. Pairing by rank rather than by
    # reversal is forced by directional stops, and pairing longest-with-longest
    # keeps a short-turn matched to a short-turn rather than to a full-length
    # run in the other direction.
    by_rd: dict[tuple[str, int], list[RoutePattern]] = {}
    for p in net.patterns.values():
        if p.route_id in skip or len(p.stops) < 2:
            continue
        by_rd.setdefault((p.route_id, p.direction_id), []).append(p)
    routes_seen = {r for (r, _) in by_rd}

    built: list[SyntheticRoute] = []
    failures: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rid in sorted(routes_seen):
        d0 = sorted(by_rd.get((rid, 0), []), key=lambda p: -len(p.stops))
        d1 = sorted(by_rd.get((rid, 1), []), key=lambda p: -len(p.stops))
        if not d0 or not d1:
            only = d0 or d1
            failures.append({"route_id": rid, "pattern_id": only[0].pattern_id,
                             "why": "route has patterns in only one direction, "
                                    "so no inbound geometry exists in the feed",
                             "n_stops": len(only[0].stops)})
            continue
        n = max(len(d0), len(d1))
        for i in range(n):
            ob = d0[min(i, len(d0) - 1)]
            ib = d1[min(i, len(d1) - 1)]
            try:
                r = route_from_path(
                    g, ob.stops, ib.stops,
                    provenance=f"legacy:{rid}:{ob.pattern_id}/{ib.pattern_id}")
            except ValueError as e:
                failures.append({"route_id": rid,
                                 "pattern_id": f"{ob.pattern_id}/{ib.pattern_id}",
                                 "why": str(e)[:160],
                                 "n_stops": len(ob.stops)})
                continue
            if r.rid in seen:
                continue
            seen.add(r.rid)
            built.append(r)
    by_route = {r: 1 for r in routes_seen}

    covered = {s for r in built for s in r.stops}
    want = {s for p in net.patterns.values() if p.route_id not in skip
            for s in p.stops}
    lengths = sorted(max(r.outbound_sec, r.inbound_sec) / 60.0 for r in built)
    report = {
        "legacy_routes_seen": len(by_route),
        "legacy_patterns_seen": sum(1 for p in net.patterns.values()
                                    if p.route_id not in skip),
        "reconstructed": len(built),
        "failed": len(failures),
        "failures": failures,
        "every_route_reconstructed": not failures,
        "stops_covered": len(covered),
        "stops_in_legacy_network": len(want),
        "stops_missed": sorted(want - covered)[:10],
        "stop_coverage_complete": covered >= want,
        "oneway_minutes": {
            "min": round(lengths[0], 1) if lengths else None,
            "p05": round(lengths[int(0.05 * len(lengths))], 1) if lengths else None,
            "median": round(lengths[len(lengths) // 2], 1) if lengths else None,
            "p95": round(lengths[int(0.95 * (len(lengths) - 1))], 1) if lengths else None,
            "max": round(lengths[-1], 1) if lengths else None,
        },
        "outside_search_bounds": [r.rid for r in built
                                  if not r.within_length_bounds()],
        "note": "Every current local route expressed as a path through the "
                "observed-link graph, with no legacy route id doing any work. "
                "If this fails, the frozen pool cannot contain the current "
                "network and Experiment 4 cannot distinguish 'greenfield is "
                "not better' from 'the generator could not propose what COTA "
                "runs'.",
    }
    return built, report
