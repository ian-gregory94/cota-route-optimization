"""The reproducibility checks have to fail when coverage silently shrinks.

A check that only ever passes is not a check. These exercise the two guards
added after a clean install ran 348 tests while the frozen record claimed 356.
"""
from __future__ import annotations

import scripts.repro_check as rc


def test_skip_counts_are_parsed():
    out = "== 348 passed, 8 skipped in 4.12s =="
    assert rc._pytest_counts(out) == {"passed": 348, "skipped": 8}


def test_clean_run_reports_no_skips():
    assert rc._pytest_counts("== 356 passed in 4.12s ==") == {"passed": 356}


def test_skip_reasons_are_extracted_not_just_counted():
    out = ("SKIPPED [8] tests/test_realtime.py:4: could not import "
           "'google.transit'\n== 348 passed, 8 skipped in 4.12s ==")
    reasons = rc._skip_reasons(out)
    assert len(reasons) == 1
    assert "google.transit" in reasons[0]


def test_the_stopwatch_is_stripped():
    a = rc._pytest_summary("== 356 passed in 4.66s ==")
    b = rc._pytest_summary("== 356 passed in 5.02s ==")
    assert a == b == "356 passed"
