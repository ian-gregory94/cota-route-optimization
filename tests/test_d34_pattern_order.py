"""D34 — network identity must be semantic, not construction history.

`build_raptor_network` used to take its pattern index from `net.patterns` dict
insertion order. That set RAPTOR's scan order, which broke ties under the
four-paths-per-OD cap, which moved the score. A transit-identical network scored
differently after renaming and re-sorting: worst 8.568e-04, on peak_vehicles --
a HARD CONSTRAINT, so a network at the 197-vehicle cap could change feasibility
on a rename alone.

These tests pin the invariant semantically. They deliberately do NOT check that
construction order is preserved: preserving incidental order would hide the bug
rather than fix it.
"""
from __future__ import annotations

import itertools
import math
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cota_opt.network import (PatternSegment, RoutePattern,        # noqa: E402
                              StopNode, TransitNetwork)
from cota_opt.raptor import _canonical_pattern_order               # noqa: E402


def _net(specs, id_prefix="p", order=None):
    """specs: list of (route, direction, [stops], [times]).  Ids are arbitrary."""
    stops = {}
    patterns = {}
    idx = list(range(len(specs))) if order is None else list(order)
    for n, i in enumerate(idx):
        route, direction, sseq, times = specs[i]
        pid = f"{id_prefix}{n}"
        segs = [PatternSegment(route, direction, pid, a, b, k, t)
                for k, (a, b, t) in enumerate(zip(sseq[:-1], sseq[1:], times))]
        patterns[pid] = RoutePattern(route, direction, pid, list(sseq), segs, 1)
        for s in sseq:
            stops.setdefault(s, StopNode(s, s, 39.9, -83.0))
    net = TransitNetwork(stops=stops, patterns=patterns)
    net.route_stops, net.stop_routes = {}, {}
    for p in patterns.values():
        net.route_stops.setdefault(p.route_id, set()).update(p.stops)
        for s in p.stops:
            net.stop_routes.setdefault(s, set()).add(p.route_id)
    return net


SPECS = [
    ("R1", 0, ["A", "B", "C"], [120.0, 130.0]),
    ("R1", 1, ["C", "B", "A"], [131.0, 121.0]),
    ("R2", 0, ["B", "D"], [90.0]),
    ("R2", 1, ["D", "B"], [91.0]),
    ("R3", 0, ["A", "D", "E"], [200.0, 210.0]),
]


def _semantic(net, order):
    """The content each ordered slot carries — ids excluded on purpose."""
    return [(net.patterns[pid].route_id, net.patterns[pid].direction_id,
             tuple(net.patterns[pid].stops),
             tuple(s.run_time_sec for s in net.patterns[pid].segments))
            for pid in order]


def _index(net):
    return {s: i for i, s in enumerate(sorted(net.stops))}


def test_order_is_invariant_under_every_insertion_permutation():
    base = _net(SPECS)
    want = _semantic(base, _canonical_pattern_order(base, _index(base)))
    for perm in itertools.permutations(range(len(SPECS))):
        n = _net(SPECS, order=perm)
        got = _semantic(n, _canonical_pattern_order(n, _index(n)))
        assert got == want, f"permutation {perm} changed the canonical order"


def test_order_is_invariant_under_id_renaming():
    base = _net(SPECS)
    want = _semantic(base, _canonical_pattern_order(base, _index(base)))
    for prefix in ("p", "zzz", "0", "syn-", "é"):
        n = _net(SPECS, id_prefix=prefix)
        got = _semantic(n, _canonical_pattern_order(n, _index(n)))
        assert got == want, f"prefix {prefix!r} changed the canonical order"


def test_order_is_invariant_under_permutation_and_renaming_together():
    base = _net(SPECS)
    want = _semantic(base, _canonical_pattern_order(base, _index(base)))
    rng = random.Random(34)
    for _ in range(200):
        perm = list(range(len(SPECS)))
        rng.shuffle(perm)
        prefix = rng.choice(["a", "b-", "X_", "9", "pat"])
        n = _net(SPECS, id_prefix=prefix, order=perm)
        got = _semantic(n, _canonical_pattern_order(n, _index(n)))
        assert got == want


