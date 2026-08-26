"""GTFS-Realtime parsing and storage, against synthetic protobuf payloads."""
import pytest

pytest.importorskip("google.transit")
from google.transit import gtfs_realtime_pb2 as pb  # noqa: E402

from cota_opt.realtime import (init_db, parse_alerts, parse_trip_updates,  # noqa: E402
                               parse_vehicle_positions, segment_runtimes, store)


def _vp_payload(rows):
    m = pb.FeedMessage()
    m.header.gtfs_realtime_version = "2.0"
    m.header.timestamp = 1700000000
    for i, (trip, route, stop, ts, status, lat, lon) in enumerate(rows):
        e = m.entity.add()
        e.id = f"v{i}"
        v = e.vehicle
        v.vehicle.id = f"bus{i}"
        v.trip.trip_id = trip
        v.trip.route_id = route
        v.stop_id = stop
        v.timestamp = ts
        v.current_status = status
        v.position.latitude = lat
        v.position.longitude = lon
    return m.SerializeToString()


def test_vehicle_positions_parse_all_fields():
    p = _vp_payload([("T1", "R1", "S1", 1700000100, 1, 39.96, -83.0)])
    r = parse_vehicle_positions(p)
    assert r.n_entities == 1 and len(r.rows) == 1
    row = r.rows[0]
    assert row["trip_id"] == "T1" and row["route_id"] == "R1"
    assert row["stop_id"] == "S1" and row["current_status"] == "STOPPED_AT"
    assert row["lat"] == pytest.approx(39.96)
    assert r.feed_timestamp == 1700000000
    assert len(r.sha256) == 64 and r.bytes == len(p)


def test_empty_feed_parses_to_zero_rows():
    m = pb.FeedMessage()
    m.header.gtfs_realtime_version = "2.0"
    r = parse_vehicle_positions(m.SerializeToString())
    assert r.n_entities == 0 and r.rows == []


def test_trip_updates_expand_one_row_per_stop_time_update():
    m = pb.FeedMessage()
    m.header.gtfs_realtime_version = "2.0"
    e = m.entity.add()
    e.id = "t1"
    tu = e.trip_update
    tu.trip.trip_id = "T1"
    tu.trip.route_id = "R1"
    for seq, (sid, delay) in enumerate([("S1", 60), ("S2", 120)], start=1):
        s = tu.stop_time_update.add()
        s.stop_id = sid
        s.stop_sequence = seq
        s.arrival.delay = delay
        s.arrival.time = 1700000000 + delay
    r = parse_trip_updates(m.SerializeToString())
    assert len(r.rows) == 2
    assert [x["stop_id"] for x in r.rows] == ["S1", "S2"]
    assert [x["arrival_delay"] for x in r.rows] == [60, 120]


def test_alerts_parse_text_and_informed_entities():
    m = pb.FeedMessage()
    m.header.gtfs_realtime_version = "2.0"
    e = m.entity.add()
    e.id = "a1"
    al = e.alert
    al.header_text.translation.add(text="Detour on Main", language="en")
    al.description_text.translation.add(text="Bridge work", language="en")
    al.informed_entity.add(route_id="R1")
    al.informed_entity.add(stop_id="S9")
    r = parse_alerts(m.SerializeToString())
    row = r.rows[0]
    assert row["header"] == "Detour on Main"
    assert row["route_ids"] == "R1" and row["stop_ids"] == "S9"


def test_store_round_trip_and_fetch_metadata(tmp_path):
    con = init_db(tmp_path / "rt.db")
    r = parse_vehicle_positions(
        _vp_payload([("T1", "R1", "S1", 1700000100, 1, 39.96, -83.0),
                     ("T1", "R1", "S2", 1700000400, 1, 39.97, -83.01)]))
    fid = store(con, r)
    assert fid == 1
    n = con.execute("SELECT COUNT(*) FROM vehicle_position").fetchone()[0]
    assert n == 2
    meta = con.execute("SELECT feed, n_entities, bytes FROM rt_fetch").fetchone()
    assert meta[0] == "vehicle_positions" and meta[1] == 2
    con.close()


def test_segment_runtime_query_recovers_the_observed_time(tmp_path):
    """The whole point of the schema: recover segment travel times."""
    con = init_db(tmp_path / "rt.db")
    store(con, parse_vehicle_positions(_vp_payload([
        ("T1", "R1", "S1", 1_700_000_000, 1, 39.96, -83.00),
        ("T1", "R1", "S2", 1_700_000_300, 1, 39.97, -83.01),   # +300 s
        ("T1", "R1", "S3", 1_700_000_720, 1, 39.98, -83.02),   # +420 s
    ])))
    segs = segment_runtimes(con)
    assert [(s[1], s[2], s[3]) for s in segs] == [
        ("S1", "S2", 300), ("S2", "S3", 420)]
    con.close()


def test_segments_do_not_cross_trips(tmp_path):
    con = init_db(tmp_path / "rt.db")
    store(con, parse_vehicle_positions(_vp_payload([
        ("T1", "R1", "S1", 1_700_000_000, 1, 39.96, -83.00),
        ("T2", "R1", "S2", 1_700_000_300, 1, 39.97, -83.01),
    ])))
    assert segment_runtimes(con) == []
    con.close()


def test_in_transit_observations_are_excluded_from_segments(tmp_path):
    con = init_db(tmp_path / "rt.db")
    store(con, parse_vehicle_positions(_vp_payload([
        ("T1", "R1", "S1", 1_700_000_000, 1, 39.96, -83.00),   # STOPPED_AT
        ("T1", "R1", "S2", 1_700_000_100, 2, 39.965, -83.005),  # IN_TRANSIT_TO
        ("T1", "R1", "S2", 1_700_000_300, 1, 39.97, -83.01),   # STOPPED_AT
    ])))
    segs = segment_runtimes(con)
    assert len(segs) == 1 and segs[0][3] == 300
    con.close()
