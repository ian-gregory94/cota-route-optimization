"""Limited, planner-legible edits to route geometry.

Experiment 1 answers "is COTA allocating its buses badly across the network it
has?". Experiment 2 asks the next question: after frequency is allocated well,
are the buses in the wrong places? To ask that without descending into
unconstrained network generation, geometry is only allowed to change through a
small vocabulary of edits a planner could read off a map:

    truncate    drop a low-productivity tail
    straighten  remove a deviation, keeping the two ends connected
    extend      continue past a terminal to reach nearby demand
    reroute     swap one stop chain for another between the same two points
    splice      through-route two lines that meet, removing a forced transfer

Every edit carries a sentence describing what it does. Nothing here invents
stops: an edit can only use stops that already exist in the feed.

Vehicle-hour bookkeeping
------------------------
An edit changes how long a trip takes, not how many trips run. Shorten a route
and each trip costs fewer vehicle-hours, so the *fixed* system budget buys more
service somewhere. That is the entire mechanism by which geometry can help, so
it has to be exact:

* segments the edit leaves alone keep their observed scheduled times;
* only genuinely new stop-to-stop links are modelled, and the model is fit to
  the edited route's own observed segments;
* splice is defined to be vehicle-hour neutral at baseline, because merging two
  routes into one has no natural "same number of trips" reading.

A modelled segment time is not an observed one. ``EditReport`` records how many
segments were modelled and how well the model reproduces the observed ones, so
a result that leans hard on modelled running time can be spotted as such.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from .network import PatternSegment, RoutePattern, TransitNetwork

log = logging.getLogger(__name__)

#: Every operation the search may construct. The contract's legal-operation
#: table and this tuple are checked against each other by
#: tests/test_contract.py -- an operation advertised as searchable that the code
#: cannot build is worse than one that is simply absent, because a reader
#: budgets search freedom that does not exist.
#:
#: `change_transfer_point` is deliberately NOT here: moving where two routes
#: meet is a reroute on one of them, and giving it a second name would let the
#: same mutation carry two canonical identities.
EDIT_KINDS = ("truncate", "straighten", "extend", "reroute", "splice",
              "add_stop", "change_terminal", "split")

#: Operations that consume their route(s) and replace them with new ids. These
#: are the only kinds where a later edit naming the old route is an error
#: rather than a composition.
CONSUMING_KINDS = ("splice", "split")


# ---------------------------------------------------------------------------
# running-time model for stop-to-stop links the schedule has never run
# ---------------------------------------------------------------------------

@dataclass
class SegmentTimeModel:
    """``seconds = intercept + slope * straight_line_metres``, fit per route.

    The intercept absorbs dwell and stop-to-stop acceleration; the slope is
    inverse running speed along the corridor. Fitting per route keeps a
    downtown circulator from being priced at freeway-express speed. Routes with
    too few segments to fit fall back to the system-wide fit.
    """

    per_route: dict[str, tuple[float, float]]
    system: tuple[float, float]
    coords: dict[str, tuple[float, float]]
    #: every stop-to-stop link the schedule runs anywhere, median seconds.
    #: An edit that routes a bus down a street some other route already uses
    #: gets an observed time rather than a modelled one, which is the
    #: difference between a running time the feed vouches for and one this
    #: module made up.
    observed_links: dict[tuple[str, str], float] = field(default_factory=dict)
    diagnostics: pd.DataFrame = field(default_factory=pd.DataFrame)

    MIN_SEGMENTS = 8

    @classmethod
    def fit(cls, net: TransitNetwork, stops_projected) -> "SegmentTimeModel":
        coords = {r.stop_id: (float(r.geometry.x), float(r.geometry.y))
                  for r in stops_projected.itertuples()}
        rows = []
        for p in net.patterns.values():
            for seg in p.segments:
                if seg.from_stop not in coords or seg.to_stop not in coords:
                    continue
                d = _dist(coords, seg.from_stop, seg.to_stop)
                if d <= 0 or not np.isfinite(seg.run_time_sec):
                    continue
                rows.append((p.route_id, d, float(seg.run_time_sec)))
        obs = pd.DataFrame(rows, columns=["route_id", "metres", "seconds"])
        if obs.empty:
            raise ValueError("no usable segments to fit a running-time model")

        link_times: dict[tuple[str, str], list[float]] = {}
        for p in net.patterns.values():
            for seg in p.segments:
                if np.isfinite(seg.run_time_sec) and seg.run_time_sec > 0:
                    link_times.setdefault((seg.from_stop, seg.to_stop),
                                          []).append(float(seg.run_time_sec))
        observed_links = {k: float(np.median(v)) for k, v in link_times.items()}

        sys_fit = _lsq(obs["metres"].to_numpy(), obs["seconds"].to_numpy())
        per_route, diag = {}, []
        for rid, grp in obs.groupby("route_id"):
            x, y = grp["metres"].to_numpy(), grp["seconds"].to_numpy()
            if len(grp) >= cls.MIN_SEGMENTS:
                fit = _lsq(x, y)
            else:
                fit = sys_fit
            per_route[rid] = fit
            pred = fit[0] + fit[1] * x
            # Percentage error on a 6-second hop is meaningless, so MAPE is
            # reported only over segments long enough for it to mean anything.
            long = y >= 30.0
            diag.append({"route_id": rid, "n_segments": len(grp),
                         "fitted_own_route": len(grp) >= cls.MIN_SEGMENTS,
                         "intercept_sec": fit[0],
                         "implied_speed_kmh": (3.6 / fit[1]) if fit[1] > 0 else np.nan,
                         "mae_sec": float(np.mean(np.abs(pred - y))),
                         "mape_pct": float(np.mean(np.abs(pred[long] - y[long])
                                                   / y[long]) * 100)
                         if long.any() else np.nan})
        return cls(per_route=per_route, system=sys_fit, coords=coords,
                   observed_links=observed_links,
                   diagnostics=pd.DataFrame(diag))

    def predict(self, route_id: str, a: str, b: str) -> float:
        c, m = self.per_route.get(route_id, self.system)
        d = _dist(self.coords, a, b)
        return max(1.0, c + m * d)

    def has(self, stop_id: str) -> bool:
        return stop_id in self.coords


def _lsq(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Least-squares intercept/slope, clamped to physically sane values."""
    A = np.column_stack([np.ones_like(x), x])
    c, m = np.linalg.lstsq(A, y, rcond=None)[0]
    # 3 km/h floor and 90 km/h ceiling on implied speed; non-negative dwell
    m = float(np.clip(m, 3.6 / 90.0, 3.6 / 3.0))
    return (float(max(0.0, c)), m)


