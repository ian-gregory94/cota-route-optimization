"""Where to propose a geometry edit, and why.

Experiment 2 must not begin with unconstrained network generation, so the
search needs a small set of *motivated* candidate edits rather than random
perturbations. Each generator here looks for a specific, nameable pathology in
the existing network and emits edits with the evidence attached, so a planner
reading the result sees "truncate route 25 past X: 11 stops, 3.1% of the
route's running time, 0.4% of its access demand" rather than an opaque index.

Nothing here evaluates an edit. Generation proposes; the screening evaluator in
``exp3`` disposes. Keeping those apart matters: a generator that also scored
its own proposals would quietly become the optimizer, and its priors would be
indistinguishable from the result.

Every measure below is computed from data already in the pipeline — LODES
worker/job counts inside each stop's catchment, the OD table's accessible flow,
projected stop geometry — so a candidate can always be traced back to a number.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .geometry import GeometryEdit, SegmentTimeModel
from .network import RoutePattern, TransitNetwork

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# stop-level context: how much demand a stop reaches, and who else serves it
# ---------------------------------------------------------------------------

@dataclass
class StopContext:
    """Per-stop demand weight and service exclusivity.

    ``weight`` is the LODES workers-plus-jobs reachable from a stop, split
    evenly among the stops that reach the same zone so a downtown block group
    is not counted once per stop on the street. ``n_routes`` is how many routes
    serve the stop, which is what makes a tail droppable: cutting a stop that
    three other routes also serve costs riders a good deal less than cutting
    the only service on the street.
    """

    weight: dict[str, float]
    n_routes: dict[str, int]
    coords: dict[str, tuple[float, float]]

    def exclusive_weight(self, stop_id: str) -> float:
        """Demand weight that disappears if this stop loses *this* route."""
        n = max(1, self.n_routes.get(stop_id, 1))
        return self.weight.get(stop_id, 0.0) / n


def stop_context(net: TransitNetwork, zs, stop_ids: list[str],
                 model: SegmentTimeModel) -> StopContext:
    weight: dict[str, float] = defaultdict(float)
    for z in range(zs.n):
        stops, _ = zs.access_of(z)
        if len(stops) == 0:
            continue
        share = float(zs.workers[z] + zs.jobs[z]) / len(stops)
        for si in stops:
            weight[stop_ids[si]] += share
    n_routes = {s: len(r) for s, r in net.stop_routes.items()}
    return StopContext(weight=dict(weight), n_routes=n_routes,
                       coords=model.coords)


# ---------------------------------------------------------------------------
# helpers over patterns
# ---------------------------------------------------------------------------

def _longest_pattern(net: TransitNetwork, route_id: str) -> RoutePattern | None:
    pats = [p for p in net.patterns.values() if p.route_id == route_id]
    return max(pats, key=lambda p: len(p.stops)) if pats else None


def _seg_seconds(p: RoutePattern) -> np.ndarray:
    return np.array([s.run_time_sec for s in p.segments], dtype=float)


def _path_length_m(ctx: StopContext, stops: list[str]) -> float:
    tot = 0.0
    for a, b in zip(stops, stops[1:]):
        if a in ctx.coords and b in ctx.coords:
            (ax, ay), (bx, by) = ctx.coords[a], ctx.coords[b]
            tot += float(np.hypot(ax - bx, ay - by))
    return tot


#: Longest gap between consecutive stops that still reads as local service.
#: Route 073 runs 19 non-stop minutes from downtown to Dublin; a "corridor"
#: containing that jump is an express alignment, and following it is route
#: replacement wearing an extension's label. Caught by hand inspection of a
#: candidate that scored well precisely because it was doing that.
MAX_LOCAL_GAP_M = 2500.0


def _is_local_chain(ctx: StopContext, stops: list[str],
                    max_gap_m: float = MAX_LOCAL_GAP_M) -> bool:
    for a, b in zip(stops, stops[1:]):
        if a in ctx.coords and b in ctx.coords:
            if _straight_m(ctx, a, b) > max_gap_m:
                return False
    return True


def _straight_m(ctx: StopContext, a: str, b: str) -> float:
    if a not in ctx.coords or b not in ctx.coords:
        return 0.0
    (ax, ay), (bx, by) = ctx.coords[a], ctx.coords[b]
    return float(np.hypot(ax - bx, ay - by))


# ---------------------------------------------------------------------------
# generators
# ---------------------------------------------------------------------------

def truncation_candidates(net: TransitNetwork, ctx: StopContext,
                          min_tail_stops: int = 3, max_tail_stops: int = 15,
                          max_demand_share: float = 0.12,
                          max_runtime_share: float = 0.35,
                          exclude_routes: set[str] | None = None,
                          top_n: int = 20) -> list[GeometryEdit]:
    """Terminal tails that consume running time without reaching much demand.

    A tail earns a proposal when it is a meaningful share of the route's
    running time but a small share of the demand the route reaches, counting
    only demand that would actually be lost -- a stop four other routes serve
    is not lost by truncating this one.
    """
    skip = exclude_routes or set()
    out = []
    for rid in sorted(net.route_stops):
        if rid in skip:
            continue
        p = _longest_pattern(net, rid)
        if p is None or len(p.stops) < 2 * min_tail_stops + 2:
            continue
        secs = _seg_seconds(p)
        total_sec = secs.sum()
        excl = np.array([ctx.exclusive_weight(s) for s in p.stops])
        total_w = excl.sum()
        if total_sec <= 0 or total_w <= 0:
            continue
        for end in ("start", "end"):
            for k in range(min_tail_stops, min(max_tail_stops, len(p.stops) // 3) + 1):
                if end == "end":
                    tail, tail_sec = p.stops[-k:], secs[-k:].sum()
                else:
                    tail, tail_sec = p.stops[:k], secs[:k].sum()
                w_share = float(np.sum([ctx.exclusive_weight(s) for s in tail])
                                / total_w)
                t_share = float(tail_sec / total_sec)
                # A tail that is most of the route is not a truncation, it is
                # a deletion; an express's single long non-stop run is the
                # route's whole purpose and must not read as a droppable tail.
                if not (0.05 <= t_share <= max_runtime_share):
                    continue
                if w_share > max_demand_share:
                    continue
                gain = t_share - w_share
                out.append((gain, GeometryEdit(
                    kind="truncate", route_id=rid, drop_stops=tuple(tail),
                    description=(
                        f"truncate route {rid} at its {end} terminal, dropping "
                        f"{k} stops: {t_share * 100:.1f}% of running time for "
                        f"{w_share * 100:.1f}% of the demand it uniquely reaches"),
                    evidence={"end": end, "n_stops": k,
                              "runtime_share": t_share,
                              "exclusive_demand_share": w_share,
                              "seconds_per_trip": float(tail_sec)})))
    return _best(out, top_n, key=lambda e: (e.route_id, e.evidence["end"]))


def straighten_candidates(net: TransitNetwork, ctx: StopContext,
                          min_circuity: float = 1.6, min_span: int = 3,
                          max_span: int = 12, max_demand_share: float = 0.10,
                          exclude_routes: set[str] | None = None,
                          top_n: int = 20) -> list[GeometryEdit]:
    """Deviations: a stretch that wanders far off the straight line between
    its own two ends, and whose intermediate stops reach little unique demand."""
    skip = exclude_routes or set()
    out = []
    for rid in sorted(net.route_stops):
        if rid in skip:
            continue
        p = _longest_pattern(net, rid)
        if p is None or len(p.stops) < min_span + 3:
            continue
        secs = _seg_seconds(p)
        total_w = sum(ctx.exclusive_weight(s) for s in p.stops) or 1.0
        n = len(p.stops)
        for i in range(1, n - min_span - 1):
            for span in range(min_span, min(max_span, n - i - 1) + 1):
                j = i + span
                a, b = p.stops[i - 1], p.stops[j]
                straight = _straight_m(ctx, a, b)
                if straight < 400:
                    continue
                along = _path_length_m(ctx, p.stops[i - 1:j + 1])
                circ = along / straight
                if circ < min_circuity:
                    continue
                mid = p.stops[i:j]
                w_share = sum(ctx.exclusive_weight(s) for s in mid) / total_w
                if w_share > max_demand_share:
                    continue
                saved = float(secs[i - 1:j].sum())
                out.append((circ * (1 - w_share), GeometryEdit(
                    kind="straighten", route_id=rid, drop_stops=tuple(mid),
                    description=(
                        f"straighten route {rid} between {a} and {b}, removing a "
                        f"{len(mid)}-stop deviation that runs {circ:.2f}x the "
                        f"direct distance for {w_share * 100:.1f}% of the demand "
                        "it uniquely reaches"),
                    evidence={"circuity": circ, "n_stops": len(mid),
                              "exclusive_demand_share": w_share,
                              "seconds_removed": saved,
                              "anchors": [a, b]})))
    return _best(out, top_n, key=lambda e: e.route_id)


def extension_candidates(net: TransitNetwork, ctx: StopContext, zs,
                         stop_ids: list[str], od_zone_flow: np.ndarray,
                         trips_by_route: dict[str, int],
                         max_reach_m: float = 1500.0, max_new_stops: int = 10,
                         max_donor_trips: int = 40,
                         max_runtime_growth: float = 0.25,
                         exclude_routes: set[str] | None = None,
                         top_n: int = 20) -> list[GeometryEdit]:
    """Extend a route along a corridor some barely-served line already runs.

    An extension has to go somewhere a bus can actually drive, and it has to be
    priced. Both come free if the extension follows an existing pattern: the
    stop sequence is a real street alignment and every link already has a
    scheduled running time. What makes it worth doing is the donor's frequency
    -- continuing a trunk route down a corridor that gets a handful of trips a
    day converts a coverage route into a usable one, whereas paralleling
    another frequent route just duplicates it.
    """
    skip = exclude_routes or set()
    zone_flow_of = _stop_zone_flow(zs, stop_ids, od_zone_flow)
    # A donor must be excluded for the same reason it cannot be edited: a
    # peak express's alignment is a commuter timetable with a long non-stop
    # run in the middle, not a corridor another route can be continued along.
    donors = [p for p in net.patterns.values()
              if p.route_id not in skip
              and trips_by_route.get(p.route_id, 0) <= max_donor_trips
              and len(p.stops) >= 3
              and _is_local_chain(ctx, p.stops)]
    if not donors:
        return []

    out = []
    for rid in sorted(net.route_stops):
        if rid in skip:
            continue
        p = _longest_pattern(net, rid)
        if p is None:
            continue
        on_route = set(p.stops)
        for end, term, inward in (("end", p.stops[-1], p.stops[-2]),
                                  ("start", p.stops[0], p.stops[1])):
            if term not in ctx.coords:
                continue
            for d in donors:
                if d.route_id == rid:
                    continue
                chain = _donor_chain_from(ctx, d, term, inward, on_route,
                                          max_reach_m, max_new_stops)
                if len(chain) < 3 or not _is_local_chain(ctx, [term] + chain):
                    continue
                # an extension has to be an extension: bounded growth, not a
                # second route bolted onto the end of the first
                added_m = _path_length_m(ctx, [term] + chain)
                own_m = _path_length_m(ctx, p.stops)
                if own_m > 0 and added_m > max_runtime_growth * own_m:
                    continue
                gained = sum(zone_flow_of.get(s, 0.0) for s in chain)
                if gained <= 0:
                    continue
                out.append((gained, GeometryEdit(
                    kind="extend", route_id=rid, append_stops=tuple(chain),
                    description=(
                        f"extend route {rid} past its {end} terminal along "
                        f"route {d.route_id}'s corridor for {len(chain)} stops, "
                        f"reaching {gained:,.0f} daily trips' worth of zone flow "
                        f"on a corridor with {trips_by_route.get(d.route_id, 0)} "
                        "trips a day today"),
                    evidence={"end": end, "n_stops": len(chain),
                              "donor_route": d.route_id,
                              "donor_daily_trips": trips_by_route.get(d.route_id, 0),
                              "zone_flow_reached": float(gained)})))
    return _best(out, top_n, key=lambda e: (e.route_id, e.evidence["end"]))


def _stop_zone_flow(zs, stop_ids: list[str],
                    od_zone_flow: np.ndarray) -> dict[str, float]:
    served = np.zeros(len(stop_ids))
    for z in range(zs.n):
        stops, _ = zs.access_of(z)
        if len(stops) == 0:
            continue
        share = float(od_zone_flow[z]) / len(stops)
        for si in stops:
            served[si] += share
    return {stop_ids[i]: float(served[i]) for i in range(len(stop_ids))}


def _donor_chain_from(ctx: StopContext, donor: RoutePattern, terminal: str,
                      inward: str, on_route: set[str], max_reach_m: float,
                      max_new: int) -> list[str]:
    """Donor stops running outward from the terminal, away from the route body.

    The chain starts at the donor stop nearest the terminal and runs whichever
    way along the donor increases distance from the route's own body, so an
    extension continues outward instead of doubling back over itself.
    """
    if terminal not in ctx.coords or inward not in ctx.coords:
        return []
    tx, ty = ctx.coords[terminal]
    best_i, best_d = -1, np.inf
    for i, s in enumerate(donor.stops):
        if s not in ctx.coords:
            continue
        d = float(np.hypot(ctx.coords[s][0] - tx, ctx.coords[s][1] - ty))
        if d < best_d:
            best_i, best_d = i, d
    if best_i < 0 or best_d > max_reach_m:
        return []

    ix, iy = ctx.coords[inward]

    def outwardness(seq):
        pts = [ctx.coords[s] for s in seq[:4] if s in ctx.coords]
        if not pts:
            return -np.inf
        return float(np.mean([np.hypot(x - ix, y - iy) for x, y in pts]))

    fwd = donor.stops[best_i:]
    bwd = list(reversed(donor.stops[:best_i + 1]))
    seq = fwd if outwardness(fwd) >= outwardness(bwd) else bwd
    return [s for s in seq if s not in on_route][:max_new]


def splice_candidates(net: TransitNetwork, ctx: StopContext,
                      terminal_window: int = 3,
                      exclude_routes: set[str] | None = None,
                      top_n: int = 20) -> list[GeometryEdit]:
    """Pairs of routes that end where the other one starts.

    A shared stop near both routes' terminals is a forced transfer: riders
    crossing it must get off and wait. Through-routing removes that wait at no
    vehicle-hour cost, so these are the cheapest structural changes on offer.
    """
    skip = exclude_routes or set()
    ends: dict[str, set[str]] = {}
    for rid in net.route_stops:
        if rid in skip:
            continue
        p = _longest_pattern(net, rid)
        if p is None or len(p.stops) < 2 * terminal_window:
            continue
        ends[rid] = set(p.stops[:terminal_window]) | set(p.stops[-terminal_window:])

    out = []
    routes = sorted(ends)
    for i, ra in enumerate(routes):
        for rb in routes[i + 1:]:
            shared = ends[ra] & ends[rb]
            if not shared:
                continue
            jx = max(shared, key=lambda s: ctx.weight.get(s, 0.0))
            w = ctx.weight.get(jx, 0.0)
            out.append((w, GeometryEdit(
                kind="splice", route_id=ra, with_route=rb, junction=jx,
                description=(
                    f"through-route {ra} and {rb} at {jx}, a stop within "
                    f"{terminal_window} stops of both routes' terminals, "
                    f"removing a forced transfer for riders crossing it"),
                evidence={"junction_demand_weight": float(w),
                          "shared_terminal_stops": len(shared)})))
    return _best(out, top_n, key=lambda e: (e.route_id, e.with_route))


def reroute_candidates(net: TransitNetwork, ctx: StopContext,
                       min_span: int = 3, max_span: int = 12,
                       max_detour: float = 1.4, min_gain: float = 1.25,
                       exclude_routes: set[str] | None = None,
                       top_n: int = 15) -> list[GeometryEdit]:
    """Move a stretch of route sideways onto a nearby corridor that reaches more.

    Both the stretch being replaced and its replacement are taken from real
    patterns, so the result is a route a driver could follow and every link has
    a scheduled running time. A swap is proposed when the alternative corridor
    reaches materially more demand that would otherwise be lost, without
    lengthening the route much.
    """
    skip = exclude_routes or set()
    out = []
    pats = [p for p in net.patterns.values()
            if len(p.stops) >= min_span + 2 and p.route_id not in skip
            and _is_local_chain(ctx, p.stops)]
    for rid in sorted(net.route_stops):
        if rid in skip:
            continue
        p = _longest_pattern(net, rid)
        if p is None or len(p.stops) < min_span + 3:
            continue
        n = len(p.stops)
        on_route = set(p.stops)
        for i in range(1, n - min_span - 1):
            for span in range(min_span, min(max_span, n - i - 1) + 1, 3):
                j = i + span
                a_s, b_s = p.stops[i - 1], p.stops[j]
                if a_s not in ctx.coords or b_s not in ctx.coords:
                    continue
                direct = _straight_m(ctx, a_s, b_s)
                if direct < 600:
                    continue
                cur = p.stops[i:j]
                cur_w = sum(ctx.exclusive_weight(s) for s in cur)
                for d in pats:
                    if d.route_id == rid:
                        continue
                    chain = _donor_chain_between(ctx, d, a_s, b_s, on_route,
                                                 direct, max_detour)
                    # A swap that replaces three stops with seventy is a route
                    # rewrite wearing a reroute's clothes, and the ratio it
                    # reports is meaningless when the stretch it replaces has
                    # almost no uniquely-served demand to divide by.
                    if not (2 <= len(chain) <= 2 * len(cur) + 2):
                        continue
                    if not _is_local_chain(ctx, [a_s] + chain + [b_s]):
                        continue
                    alt_w = sum(ctx.exclusive_weight(s) for s in chain)
                    if cur_w < 1.0 or alt_w <= cur_w * min_gain:
                        continue
                    out.append((alt_w - cur_w, GeometryEdit(
                        kind="reroute", route_id=rid,
                        replace_between=(a_s, b_s), replace_with=tuple(chain),
                        description=(
                            f"reroute route {rid} between {a_s} and {b_s} onto "
                            f"route {d.route_id}'s alignment, {len(chain)} stops "
                            f"reaching {alt_w / max(cur_w, 1e-9):.1f}x the "
                            f"uniquely-served demand of the {len(cur)} stops it "
                            "replaces"),
                        evidence={"donor_route": d.route_id,
                                  "current_weight": float(cur_w),
                                  "alternative_weight": float(alt_w),
                                  "direct_m": direct,
                                  "n_replaced": len(cur),
                                  "n_new": len(chain)})))
    return _best(out, top_n, key=lambda e: e.route_id)


def _donor_chain_between(ctx: StopContext, donor: RoutePattern, a: str, b: str,
                         on_route: set[str], direct_m: float,
                         max_detour: float) -> list[str]:
    """A donor's own stop sequence spanning roughly the same two points."""
    if a not in ctx.coords or b not in ctx.coords:
        return []
    (ax, ay), (bx, by) = ctx.coords[a], ctx.coords[b]
    pts = [(k, ctx.coords[s]) for k, s in enumerate(donor.stops)
           if s in ctx.coords]
    if len(pts) < 3:
        return []
    ka, da = min(((k, np.hypot(x - ax, y - ay)) for k, (x, y) in pts),
                 key=lambda t: t[1])
    kb, db = min(((k, np.hypot(x - bx, y - by)) for k, (x, y) in pts),
                 key=lambda t: t[1])
    # the donor has to actually start and end near the anchors, not merely
    # pass within a mile of them somewhere along its length
    if da > 0.35 * direct_m or db > 0.35 * direct_m or ka == kb:
        return []
    seq = donor.stops[ka:kb + 1] if ka < kb else list(
        reversed(donor.stops[kb:ka + 1]))
    chain = [s for s in seq if s not in on_route]
    if not chain:
        return []
    length = _path_length_m(ctx, seq)
    if length > max_detour * direct_m:
        return []
    return chain


