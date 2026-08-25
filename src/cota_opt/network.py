"""Scheduled transit network representation.

Deliberately *not* a full RAPTOR/CSA implementation yet (AGENTS.md: build clean
abstractions first). This module provides:

- ``StopNode`` / ``PatternSegment`` — stop nodes and route-pattern connections
  with scheduled segment travel times;
- ``TransitNetwork`` — a frequency-based network view: per (route, direction,
  period) headway and per-segment run time, plus stop→route incidence and
  route↔route transfer opportunities;
- a ``networkx`` export for later shortest-path / RAPTOR work.

A frequency-based view (rather than a full timetable graph) is the right
abstraction for Experiment 1, whose decision variable *is* the headway.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import networkx as nx
import numpy as np
import pandas as pd

from .configs import period_of_seconds
from .gtfs import GTFSFeed


@dataclass(frozen=True)
class StopNode:
    stop_id: str
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class PatternSegment:
    """A scheduled connection between consecutive stops on a route pattern."""

    route_id: str
    direction_id: int
    pattern_id: str
    from_stop: str
    to_stop: str
    seq: int
    run_time_sec: float


@dataclass
class RoutePattern:
    route_id: str
    direction_id: int
    pattern_id: str
    stops: list[str]
    segments: list[PatternSegment]
    n_trips: int

    @property
    def total_run_time_min(self) -> float:
        return sum(s.run_time_sec for s in self.segments) / 60.0


@dataclass
class TransitNetwork:
    """Frequency-based scheduled network for one service day."""

    stops: dict[str, StopNode]
    patterns: dict[str, RoutePattern]                 # keyed by pattern_id
    stop_routes: dict[str, set[str]] = field(default_factory=dict)
    route_stops: dict[str, set[str]] = field(default_factory=dict)

    # -- construction -----------------------------------------------------
    @classmethod
    def from_feed(cls, feed: GTFSFeed, tstats: pd.DataFrame,
                  min_trips_per_pattern: int = 1) -> "TransitNetwork":
        stops = {}
        s = feed.stops
        lat = pd.to_numeric(s["stop_lat"], errors="coerce")
        lon = pd.to_numeric(s["stop_lon"], errors="coerce")
        for sid, name, la, lo in zip(s["stop_id"], s.get("stop_name", s["stop_id"]),
                                     lat, lon):
            if np.isfinite(la) and np.isfinite(lo):
                stops[sid] = StopNode(sid, str(name), float(la), float(lo))

        st = feed.stop_times[feed.stop_times["trip_id"].isin(tstats["trip_id"])]
        st = st.sort_values(["trip_id", "stop_sequence"])
        trip_meta = tstats.set_index("trip_id")[
            ["route_id", "direction_id", "pattern_id"]]

        # representative trip per pattern (median runtime) → segment times
        pat_counts = tstats.groupby("pattern_id")["trip_id"].count()
        patterns: dict[str, RoutePattern] = {}
        seg_accum: dict[str, dict[tuple[str, str, int], list[float]]] = defaultdict(
            lambda: defaultdict(list))
        pattern_stop_seq: dict[str, list[str]] = {}

        st = st.join(trip_meta, on="trip_id")
        for tid, grp in st.groupby("trip_id", sort=False):
            pid = grp["pattern_id"].iloc[0]
            sids = grp["stop_id"].tolist()
            pattern_stop_seq.setdefault(pid, sids)
            dep = grp["departure_sec"].to_numpy()
            arr = (grp["arrival_sec"].to_numpy() if "arrival_sec" in grp.columns
                   else dep)
            for i in range(len(sids) - 1):
                dt_sec = float(arr[i + 1] - dep[i])
                if np.isfinite(dt_sec) and dt_sec >= 0:
                    seg_accum[pid][(sids[i], sids[i + 1], i)].append(dt_sec)

        for pid, segmap in seg_accum.items():
            n = int(pat_counts.get(pid, 0))
            if n < min_trips_per_pattern:
                continue
            meta = tstats[tstats["pattern_id"] == pid].iloc[0]
            segs = [PatternSegment(str(meta["route_id"]), int(meta["direction_id"]),
                                   pid, a, b, i, float(np.median(v)))
                    for (a, b, i), v in sorted(segmap.items(), key=lambda kv: kv[0][2])]
            patterns[pid] = RoutePattern(
                route_id=str(meta["route_id"]),
                direction_id=int(meta["direction_id"]),
                pattern_id=pid,
                stops=pattern_stop_seq[pid],
                segments=segs,
                n_trips=n,
            )

        stop_routes: dict[str, set[str]] = defaultdict(set)
        route_stops: dict[str, set[str]] = defaultdict(set)
        for p in patterns.values():
            for sid in p.stops:
                stop_routes[sid].add(p.route_id)
                route_stops[p.route_id].add(sid)
        return cls(stops=stops, patterns=patterns,
                   stop_routes=dict(stop_routes), route_stops=dict(route_stops))

    # -- derived views ----------------------------------------------------
    def transfer_stops(self) -> dict[str, set[str]]:
        """Stops served by more than one route."""
        return {s: r for s, r in self.stop_routes.items() if len(r) > 1}

    def route_connections(self) -> dict[tuple[str, str], int]:
        """(route_a, route_b) → number of shared stops, a < b."""
        out: dict[tuple[str, str], int] = defaultdict(int)
        for routes in self.stop_routes.values():
            rs = sorted(routes)
            for i in range(len(rs)):
                for j in range(i + 1, len(rs)):
                    out[(rs[i], rs[j])] += 1
        return dict(out)

    def to_networkx(self) -> nx.DiGraph:
        """Directed graph of stop nodes and scheduled route-pattern segments."""
        g = nx.DiGraph()
        for sid, node in self.stops.items():
            g.add_node(sid, name=node.name, lat=node.lat, lon=node.lon)
        for p in self.patterns.values():
            for seg in p.segments:
                if g.has_edge(seg.from_stop, seg.to_stop):
                    e = g[seg.from_stop][seg.to_stop]
                    e["patterns"].add(p.pattern_id)
                    e["run_time_sec"] = min(e["run_time_sec"], seg.run_time_sec)
                else:
                    g.add_edge(seg.from_stop, seg.to_stop,
                               run_time_sec=seg.run_time_sec,
                               patterns={p.pattern_id})
        return g


def period_headways(tstats: pd.DataFrame,
                    periods: dict[str, tuple[float, float]]) -> pd.DataFrame:
    """Observed headway per (route, direction, period) — the baseline plan."""
    ts = tstats.copy()
    ts["period"] = ts["first_dep_sec"].map(lambda s: period_of_seconds(s, periods))
    ts = ts.dropna(subset=["period"])
    rows = []
    for (rid, did, per), grp in ts.groupby(["route_id", "direction_id", "period"]):
        deps = np.sort(grp["first_dep_sec"].to_numpy())
        dur_min = (periods[per][1] - periods[per][0]) * 60.0
        headway = (float(np.mean(np.diff(deps)) / 60.0) if len(deps) >= 2
                   else dur_min / len(deps))
        rows.append({"route_id": rid, "direction_id": did, "period": per,
                     "n_trips": len(deps), "headway_min": headway,
                     "runtime_min": float(grp["runtime_min"].mean()),
                     "period_duration_min": dur_min})
    return pd.DataFrame(rows)