def _dist(coords: dict[str, tuple[float, float]], a: str, b: str) -> float:
    (ax, ay), (bx, by) = coords[a], coords[b]
    return float(np.hypot(ax - bx, ay - by))


# ---------------------------------------------------------------------------
# the edit vocabulary
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GeometryEdit:
    kind: str
    route_id: str
    description: str
    drop_stops: tuple[str, ...] = ()          # truncate / straighten
    append_stops: tuple[str, ...] = ()        # extend (beyond the far terminal)
    replace_between: tuple[str, str] | None = None   # reroute: (from, to)
    replace_with: tuple[str, ...] = ()        # reroute: the alternative chain
    with_route: str | None = None             # splice partner
    junction: str | None = None               # splice junction stop
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in EDIT_KINDS:
            raise ValueError(f"unknown edit kind {self.kind!r}")
        if self.kind == "splice" and not (self.with_route and self.junction):
            raise ValueError("splice needs with_route and junction")
        if self.kind == "reroute" and not self.replace_between:
            raise ValueError("reroute needs replace_between")
        if self.kind == "split" and not self.junction:
            raise ValueError("split needs a junction to cut at")
        if self.kind == "add_stop" and not self.append_stops:
            raise ValueError("add_stop needs the stop(s) to insert")
        if self.kind == "change_terminal" and not (self.junction
                                                   and self.append_stops):
            raise ValueError("change_terminal needs the old terminal "
                             "(junction) and the new one (append_stops)")

    @property
    def key(self) -> str:
        bits = [self.kind, self.route_id]
        if self.with_route:
            bits.append(self.with_route)
        if self.junction:
            bits.append(self.junction)
        if self.drop_stops:
            bits.append(f"d{len(self.drop_stops)}:{self.drop_stops[0]}")
        if self.append_stops:
            bits.append(f"a{len(self.append_stops)}:{self.append_stops[-1]}")
        if self.replace_between:
            bits.append("r" + "-".join(self.replace_between))
        return "|".join(bits)

    def routes_touched(self) -> set[str]:
        return {self.route_id} | ({self.with_route} if self.with_route else set())


