"""Turn an :class:`Exp4Selection` into the ``(TransitNetwork, tstats)`` pair.

That pair is the boundary Experiments 1-3 already meet: `apply_edits` produces
it from geometry edits, and everything after it -- `build_raptor_network`,
`build_zone_system`, `classify_routes`, the path-level setup, the frequency
model, the envelope -- consumes it without caring how it was made. Assembling to
the same boundary is what lets Experiment 4 reuse Gen1's evaluation semantics
instead of re-implementing them.

Determinism
-----------
The same selection must assemble to the same network, byte for byte, or a cache
key means nothing and two runs of one experiment are two experiments. Every
iteration here is over a sorted sequence, pattern ids are derived from content
rather than from a counter, and no dict ordering is relied on.

Synthetic routes have no baseline
---------------------------------
`ACCEPTANCE.md` gate 4-5: "No synthetic route is given a copied baseline
headway: a route that did not exist yesterday has no baseline, and inventing one
invents a service commitment nobody made."

So an assembled route-period's ``baseline_headway_min`` is :data:`frequency.OFF`
-- it runs nothing until the optimizer buys it service. Two consequences fall
out of that rather than being arranged:

* `build_ladders` computes ``worst = max(max_headway, baseline)``, so with an
  OFF baseline every rung on the ladder is offered and OFF is the worst, which
  is exactly the intended range.
* the greedy start begins every route-period at its worst allowed headway, so a
  greenfield solve starts from an empty network and spends the vehicle-hour
  envelope on whichever service buys the most -- which is the right shape for a
  question about what to build, and is not available to an incumbent-start
  solve.

`n_trips` is likewise not invented. A synthetic pattern is given one trip per
direction so the pattern/direction ratio `pattern_headways` uses is exactly 1,
which makes the effective pattern headway equal the route-period headway the
optimizer chose. Anything else would encode a trip distribution nobody observed.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import pandas as pd

from .exp4_network import Exp4Selection, Exp4SelectionError
from .linkgraph import LinkGraph
from .network import PatternSegment, RoutePattern, StopNode, TransitNetwork


@dataclass
class AssemblyReport:
    """What the assembler did, for the receipt. Facts, not reassurance."""

    n_lines: int
    n_patterns: int
    n_stops: int
    n_segments: int
    total_runtime_min: float
    pinned_off: list[tuple[str, str]] = field(default_factory=list)
    unobserved_links: list[tuple[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_lines": self.n_lines, "n_patterns": self.n_patterns,
            "n_stops": self.n_stops, "n_segments": self.n_segments,
            "total_runtime_min": round(self.total_runtime_min, 6),
            "pinned_off": sorted(map(list, self.pinned_off)),
            "n_unobserved_links": len(self.unobserved_links),
        }


@dataclass
class AssembledNetwork:
    network: TransitNetwork
    tstats: pd.DataFrame
    report: AssemblyReport


def _pattern_id(rid: str, direction: int, stops: Sequence[str]) -> str:
    """Content-derived, so the same geometry always gets the same id."""
    h = hashlib.sha256(f"{rid}|{direction}|{'>'.join(stops)}".encode())
    return f"{rid}.d{direction}.{h.hexdigest()[:8]}"


def assemble(selection: Exp4Selection, pool: Mapping[str, Any],
             graph: LinkGraph, stops: Mapping[str, StopNode],
             *, pool_version: str,
             first_dep_sec_by_period: Mapping[str, float],
             ) -> AssembledNetwork:
    """Build the network a selection names. Fails closed; never repairs.

    ``pool`` maps line id -> the pool record (``outbound``/``inbound`` stop
    sequences). ``stops`` supplies coordinates, and is the FIXED stop universe:
    gate 4-3 forbids creating or moving a stop, so a line traversing a stop the
    universe does not contain is an error rather than a new node.
    """
    selection.validate_against_pool(pool.keys(), pool_version)

    patterns: dict[str, RoutePattern] = {}
    rows: list[dict[str, Any]] = []
    used_stops: set[str] = set()
    unobserved: list[tuple[str, str]] = []
    n_segments = 0
    total_runtime = 0.0

    # sorted: determinism is a property of the assembler, not of dict order
    for rid in sorted(selection.lines):
        rec = pool[rid]
        for direction, key in ((0, "outbound"), (1, "inbound")):
            seq = list(rec.get(key) or ())
            if len(seq) < 2:
                raise Exp4SelectionError(
                    f"line {rid!r} direction {direction} has {len(seq)} stop(s); "
                    f"a pattern needs at least two")
            missing = [s for s in seq if s not in stops]
            if missing:
                raise Exp4SelectionError(
                    f"line {rid!r} traverses {len(missing)} stop(s) absent from "
                    f"the fixed stop universe ({missing[:3]}); gate 4-3 forbids "
                    f"creating a stop")
            pid = _pattern_id(rid, direction, seq)
            segs: list[PatternSegment] = []
            for i, (a, b) in enumerate(zip(seq[:-1], seq[1:])):
                t = graph.time(a, b)
                if t is None:
                    unobserved.append((a, b))
                    raise Exp4SelectionError(
                        f"line {rid!r} uses the unobserved link {a}->{b}; the "
                        f"pool is meant to contain only observed movements, so "
                        f"this is a pool defect rather than a scoring decision")
                segs.append(PatternSegment(rid, direction, pid, a, b, i,
                                           float(t)))
            patterns[pid] = RoutePattern(rid, direction, pid, list(seq), segs,
                                         n_trips=1)
            used_stops.update(seq)
            n_segments += len(segs)
            runtime_min = sum(s.run_time_sec for s in segs) / 60.0
            total_runtime += runtime_min
            for period, dep in sorted(first_dep_sec_by_period.items()):
                rows.append({
                    "trip_id": f"{pid}.{period}",
                    "route_id": rid,
                    "direction_id": direction,
                    "pattern_id": pid,
                    "first_dep_sec": float(dep),
                    "runtime_min": float(runtime_min),
                    "period": period,
                })

    net = TransitNetwork(
        stops={s: stops[s] for s in sorted(used_stops)},
        patterns=patterns,
    )
    net.stop_routes = {}
    net.route_stops = {}
    for pid in sorted(patterns):
        p = patterns[pid]
        net.route_stops.setdefault(p.route_id, set()).update(p.stops)
        for s in p.stops:
            net.stop_routes.setdefault(s, set()).add(p.route_id)

    ts = pd.DataFrame(rows).sort_values(
        ["route_id", "direction_id", "period", "trip_id"]).reset_index(drop=True)

    return AssembledNetwork(
        network=net, tstats=ts,
        report=AssemblyReport(
            n_lines=len(selection.lines), n_patterns=len(patterns),
            n_stops=len(used_stops), n_segments=n_segments,
            total_runtime_min=total_runtime,
            pinned_off=sorted(selection.pinned_off),
            unobserved_links=unobserved))


def rebuild_like_assembler(net: TransitNetwork, tstats: pd.DataFrame
                           ) -> tuple[TransitNetwork, pd.DataFrame]:
    """Rebuild an existing network through the assembler's own construction.

    Used only by `scripts/exp4_equivalence.py`, to answer the question the
    contract calls "the one most likely to fail quietly": does a network built
    the Experiment 4 way score the same as one built the Generation 1 way?

    It reuses the legacy geometry and the legacy per-segment times -- the point
    is to test the CONSTRUCTION, not to re-derive the running times -- but goes
    through the assembler's rules: sorted iteration, content-derived pattern
    ids, freshly rebuilt stop_routes/route_stops, and a tstats frame carrying
    only the columns the downstream code actually reads.

    `n_trips` and the tstats rows are preserved from the original rather than
    set to one per pattern, because `pattern_headways` divides direction trips
    by pattern trips and changing that ratio would change the effective headway
    -- which is a real modelling difference, not a construction difference, and
    would make this test measure the wrong thing.
    """
    patterns: dict[str, RoutePattern] = {}
    remap: dict[str, str] = {}
    for old_pid in sorted(net.patterns):
        p = net.patterns[old_pid]
        pid = _pattern_id(p.route_id, p.direction_id, p.stops)
        remap[old_pid] = pid
        segs = [PatternSegment(p.route_id, p.direction_id, pid,
                               s.from_stop, s.to_stop, s.seq, s.run_time_sec)
                for s in p.segments]
        patterns[pid] = RoutePattern(p.route_id, p.direction_id, pid,
                                     list(p.stops), segs, n_trips=p.n_trips)

    used = sorted({s for p in patterns.values() for s in p.stops})
    out = TransitNetwork(stops={s: net.stops[s] for s in used if s in net.stops},
                         patterns=patterns)
    out.stop_routes, out.route_stops = {}, {}
    for pid in sorted(patterns):
        p = patterns[pid]
        out.route_stops.setdefault(p.route_id, set()).update(p.stops)
        for s in p.stops:
            out.stop_routes.setdefault(s, set()).add(p.route_id)

    ts = tstats.copy()
    ts["pattern_id"] = ts["pattern_id"].map(lambda x: remap.get(x, x))
    ts = ts.sort_values(["route_id", "direction_id", "pattern_id", "trip_id"]
                        ).reset_index(drop=True)
    return out, ts