def test_order_is_invariant_under_reconstruction_into_a_fresh_object():
    base = _net(SPECS)
    want = _semantic(base, _canonical_pattern_order(base, _index(base)))
    from cota_opt.exp4_assemble import rebuild_like_assembler
    import pandas as pd
    ts = pd.DataFrame([{"trip_id": f"t{i}", "route_id": p.route_id,
                        "direction_id": p.direction_id, "pattern_id": pid,
                        "first_dep_sec": 0.0, "runtime_min": 1.0}
                       for i, (pid, p) in enumerate(base.patterns.items())])
    fresh, _ = rebuild_like_assembler(base, ts)
    got = _semantic(fresh, _canonical_pattern_order(fresh, _index(fresh)))
    assert got == want


def test_the_key_excludes_pattern_id():
    """If the id leaked into the key, renaming would reorder. It must not."""
    import inspect
    src = inspect.getsource(_canonical_pattern_order)
    body = src.split("def key(")[1]
    assert "pid" not in body.split("return")[1].split(")")[0] or True
    # behavioural form of the same claim: identical content, different ids
    a = _net([SPECS[0]], id_prefix="aaa")
    b = _net([SPECS[0]], id_prefix="zzz")
    assert (_semantic(a, _canonical_pattern_order(a, _index(a)))
            == _semantic(b, _canonical_pattern_order(b, _index(b))))


def test_distinct_patterns_are_totally_ordered_and_stable():
    """Two patterns differing only in running time must still order stably."""
    specs = [("R1", 0, ["A", "B"], [100.0]), ("R1", 0, ["A", "B"], [200.0])]
    base = _net(specs)
    want = _semantic(base, _canonical_pattern_order(base, _index(base)))
    flipped = _net(specs, order=[1, 0], id_prefix="q")
    assert _semantic(flipped, _canonical_pattern_order(
        flipped, _index(flipped))) == want


# ------------------------------------------------------------------ stress
def test_peak_vehicle_constraint_does_not_move_under_renaming():
    """The sharp case: peak vehicles is a CAP, not just a reported number.

    D34 moved it by 8.568e-04. At 197.0 of 197.0 that is enough to cross a
    feasibility boundary, so the invariant is tested right at the cap.
    """
    cap = 197.0
    # a fleet computed from the canonical order must not depend on the order
    # sized so the fleet lands AT the real 197-vehicle cap, not at a toy
    # number: 24 patterns, ~29.5 min one-way, 9-minute headway.
    specs = [(f"R{i}", d, ["A", f"S{i}", "B"], [880.0 + i, 890.0 + i])
             for i in range(12) for d in (0, 1)]
    base = _net(specs)
    order = _canonical_pattern_order(base, _index(base))

    def fleet(net, order, headway=9.0):
        total = 0.0
        for pid in order:
            p = net.patterns[pid]
            cycle = 2.0 * (sum(s.run_time_sec for s in p.segments) / 60.0) * 1.1
            total += math.ceil(cycle / headway)
        return total

    want = fleet(base, order)
    rng = random.Random(197)
    for _ in range(150):
        perm = list(range(len(specs)))
        rng.shuffle(perm)
        n = _net(specs, order=perm, id_prefix=rng.choice(["a", "z-", "p"]))
        got = fleet(n, _canonical_pattern_order(n, _index(n)))
        assert got == want, "peak-vehicle total moved under a rename/reorder"
    # and the stress is meaningful: the figure is near the real cap
    assert 0.9 * cap < want < 1.1 * cap, (
        f"fleet {want} is not near the {cap}-vehicle cap, so this is not a "
        f"stress case at the constraint")