@dataclass
class EditReport:
    edits: list[GeometryEdit]
    patterns_changed: int
    segments_kept: int
    segments_modelled: int
    baseline_veh_hours_before: float
    baseline_veh_hours_after: float
    stops_dropped: int
    stops_added: int
    model_mape_pct: float
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_edits": len(self.edits),
            "edits": [e.description for e in self.edits],
            "edit_keys": [e.key for e in self.edits],
            "patterns_changed": self.patterns_changed,
            "segments_kept": self.segments_kept,
            "segments_modelled": self.segments_modelled,
            "modelled_share_pct": (100.0 * self.segments_modelled
                                   / max(1, self.segments_kept + self.segments_modelled)),
            "baseline_veh_hours_before": self.baseline_veh_hours_before,
            "baseline_veh_hours_after": self.baseline_veh_hours_after,
            "veh_hours_freed": (self.baseline_veh_hours_before
                                - self.baseline_veh_hours_after),
            "stops_dropped": self.stops_dropped,
            "stops_added": self.stops_added,
            "running_time_model_mape_pct": self.model_mape_pct,
            "notes": self.notes,
        }


@dataclass
class EditedNetwork:
    network: TransitNetwork
    tstats: pd.DataFrame
    report: EditReport


# ---------------------------------------------------------------------------
# application
# ---------------------------------------------------------------------------

