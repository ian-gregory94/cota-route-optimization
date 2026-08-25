"""GTFS parsing and validation against a tiny synthetic feed."""
import datetime as dt

import pytest

from cota_opt.calendar_utils import (busiest_weekday, feed_date_range,
                                     representative_weekday, service_ids_for_date)
from cota_opt.gtfs import load_feed, parse_gtfs_time, validate_feed
from cota_opt.configs import period_of_seconds

FILES = {
    "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\nT,Test,http://x,America/New_York\n",
    "stops.txt": ("stop_id,stop_name,stop_lat,stop_lon\n"
                  "S1,First,39.96,-83.00\nS2,Second,39.97,-83.01\nS3,Third,39.98,-83.02\n"),
    "routes.txt": "route_id,agency_id,route_short_name,route_long_name,route_type\nR1,T,1,Main,3\n",
    "trips.txt": ("route_id,service_id,trip_id,direction_id,shape_id\n"
                  "R1,WK,T1,0,SH1\nR1,WK,T2,0,SH1\n"),
    "stop_times.txt": ("trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
                       "T1,08:00:00,08:00:00,S1,1\nT1,08:10:00,08:10:00,S2,2\n"
                       "T1,08:20:00,08:20:00,S3,3\n"
                       "T2,08:30:00,08:30:00,S1,1\nT2,08:40:00,08:40:00,S2,2\n"
                       "T2,08:50:00,08:50:00,S3,3\n"),
    "calendar.txt": ("service_id,monday,tuesday,wednesday,thursday,friday,saturday,"
                     "sunday,start_date,end_date\nWK,1,1,1,1,1,0,0,20260601,20260630\n"),
    "calendar_dates.txt": "service_id,date,exception_type\nWK,20260604,2\n",
    "shapes.txt": ("shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
                   "SH1,39.96,-83.00,1\nSH1,39.97,-83.01,2\nSH1,39.98,-83.02,3\n"),
}


@pytest.fixture
def feed_dir(tmp_path):
    for name, text in FILES.items():
        (tmp_path / name).write_text(text)
    return tmp_path


def test_parse_gtfs_time_handles_normal_and_past_midnight():
    assert parse_gtfs_time("00:00:00") == 0
    assert parse_gtfs_time("08:30:15") == 8 * 3600 + 30 * 60 + 15
    assert parse_gtfs_time("25:10:00") == 25 * 3600 + 600


def test_parse_gtfs_time_rejects_malformed():
    import math
    for bad in ("", "8:30", "aa:bb:cc", "08:70:00", None):
        assert math.isnan(parse_gtfs_time(bad))


def test_clean_feed_has_no_errors(feed_dir):
    rep = validate_feed(load_feed(feed_dir))
    assert rep.errors == [], [i.message for i in rep.errors]


def test_missing_required_file_raises(feed_dir):
    (feed_dir / "stop_times.txt").unlink()
    with pytest.raises(FileNotFoundError):
        load_feed(feed_dir)


def test_dangling_stop_reference_is_reported_not_dropped(feed_dir):
    (feed_dir / "stop_times.txt").write_text(
        FILES["stop_times.txt"] + "T2,09:00:00,09:00:00,GHOST,4\n")
    feed = load_feed(feed_dir)
    rep = validate_feed(feed)
    codes = {i.code for i in rep.errors}
    assert "stoptime_stop_ref" in codes
    # the malformed row is still present — nothing was silently discarded
    assert (feed.stop_times["stop_id"] == "GHOST").sum() == 1


def test_duplicate_stop_id_is_an_error(feed_dir):
    (feed_dir / "stops.txt").write_text(FILES["stops.txt"] + "S1,Dup,39.99,-83.03\n")
    rep = validate_feed(load_feed(feed_dir))
    assert "duplicate_ids" in {i.code for i in rep.errors}


def test_invalid_coordinates_are_an_error(feed_dir):
    (feed_dir / "stops.txt").write_text(
        "stop_id,stop_name,stop_lat,stop_lon\nS1,A,0,0\nS2,B,39.97,-83.01\n"
        "S3,C,999,-83.02\n")
    rep = validate_feed(load_feed(feed_dir))
    issue = next(i for i in rep.errors if i.code == "bad_coords")
    assert issue.count == 2


def test_out_of_order_stop_sequence_is_an_error(feed_dir):
    (feed_dir / "stop_times.txt").write_text(
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T1,08:00:00,08:00:00,S1,1\nT1,08:10:00,08:10:00,S2,1\n"
        "T2,08:30:00,08:30:00,S1,1\nT2,08:40:00,08:40:00,S2,2\n")
    rep = validate_feed(load_feed(feed_dir))
    assert "stop_seq_order" in {i.code for i in rep.errors}


def test_backwards_time_is_an_error(feed_dir):
    (feed_dir / "stop_times.txt").write_text(
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T1,08:00:00,08:00:00,S1,1\nT1,07:50:00,07:50:00,S2,2\n"
        "T2,08:30:00,08:30:00,S1,1\nT2,08:40:00,08:40:00,S2,2\n")
    rep = validate_feed(load_feed(feed_dir))
    assert "time_travel" in {i.code for i in rep.errors}


def test_unknown_service_id_is_an_error(feed_dir):
    (feed_dir / "trips.txt").write_text(
        FILES["trips.txt"] + "R1,NOPE,T3,0,SH1\n")
    rep = validate_feed(load_feed(feed_dir))
    assert "trip_service_ref" in {i.code for i in rep.errors}


def test_calendar_dates_exception_removes_service(feed_dir):
    feed = load_feed(feed_dir)
    assert service_ids_for_date(feed, dt.date(2026, 6, 3)) == {"WK"}
    assert service_ids_for_date(feed, dt.date(2026, 6, 4)) == set()   # removed
    assert service_ids_for_date(feed, dt.date(2026, 6, 6)) == set()   # Saturday


def test_feed_date_range_and_weekday_selection(feed_dir):
    feed = load_feed(feed_dir)
    assert feed_date_range(feed) == (dt.date(2026, 6, 1), dt.date(2026, 6, 30))
    d, sids = busiest_weekday(feed)
    assert sids == {"WK"} and d.weekday() in (1, 2, 3)
    rd, rsids, n_days = representative_weekday(feed)
    assert rsids == {"WK"} and n_days >= 8


def test_period_assignment_folds_late_night_correctly():
    periods = {"am_peak": (6, 9), "midday": (9, 15), "owl": (22, 28)}
    assert period_of_seconds(7 * 3600, periods) == "am_peak"
    assert period_of_seconds(23 * 3600, periods) == "owl"
    assert period_of_seconds(25 * 3600, periods) == "owl"   # 01:00 next day
    assert period_of_seconds(2 * 3600, periods) == "owl"    # 02:00 folds to 26h
    assert period_of_seconds(20 * 3600, periods) is None    # uncovered gap
