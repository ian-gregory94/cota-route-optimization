"""Experiment 3 infrastructure: a stop-edit vocabulary that cannot overclaim.

The audit that preceded this module asked whether COTA's own schedule can price
a stop, and the answer was no: across the eleven natural experiments the feed
offers -- same route, same direction, one pattern skipping a subset of another's
stops -- patterns serving *more* stops are scheduled 157 seconds *faster* per
extra stop, on three routes, with too few routes to hold any out. No dwell
penalty produces that sign. Those comparisons are measuring something else
(express runs on different streets, different times of day, padding), and this
feed cannot tell us what a stop costs.

That finding is not a footnote, it is the design constraint. Consolidation's
whole case is a runtime saving: fewer stops, faster trips, freed vehicle-hours.
If the size of that saving has to be assumed, then any "consolidation improves
access by X%" would be a restatement of the assumption with the network as
decoration. So this vocabulary is built to make the assumption impossible to
hide:

* **Edits are applied with runtime held exactly fixed.** Dropping stop *b*
  between *a* and *c* replaces two segments with one whose running time is
  their sum. The edited network is therefore strictly worse for the people who
  used *b* and no better for anybody -- zero assumed benefit.
* **The measurable side is measured.** Riders who boarded or alighted at *b*
  walk further, or lose their trip. That is priced by the same evaluator
  Experiments 1 and 2 use, with no new parameter.
* **The unmeasurable side becomes a threshold, not an estimate.** Instead of
  "this edit is worth X", the output is *the stop penalty at which this edit
  breaks even*. A planner who believes a stop costs 25 seconds can read off
  which edits clear it; one who believes 5 seconds reads off a much shorter
  list. Nobody has to accept a number this feed cannot support.

Nothing here is an Experiment 3 result. The benchmark for one is the finalized
Experiment 2 frontier, which does not exist yet.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable

import numpy as np
import pandas as pd

from .network import PatternSegment, RoutePattern, TransitNetwork

KINDS = ("remove", "consolidate", "relocate")


@dataclass(frozen=True)
class StopEdit:
    """One conservative change to where a route stops.

    ``remove`` drops the stop from every pattern of ``route_id`` that serves it.
    ``consolidate`` is a remove with a named receiver, which is what makes the
    walk delta attributable to a specific pair. ``relocate`` moves a stop to a
    point between two, serving both catchments at a cost to each; it changes no
    stop counts and so has no runtime story at all, which is why it is the one
    edit this feed can evaluate end to end.
    """

    kind: str
    route_id: str
    stop_id: str
    receiver_id: str | None = None
    to_lonlat: tuple[float, float] | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown stop edit {self.kind!r}")
        if self.kind == "consolidate" and not self.receiver_id:
            raise ValueError("consolidate needs a receiver stop")
        if self.kind == "relocate" and self.to_lonlat is None:
            raise ValueError("relocate needs a destination")

    @property
    def edit_id(self) -> str:
        tail = self.receiver_id or (
            "@%.5f,%.5f" % self.to_lonlat if self.to_lonlat else "")
        return f"{self.kind}|{self.route_id}|{self.stop_id}|{tail}"

    @property
    def description(self) -> str:
        if self.kind == "relocate":
            return (f"move stop {self.stop_id} on route {self.route_id} to "
                    f"{self.to_lonlat}")
        if self.kind == "consolidate":
            return (f"drop stop {self.stop_id} on route {self.route_id}, "
                    f"riders walk to {self.receiver_id}")
        return f"drop stop {self.stop_id} from route {self.route_id}"


@dataclass(frozen=True)
class Guard:
    """Thresholds a candidate must clear, each nameable and arguable on its own.

    Deliberately strict. The pool this produces is not "the stops worth
    removing" -- it is "the stops this analysis cannot show are load-bearing",
    which is a much weaker claim and the only one the evidence supports.
    """

    max_pair_spacing_m: float = 200.0
    max_added_walk_min: float = 3.0
    max_removed_per_route: int = 6
    require_unprotected: bool = True
    min_daily_trips: float = 1.0


def guard_reasons(row, receiver, guard: Guard) -> list[str]:
    """Every reason this candidate fails, not just the first one.

    Reporting all of them stops the pool from moving when one rule is relaxed
    and a second, unmentioned rule was doing the real work.
    """
    why: list[str] = []
    protected = str(getattr(row, "protected", "") or "")
    if guard.require_unprotected and protected:
        why.append(f"protected: {protected}")
    walk = float(getattr(row, "nearest_walk_min", np.inf))
    if not np.isfinite(walk):
        why.append("no walking alternative at all")
    elif walk > guard.max_added_walk_min:
        why.append(f"nearest alternative {walk:.1f} min > "
                   f"{guard.max_added_walk_min:.1f}")
    if receiver is None:
        why.append("no receiver stop on the same route")
    if float(getattr(row, "daily_trips", 0.0)) < guard.min_daily_trips:
        why.append("no scheduled service")
    return why


def propose(audit: pd.DataFrame, guard: Guard = Guard(),
            spacing_col: str = "prev_spacing_m") -> pd.DataFrame:
    """Candidate stop edits with the reason each was kept or dropped.

    Returns every stop considered, not only the survivors: a consolidation
    study whose candidate pool arrives without its rejections is unauditable,
    and the rejections are where the protection rules are actually visible.
    """
    if audit.empty:
        return pd.DataFrame(columns=["edit_id", "kind", "route_id", "stop_id",
                                     "receiver_id", "eligible", "rejected_for"])
    rows = []
    kept_per_route: dict[str, int] = {}
    order = audit.sort_values(
        [c for c in ("catchment_flow", "unique_flow") if c in audit.columns],
        ascending=True)
    for r in order.itertuples():
        routes = [x for x in str(getattr(r, "routes", "")).split(";") if x]
        route = routes[0] if len(routes) == 1 else ""
        receiver = getattr(r, "nearest_stop_id", None)
        receiver = None if (isinstance(receiver, float)
                            and not np.isfinite(receiver)) else receiver
        why = guard_reasons(r, receiver, guard)
        if len(routes) != 1:
            why.append(f"serves {len(routes)} routes" if routes
                       else "no route recorded")
        gap = float(getattr(r, spacing_col, np.nan))
        if not np.isfinite(gap):
            why.append("spacing unknown")
        elif gap > guard.max_pair_spacing_m:
            why.append(f"spacing {gap:.0f} m > {guard.max_pair_spacing_m:.0f} m")
        if not why and kept_per_route.get(route, 0) >= guard.max_removed_per_route:
            why.append(f"route already at the {guard.max_removed_per_route}-stop cap")
        eligible = not why
        if eligible:
            kept_per_route[route] = kept_per_route.get(route, 0) + 1
        e = StopEdit("consolidate", route or "?", str(r.stop_id),
                     receiver_id=str(receiver) if receiver else None) \
            if eligible else None
        rows.append({
            "edit_id": e.edit_id if e else "",
            "kind": "consolidate", "route_id": route,
            "stop_id": str(r.stop_id),
            "stop_name": getattr(r, "stop_name", ""),
            "receiver_id": str(receiver) if receiver else "",
            "spacing_m": gap,
            "added_walk_min": float(getattr(r, "nearest_walk_min", np.nan)),
            "catchment_flow": float(getattr(r, "catchment_flow", np.nan)),
            "unique_flow": float(getattr(r, "unique_flow", np.nan)),
            "daily_trips": float(getattr(r, "daily_trips", np.nan)),
            "eligible": eligible,
            "rejected_for": "; ".join(why),
        })
    return pd.DataFrame(rows).sort_values(
        ["eligible", "catchment_flow"], ascending=[False, True],
        ignore_index=True)


def edits_from(frame: pd.DataFrame) -> list[StopEdit]:
    return [StopEdit("consolidate", str(r.route_id), str(r.stop_id),
                     receiver_id=str(r.receiver_id) or None)
            for r in frame[frame["eligible"]].itertuples()]


# -- applying an edit --------------------------------------------------------

@dataclass
class StopEditReport:
    applied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    patterns_changed: int = 0
    stop_services_removed: int = 0
    runtime_delta_min: float = 0.0

    def summary(self) -> dict:
        return {"n_applied": len(self.applied), "n_skipped": len(self.skipped),
                "patterns_changed": self.patterns_changed,
                "stop_services_removed": self.stop_services_removed,
                "runtime_delta_min": self.runtime_delta_min,
                "runtime_treatment": "held fixed: dropped segments are merged "
                                     "by summing their running times, so the "
                                     "edited network is granted no time saving"}


def apply_stop_edits(net: TransitNetwork, edits: Iterable[StopEdit]
                     ) -> tuple[TransitNetwork, StopEditReport]:
    """Apply stop edits with running time preserved exactly.

    The geometry operators in ``geometry.py`` *rescale* runtime when a pattern's
    length changes, which is right there: a rerouted bus really does cover
    different ground. It would be wrong here. A consolidated stop leaves the
    route on the same streets, and the only thing that could make it faster is
    the stop penalty this feed cannot measure. So the two segments either side
    of a dropped stop are merged by adding their times, and ``runtime_delta_min``
    comes back as zero by construction -- a value worth asserting on, because a
    non-zero one means a time saving crept in somewhere.
    """
    rep = StopEditReport()
    pats = {pid: p for pid, p in net.patterns.items()}
    by_route: dict[str, list[str]] = {}
    for pid, p in pats.items():
        by_route.setdefault(p.route_id, []).append(pid)

    before = sum(p.total_run_time_min for p in pats.values())
    for e in edits:
        if e.kind == "relocate":
            rep.skipped.append(f"{e.edit_id}: relocate changes coordinates, "
                               "not pattern structure; apply it to the stop table")
            continue
        touched = 0
        for pid in by_route.get(e.route_id, []):
            p = pats[pid]
            if e.stop_id not in p.stops or len(p.stops) <= 2:
                continue
            if p.stops[0] == e.stop_id or p.stops[-1] == e.stop_id:
                continue          # a terminal is a different edit entirely
            pats[pid] = _drop_stop(p, e.stop_id)
            touched += 1
            rep.stop_services_removed += p.n_trips
        if touched:
            rep.applied.append(e.edit_id)
            rep.patterns_changed += touched
        else:
            rep.skipped.append(f"{e.edit_id}: no eligible pattern serves it "
                               "at an interior position")
    rep.runtime_delta_min = sum(p.total_run_time_min for p in pats.values()) - before
    return _rebuild(net, pats), rep


def _drop_stop(p: RoutePattern, stop_id: str) -> RoutePattern:
    i = p.stops.index(stop_id)
    stops = p.stops[:i] + p.stops[i + 1:]
    times = [s.run_time_sec for s in p.segments]
    # segment i-1 ends at the dropped stop and segment i leaves it; one segment
    # spanning the gap carries the sum, so the pattern's total is unchanged
    merged = times[:i - 1] + [times[i - 1] + times[i]] + times[i + 1:]
    segs = [PatternSegment(p.route_id, p.direction_id, p.pattern_id,
                           stops[j], stops[j + 1], j, merged[j])
            for j in range(len(stops) - 1)]
    return RoutePattern(p.route_id, p.direction_id, p.pattern_id, stops, segs,
                        p.n_trips)


def _rebuild(net: TransitNetwork, patterns: dict) -> TransitNetwork:
    stop_routes: dict[str, set[str]] = {}
    route_stops: dict[str, set[str]] = {}
    for p in patterns.values():
        for sid in p.stops:
            stop_routes.setdefault(sid, set()).add(p.route_id)
            route_stops.setdefault(p.route_id, set()).add(sid)
    return TransitNetwork(stops=net.stops, patterns=patterns,
                          stop_routes=stop_routes, route_stops=route_stops)


# -- what a stop is carrying -------------------------------------------------

def stop_flows(ev, headways: np.ndarray, pattern_index: dict[str, int],
               pattern_positions: dict[str, int]) -> dict[str, float]:
    """Daily flow boarding, alighting and riding through a stop.

    ``pattern_positions`` maps pattern id to the stop's position along it. The
    split matters because the three groups are affected in different
    directions: boarders and alighters pay the whole access penalty, riders
    passing through pay nothing and would collect the entire (unmeasurable)
    time saving.
    """
    ps = ev.ps
    if ps.n_paths == 0 or ps.leg_pattern is None:
        return {"boarding": 0.0, "alighting": 0.0, "through": 0.0}
    pf = ev.path_flows(np.asarray(headways, float))
    flow = pf[ps.leg_path]
    board = alight = through = 0.0
    for pid, pos in pattern_positions.items():
        pi = pattern_index.get(pid)
        if pi is None:
            continue
        on = ps.leg_pattern == pi
        if not on.any():
            continue
        b, a = ps.leg_board_pos[on], ps.leg_alight_pos[on]
        f = flow[on]
        board += float(f[b == pos].sum())
        alight += float(f[a == pos].sum())
        through += float(f[(b < pos) & (a > pos)].sum())
    return {"boarding": board, "alighting": alight, "through": through}


@dataclass(frozen=True)
class BreakEven:
    """The stop penalty at which an edit stops costing more than it saves."""

    access_cost_min_per_day: float
    through_riders_per_day: float
    trips_per_day: float
    seconds_per_stop_required: float
    basis: str = ("rider time only; freed vehicle-hours are NOT counted, so "
                  "this threshold is an upper bound on what the edit must "
                  "clear and consolidation is judged conservatively")

    def verdict(self, believed_sec: float) -> str:
        if not np.isfinite(self.seconds_per_stop_required):
            return ("no rider passes this stop without using it, so no stop "
                    "penalty can pay for removing it")
        if self.seconds_per_stop_required <= believed_sec:
            return (f"breaks even at {self.seconds_per_stop_required:.1f} s per "
                    f"stop, below the {believed_sec:.0f} s assumed")
        return (f"needs {self.seconds_per_stop_required:.1f} s per stop, above "
                f"the {believed_sec:.0f} s assumed — not justified")


def breakeven(access_cost_min_per_day: float, flows: dict, w_in_vehicle: float,
              trips_per_day: float = 0.0) -> BreakEven:
    """Seconds per stop the edit must save to pay for the walking it imposes.

    Only the in-vehicle time of riders passing the stop is counted on the
    benefit side. Freed vehicle-hours could be reinvested as frequency, which
    would lower the threshold, but establishing by how much needs the
    optimizer -- and leaving it out makes removal harder to justify rather than
    easier, which is the correct direction to err in when the penalty itself is
    unmeasured.
    """
    thru = float(flows.get("through", 0.0))
    req = (np.inf if thru <= 0 else
           access_cost_min_per_day / thru * 60.0 / max(w_in_vehicle, 1e-9))
    return BreakEven(float(access_cost_min_per_day), thru, float(trips_per_day),
                     float(req))


def register(frame: pd.DataFrame, results: list[dict]) -> pd.DataFrame:
    """Join candidate bookkeeping to whatever has been scored so far.

    Every proposed edit keeps a row whether or not it was scored, so a later
    reader can see how many candidates were considered and never evaluated
    rather than inferring the pool from the survivors.
    """
    base = frame.copy()
    if not results:
        return base.assign(scored=False)
    res = pd.DataFrame(results)
    out = base.merge(res, on="edit_id", how="left", suffixes=("", "_scored"))
    out["scored"] = out[res.columns.drop("edit_id")[0]].notna() \
        if len(res.columns) > 1 else True
    return out