def apply_edits(net: TransitNetwork, tstats: pd.DataFrame,
                model: SegmentTimeModel,
                edits: Sequence[GeometryEdit],
                require_disjoint_routes: bool = True) -> EditedNetwork:
    """Apply edits in order, returning a new network and matching trip stats.

    **At most one edit per route**, enforced here rather than assumed. The
    treatment contract declares two mutations naming a common route
    structurally incompatible and used to claim this function already enforced
    it; it did not — only splices consumed their routes, and two truncations of
    the same line composed in application order. That gap matters more than it
    looks: a state whose meaning depends on the order its edits were applied
    has no permutation-invariant content digest, so two searches reaching the
    same set of mutations by different routes would cache and compare as
    different states. Requiring route-disjointness makes a state a genuine SET
    and the digest genuinely order-free — which
    ``tests/test_geometry_order.py`` asserts by applying a state's edits in
    every order and demanding the same network back.

    ``require_disjoint_routes=False`` is available for the historical
    complexity-ladder runs, which deliberately composed edits on shared routes
    before this rule existed; nothing in Experiment 3 may use it.
    """
    patterns = {pid: _clone(p) for pid, p in net.patterns.items()}
    ts = tstats.copy()
    notes: list[str] = []
    kept = modelled = dropped = added = 0
    vh_before = float(ts["runtime_min"].sum() / 60.0)
    alive = {p.route_id for p in patterns.values()}

    if require_disjoint_routes:
        seen: dict[str, str] = {}
        for e in edits:
            for r in sorted(e.routes_touched()):
                if r in seen:
                    raise ValueError(
                        f"edits {seen[r]} and {e.key} both name route {r}. Two "
                        f"mutations on one route are structurally incompatible "
                        f"(EXPERIMENT3_CONTRACT.md section 3): their combined "
                        f"effect would depend on application order, and a "
                        f"state whose meaning depends on order has no "
                        f"order-free digest.")
                seen[r] = e.key

    for e in edits:
        missing = e.routes_touched() - alive
        if missing:
            raise ValueError(
                f"edit {e.key} names route(s) {sorted(missing)} that no longer "
                "exist in the edited network")
        if e.kind == "splice":
            k, m, d, a, note = _apply_splice(patterns, ts, model, e)
            notes.append(note)
            alive -= {e.route_id, e.with_route}
            alive.add(_splice_id(e))
        elif e.kind == "split":
            k, m, d, a, note = _apply_split(patterns, ts, model, e)
            notes.append(note)
            alive.discard(e.route_id)
            alive |= set(_split_ids(e))
        else:
            k, m, d, a = _apply_pattern_edit(patterns, model, e)
        kept += k
        modelled += m
        dropped += d
        added += a

    # patterns that lost too much to be a route any more are removed outright
    for pid in [p for p, v in patterns.items() if len(v.stops) < 2]:
        notes.append(f"pattern {pid} dropped: fewer than two stops remain")
        patterns.pop(pid)

    ts = _retime_tstats(ts, patterns, net.patterns)
    net2 = _rebuild(net, patterns)
    vh_after = float(ts["runtime_min"].sum() / 60.0)

    mape = (float(model.diagnostics["mape_pct"].mean())
            if not model.diagnostics.empty else float("nan"))
    report = EditReport(
        edits=list(edits), patterns_changed=len(
            {p for p in patterns if _differs(net.patterns.get(p), patterns[p])}),
        segments_kept=kept, segments_modelled=modelled,
        baseline_veh_hours_before=vh_before, baseline_veh_hours_after=vh_after,
        stops_dropped=dropped, stops_added=added, model_mape_pct=mape,
        notes=notes)
    return EditedNetwork(net2, ts, report)


def _clone(p: RoutePattern) -> RoutePattern:
    return RoutePattern(p.route_id, p.direction_id, p.pattern_id,
                        list(p.stops), list(p.segments), p.n_trips)


def _differs(a: RoutePattern | None, b: RoutePattern) -> bool:
    return a is None or a.stops != b.stops


def _apply_pattern_edit(patterns: dict[str, RoutePattern],
                        model: SegmentTimeModel,
                        e: GeometryEdit) -> tuple[int, int, int, int]:
    kept = modelled = dropped = added = 0
    for pid, p in list(patterns.items()):
        if p.route_id != e.route_id:
            continue
        old = list(p.stops)
        new = _edit_stop_list(old, e, model)
        if new == old:
            continue
        dropped += len(set(old) - set(new))
        added += len(set(new) - set(old))
        segs, k, m = _retime(p, new, model)
        patterns[pid] = RoutePattern(p.route_id, p.direction_id, p.pattern_id,
                                     new, segs, p.n_trips)
        kept += k
        modelled += m
    return kept, modelled, dropped, added


