"""Generate the frozen Experiment 4 route pool.

Every stop sequence over 2,763 stops is not a search space. This produces a
broad but finite set of lines from the observed-link graph, using several
independent generators so that no single heuristic defines the answer — the
same reasoning that made Experiment 2's splice-only candidate set produce a
conclusion about splices while reading as a conclusion about geometry.

**Legacy inclusion is mandatory.** Every supported current local route must be
in the pool, demonstrated by reconstruction rather than asserted, or a poor
Experiment 4 result cannot be told apart from a generator that failed to
propose what COTA already runs.

Two facts about this network shape everything here. Stops are **directional**,
so an inbound path is found in the graph rather than mirrored from the
outbound. And only **166 of 2,763 stops offer a choice of continuation**, so
the design freedom lives at those branch points; a generator that ignores them
is really just re-tracing corridors.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np

from .linkgraph import LinkGraph, k_shortest_paths, opposite_side, shortest_path
from .synthetic import (MAX_ONEWAY_MIN, MIN_ONEWAY_MIN, SyntheticRoute,
                        route_from_path)

log = logging.getLogger(__name__)


@dataclass
class PoolAudit:
    """What each generator proposed, what survived, and why the rest did not."""

    accepted: list[SyntheticRoute] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    proposed: int = 0

    def reject(self, gen: str, why: str, detail: str = "") -> None:
        self.rejected.append({"generator": gen, "why": why, "detail": detail})

    def as_dict(self) -> dict[str, Any]:
        prov = Counter(r.provenance.split(":")[0] for r in self.accepted)
        lens = sorted(max(r.outbound_sec, r.inbound_sec) / 60.0
                      for r in self.accepted)
        return {
            "proposed": self.proposed,
            "accepted": len(self.accepted),
            "rejected": len(self.rejected),
            "accepted_by_generator": dict(prov),
            "rejected_by_reason": dict(Counter(r["why"] for r in self.rejected)),
            "oneway_minutes": {
                "min": round(lens[0], 1) if lens else None,
                "median": round(lens[len(lens) // 2], 1) if lens else None,
                "max": round(lens[-1], 1) if lens else None,
            },
            "on_length_bound": sum(1 for r in self.accepted
                                   if r.touches_length_bound()),
            "modelled_share_max": round(max((r.modelled_share
                                             for r in self.accepted),
                                            default=0.0), 4),
            "note": "Several independent generators, so no single heuristic "
                    "defines the design space. Legacy inclusion is mandatory: "
                    "without the current network in the pool, a poor result "
                    "cannot be told apart from a generator that failed to "
                    "propose what COTA already runs.",
        }


def _paired_route(g: LinkGraph, coords: dict[str, tuple[float, float]],
                  a: str, b: str, provenance: str,
                  k: int = 2, opp_tries: int = 4) -> list[SyntheticRoute]:
    """Lines from `a` to `b`, each with an inbound path found in the graph.

    The inbound starts across the street from `b` and ends across the street
    from `a`, because stops are directional. Several opposite-side candidates
    are tried: the nearest stop may have no outgoing link in the direction
    wanted, and giving up on the first failure would silently drop most
    endpoint pairs.
    """
    out: list[SyntheticRoute] = []
    max_sec = MAX_ONEWAY_MIN * 60.0
    for ob in k_shortest_paths(g, a, b, k=k, max_sec=max_sec):
        ib = None
        for sb in opposite_side(g, coords, b)[:opp_tries]:
            for sa in opposite_side(g, coords, a)[:opp_tries]:
                cand = shortest_path(g, sb, sa, max_sec=max_sec)
                if cand:
                    ib = cand
                    break
            if ib:
                break
        if ib is None:
            continue
        try:
            out.append(route_from_path(g, ob, ib, provenance=provenance))
        except ValueError:
            continue
    return out


def generate_pool(g: LinkGraph, coords: dict[str, tuple[float, float]],
                  legacy: Sequence[SyntheticRoute],
                  stop_demand: dict[str, float] | None = None,
                  terminals: Iterable[str] = (),
                  per_pair: int = 2,
                  n_od_pairs: int = 60,
                  n_terminal_pairs: int = 40,
                  n_crosstown: int = 40,
                  n_trunk: int = 25) -> PoolAudit:
    """The frozen pool: legacy lines plus four independent generators.

    Deterministic given its inputs — endpoint choices come from sorted, ranked
    lists rather than sampling, so the pool is a property of the network and
    the rules rather than of when it was generated. Experiment 2B lost 57 of
    240 subsets to an enumeration order that changed mid-sweep.
    """
    audit = PoolAudit()
    seen: set[str] = set()

    def take(routes: Iterable[SyntheticRoute], gen: str) -> None:
        for r in routes:
            audit.proposed += 1
            if r.rid in seen:
                audit.reject(gen, "duplicate geometry", r.rid)
                continue
            if not r.within_length_bounds():
                audit.reject(gen, "outside the 10-120 minute search bound",
                             f"{max(r.outbound_sec, r.inbound_sec) / 60:.1f} min")
                continue
            if len(r.stops) < 4:
                audit.reject(gen, "too few stops to be a line", str(len(r.stops)))
                continue
            seen.add(r.rid)
            audit.accepted.append(r)

    # 1. LEGACY — mandatory, and first so nothing can crowd it out.
    take(legacy, "legacy")
    log.info("pool: %d legacy lines", len(audit.accepted))

    dem = stop_demand or {}
    ranked = [s for s in sorted(dem, key=lambda s: (-dem[s], s)) if s in g.out]
    branch = sorted((s for s in g.out if len(g.out[s]) >= 2),
                    key=lambda s: (-dem.get(s, 0.0), s))

    # 2. OD-DRIVEN — direct lines between the stops most demand touches.
    od: list[SyntheticRoute] = []
    top = ranked[:max(4, int(np.sqrt(2 * n_od_pairs)) + 1)]
    for i, a in enumerate(top):
        for b in top[i + 1:]:
            if len(od) >= n_od_pairs:
                break
            od += _paired_route(g, coords, a, b, "od", k=per_pair)
        if len(od) >= n_od_pairs:
            break
    take(od, "od")

    # 3. TERMINAL-TO-TERMINAL — through the graph, not along today's routes.
    terms = sorted(set(terminals) & set(g.out))
    tt: list[SyntheticRoute] = []
    for i, a in enumerate(terms):
        for b in terms[i + 1:]:
            if len(tt) >= n_terminal_pairs:
                break
            tt += _paired_route(g, coords, a, b, "terminal", k=1)
        if len(tt) >= n_terminal_pairs:
            break
    take(tt, "terminal")

    # 4. CROSSTOWN — endpoints deliberately far apart in opposite directions
    #    from the demand centroid, so a radial legacy network does not define
    #    every seed. Non-downtown movement has to be generated on purpose.
    cross: list[SyntheticRoute] = []
    if ranked and coords:
        pts = np.array([coords[s] for s in ranked[:200] if s in coords])
        if len(pts):
            cx, cy = pts.mean(axis=0)
            far = sorted((s for s in ranked[:400] if s in coords),
                         key=lambda s: -((coords[s][0] - cx) ** 2
                                         + (coords[s][1] - cy) ** 2))
            for i, a in enumerate(far[:40]):
                ax, ay = coords[a]
                for b in far[:40]:
                    if len(cross) >= n_crosstown:
                        break
                    bx, by = coords[b]
                    # opposite sides of the centroid
                    if (ax - cx) * (bx - cx) + (ay - cy) * (by - cy) >= 0:
                        continue
                    cross += _paired_route(g, coords, a, b, "crosstown", k=1)
                if len(cross) >= n_crosstown:
                    break
    take(cross, "crosstown")

    # 5. TRUNK — spines through the busiest branch points, which is where a
    #    corridor can actually carry several movements at once.
    trunk: list[SyntheticRoute] = []
    for i, a in enumerate(branch[:20]):
        for b in branch[:20]:
            if a == b or len(trunk) >= n_trunk:
                continue
            trunk += _paired_route(g, coords, a, b, "trunk", k=1)
        if len(trunk) >= n_trunk:
            break
    take(trunk, "trunk")

    # Canonical order, so the pool is a set with a stable listing and any later
    # partition is a property of the pool rather than of generation order.
    audit.accepted.sort(key=lambda r: r.rid)
    log.info("pool frozen: %d accepted of %d proposed (%s)",
             len(audit.accepted), audit.proposed,
             audit.as_dict()["accepted_by_generator"])
    return audit
