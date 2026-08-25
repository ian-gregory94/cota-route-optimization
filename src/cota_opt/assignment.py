"""Generalized-cost passenger path assignment on a frequency-based network.

Deliberately simple and analytically checkable: a label-correcting search over
a small graph whose edge costs are the generalized cost components from
:mod:`cota_opt.cost`. Boarding a route costs the expected wait for its headway
(plus a transfer penalty if the traveller is already on the system); walking
edges cost walk time; riding costs in-vehicle time.

This is the abstraction a RAPTOR/CSA implementation will replace; the interface
(``assign``/``AssignmentResult``) is designed to survive that swap.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from .cost import CostWeights, expected_wait_min


@dataclass
class RouteSpec:
    """A route as a sequence of stops with per-segment in-vehicle times."""

    route_id: str
    stops: list[str]
    segment_min: list[float]        # len(stops) - 1
    headway_min: float

    def __post_init__(self) -> None:
        if len(self.segment_min) != len(self.stops) - 1:
            raise ValueError(
                f"route {self.route_id}: {len(self.segment_min)} segments for "
                f"{len(self.stops)} stops")


@dataclass
class WalkLink:
    from_stop: str
    to_stop: str
    walk_min: float


@dataclass
class SmallNetwork:
    routes: list[RouteSpec]
    walk_links: list[WalkLink] = field(default_factory=list)

    def stops(self) -> set[str]:
        s: set[str] = set()
        for r in self.routes:
            s |= set(r.stops)
        for w in self.walk_links:
            s |= {w.from_stop, w.to_stop}
        return s


@dataclass
class AssignmentResult:
    """Least-generalized-cost path for one OD pair."""

    origin: str
    destination: str
    reachable: bool
    generalized_cost: float = float("inf")
    in_vehicle_min: float = 0.0
    wait_min: float = 0.0
    walk_min: float = 0.0
    n_transfers: int = 0
    routes_used: list[str] = field(default_factory=list)
    path: list[str] = field(default_factory=list)


def assign(net: SmallNetwork, origin: str, destination: str, w: CostWeights,
           wait_kwargs: dict | None = None,
           max_transfers: int = 3) -> AssignmentResult:
    """Least generalized-cost path from origin to destination.

    State = (stop, current_route or None, n_boardings). Cost accrues as:
    boarding → expected wait (+ transfer penalty when n_boardings > 0),
    riding → in-vehicle minutes, walking → walk minutes.
    """
    wk = wait_kwargs or {}
    if origin not in net.stops() or destination not in net.stops():
        return AssignmentResult(origin, destination, reachable=False)

    # index: stop -> [(route_index, position)]
    boardings: dict[str, list[tuple[int, int]]] = {}
    for ri, r in enumerate(net.routes):
        for pos, s in enumerate(r.stops):
            boardings.setdefault(s, []).append((ri, pos))
    walks: dict[str, list[WalkLink]] = {}
    for wl in net.walk_links:
        walks.setdefault(wl.from_stop, []).append(wl)
        walks.setdefault(wl.to_stop, []).append(
            WalkLink(wl.to_stop, wl.from_stop, wl.walk_min))

    Start = (origin, -1, 0)
    best: dict[tuple[str, int, int], float] = {Start: 0.0}
    meta: dict[tuple, tuple] = {Start: (0.0, 0.0, 0.0, 0, [], [origin])}
    pq: list[tuple[float, tuple[str, int, int]]] = [(0.0, Start)]
    result: AssignmentResult | None = None

    while pq:
        cost, state = heapq.heappop(pq)
        if cost > best.get(state, float("inf")) + 1e-12:
            continue
        stop, cur_route, nb = state
        ivt, wait, walk, ntr, routes, path = meta[state]
        if stop == destination:
            result = AssignmentResult(
                origin, destination, True, cost, ivt, wait, walk, ntr,
                list(routes), list(path))
            break

        def push(nstate, ncost, nivt, nwait, nwalk, nntr, nroutes, npath):
            if ncost < best.get(nstate, float("inf")) - 1e-12:
                best[nstate] = ncost
                meta[nstate] = (nivt, nwait, nwalk, nntr, nroutes, npath)
                heapq.heappush(pq, (ncost, nstate))

        # walk
        for wl in walks.get(stop, []):
            push((wl.to_stop, -1, nb), cost + w.walking * wl.walk_min,
                 ivt, wait, walk + wl.walk_min, ntr, routes, path + [wl.to_stop])

        # board a route (or stay on the current one by riding, below)
        if nb <= max_transfers:
            for ri, pos in boardings.get(stop, []):
                if ri == cur_route:
                    continue
                r = net.routes[ri]
                if pos >= len(r.stops) - 1:
                    continue
                ew = expected_wait_min(r.headway_min, **wk)
                add = w.waiting * ew if nb == 0 else (
                    w.transfer_wait * ew + w.transfer_penalty)
                push((stop, ri, nb + 1), cost + add, ivt, wait + ew, walk,
                     ntr + (1 if nb > 0 else 0), routes + [r.route_id], path)

        # ride one segment forward on the current route
        if cur_route >= 0:
            r = net.routes[cur_route]
            try:
                pos = r.stops.index(stop)
            except ValueError:
                continue
            if pos < len(r.stops) - 1:
                seg = r.segment_min[pos]
                nxt = r.stops[pos + 1]
                push((nxt, cur_route, nb), cost + w.in_vehicle * seg,
                     ivt + seg, wait, walk, ntr, routes, path + [nxt])

    return result or AssignmentResult(origin, destination, reachable=False)