def _edit_stop_list(stops: list[str], e: GeometryEdit,
                    model: SegmentTimeModel) -> list[str]:
    if e.kind in ("truncate", "straighten"):
        drop = set(e.drop_stops)
        return [s for s in stops if s not in drop]

    if e.kind == "extend":
        tail = [s for s in e.append_stops if model.has(s) and s not in stops]
        if not tail:
            return stops
        # a route runs both ways; append at whichever end is nearer the new
        # stops, so the reverse-direction pattern extends at its own start
        first, last = stops[0], stops[-1]
        d_last = _dist(model.coords, last, tail[0])
        d_first = _dist(model.coords, first, tail[0])
        return stops + tail if d_last <= d_first else list(reversed(tail)) + stops

    if e.kind == "reroute":
        a, b = e.replace_between            # type: ignore[misc]
        if a not in stops or b not in stops:
            return stops
        i, j = stops.index(a), stops.index(b)
        if i > j:                            # reverse direction pattern
            i, j = j, i
            mid = list(reversed(e.replace_with))
        else:
            mid = list(e.replace_with)
        mid = [s for s in mid if model.has(s)]
        return stops[:i + 1] + mid + stops[j:]

    if e.kind == "add_stop":
        # Insert each stop where it costs the least detour. Deterministic: ties
        # break to the earliest position, so the same request on the same
        # pattern always produces the same stop list -- which is what lets a
        # network state have a stable digest.
        out = list(stops)
        for sid in e.append_stops:
            if sid in out or not model.has(sid):
                continue
            best, best_cost = None, None
            for i in range(len(out) - 1):
                a, b = out[i], out[i + 1]
                cost = (_dist(model.coords, a, sid)
                        + _dist(model.coords, sid, b)
                        - _dist(model.coords, a, b))
                if best_cost is None or cost < best_cost - 1e-9:
                    best, best_cost = i + 1, cost
            if best is not None:
                out.insert(best, sid)
        return out

    if e.kind == "change_terminal":
        old_t, new_t = e.junction, e.append_stops[0]
        if not model.has(new_t) or new_t in stops:
            return stops
        if stops and stops[-1] == old_t:
            return stops[:-1] + [new_t]
        if stops and stops[0] == old_t:
            # the reverse-direction pattern of the same route: same edit, other
            # end. Both are rewritten, so the route stays a route.
            return [new_t] + stops[1:]
        return stops                      # this variant never reached it

    raise ValueError(f"{e.kind} is not a per-pattern edit")


def _retime(p: RoutePattern, new_stops: list[str],
            model: SegmentTimeModel) -> tuple[list[PatternSegment], int, int]:
    """Keep observed times for links the schedule already runs; model the rest.

    Preference order: this pattern's own scheduled time for the link, then the
    same link in the other direction, then any other route's scheduled time for
    it, and only then the fitted model. Most edits route buses down streets
    some line already serves, so in practice very little running time is
    invented.
    """
    observed = {(s.from_stop, s.to_stop): s.run_time_sec for s in p.segments}
    sysobs = model.observed_links
    segs, kept, modelled = [], 0, 0
    for i in range(len(new_stops) - 1):
        a, b = new_stops[i], new_stops[i + 1]
        if (a, b) in observed:
            t = observed[(a, b)]
            kept += 1
        elif (b, a) in observed:            # same link, other direction
            t = observed[(b, a)]
            kept += 1
        elif (a, b) in sysobs:              # another route runs this link
            t = sysobs[(a, b)]
            kept += 1
        elif (b, a) in sysobs:
            t = sysobs[(b, a)]
            kept += 1
        else:
            t = model.predict(p.route_id, a, b)
            modelled += 1
        segs.append(PatternSegment(p.route_id, p.direction_id, p.pattern_id,
                                   a, b, i, float(t)))
    return segs, kept, modelled


def _splice_id(e: GeometryEdit) -> str:
    return f"{e.route_id}+{e.with_route}"


