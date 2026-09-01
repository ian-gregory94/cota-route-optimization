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


def test_no_shadowed_module_level_names():
    """A second `def` of a live name silently replaces the first.

    Appending `snap_to_ladder(ladders, plan)` to frequency.py shadowed the
    existing `snap_to_ladder(headway, ladder)` there, and the whole suite still
    passed because nothing covered the original. Python does not warn; the
    later definition simply wins, for every caller, everywhere.
    """
    import ast
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "cota_opt"
    bad = []
    for p in sorted(root.glob("*.py")):
        tree = ast.parse(p.read_text())
        seen: dict[str, int] = {}
        for node in tree.body:                       # module level only
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                if node.name in seen and not any(
                        isinstance(d, ast.Attribute) and
                        d.attr in ("setter", "getter", "deleter")
                        for d in node.decorator_list):
                    bad.append(f"{p.name}:{node.lineno} redefines "
                               f"{node.name!r} (first at line {seen[node.name]})")
                seen[node.name] = node.lineno
    assert not bad, "shadowed definitions:\n  " + "\n  ".join(bad)