def _best(scored: list[tuple[float, GeometryEdit]], top_n: int,
          key) -> list[GeometryEdit]:
    """Highest-scoring proposals, at most one per key so one route cannot
    monopolise the shortlist with fifty variants of the same idea."""
    seen: set = set()
    out: list[GeometryEdit] = []
    for _, e in sorted(scored, key=lambda t: -t[0]):
        k = key(e)
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
        if len(out) >= top_n:
            break
    return out


def generate_all(net: TransitNetwork, ctx: StopContext, zs,
                 stop_ids: list[str], od_zone_flow: np.ndarray,
                 trips_by_route: dict[str, int],
                 exclude_routes: set[str] | None = None,
                 per_kind: int = 12) -> list[GeometryEdit]:
    """Every generator, shortlisted per kind.

    ``exclude_routes`` should carry the peak-only expresses. Experiment 1
    already established that their timetable is a design choice rather than
    neglect, and their single long non-stop run reads to a geometry generator
    as a droppable tail, which it emphatically is not.
    """
    ex = exclude_routes or set()
    cands = (truncation_candidates(net, ctx, exclude_routes=ex, top_n=per_kind)
             + straighten_candidates(net, ctx, exclude_routes=ex, top_n=per_kind)
             + extension_candidates(net, ctx, zs, stop_ids, od_zone_flow,
                                    trips_by_route, exclude_routes=ex,
                                    top_n=per_kind)
             + splice_candidates(net, ctx, exclude_routes=ex, top_n=per_kind)
             + reroute_candidates(net, ctx, exclude_routes=ex, top_n=per_kind))
    log.info("generated %d candidate edits: %s", len(cands),
             pd.Series([c.kind for c in cands]).value_counts().to_dict())
    return cands


def candidate_frame(edits: list[GeometryEdit]) -> pd.DataFrame:
    rows = []
    for e in edits:
        row: dict[str, Any] = {"key": e.key, "kind": e.kind,
                               "route_id": e.route_id,
                               "with_route": e.with_route,
                               "description": e.description}
        row.update({f"ev_{k}": v for k, v in e.evidence.items()
                    if not isinstance(v, (list, dict))})
        rows.append(row)
    return pd.DataFrame(rows)