def _apply_splice(patterns: dict[str, RoutePattern], ts: pd.DataFrame,
                  model: SegmentTimeModel,
                  e: GeometryEdit) -> tuple[int, int, int, int, str]:
    """Through-route two lines at a shared stop, vehicle-hour neutral at baseline.

    The through pattern is the body of each route on either side of the
    junction, oriented so one runs in to it and the other out. Pattern variants
    that do not reach the junction are kept as short-turn variants of the
    merged route rather than deleted, so through-routing never quietly removes
    service from a street.

    Trip counts on the through pattern are set to hold the two routes' combined
    baseline vehicle-hours, because "the same number of trips" has no meaning
    once two routes become one: a through trip is one trip of each.
    """
    rid, oid, jx = e.route_id, e.with_route, e.junction
    new_id = _splice_id(e)
    a_pats = [p for p in patterns.values() if p.route_id == rid and jx in p.stops]
    b_pats = [p for p in patterns.values() if p.route_id == oid and jx in p.stops]
    if not a_pats or not b_pats:
        raise ValueError(f"splice {rid}+{oid}: junction {jx} is not on both routes")

    a = max(a_pats, key=lambda p: len(p.stops))
    b = max(b_pats, key=lambda p: len(p.stops))
    a_body = _body_ending_at(a.stops, jx)
    b_body = list(reversed(_body_ending_at(b.stops, jx)))     # runs out from jx
    fwd = a_body + [s for s in b_body[1:] if s not in a_body]
    if len(fwd) < 2:
        raise ValueError(f"splice {rid}+{oid}: nothing left to through-route")
    rev = list(reversed(fwd))

    kept = modelled = dropped = added = 0
    built: dict[str, RoutePattern] = {}
    donor = RoutePattern(new_id, 0, f"{new_id}_d0", fwd,
                         list(a.segments) + list(b.segments), 0)
    for d, stops in ((0, fwd), (1, rev)):
        pid = f"{new_id}_d{d}"
        segs, k, m = _retime(RoutePattern(new_id, d, pid, stops,
                                          donor.segments, 0), stops, model)
        built[pid] = RoutePattern(new_id, d, pid, list(stops), segs, 0)
        kept += k
        modelled += m

    primary = {a.pattern_id, b.pattern_id}
    variants = [p for p in patterns.values()
                if p.route_id in (rid, oid) and p.pattern_id not in primary]
    old_stops = {s for p in patterns.values() if p.route_id in (rid, oid)
                 for s in p.stops}
    new_stops = ({s for p in built.values() for s in p.stops}
                 | {s for p in variants for s in p.stops})
    dropped += len(old_stops - new_stops)
    added += len(new_stops - old_stops)

    moved = ts["pattern_id"].isin(primary)
    moved_vh = float(ts.loc[moved, "runtime_min"].sum() / 60.0)
    thru_rt = float(np.mean([sum(x.run_time_sec for x in p.segments) / 60.0
                             for p in built.values()])) or 1.0
    n_thru = max(2, int(round(moved_vh * 60.0 / thru_rt)))

    src = ts.loc[moved].sort_values("first_dep_sec")
    take = src.iloc[np.linspace(0, len(src) - 1, min(len(src), n_thru))
                    .astype(int)].copy()
    pids = list(built)
    take["route_id"] = new_id
    take["pattern_id"] = [pids[i % len(pids)] for i in range(len(take))]
    take["direction_id"] = [built[p].direction_id for p in take["pattern_id"]]
    take["trip_id"] = [f"{new_id}_t{i}" for i in range(len(take))]

    rest = ts.loc[~moved].copy()
    rest.loc[rest["route_id"].isin([rid, oid]), "route_id"] = new_id
    for p in variants:
        p.route_id = new_id
        for i, sg in enumerate(p.segments):
            p.segments[i] = PatternSegment(new_id, sg.direction_id, sg.pattern_id,
                                           sg.from_stop, sg.to_stop, sg.seq,
                                           sg.run_time_sec)
    for pid in primary:
        patterns.pop(pid, None)
    for pid, p in built.items():
        patterns[pid] = p
        p.n_trips = int((take["pattern_id"] == pid).sum())

    merged = pd.concat([rest, take], ignore_index=True)
    ts.drop(ts.index, inplace=True)
    for c in merged.columns:
        ts[c] = merged[c].values

    note = (f"splice {rid}+{oid} at {jx}: {len(src)} trips on the two main "
            f"patterns become {len(take)} through trips of {thru_rt:.0f} min, "
            f"holding {moved_vh:.1f} baseline vehicle-hours; "
            f"{len(variants)} short-turn variant(s) kept")
    return kept, modelled, dropped, added, note


