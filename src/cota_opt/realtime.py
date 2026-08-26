"""GTFS-Realtime collection architecture.

Purpose: build empirical segment travel-time distributions from observed vehicle
movement, so the reliability term in the passenger cost stops being a
placeholder and schedule padding can be located.

Design: **one-shot fetch only.** There is no endless collector here — a single
`fetch_and_store` call is the unit of work, and repetition is the scheduler's
job (cron / systemd timer / `python -m cota_opt.rt collect`). Storage is SQLite
with a schema keyed for the segment-runtime query the analysis will need.

The three COTA feeds (vehicle positions, trip updates, alerts) are declared in
``config/sources.yaml``.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS rt_fetch (
    fetch_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    feed          TEXT NOT NULL,
    url           TEXT NOT NULL,
    fetched_at    TEXT NOT NULL,
    feed_timestamp INTEGER,
    n_entities    INTEGER NOT NULL,
    sha256        TEXT NOT NULL,
    bytes         INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS vehicle_position (
    fetch_id   INTEGER NOT NULL REFERENCES rt_fetch(fetch_id),
    vehicle_id TEXT,
    trip_id    TEXT,
    route_id   TEXT,
    direction_id INTEGER,
    stop_id    TEXT,
    current_status TEXT,
    timestamp  INTEGER,
    lat        REAL,
    lon        REAL,
    bearing    REAL,
    speed      REAL
);
CREATE INDEX IF NOT EXISTS ix_vp_trip ON vehicle_position(trip_id, timestamp);
CREATE INDEX IF NOT EXISTS ix_vp_route ON vehicle_position(route_id, timestamp);
CREATE TABLE IF NOT EXISTS trip_update (
    fetch_id   INTEGER NOT NULL REFERENCES rt_fetch(fetch_id),
    trip_id    TEXT,
    route_id   TEXT,
    direction_id INTEGER,
    vehicle_id TEXT,
    stop_id    TEXT,
    stop_sequence INTEGER,
    arrival_time INTEGER,
    arrival_delay INTEGER,
    departure_time INTEGER,
    departure_delay INTEGER,
    schedule_relationship TEXT
);
CREATE INDEX IF NOT EXISTS ix_tu_trip ON trip_update(trip_id, stop_sequence);
CREATE TABLE IF NOT EXISTS alert (
    fetch_id   INTEGER NOT NULL REFERENCES rt_fetch(fetch_id),
    alert_id   TEXT,
    cause      TEXT,
    effect     TEXT,
    header     TEXT,
    description TEXT,
    route_ids  TEXT,
    stop_ids   TEXT,
    active_start INTEGER,
    active_end   INTEGER
);
"""

VEHICLE_STATUS = {0: "INCOMING_AT", 1: "STOPPED_AT", 2: "IN_TRANSIT_TO"}


@dataclass
class FetchResult:
    feed: str
    url: str
    fetched_at: str
    feed_timestamp: int | None
    n_entities: int
    sha256: str
    bytes: int
    rows: list[dict[str, Any]]

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("rows")
        return d


def parse_vehicle_positions(payload: bytes) -> FetchResult:
    return _parse(payload, "vehicle_positions")


def parse_trip_updates(payload: bytes) -> FetchResult:
    return _parse(payload, "trip_updates")


def parse_alerts(payload: bytes) -> FetchResult:
    return _parse(payload, "alerts")


