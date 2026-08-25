"""GTFS parsing and validation.

Parses the core GTFS files into typed pandas DataFrames and runs a structural
validation pass. Malformed records are *reported*, never silently discarded:
every check appends a ``ValidationIssue`` with a count and examples, and the
feed object retains all rows.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

CORE_FILES = ["agency", "stops", "routes", "trips", "stop_times",
              "calendar", "calendar_dates", "shapes"]

REQUIRED_FILES = {"agency", "stops", "routes", "trips", "stop_times"}

REQUIRED_FIELDS: dict[str, list[str]] = {
    "agency": ["agency_name", "agency_url", "agency_timezone"],
    "stops": ["stop_id"],
    "routes": ["route_id", "route_type"],
    "trips": ["route_id", "service_id", "trip_id"],
    "stop_times": ["trip_id", "stop_id", "stop_sequence"],
    "calendar": ["service_id", "monday", "tuesday", "wednesday", "thursday",
                 "friday", "saturday", "sunday", "start_date", "end_date"],
    "calendar_dates": ["service_id", "date", "exception_type"],
    "shapes": ["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"],
}

DTYPES = {
    "stop_id": str, "route_id": str, "trip_id": str, "service_id": str,
    "shape_id": str, "agency_id": str, "parent_station": str,
}


def parse_gtfs_time(value: str | float) -> float:
    """GTFS HH:MM:SS (hours may exceed 24) → seconds since service midnight.

    Returns NaN for missing/malformed values.
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    s = str(value).strip()
    if not s:
        return np.nan
    parts = s.split(":")
    if len(parts) != 3:
        return np.nan
    try:
        h, m, sec = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return np.nan
    if m > 59 or sec > 59 or h < 0 or m < 0 or sec < 0:
        return np.nan
    return h * 3600 + m * 60 + sec


@dataclass
class ValidationIssue:
    severity: str          # ERROR | WARNING | INFO
    code: str
    message: str
    count: int = 1
    examples: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    def add(self, severity: str, code: str, message: str,
            count: int = 1, examples: list | None = None) -> None:
        self.issues.append(ValidationIssue(
            severity, code, message, count,
            [str(e) for e in (examples or [])[:5]]))

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "ERROR"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "WARNING"]

    def to_dict(self) -> dict:
        return {"n_errors": len(self.errors), "n_warnings": len(self.warnings),
                "issues": [vars(i) for i in self.issues]}


@dataclass
class GTFSFeed:
    """Parsed GTFS tables. Missing optional tables are empty DataFrames."""

    tables: dict[str, pd.DataFrame]
    source_dir: Path

    def __getattr__(self, name: str) -> pd.DataFrame:
        if name in CORE_FILES:
            return self.tables.get(name, pd.DataFrame())
        raise AttributeError(name)


def load_feed(gtfs_dir: Path) -> GTFSFeed:
    """Load GTFS CSVs. Raises FileNotFoundError if a required file is absent."""
    gtfs_dir = Path(gtfs_dir)
    tables: dict[str, pd.DataFrame] = {}
    for name in CORE_FILES:
        p = gtfs_dir / f"{name}.txt"
        if not p.exists():
            if name in REQUIRED_FILES:
                raise FileNotFoundError(f"required GTFS file missing: {p}")
            tables[name] = pd.DataFrame()
            continue
        df = pd.read_csv(p, dtype=DTYPES, low_memory=False,
                         skipinitialspace=True)
        df.columns = [c.strip().lstrip("﻿") for c in df.columns]
        tables[name] = df
        log.info("loaded %s: %d rows", name, len(df))
    st = tables["stop_times"]
    if "arrival_time" in st.columns:
        st["arrival_sec"] = st["arrival_time"].map(parse_gtfs_time)
    if "departure_time" in st.columns:
        st["departure_sec"] = st["departure_time"].map(parse_gtfs_time)
    return GTFSFeed(tables=tables, source_dir=gtfs_dir)