def _split_ids(e: GeometryEdit) -> tuple[str, str]:
    return f"{e.route_id}a", f"{e.route_id}b"


def _apply_split(patterns: dict[str, RoutePattern], ts: pd.DataFrame,
                 model: SegmentTimeModel,
                 e: GeometryEdit) -> tuple[int, int, int, int, str]:
    """Cut one route in two at a shared stop, vehicle-hour neutral at baseline.

    The mirror of `_apply_splice`, and the only operation that raises the route
    count -- which is the point of having it. Everything else in this vocabulary
    recombines what COTA already runs; splitting is the one way the search can
    propose that a long route is two shorter ones badly joined.

    Both halves keep the junction stop, so nobody loses access there and a rider
    who used to stay aboard now transfers. Trip counts are held rather than
    doubled in vehicle-hours: each original trip becomes one trip on each half,
    and each half's runtime is its own share of the original, so the two halves
    together cost what the whole cost. That is the honest baseline -- a split
    that only paid for itself by cutting service would be measuring the cut.
    """
    rid, jx = e.route_id, e.junction
    a_id, b_id = _split_ids(e)
    mine = [p for p in patterns.values() if p.route_id == rid]
    if not mine:
        raise ValueError(f"split {rid}: route not present")
    reach = [p for p in mine if jx in p.stops]
    if not reach:
        raise ValueError(f"split {rid}: junction {jx} is on no pattern of it")
    for p in reach:
        i = p.stops.index(jx)
        if i < 1 or i > len(p.stops) - 2:
            raise ValueError(
                f"split {rid} at {jx}: the junction is a terminal of pattern "
                f"{p.pattern_id}, so one half would be a single stop")

    kept = modelled = dropped = added = 0
    built: dict[str, RoutePattern] = {}
    share: dict[str, dict[str, float]] = {}
    for p in mine:
        if jx not in p.stops:
            # A short-turn variant that never reaches the cut keeps running,
            # assigned to whichever half contains it.
            half = a_id if any(s in p.stops for s in
                               reach[0].stops[:reach[0].stops.index(jx) + 1]) \
                else b_id
            np_ = RoutePattern(half, p.direction_id, f"{half}_{p.pattern_id}",
                               list(p.stops), list(p.segments), p.n_trips)
            for i, sg in enumerate(np_.segments):
                np_.segments[i] = PatternSegment(
                    half, sg.direction_id, np_.pattern_id, sg.from_stop,
                    sg.to_stop, sg.seq, sg.run_time_sec)
            built[np_.pattern_id] = np_
            share[p.pattern_id] = {np_.pattern_id: 1.0}
            continue
        i = p.stops.index(jx)
        halves = ((a_id, p.stops[:i + 1]), (b_id, p.stops[i:]))
        tot = 0.0
        parts: dict[str, float] = {}
        for half, chain in halves:
            pid = f"{half}_{p.pattern_id}"
            segs, k, m = _retime(p, list(chain), model)
            built[pid] = RoutePattern(half, p.direction_id, pid, list(chain),
                                      segs, 0)
            kept += k
            modelled += m
            t = sum(x.run_time_sec for x in segs)
            parts[pid] = t
            tot += t
        share[p.pattern_id] = ({k2: v / tot for k2, v in parts.items()} if tot
                               else {k2: 0.5 for k2 in parts})

    old_stops = {s for p in mine for s in p.stops}
    new_stops = {s for p in built.values() for s in p.stops}
    dropped += len(old_stops - new_stops)
    added += len(new_stops - old_stops)

    moved = ts["pattern_id"].isin({p.pattern_id for p in mine})
    src = ts.loc[moved]
    rows = []
    for _, row in src.iterrows():
        for pid, frac in share.get(row["pattern_id"], {}).items():
            r = row.copy()
            r["route_id"] = built[pid].route_id
            r["pattern_id"] = pid
            r["direction_id"] = built[pid].direction_id
            r["trip_id"] = f"{pid}_{row['trip_id']}"
            r["runtime_min"] = float(row["runtime_min"]) * frac
            rows.append(r)
    take = (pd.DataFrame(rows).reset_index(drop=True) if rows
            else src.iloc[0:0].copy())

    for p in mine:
        patterns.pop(p.pattern_id, None)
    for pid, p in built.items():
        patterns[pid] = p
        p.n_trips = int((take["pattern_id"] == pid).sum()) if len(take) else 0

    merged = pd.concat([ts.loc[~moved], take], ignore_index=True)
    ts.drop(ts.index, inplace=True)
    for c in merged.columns:
        ts[c] = merged[c].values

    note = (f"split {rid} at {jx}: {len(src)} trips become {len(take)} on "
            f"{a_id} and {b_id}, each half carrying its own share of the "
            f"original running time, so the pair costs what the whole cost")
    return kept, modelled, dropped, added, note