def _parse(payload: bytes, feed: str, url: str = "") -> FetchResult:
    from google.transit import gtfs_realtime_pb2  # imported lazily
    import hashlib

    msg = gtfs_realtime_pb2.FeedMessage()
    msg.ParseFromString(payload)
    rows: list[dict[str, Any]] = []
    for ent in msg.entity:
        if feed == "vehicle_positions" and ent.HasField("vehicle"):
            v = ent.vehicle
            rows.append({
                "vehicle_id": v.vehicle.id or None,
                "trip_id": v.trip.trip_id or None,
                "route_id": v.trip.route_id or None,
                "direction_id": v.trip.direction_id if v.trip.HasField("direction_id") else None,
                "stop_id": v.stop_id or None,
                "current_status": VEHICLE_STATUS.get(v.current_status),
                "timestamp": v.timestamp or None,
                "lat": v.position.latitude if v.HasField("position") else None,
                "lon": v.position.longitude if v.HasField("position") else None,
                "bearing": v.position.bearing if v.HasField("position") else None,
                "speed": v.position.speed if v.HasField("position") else None,
            })
        elif feed == "trip_updates" and ent.HasField("trip_update"):
            tu = ent.trip_update
            for stu in tu.stop_time_update:
                rows.append({
                    "trip_id": tu.trip.trip_id or None,
                    "route_id": tu.trip.route_id or None,
                    "direction_id": tu.trip.direction_id if tu.trip.HasField("direction_id") else None,
                    "vehicle_id": tu.vehicle.id or None,
                    "stop_id": stu.stop_id or None,
                    "stop_sequence": stu.stop_sequence if stu.HasField("stop_sequence") else None,
                    "arrival_time": stu.arrival.time if stu.HasField("arrival") else None,
                    "arrival_delay": stu.arrival.delay if stu.HasField("arrival") else None,
                    "departure_time": stu.departure.time if stu.HasField("departure") else None,
                    "departure_delay": stu.departure.delay if stu.HasField("departure") else None,
                    "schedule_relationship": str(stu.schedule_relationship),
                })
        elif feed == "alerts" and ent.HasField("alert"):
            al = ent.alert
            rows.append({
                "alert_id": ent.id,
                "cause": str(al.cause), "effect": str(al.effect),
                "header": al.header_text.translation[0].text
                if al.header_text.translation else None,
                "description": al.description_text.translation[0].text
                if al.description_text.translation else None,
                "route_ids": ",".join(e.route_id for e in al.informed_entity
                                      if e.route_id),
                "stop_ids": ",".join(e.stop_id for e in al.informed_entity
                                     if e.stop_id),
                "active_start": al.active_period[0].start if al.active_period else None,
                "active_end": al.active_period[0].end if al.active_period else None,
            })
    return FetchResult(
        feed=feed, url=url,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        feed_timestamp=msg.header.timestamp or None,
        n_entities=len(msg.entity),
        sha256=hashlib.sha256(payload).hexdigest(),
        bytes=len(payload), rows=rows)


def fetch_once(feed: str, url: str, timeout: float = 30.0) -> FetchResult:
    """Single HTTP GET + parse. No retry loop, no daemon."""
    resp = requests.get(url, timeout=timeout,
                        headers={"User-Agent": "cota-opt-research/0.1"})
    resp.raise_for_status()
    r = _parse(resp.content, feed, url)
    log.info("%s: %d entities, %d rows, %d bytes", feed, r.n_entities,
             len(r.rows), r.bytes)
    return r


def init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.commit()
    return con


TABLE_FOR_FEED = {"vehicle_positions": "vehicle_position",
                  "trip_updates": "trip_update", "alerts": "alert"}


def store(con: sqlite3.Connection, result: FetchResult) -> int:
    cur = con.execute(
        "INSERT INTO rt_fetch (feed, url, fetched_at, feed_timestamp, "
        "n_entities, sha256, bytes) VALUES (?,?,?,?,?,?,?)",
        (result.feed, result.url, result.fetched_at, result.feed_timestamp,
         result.n_entities, result.sha256, result.bytes))
    fetch_id = int(cur.lastrowid)
    table = TABLE_FOR_FEED[result.feed]
    if result.rows:
        cols = list(result.rows[0])
        sql = (f"INSERT INTO {table} (fetch_id, {', '.join(cols)}) VALUES "
               f"({', '.join(['?'] * (len(cols) + 1))})")
        con.executemany(sql, [[fetch_id] + [r.get(c) for c in cols]
                              for r in result.rows])
    con.commit()
    return fetch_id


def fetch_and_store(feed: str, url: str, db_path: Path) -> int:
    con = init_db(db_path)
    try:
        return store(con, fetch_once(feed, url))
    finally:
        con.close()


def segment_runtimes(con: sqlite3.Connection) -> Iterable[tuple]:
    """Observed dwell-to-dwell segment times from stored vehicle positions.

    The analysis query this schema exists to serve: consecutive STOPPED_AT
    observations for the same trip give an observed segment traversal time.
    """
    return con.execute("""
        WITH s AS (
          SELECT trip_id, route_id, stop_id, MIN(timestamp) AS t
          FROM vehicle_position
          WHERE current_status = 'STOPPED_AT' AND trip_id IS NOT NULL
          GROUP BY trip_id, route_id, stop_id
        )
        SELECT a.route_id, a.stop_id AS from_stop, b.stop_id AS to_stop,
               b.t - a.t AS run_time_sec, a.trip_id
        FROM s a JOIN s b
          ON a.trip_id = b.trip_id AND b.t > a.t
        WHERE NOT EXISTS (
          SELECT 1 FROM s c
          WHERE c.trip_id = a.trip_id AND c.t > a.t AND c.t < b.t)
        ORDER BY a.trip_id, a.t
    """).fetchall()