def validate_feed(feed: GTFSFeed) -> ValidationReport:
    """Structural validation. Returns a report; never mutates the feed."""
    rep = ValidationReport()
    t = feed.tables

    # required fields present
    for name, fields_ in REQUIRED_FIELDS.items():
        df = t.get(name)
        if df is None or df.empty:
            if name in REQUIRED_FILES:
                rep.add("ERROR", "missing_table", f"{name}.txt missing or empty")
            else:
                rep.add("INFO", "optional_missing", f"{name}.txt not provided")
            continue
        missing = [f for f in fields_ if f not in df.columns]
        if missing:
            rep.add("ERROR", "missing_fields", f"{name}: missing {missing}")

    # unique IDs
    for name, col in [("stops", "stop_id"), ("routes", "route_id"),
                      ("trips", "trip_id")]:
        df = t.get(name, pd.DataFrame())
        if col in df.columns:
            dup = df[df[col].duplicated()]
            if len(dup):
                rep.add("ERROR", "duplicate_ids",
                        f"{name}: {len(dup)} duplicate {col}",
                        len(dup), dup[col].tolist())

    stops, routes, trips, st = (t.get(k, pd.DataFrame()) for k in
                                ("stops", "routes", "trips", "stop_times"))

    # referential integrity
    if not trips.empty and not routes.empty:
        bad = trips.loc[~trips["route_id"].isin(routes["route_id"]), "trip_id"]
        if len(bad):
            rep.add("ERROR", "trip_route_ref",
                    f"{len(bad)} trips reference unknown route_id",
                    len(bad), bad.tolist())
    if not st.empty and not trips.empty:
        bad_ids = set(st["trip_id"]) - set(trips["trip_id"])
        if bad_ids:
            rep.add("ERROR", "stoptime_trip_ref",
                    f"{len(bad_ids)} trip_ids in stop_times not in trips",
                    len(bad_ids), sorted(bad_ids))
    if not st.empty and not stops.empty:
        bad_ids = set(st["stop_id"]) - set(stops["stop_id"])
        if bad_ids:
            rep.add("ERROR", "stoptime_stop_ref",
                    f"{len(bad_ids)} stop_ids in stop_times not in stops",
                    len(bad_ids), sorted(bad_ids))

    # coordinates
    if {"stop_lat", "stop_lon"} <= set(stops.columns):
        lat = pd.to_numeric(stops["stop_lat"], errors="coerce")
        lon = pd.to_numeric(stops["stop_lon"], errors="coerce")
        bad = stops[lat.isna() | lon.isna() | (lat.abs() > 90) |
                    (lon.abs() > 180) | ((lat == 0) & (lon == 0))]
        if len(bad):
            rep.add("ERROR", "bad_coords",
                    f"{len(bad)} stops with invalid coordinates",
                    len(bad), bad["stop_id"].tolist())

    # stop sequence ordering and times
    if {"trip_id", "stop_sequence"} <= set(st.columns) and len(st):
        seq = st.sort_values(["trip_id", "stop_sequence"])
        grp = seq.groupby("trip_id")["stop_sequence"]
        nonmono = (grp.diff().dropna() <= 0)
        if nonmono.any():
            bad_trips = seq.loc[nonmono[nonmono].index, "trip_id"].unique()
            rep.add("ERROR", "stop_seq_order",
                    f"{len(bad_trips)} trips with non-increasing stop_sequence",
                    len(bad_trips), list(bad_trips))
        if "departure_sec" in seq.columns:
            n_missing = int(seq["departure_sec"].isna().sum())
            timed = seq.dropna(subset=["departure_sec"])
            neg = (timed.groupby("trip_id")["departure_sec"].diff().dropna() < 0)
            if neg.any():
                bad_trips = timed.loc[neg[neg].index, "trip_id"].unique()
                rep.add("ERROR", "time_travel",
                        f"{len(bad_trips)} trips with decreasing departure times",
                        len(bad_trips), list(bad_trips))
            if n_missing:
                rep.add("INFO", "untimed_stops",
                        f"{n_missing} stop_times rows without departure_time "
                        "(timepoint interpolation feed)", n_missing)

    # service calendars
    cal, cal_d = t.get("calendar", pd.DataFrame()), t.get("calendar_dates", pd.DataFrame())
    if cal.empty and cal_d.empty:
        rep.add("ERROR", "no_calendar",
                "neither calendar.txt nor calendar_dates.txt present")
    if not trips.empty:
        svc = set()
        if "service_id" in cal.columns:
            svc |= set(cal["service_id"])
        if "service_id" in cal_d.columns:
            svc |= set(cal_d["service_id"])
        if svc:
            bad_ids = set(trips["service_id"]) - svc
            if bad_ids:
                rep.add("ERROR", "trip_service_ref",
                        f"{len(bad_ids)} service_ids in trips not in calendars",
                        len(bad_ids), sorted(bad_ids))

    # shapes
    shapes = t.get("shapes", pd.DataFrame())
    if not trips.empty and "shape_id" in trips.columns and not shapes.empty:
        used = set(trips["shape_id"].dropna())
        have = set(shapes["shape_id"])
        missing_sh = used - have
        if missing_sh:
            rep.add("WARNING", "shape_ref",
                    f"{len(missing_sh)} shape_ids referenced but not defined",
                    len(missing_sh), sorted(missing_sh))
    return rep
