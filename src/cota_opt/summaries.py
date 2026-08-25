"""Baseline schedule summaries derived from a GTFS feed.

All metrics here are *scheduled estimates* derived from GTFS. They are not
COTA's reported operating statistics (see AGENTS.md rule 6).

Methodology notes
-----------------
- "busiest weekday" = the Tue/Wed/Thu in the feed window with most scheduled trips.
- trip runtime = last scheduled arrival − first scheduled departure.
- headway within a period = mean gap between consecutive first departures of
  trips of the same route+direction whose first departure falls in the period;
  with n<2 trips, the period length divided by n.
- revenue vehicle-hours = Σ trip runtimes (excludes deadhead and layover).
- peak concurrent buses = max over time of simultaneously running trips
  (schedule-based; excludes layover/deadhead, so understates true pull-out).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .configs import period_of_seconds
from .gtfs import GTFSFeed


def trip_stats(feed: GTFSFeed, service_ids: set[str]) -> pd.DataFrame:
    """Per-trip schedule statistics for the given service day."""
    trips = feed.trips[feed.trips["service_id"].isin(service_ids)].copy()
    st = feed.stop_times[feed.stop_times["trip_id"].isin(trips["trip_id"])]
    st = st.dropna(subset=["departure_sec"]).sort_values(["trip_id", "stop_sequence"])

    g = st.groupby("trip_id")
    first_dep = g["departure_sec"].first()
    last_arr = g["arrival_sec"].last() if "arrival_sec" in st.columns else g["departure_sec"].last()
    n_stops = g["stop_id"].count()
    pattern = g["stop_id"].agg(
        lambda s: hashlib.md5("|".join(s).encode()).hexdigest()[:10])

    out = trips.set_index("trip_id")
    out["first_dep_sec"] = first_dep
    out["last_arr_sec"] = last_arr
    out["runtime_min"] = (out["last_arr_sec"] - out["first_dep_sec"]) / 60.0
    out["n_stops"] = n_stops
    out["pattern_id"] = pattern
    if "direction_id" not in out.columns:
        out["direction_id"] = 0
    out["direction_id"] = pd.to_numeric(out["direction_id"], errors="coerce").fillna(0).astype(int)
    out = out.dropna(subset=["first_dep_sec", "runtime_min"])
    return out.reset_index()


def route_period_stats(tstats: pd.DataFrame,
                       periods: dict[str, tuple[float, float]]) -> pd.DataFrame:
    """Per route × direction × period supply statistics."""
    ts = tstats.copy()
    ts["period"] = ts["first_dep_sec"].map(lambda s: period_of_seconds(s, periods))
    ts = ts.dropna(subset=["period"])
    rows = []
    for (rid, did, per), grp in ts.groupby(["route_id", "direction_id", "period"]):
        deps = np.sort(grp["first_dep_sec"].to_numpy())
        dur_min = (periods[per][1] - periods[per][0]) * 60.0
        if len(deps) >= 2:
            headway = float(np.mean(np.diff(deps)) / 60.0)
        else:
            headway = dur_min / len(deps)
        rows.append({
            "route_id": rid, "direction_id": did, "period": per,
            "n_trips": int(len(deps)),
            "mean_headway_min": headway,
            "mean_runtime_min": float(grp["runtime_min"].mean()),
            "period_duration_min": dur_min,
        })
    return pd.DataFrame(rows)


def route_summary(tstats: pd.DataFrame, feed: GTFSFeed) -> pd.DataFrame:
    """Per-route service-day summary."""
    rows = []
    routes = feed.routes.set_index("route_id")
    for rid, grp in tstats.groupby("route_id"):
        first = grp["first_dep_sec"].min() / 3600.0
        last = (grp["first_dep_sec"] + grp["runtime_min"] * 60).max() / 3600.0
        name = ""
        if rid in routes.index:
            r = routes.loc[rid]
            name = str(r.get("route_short_name", "") or "") + " " + \
                   str(r.get("route_long_name", "") or "")
        rows.append({
            "route_id": rid, "route_name": name.strip(),
            "n_trips": int(len(grp)),
            "n_patterns": int(grp["pattern_id"].nunique()),
            "n_directions": int(grp["direction_id"].nunique()),
            "span_start_hr": float(first), "span_end_hr": float(last),
            "span_hours": float(last - first),
            "mean_runtime_min": float(grp["runtime_min"].mean()),
            "revenue_veh_hours": float(grp["runtime_min"].sum() / 60.0),
        })
    return pd.DataFrame(rows).sort_values("revenue_veh_hours", ascending=False)


def concurrent_trips(tstats: pd.DataFrame,
                     periods: dict[str, tuple[float, float]] | None = None,
                     ) -> tuple[int, dict[str, int]]:
    """Peak number of simultaneously running scheduled trips (system, per period)."""
    starts = tstats["first_dep_sec"].to_numpy()
    ends = tstats["last_arr_sec"].to_numpy()
    events = np.concatenate([
        np.stack([starts, np.ones_like(starts)], axis=1),
        np.stack([ends, -np.ones_like(ends)], axis=1)])
    events = events[np.lexsort((events[:, 1], events[:, 0]))]
    running = np.cumsum(events[:, 1])
    system_peak = int(running.max()) if len(running) else 0
    per_period: dict[str, int] = {}
    if periods:
        for name in periods:
            per_period[name] = 0
        for (t, _), r in zip(events, running):
            pname = period_of_seconds(t, periods)
            if pname is not None:
                per_period[pname] = max(per_period[pname], int(r))
    return system_peak, per_period


@dataclass
class SystemSummary:
    service_date: str
    n_routes: int
    n_stops_served: int
    n_trips: int
    revenue_veh_hours: float
    peak_concurrent_buses: int
    peak_by_period: dict[str, int]
    veh_miles_scheduled: float | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in vars(self).items()}


def system_summary(feed: GTFSFeed, tstats: pd.DataFrame, service_date: str,
                   periods: dict[str, tuple[float, float]],
                   veh_miles: float | None = None) -> SystemSummary:
    st = feed.stop_times[feed.stop_times["trip_id"].isin(tstats["trip_id"])]
    peak, by_period = concurrent_trips(tstats, periods)
    return SystemSummary(
        service_date=service_date,
        n_routes=int(tstats["route_id"].nunique()),
        n_stops_served=int(st["stop_id"].nunique()),
        n_trips=int(len(tstats)),
        revenue_veh_hours=float(tstats["runtime_min"].sum() / 60.0),
        peak_concurrent_buses=peak,
        peak_by_period=by_period,
        veh_miles_scheduled=veh_miles,
    )
