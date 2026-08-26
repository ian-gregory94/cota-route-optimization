"""Route classification from observed service patterns.

Why this exists: a frequency model prices service as ``E[wait](headway)``. That
is meaningful for a route running every 10-30 minutes all day. It is *not*
meaningful for a route that runs one trip at 07:15 and one at 17:40 — nobody
waits 90 minutes at that stop, they catch the 07:15. Treating such a route's
"headway" as 180 minutes makes a demand-retention curve read a deliberate
commuter-express timetable as a coverage failure, and an optimizer will then
lavish service on it.

Classes are derived from the GTFS service pattern, not from route names or
numbering, so the rule transfers to other agencies.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

log = logging.getLogger(__name__)

PEAK_PERIODS = ("am_peak", "pm_peak")
ALLDAY_PERIODS = ("midday", "evening")


@dataclass(frozen=True)
class RouteClass:
    route_id: str
    name: str
    klass: str            # all_day | peak_express | limited | owl_only
    trips_by_period: dict[str, int]
    total_trips: int

    @property
    def is_peak_express(self) -> bool:
        return self.klass == "peak_express"


def classify_routes(tstats: pd.DataFrame, routes: pd.DataFrame,
                    period_col: str = "period",
                    min_alldaytrips: int = 1) -> dict[str, RouteClass]:
    """Classify each route from the periods in which it actually operates.

    - ``peak_express``: runs in a peak but has **no** midday and **no** evening
      service. A designed commuter timetable, not a frequency.
    - ``owl_only``: operates only in the owl window.
    - ``limited``: has all-day service but fewer than two trips in every period
      it serves — too sparse for the headway abstraction to mean much.
    - ``all_day``: everything else.
    """
    if period_col not in tstats.columns:
        raise ValueError(f"tstats has no '{period_col}' column")
    counts = (tstats.groupby(["route_id", period_col])["trip_id"].count()
              .unstack(fill_value=0))
    name_of = {}
    if not routes.empty:
        for r in routes.itertuples():
            short = str(getattr(r, "route_short_name", "") or "")
            long_ = str(getattr(r, "route_long_name", "") or "")
            name_of[str(r.route_id)] = f"{short} {long_}".strip()

    out: dict[str, RouteClass] = {}
    for rid, row in counts.iterrows():
        by = {p: int(row.get(p, 0)) for p in counts.columns}
        allday = sum(by.get(p, 0) for p in ALLDAY_PERIODS)
        peak = sum(by.get(p, 0) for p in PEAK_PERIODS)
        total = int(row.sum())
        if peak > 0 and allday < min_alldaytrips:
            k = "peak_express"
        elif total > 0 and by.get("owl", 0) == total:
            k = "owl_only"
        elif max(by.values()) <= 2:
            k = "limited"
        else:
            k = "all_day"
        out[str(rid)] = RouteClass(str(rid), name_of.get(str(rid), ""), k, by, total)

    n = {}
    for rc in out.values():
        n[rc.klass] = n.get(rc.klass, 0) + 1
    log.info("route classes: %s", n)
    return out


def summary_frame(classes: dict[str, RouteClass]) -> pd.DataFrame:
    rows = []
    for rc in classes.values():
        rows.append({"route_id": rc.route_id, "name": rc.name, "class": rc.klass,
                     "total_trips": rc.total_trips, **rc.trips_by_period})
    return pd.DataFrame(rows).sort_values(["class", "route_id"])


def locked_keys(classes: dict[str, RouteClass], services: dict,
                lock_classes: tuple[str, ...] = ("peak_express",)) -> set:
    """(route, period) keys whose headway must be held at baseline."""
    locked = {k for k in services
              if classes.get(k[0]) and classes[k[0]].klass in lock_classes}
    if locked:
        log.info("locking %d route-periods across %d routes in classes %s",
                 len(locked), len({k[0] for k in locked}), lock_classes)
    return locked
