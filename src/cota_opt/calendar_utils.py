"""GTFS service calendar resolution."""
from __future__ import annotations

import datetime as dt

import pandas as pd

from .gtfs import GTFSFeed

WEEKDAY_COLS = ["monday", "tuesday", "wednesday", "thursday", "friday",
                "saturday", "sunday"]


def service_ids_for_date(feed: GTFSFeed, date: dt.date) -> set[str]:
    """Active service_ids on a calendar date (calendar + calendar_dates)."""
    ids: set[str] = set()
    cal = feed.calendar
    d_int = int(date.strftime("%Y%m%d"))
    if not cal.empty:
        col = WEEKDAY_COLS[date.weekday()]
        m = (
            (pd.to_numeric(cal[col], errors="coerce") == 1)
            & (pd.to_numeric(cal["start_date"], errors="coerce") <= d_int)
            & (pd.to_numeric(cal["end_date"], errors="coerce") >= d_int)
        )
        ids |= set(cal.loc[m, "service_id"])
    cd = feed.calendar_dates
    if not cd.empty:
        cd_date = cd[pd.to_numeric(cd["date"], errors="coerce") == d_int]
        ex = pd.to_numeric(cd_date["exception_type"], errors="coerce")
        ids |= set(cd_date.loc[ex == 1, "service_id"])
        ids -= set(cd_date.loc[ex == 2, "service_id"])
    return ids


def feed_date_range(feed: GTFSFeed) -> tuple[dt.date, dt.date]:
    """Overall [start, end] date range covered by the calendars."""
    dates: list[int] = []
    if not feed.calendar.empty:
        dates += pd.to_numeric(feed.calendar["start_date"], errors="coerce").dropna().astype(int).tolist()
        dates += pd.to_numeric(feed.calendar["end_date"], errors="coerce").dropna().astype(int).tolist()
    if not feed.calendar_dates.empty:
        dates += pd.to_numeric(feed.calendar_dates["date"], errors="coerce").dropna().astype(int).tolist()
    if not dates:
        raise ValueError("feed has no calendar dates")
    def to_date(x: int) -> dt.date:
        s = str(x)
        return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    return to_date(min(dates)), to_date(max(dates))


def _weekday_service_days(feed: GTFSFeed) -> list[tuple[dt.date, frozenset[str], int]]:
    """(date, active service_ids, scheduled trip count) for each Tue/Wed/Thu."""
    start, end = feed_date_range(feed)
    counts_by_sid = feed.trips.groupby("service_id")["trip_id"].count()
    out = []
    d = start
    while d <= end:
        if d.weekday() in (1, 2, 3):  # Tue, Wed, Thu — avoids Mon/Fri holiday skew
            sids = frozenset(service_ids_for_date(feed, d))
            n = int(counts_by_sid.reindex(list(sids)).fillna(0).sum())
            if n:
                out.append((d, sids, n))
        d += dt.timedelta(days=1)
    return out


def busiest_weekday(feed: GTFSFeed) -> tuple[dt.date, set[str]]:
    """The Tue/Wed/Thu within the feed window with the most scheduled trips."""
    days = _weekday_service_days(feed)
    if not days:
        raise ValueError("no weekday service found in feed window")
    d, sids, _ = max(days, key=lambda r: r[2])
    return d, set(sids)


def representative_weekday(feed: GTFSFeed) -> tuple[dt.date, set[str], int]:
    """The *modal* weekday service pattern — the typical operating day.

    Preferred over :func:`busiest_weekday` for a baseline: a single unusually
    busy date (special event service, a one-off added calendar exception) is not
    representative of the resource envelope COTA actually operates.
    Returns (earliest date with that pattern, service_ids, number of days it occurs).
    """
    days = _weekday_service_days(feed)
    if not days:
        raise ValueError("no weekday service found in feed window")
    counts: dict[frozenset[str], list] = {}
    for d, sids, _ in days:
        counts.setdefault(sids, []).append(d)
    modal = max(counts.items(), key=lambda kv: (len(kv[1]), -kv[1][0].toordinal()))
    return min(modal[1]), set(modal[0]), len(modal[1])
