"""RAPTOR over the scheduled transit network.

Two routers share one precomputed network:

``earliest_arrival``
    Classic timetabled RAPTOR (Delling, Pajor & Werneck). Given a source stop
    and a departure time it returns earliest arrival at every stop by round.
    This is ground truth against the real published schedule and is what
    validates the pattern/segment extraction.

``generalized_cost``
    Frequency-based RAPTOR with generalized-cost labels instead of clock times.
    Boarding a pattern costs the expected wait implied by that pattern's
    headway, riding costs weighted in-vehicle time, walking costs weighted walk
    time, and every boarding after the first adds the transfer penalty. Because
    the only frequency input is a headway per (route, period), this router
    composes directly with :class:`~cota_opt.frequency.FrequencyPlan` — which is
    what lets passengers re-route when the service plan changes.

Round structure carries the transfer dimension: round *k* holds the best label
reachable with exactly *k* boardings, so the result is a Pareto set over
(cost, number of transfers) rather than a single scalar.

Known approximation
-------------------
A passenger is assigned to the single best *pattern*, not to the combined
frequency of every pattern that would serve them (the "optimal strategy" or
hyperpath problem). On this network 52 of 78 route-directions run a single
pattern and the dominant pattern carries 86% of trips on average, so the
understatement of effective frequency is small. It is an understatement, not a
bias in either direction of the experiment's conclusion.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from .cost import CostWeights, expected_wait_min
from .gtfs import GTFSFeed
from .network import TransitNetwork

log = logging.getLogger(__name__)

INF = np.inf
WALK_SPEED_M_PER_MIN = 80.0     # 4.8 km/h; overridden from config


@dataclass
class RaptorNetwork:
    """Flat-array network for round-based routing."""

    stop_ids: list[str]
    stop_index: dict[str, int]
    pattern_ids: list[str]
    pattern_route: list[str]
    pattern_direction: list[int]
    # pattern -> ordered stops and cumulative run seconds from the first stop
    pat_offsets: np.ndarray          # (n_pat + 1,)
    pat_stops: np.ndarray            # flat stop indices
    pat_cumsec: np.ndarray           # flat cumulative seconds
    # stop -> patterns serving it, with the position along each pattern
    stop_pat_offsets: np.ndarray     # (n_stops + 1,)
    stop_pat_idx: np.ndarray
    stop_pat_pos: np.ndarray
    # footpaths
    fp_offsets: np.ndarray           # (n_stops + 1,)
    fp_to: np.ndarray
    fp_min: np.ndarray               # walk minutes
    # timetable (optional, for earliest_arrival)
    trip_offsets: np.ndarray | None = None      # per pattern, trip counts (cumulative)
    trip_elem_offsets: np.ndarray | None = None  # per pattern, index into the flat arrays
    trip_dep: np.ndarray | None = None          # flattened trip x stop departure secs
    trip_arr: np.ndarray | None = None
    trip_count: np.ndarray | None = None        # trips per pattern
    pattern_trips_period: dict[tuple[str, str], int] = field(default_factory=dict)
    direction_trips_period: dict[tuple[str, int, str], int] = field(default_factory=dict)

    @property
    def n_stops(self) -> int:
        return len(self.stop_ids)

    @property
    def n_patterns(self) -> int:
        return len(self.pattern_ids)

    def idx(self, stop_id: str) -> int:
        return self.stop_index[stop_id]


def build_raptor_network(
    feed: GTFSFeed,
    net: TransitNetwork,
    tstats: pd.DataFrame,
    stops_projected,
    walk_radius_m: float = 400.0,
    walk_speed_m_per_min: float = WALK_SPEED_M_PER_MIN,
    max_footpaths_per_stop: int = 12,
    periods: dict[str, tuple[float, float]] | None = None,
    with_timetable: bool = True,
) -> RaptorNetwork:
    """Precompute the flat network. Footpaths come from ``transfers.txt`` plus
    generated links between stops within ``walk_radius_m`` (projected CRS)."""
    served = sorted(set().union(*net.route_stops.values())) if net.route_stops else []
    stop_ids = [s for s in served if s in net.stops]
    stop_index = {s: i for i, s in enumerate(stop_ids)}
    n_stops = len(stop_ids)

    pattern_ids = [p for p in net.patterns
                   if all(s in stop_index for s in net.patterns[p].stops)]
    pat_offsets = np.zeros(len(pattern_ids) + 1, dtype=np.int64)
    stops_flat: list[int] = []
    cum_flat: list[float] = []
    pattern_route, pattern_direction = [], []
    for i, pid in enumerate(pattern_ids):
        p = net.patterns[pid]
        pattern_route.append(p.route_id)
        pattern_direction.append(p.direction_id)
        cum = 0.0
        stops_flat.append(stop_index[p.stops[0]])
        cum_flat.append(0.0)
        for seg in p.segments:
            cum += seg.run_time_sec
            stops_flat.append(stop_index[seg.to_stop])
            cum_flat.append(cum)
        pat_offsets[i + 1] = len(stops_flat)
    pat_stops = np.asarray(stops_flat, dtype=np.int64)
    pat_cumsec = np.asarray(cum_flat, dtype=np.float64)

    # stop -> (pattern, position)
    by_stop: dict[int, list[tuple[int, int]]] = {i: [] for i in range(n_stops)}
    for pi in range(len(pattern_ids)):
        a, b = pat_offsets[pi], pat_offsets[pi + 1]
        for pos, s in enumerate(pat_stops[a:b]):
            by_stop[int(s)].append((pi, pos))
    stop_pat_offsets = np.zeros(n_stops + 1, dtype=np.int64)
    sp_idx, sp_pos = [], []
    for s in range(n_stops):
        for pi, pos in by_stop[s]:
            sp_idx.append(pi)
            sp_pos.append(pos)
        stop_pat_offsets[s + 1] = len(sp_idx)

    # footpaths
    fp = _build_footpaths(feed, stop_ids, stop_index, stops_projected,
                          walk_radius_m, walk_speed_m_per_min,
                          max_footpaths_per_stop)
    fp_offsets, fp_to, fp_min = fp

    rn = RaptorNetwork(
        stop_ids=stop_ids, stop_index=stop_index, pattern_ids=pattern_ids,
        pattern_route=pattern_route, pattern_direction=pattern_direction,
        pat_offsets=pat_offsets, pat_stops=pat_stops, pat_cumsec=pat_cumsec,
        stop_pat_offsets=stop_pat_offsets,
        stop_pat_idx=np.asarray(sp_idx, dtype=np.int64),
        stop_pat_pos=np.asarray(sp_pos, dtype=np.int64),
        fp_offsets=fp_offsets, fp_to=fp_to, fp_min=fp_min)

    if periods is not None:
        _attach_trip_counts(rn, tstats, periods)
    if with_timetable:
        _attach_timetable(rn, feed, tstats)
    log.info("raptor network: %d stops, %d patterns, %d footpaths",
             n_stops, len(pattern_ids), len(fp_to))
    return rn


def _build_footpaths(feed, stop_ids, stop_index, stops_projected,
                     radius_m, speed, max_per_stop):
    sp = stops_projected[stops_projected["stop_id"].isin(stop_index)].copy()
    sp = sp.set_index("stop_id").loc[stop_ids]
    geoms = sp.geometry.to_numpy()
    sidx = sp.sindex
    pairs: dict[int, dict[int, float]] = {i: {} for i in range(len(stop_ids))}

    for i, g in enumerate(geoms):
        cand = list(sidx.query(g.buffer(radius_m)))
        d = [(j, g.distance(geoms[j])) for j in cand if j != i]
        d = [(j, dist) for j, dist in d if dist <= radius_m]
        d.sort(key=lambda t: t[1])
        for j, dist in d[:max_per_stop]:
            pairs[i][int(j)] = dist / speed

    # transfers.txt links are agency-asserted and always kept
    tr = feed.tables.get("transfers", pd.DataFrame())
    n_declared = 0
    if not tr.empty and {"from_stop_id", "to_stop_id"} <= set(tr.columns):
        gmap = {s: geoms[k] for k, s in enumerate(stop_ids)}
        for a, b, mtt in zip(tr["from_stop_id"], tr["to_stop_id"],
                             tr.get("min_transfer_time", pd.Series([np.nan] * len(tr)))):
            if a not in stop_index or b not in stop_index or a == b:
                continue
            i, j = stop_index[a], stop_index[b]
            walk = (float(mtt) / 60.0 if pd.notna(mtt)
                    else gmap[a].distance(gmap[b]) / speed)
            if j not in pairs[i] or walk < pairs[i][j]:
                pairs[i][j] = walk
                n_declared += 1
            if i not in pairs[j] or walk < pairs[j][i]:
                pairs[j][i] = walk

    offsets = np.zeros(len(stop_ids) + 1, dtype=np.int64)
    to_flat, min_flat = [], []
    for i in range(len(stop_ids)):
        for j, w in sorted(pairs[i].items()):
            to_flat.append(j)
            min_flat.append(w)
        offsets[i + 1] = len(to_flat)
    log.info("footpaths: %d links (%d from transfers.txt)", len(to_flat), n_declared)
    return offsets, np.asarray(to_flat, dtype=np.int64), np.asarray(min_flat, float)


def _attach_trip_counts(rn: RaptorNetwork, tstats: pd.DataFrame,
                        periods: dict[str, tuple[float, float]]) -> None:
    """Trips per (pattern, period) and per (route, direction, period).

    A pattern's effective headway is the route-direction headway scaled by the
    share of that direction's trips the pattern actually carries.
    """
    from .configs import period_of_seconds
    ts = tstats.copy()
    ts["period"] = ts["first_dep_sec"].map(lambda s: period_of_seconds(s, periods))
    ts = ts.dropna(subset=["period"])
    rn.pattern_trips_period = {
        (str(p), str(per)): int(n) for (p, per), n in
        ts.groupby(["pattern_id", "period"])["trip_id"].count().items()}
    rn.direction_trips_period = {
        (str(r), int(d), str(per)): int(n) for (r, d, per), n in
        ts.groupby(["route_id", "direction_id", "period"])["trip_id"].count().items()}


def _attach_timetable(rn: RaptorNetwork, feed: GTFSFeed, tstats: pd.DataFrame) -> None:
    """Per-pattern trip departure/arrival matrices for timetabled RAPTOR."""
    st = feed.stop_times[feed.stop_times["trip_id"].isin(tstats["trip_id"])]
    st = st.sort_values(["trip_id", "stop_sequence"])
    pat_of_trip = tstats.set_index("trip_id")["pattern_id"].to_dict()
    pid_index = {p: i for i, p in enumerate(rn.pattern_ids)}

    per_pat: dict[int, list[tuple[float, np.ndarray, np.ndarray]]] = {
        i: [] for i in range(rn.n_patterns)}
    for tid, grp in st.groupby("trip_id", sort=False):
        pid = pat_of_trip.get(tid)
        pi = pid_index.get(pid)
        if pi is None:
            continue
        dep = grp["departure_sec"].to_numpy(float)
        arr = (grp["arrival_sec"].to_numpy(float)
               if "arrival_sec" in grp.columns else dep)
        if len(dep) != rn.pat_offsets[pi + 1] - rn.pat_offsets[pi]:
            continue
        per_pat[pi].append((dep[0], dep, arr))

    # Patterns have different stop counts, so the flat arrays need an explicit
    # element offset per pattern; a trip-count offset alone mis-slices.
    offsets = np.zeros(rn.n_patterns + 1, dtype=np.int64)
    elem_offsets = np.zeros(rn.n_patterns + 1, dtype=np.int64)
    dep_rows, arr_rows, counts = [], [], np.zeros(rn.n_patterns, dtype=np.int64)
    n_elems = 0
    for pi in range(rn.n_patterns):
        m = int(rn.pat_offsets[pi + 1] - rn.pat_offsets[pi])
        trips = sorted(per_pat[pi], key=lambda t: t[0])
        counts[pi] = len(trips)
        for _, dep, arr in trips:
            dep_rows.append(dep)
            arr_rows.append(arr)
        n_elems += len(trips) * m
        offsets[pi + 1] = offsets[pi] + len(trips)
        elem_offsets[pi + 1] = n_elems
    rn.trip_offsets = offsets
    rn.trip_elem_offsets = elem_offsets
    rn.trip_count = counts
    rn.trip_dep = np.concatenate(dep_rows) if dep_rows else np.zeros(0)
    rn.trip_arr = np.concatenate(arr_rows) if arr_rows else np.zeros(0)


# ---------------------------------------------------------------------------
# Timetabled RAPTOR — earliest arrival
# ---------------------------------------------------------------------------

def earliest_arrival(rn: RaptorNetwork, source: str, departure_sec: float,
                     max_rounds: int = 4,
                     min_transfer_sec: float = 60.0) -> np.ndarray:
    """Earliest arrival time (seconds) at every stop. INF where unreachable.

    Returns an array of shape ``(max_rounds + 1, n_stops)``: row *k* is the
    earliest arrival using at most *k* boardings.
    """
    n = rn.n_stops
    best = np.full(n, INF)
    rounds = np.full((max_rounds + 1, n), INF)
    s0 = rn.idx(source)
    best[s0] = departure_sec
    rounds[0, s0] = departure_sec
    # initial footpaths
    for k in range(rn.fp_offsets[s0], rn.fp_offsets[s0 + 1]):
        j, w = int(rn.fp_to[k]), rn.fp_min[k] * 60.0
        if departure_sec + w < best[j]:
            best[j] = rounds[0, j] = departure_sec + w
    marked = set(np.flatnonzero(np.isfinite(rounds[0])).tolist())

    for rnd in range(1, max_rounds + 1):
        rounds[rnd] = rounds[rnd - 1]
        # patterns to scan, with the earliest marked boarding position
        queue: dict[int, int] = {}
        for s in marked:
            a, b = rn.stop_pat_offsets[s], rn.stop_pat_offsets[s + 1]
            for k in range(a, b):
                pi, pos = int(rn.stop_pat_idx[k]), int(rn.stop_pat_pos[k])
                if pi not in queue or pos < queue[pi]:
                    queue[pi] = pos
        new_marked: set[int] = set()

        for pi, start_pos in queue.items():
            a, b = rn.pat_offsets[pi], rn.pat_offsets[pi + 1]
            pstops = rn.pat_stops[a:b]
            m = b - a
            n_trips = int(rn.trip_offsets[pi + 1] - rn.trip_offsets[pi])
            if n_trips == 0:
                continue
            e0 = int(rn.trip_elem_offsets[pi])
            e1 = e0 + n_trips * m
            dep = rn.trip_dep[e0:e1].reshape(n_trips, m)
            arr = rn.trip_arr[e0:e1].reshape(n_trips, m)
            cur_trip = -1
            for pos in range(start_pos, m):
                s = int(pstops[pos])
                if cur_trip >= 0:
                    t = arr[cur_trip, pos]
                    if t < best[s] - 1e-9:
                        best[s] = rounds[rnd, s] = t
                        new_marked.add(s)
                # can we catch an earlier trip here?
                ready = rounds[rnd - 1, s]
                if np.isfinite(ready):
                    ready_t = ready + (min_transfer_sec if rnd > 1 else 0.0)
                    col = dep[:, pos]
                    cand = int(np.searchsorted(col, ready_t, side="left"))
                    if cand < n_trips and (cur_trip < 0 or cand < cur_trip):
                        cur_trip = cand
        # footpath relaxation
        for s in list(new_marked):
            base = rounds[rnd, s]
            for k in range(rn.fp_offsets[s], rn.fp_offsets[s + 1]):
                j, w = int(rn.fp_to[k]), rn.fp_min[k] * 60.0
                if base + w < best[j] - 1e-9:
                    best[j] = rounds[rnd, j] = base + w
                    new_marked.add(j)
        marked = new_marked
        if not marked:
            rounds[rnd + 1:] = rounds[rnd]
            break
    return rounds


# ---------------------------------------------------------------------------
# Frequency-based generalized-cost RAPTOR
# ---------------------------------------------------------------------------

@dataclass
class Leg:
    kind: str                  # "ride" | "walk"
    from_stop: str
    to_stop: str
    route_id: str = ""
    pattern_id: str = ""
    in_vehicle_min: float = 0.0
    walk_min: float = 0.0

    def to_tuple(self) -> tuple:
        return (self.kind, self.from_stop, self.to_stop, self.route_id,
                self.pattern_id, round(self.in_vehicle_min, 4),
                round(self.walk_min, 4))


@dataclass
class Journey:
    origin: str
    destination: str
    cost: float
    n_transfers: int
    legs: list[Leg]

    @property
    def routes(self) -> list[str]:
        return [l.route_id for l in self.legs if l.kind == "ride"]

    @property
    def in_vehicle_min(self) -> float:
        return sum(l.in_vehicle_min for l in self.legs)

    @property
    def walk_min(self) -> float:
        return sum(l.walk_min for l in self.legs)


def route_level_headways(rn: RaptorNetwork, headway_by_route_period: dict,
                         period: str, fallback: float = np.inf) -> np.ndarray:
    """Every pattern at its route's whole frequency -- multiplier 1.0.

    Deliberately more generous than any real Model B multiplier, which counts
    only the patterns that serve a particular movement in a particular order:
    this counts every trip the direction runs. A path priced here can only be
    cheaper than the same path priced properly, which is what makes it a strict
    lower bound.

    One definition, two callers. The gate 11 diagnostic uses it to decide which
    OD pairs *could* be hiding a cheaper Model B path, and path enumeration uses
    it as a search scenario to go find them. If those two drifted apart the
    rerun would be testing something other than what the augmentation provides.
    """
    out = np.full(rn.n_patterns, fallback)
    for pi in range(rn.n_patterns):
        h = headway_by_route_period.get((rn.pattern_route[pi], period))
        if h is None:
            continue
        n_pat = rn.pattern_trips_period.get((rn.pattern_ids[pi], period), 0)
        n_dir = rn.direction_trips_period.get(
            (rn.pattern_route[pi], rn.pattern_direction[pi], period), 0)
        if n_pat <= 0 or n_dir <= 0:
            continue
        out[pi] = h
    return out


def pattern_headways(rn: RaptorNetwork, headway_by_route_period: dict,
                     period: str, fallback: float = np.inf) -> np.ndarray:
    """Effective headway per pattern in a period.

    ``headway_by_route_period[(route_id, period)]`` is the route's per-direction
    headway. A pattern carrying only part of its direction's trips is
    proportionally less frequent.
    """
    out = np.full(rn.n_patterns, fallback)
    for pi, pid in enumerate(rn.pattern_ids):
        route = rn.pattern_route[pi]
        direction = rn.pattern_direction[pi]
        h = headway_by_route_period.get((route, period))
        if h is None:
            continue
        n_pat = rn.pattern_trips_period.get((pid, period), 0)
        n_dir = rn.direction_trips_period.get((route, direction, period), 0)
        if n_pat <= 0 or n_dir <= 0:
            continue
        out[pi] = h * (n_dir / n_pat)
    return out


def generalized_cost(
    rn: RaptorNetwork,
    sources: Sequence[str] | str,
    pat_headway: np.ndarray,
    w: CostWeights,
    wait_kwargs: dict | None = None,
    max_rounds: int = 3,
    source_costs: Sequence[float] | None = None,
    max_cost: float = INF,
    trace: bool = False,
) -> tuple[np.ndarray, np.ndarray, dict | None]:
    """Least generalized cost from ``sources`` to every stop.

    Returns ``(best_cost, best_round, parents)``. ``best_cost[i]`` is the least
    generalized cost (equivalent in-vehicle minutes) of reaching stop *i*;
    ``best_round[i]`` is the number of boardings on that path. ``parents`` is
    returned only when ``trace`` is set and is used to reconstruct journeys.
    """
    wk = wait_kwargs or {}
    n = rn.n_stops
    if isinstance(sources, str):
        sources = [sources]
    src = [rn.idx(s) for s in sources]
    init = list(source_costs) if source_costs is not None else [0.0] * len(src)

    wait_cost = np.array([
        w.waiting * expected_wait_min(h, **wk) if np.isfinite(h) and h < 1e5
        else INF for h in pat_headway])
    ivt_per_sec = w.in_vehicle / 60.0

    best = np.full(n, INF)
    prev = np.full(n, INF)
    best_round = np.zeros(n, dtype=np.int8)
    # Labels are carried forward between rounds, so a label reached in round k
    # may represent fewer than k boardings (a walk-only path, say). Boarding
    # cost must key off how many times this traveller has actually boarded, not
    # off the round counter, or a first boarding gets charged as a transfer.
    nboard = np.zeros(n, dtype=np.int8)
    nboard_prev = np.zeros(n, dtype=np.int8)
    parents: dict[tuple[int, int], tuple] = {}

    for s, c in zip(src, init):
        if c < prev[s]:
            prev[s] = best[s] = c
    # initial walk
    for s, c in zip(src, init):
        for k in range(rn.fp_offsets[s], rn.fp_offsets[s + 1]):
            j = int(rn.fp_to[k])
            cand = c + w.walking * rn.fp_min[k]
            if cand < prev[j]:
                prev[j] = best[j] = cand
                nboard[j] = nboard_prev[j] = 0
                if trace:
                    parents[(0, j)] = ("walk", s, rn.fp_min[k])
    marked = set(np.flatnonzero(np.isfinite(prev)).tolist())

    for rnd in range(1, max_rounds + 1):
        cur = prev.copy()
        queue: dict[int, int] = {}
        for s in marked:
            a, b = rn.stop_pat_offsets[s], rn.stop_pat_offsets[s + 1]
            for k in range(a, b):
                pi, pos = int(rn.stop_pat_idx[k]), int(rn.stop_pat_pos[k])
                if pi not in queue or pos < queue[pi]:
                    queue[pi] = pos
        new_marked: set[int] = set()
        cur_nb = nboard_prev.copy()

        for pi, start_pos in queue.items():
            wc = wait_cost[pi]
            if not np.isfinite(wc):
                continue
            a, b = rn.pat_offsets[pi], rn.pat_offsets[pi + 1]
            pstops = rn.pat_stops[a:b]
            pcum = rn.pat_cumsec[a:b]
            xfer_wc = ((w.transfer_wait / w.waiting) * wc if w.waiting else wc)
            m = b - a
            best_board = INF
            board_at = -1
            board_nb = 0
            for pos in range(start_pos, m):
                s = int(pstops[pos])
                if np.isfinite(best_board):
                    cand = best_board + ivt_per_sec * pcum[pos]
                    if cand < best[s] - 1e-9 and cand <= max_cost:
                        best[s] = cur[s] = cand
                        best_round[s] = rnd
                        cur_nb[s] = board_nb + 1
                        new_marked.add(s)
                        if trace:
                            parents[(rnd, s)] = ("ride", pi, board_at, pos)
                ready = prev[s]
                if np.isfinite(ready):
                    # first boarding for this traveller, or a transfer?
                    is_xfer = nboard_prev[s] > 0
                    wait_here = xfer_wc if is_xfer else wc
                    pen = w.transfer_penalty if is_xfer else 0.0
                    v = ready + wait_here + pen - ivt_per_sec * pcum[pos]
                    if v < best_board - 1e-9:
                        best_board = v
                        board_at = pos
                        board_nb = int(nboard_prev[s])

        for s in list(new_marked):
            base = cur[s]
            for k in range(rn.fp_offsets[s], rn.fp_offsets[s + 1]):
                j = int(rn.fp_to[k])
                cand = base + w.walking * rn.fp_min[k]
                if cand < best[j] - 1e-9 and cand <= max_cost:
                    best[j] = cur[j] = cand
                    best_round[j] = rnd
                    cur_nb[j] = cur_nb[s]
                    new_marked.add(j)
                    if trace:
                        parents[(rnd, j)] = ("walk_after", s, rn.fp_min[k])
        prev = cur
        nboard_prev = cur_nb
        marked = new_marked
        if not marked:
            break
    return best, best_round, (parents if trace else None)


def reconstruct(rn: RaptorNetwork, parents: dict, target: str,
                rnd: int, sources: set[str]) -> Journey | None:
    """Rebuild the journey to ``target`` found in round ``rnd``.

    Returns ``None`` unless the back-walk actually terminates at a source stop.
    A partial trace is not a journey: storing one as if it were would understate
    its cost, because the missing legs are the ones nearest the origin.
    """
    legs: list[Leg] = []
    s = rn.idx(target)
    k = rnd
    guard = 0
    complete = False
    while guard < 64:
        guard += 1
        if rn.stop_ids[s] in sources and k == 0:
            complete = True
            break
        ent = parents.get((k, s))
        if ent is None:
            if k > 0:
                k -= 1
                continue
            break
        if ent[0] == "walk" or ent[0] == "walk_after":
            _, frm, wmin = ent
            legs.append(Leg("walk", rn.stop_ids[frm], rn.stop_ids[s],
                            walk_min=float(wmin)))
            s = frm
            if ent[0] == "walk":
                k = 0
        else:
            _, pi, board_pos, alight_pos = ent
            a = rn.pat_offsets[pi]
            frm = int(rn.pat_stops[a + board_pos])
            ivt = (rn.pat_cumsec[a + alight_pos] - rn.pat_cumsec[a + board_pos]) / 60.0
            legs.append(Leg("ride", rn.stop_ids[frm], rn.stop_ids[s],
                            route_id=rn.pattern_route[pi],
                            pattern_id=rn.pattern_ids[pi],
                            in_vehicle_min=float(ivt)))
            s = frm
            k -= 1
    if not complete and rn.stop_ids[s] in sources:
        complete = True
    legs.reverse()
    if not legs or not complete:
        return None
    n_rides = sum(1 for l in legs if l.kind == "ride")
    return Journey(origin=legs[0].from_stop, destination=target, cost=0.0,
                   n_transfers=max(0, n_rides - 1), legs=legs)