def _body_ending_at(stops: list[str], jx: str) -> list[str]:
    """The longer half of a stop list around ``jx``, oriented to end at it."""
    i = stops.index(jx)
    head, tail = stops[:i + 1], stops[i:]
    return head if len(head) >= len(tail) else list(reversed(tail))


def _pick_direction(pats: list[RoutePattern], d: int) -> RoutePattern | None:
    same = [p for p in pats if p.direction_id == d]
    pool = same or pats
    return max(pool, key=lambda p: len(p.stops)) if pool else None


def _retime_tstats(ts: pd.DataFrame, patterns: dict[str, RoutePattern],
                   before: dict[str, RoutePattern]) -> pd.DataFrame:
    """Scale each trip's scheduled runtime by how much its pattern changed.

    A trip's ``runtime_min`` comes from the feed and includes recovery and
    slack that the sum of median segment times does not reproduce. Replacing it
    with a pattern sum would therefore move vehicle-hours even when nothing was
    edited. Scaling by the ratio of new to old pattern running time changes
    exactly the geometry and nothing else, so an unedited pattern is an exact
    identity and an edited one keeps its schedule's own padding.

    Trips on a pattern that no longer exists are dropped, and trips created by
    a splice already carry the merged pattern's runtime.
    """
    def total(p: RoutePattern) -> float:
        return sum(s.run_time_sec for s in p.segments) / 60.0

    ratio, absolute, ns = {}, {}, {}
    for pid, p in patterns.items():
        ns[pid] = len(p.stops)
        old = before.get(pid)
        if old is not None and total(old) > 0:
            ratio[pid] = total(p) / total(old)
        else:
            absolute[pid] = total(p)          # new pattern: no schedule to scale

    out = ts[ts["pattern_id"].isin(ns)].copy()
    r = out["pattern_id"].map(ratio)
    a = out["pattern_id"].map(absolute)
    out["runtime_min"] = np.where(r.notna(),
                                  out["runtime_min"] * r.fillna(1.0),
                                  a.fillna(out["runtime_min"]))
    out["n_stops"] = out["pattern_id"].map(ns).astype(int)
    out["last_arr_sec"] = out["first_dep_sec"] + out["runtime_min"] * 60.0
    return out.reset_index(drop=True)


def _rebuild(net: TransitNetwork,
             patterns: dict[str, RoutePattern]) -> TransitNetwork:
    stop_routes: dict[str, set[str]] = {}
    route_stops: dict[str, set[str]] = {}
    for p in patterns.values():
        for sid in p.stops:
            stop_routes.setdefault(sid, set()).add(p.route_id)
            route_stops.setdefault(p.route_id, set()).add(sid)
    return TransitNetwork(stops=net.stops, patterns=patterns,
                          stop_routes=stop_routes, route_stops=route_stops)


def describe(edits: Iterable[GeometryEdit]) -> str:
    return "; ".join(e.description for e in edits) or "no geometry change"
