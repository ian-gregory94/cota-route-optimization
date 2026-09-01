"""The observed-link graph: greenfield topology without greenfield runtimes.

Every directed edge is a consecutive stop-to-stop movement that **some** COTA
route actually operates, carrying that movement's observed median scheduled
running time. Synthetic routes are then paths through this graph — free to
combine pieces of routes 1, 8, 31 and 34 into a line nobody runs, while every
individual segment remains a road COTA already drives at a speed we have
measured.

That is the whole design constraint of Experiment 4's primary evidence class.
The alternative — letting a generator draw arbitrary straight lines between
stops — would put modelled running time at 50-100% of a network, and the
optimizer would mostly be optimizing our estimator, whose median absolute error
on a single link is **20.5%**. Experiment 3 tolerates the estimator only because
headline candidates must stay under 2% modelled exposure.

The graph is also the thing that makes "greenfield" finite. Its edges are the
moves that exist; a path through it is a route that could be driven.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .network import TransitNetwork

log = logging.getLogger(__name__)


@dataclass
class ObservedLink:
    """One directed stop-to-stop movement, as operated."""

    from_stop: str
    to_stop: str
    run_time_sec: float
    n_observations: int
    routes: tuple[str, ...]
    spread_sec: float

    @property
    def key(self) -> tuple[str, str]:
        return (self.from_stop, self.to_stop)


@dataclass
class LinkGraph:
    """The directed graph of everything COTA is observed to drive.

    `links` is keyed by (from_stop, to_stop). `out` is the adjacency used by
    route generation. Both are built once and frozen: the route universe has to
    be fixed before a master path set can be enumerated over it, and a graph
    that shifted under the search would invalidate every cached path.
    """

    links: dict[tuple[str, str], ObservedLink]
    out: dict[str, list[str]]
    stops: tuple[str, ...]

    def time(self, a: str, b: str) -> float | None:
        ln = self.links.get((a, b))
        return ln.run_time_sec if ln else None

    def path_time(self, stops: list[str]) -> float | None:
        """Total running time, or None if any hop is not an observed link."""
        t = 0.0
        for i in range(len(stops) - 1):
            v = self.time(stops[i], stops[i + 1])
            if v is None:
                return None
            t += v
        return t

    def is_serviceable(self, stops: Iterable[str]) -> bool:
        s = list(stops)
        return len(s) >= 2 and self.path_time(s) is not None

    def as_dict(self) -> dict[str, Any]:
        deg = [len(v) for v in self.out.values()]
        times = [l.run_time_sec for l in self.links.values()]
        obs = [l.n_observations for l in self.links.values()]
        multi = sum(1 for l in self.links.values() if len(l.routes) > 1)
        return {
            "n_stops": len(self.stops),
            "n_directed_links": len(self.links),
            "n_links_served_by_more_than_one_route": multi,
            "mean_out_degree": round(float(np.mean(deg)), 3) if deg else 0.0,
            "max_out_degree": int(max(deg)) if deg else 0,
            "stops_with_no_outgoing_link": sum(
                1 for s in self.stops if not self.out.get(s)),
            "run_time_sec": {
                "min": round(float(np.min(times)), 1),
                "median": round(float(np.median(times)), 1),
                "p95": round(float(np.percentile(times, 95)), 1),
                "max": round(float(np.max(times)), 1),
            } if times else {},
            "observations_per_link": {
                "median": int(np.median(obs)),
                "p05": int(np.percentile(obs, 5)),
                "singletons": sum(1 for n in obs if n == 1),
            } if obs else {},
        }


def build_link_graph(net: TransitNetwork, tstats: pd.DataFrame | None = None,
                     exclude_routes: Iterable[str] = ()) -> LinkGraph:
    """Every consecutive stop pair any route operates, with its median time.

    `exclude_routes` takes the peak-express class. Those routes are frozen as an
    external layer (contract section 4), and their long non-stop runs are not
    links a local route may borrow: a generator handed a 20-minute freeway hop
    would use it as a cheap teleport between suburbs, which is exactly the fake
    improvement Experiment 1 found when express service was treated as
    frequency service.

    The median rather than the mean, because a handful of trips scheduled around
    a special event or a construction detour should not move a link that
    hundreds of ordinary trips agree on.
    """
    skip = set(exclude_routes)
    acc: dict[tuple[str, str], list[float]] = {}
    routes: dict[tuple[str, str], set[str]] = {}

    for p in net.patterns.values():
        if p.route_id in skip:
            continue
        for seg in p.segments:
            k = (seg.from_stop, seg.to_stop)
            acc.setdefault(k, []).append(float(seg.run_time_sec))
            routes.setdefault(k, set()).add(p.route_id)

    links: dict[tuple[str, str], ObservedLink] = {}
    out: dict[str, list[str]] = {}
    for k, vals in acc.items():
        a, b = k
        arr = np.asarray(vals, dtype=float)
        links[k] = ObservedLink(
            from_stop=a, to_stop=b,
            run_time_sec=float(np.median(arr)),
            n_observations=len(arr),
            routes=tuple(sorted(routes[k])),
            spread_sec=float(arr.max() - arr.min()) if len(arr) > 1 else 0.0)
        out.setdefault(a, []).append(b)
    for a in out:
        out[a] = sorted(out[a])

    stops = tuple(sorted({s for k in links for s in k}))
    g = LinkGraph(links=links, out=out, stops=stops)
    log.info("observed-link graph: %d stops, %d directed links, %d excluded "
             "routes", len(stops), len(links), len(skip))
    return g


def reachable(g: LinkGraph, start: str, max_hops: int = 60) -> set[str]:
    """Stops reachable from `start` within `max_hops` observed links."""
    seen, frontier = {start}, [start]
    for _ in range(max_hops):
        nxt = []
        for s in frontier:
            for t in g.out.get(s, ()):
                if t not in seen:
                    seen.add(t)
                    nxt.append(t)
        if not nxt:
            break
        frontier = nxt
    return seen


def audit(g: LinkGraph, net: TransitNetwork,
          exclude_routes: Iterable[str] = ()) -> dict[str, Any]:
    """Does the graph actually contain the network it was built from?

    The check that matters before anything is generated: every pattern of every
    included route must be a **serviceable path** through the graph. If it is
    not, the graph has lost a movement COTA operates, and a route pool built on
    it could not contain the current network — which the contract makes
    mandatory, because otherwise a poor Experiment 4 result might only mean the
    generator failed to propose what COTA already runs.
    """
    skip = set(exclude_routes)
    checked = broken = 0
    examples: list[str] = []
    for p in net.patterns.values():
        if p.route_id in skip:
            continue
        checked += 1
        if not g.is_serviceable(p.stops):
            broken += 1
            if len(examples) < 5:
                examples.append(p.pattern_id)

    comps = strongly_connected(g)
    largest = max((len(c) for c in comps), default=0)

    # Where a synthetic route can actually make a CHOICE. This is the real
    # measure of design freedom in the primary evidence class, and it is much
    # smaller than the stop count suggests: most stops sit mid-corridor with
    # exactly one continuation, so a route arriving there has nowhere to go but
    # onward. The freedom lives at the branch points.
    branch = [s for s, v in g.out.items() if len(v) >= 2]
    indeg: dict[str, int] = {}
    for (_, b) in g.links:
        indeg[b] = indeg.get(b, 0) + 1
    merge = [s for s, n in indeg.items() if n >= 2]
    junctions = sorted(set(branch) & set(merge))

    # Half this graph's links rest on a single observed trip. "Observed" is
    # still far better than the estimator's 20.5% median single-link error, but
    # it is not the same as a link hundreds of trips agree on, and a synthetic
    # route is free to lean on the thin ones.
    single = [l for l in g.links.values() if l.n_observations == 1]

    res = {
        **g.as_dict(),
        "patterns_checked": checked,
        "patterns_not_serviceable": broken,
        "not_serviceable_examples": examples,
        "every_pattern_is_a_path": broken == 0,
        "strongly_connected_components": len(comps),
        "largest_component_stops": largest,
        "is_strongly_connected": len(comps) == 1,
        "branch_points": len(branch),
        "branch_point_share": round(len(branch) / max(1, len(g.stops)), 4),
        "merge_points": len(merge),
        "true_junctions": len(junctions),
        "links_with_one_observation": len(single),
        "single_observation_share": round(len(single) / max(1, len(g.links)), 4),
        "excluded_routes": sorted(skip),
        "note": "Every directed edge is a consecutive stop-to-stop movement "
                "some COTA route operates, with that movement's observed "
                "median scheduled running time. A synthetic route is a path "
                "through this graph, so its topology is free while its running "
                "times are all observed.",
        "design_freedom_note":
            "The graph is strongly connected, so any stop can reach any other. "
            "But only the branch points offer a CHOICE: everywhere else a route "
            "has exactly one continuation. Experiment 4's primary evidence "
            "class is therefore not 'any network over 2,763 stops' — it is "
            "'re-cut and re-splice COTA's existing corridors at the places "
            "they already meet'. That is a real and statable limit on what the "
            "primary class can answer, and the honest framing of the result.",
        "runtime_confidence_note":
            "Links with a single observation take their running time from one "
            "trip's schedule. Better than the estimator's 20.5% median "
            "single-link error, but not equivalent to a link many trips agree "
            "on — and a synthetic route is free to lean on the thin ones, "
            "which the existing route that produced them does not do more than "
            "once.",
    }
    return res


def strongly_connected(g: LinkGraph) -> list[list[str]]:
    """Kosaraju. Iterative, because the corridors are long and deep."""
    order: list[str] = []
    seen: set[str] = set()
    for s in g.stops:
        if s in seen:
            continue
        seen.add(s)
        stack = [(s, iter(g.out.get(s, ())))]
        while stack:
            node, it = stack[-1]
            advanced = False
            for t in it:
                if t not in seen:
                    seen.add(t)
                    stack.append((t, iter(g.out.get(t, ()))))
                    advanced = True
                    break
            if not advanced:
                order.append(stack.pop()[0])
    rev: dict[str, list[str]] = {}
    for (a, b) in g.links:
        rev.setdefault(b, []).append(a)
    seen2: set[str] = set()
    comps: list[list[str]] = []
    for s in reversed(order):
        if s in seen2:
            continue
        comp, st = [], [s]
        seen2.add(s)
        while st:
            n = st.pop()
            comp.append(n)
            for t in rev.get(n, ()):
                if t not in seen2:
                    seen2.add(t)
                    st.append(t)
        comps.append(comp)
    return comps
