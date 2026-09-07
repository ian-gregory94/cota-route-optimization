"""Candidate blocking: what fleet does a schedule with no block_id require?

TWO INSTRUMENTS, AND THEY ANSWER DIFFERENT QUESTIONS
-----------------------------------------------------
``blocks.reconstruct``    "How many vehicles does COTA's PUBLISHED blocking
                          use?" It reads `block_id` off 5,435 real trips and
                          produces the canonical envelope: early 135, am_peak
                          187, midday 173, pm_peak 197, evening 178, owl 149,
                          system peak 197 at 17:13. Its semantics are frozen
                          and this module does not touch them.

``block_candidate_schedule`` (here)
                          "Given these concrete trips and the frozen
                          connection assumptions, what fleet is REQUIRED if the
                          trips are feasibly reblocked?" It has no `block_id`
                          to read, so it solves for one.

The second is **not** a reconstruction and is never called one. It is a
minimum-fleet requirement under a stated connection model, and it may land
above or below the published figure without either being wrong: COTA's blocking
is one feasible solution shaped by crew rules, depots and history, not the
minimum.

WHAT THIS MODULE REFUSES TO DO
------------------------------
It does not return `FitnessVector.peak_vehicles` (peak concurrency, 176.49 on
the baseline). It does not apply the 1.307 interlining factor, or any other
multiplier, to convert one quantity into another. It contains no speed, no
distance, and no fallback deadhead assumption: every cross-terminal connection
is decided by a `DeadheadOracle`, and an oracle with no value for a connection
makes that connection **infeasible**, never free.

That last rule is the one that matters. A missing deadhead silently treated as
zero would let a bus teleport, which is exactly the class of error -- a
constraint that appears to be checked and is not -- that produced the
concurrency confusion in the first place.

DEADHEAD PROVENANCE IS NOT SOMETHING THIS FILE MAY INVENT
----------------------------------------------------------
Estimating deadhead from the observed slack between consecutive trips in
published blocks is specifically forbidden, and the reason is worth stating:
that gap proves a connection *happened*, and bounds deadhead from above by
however much slack the scheduler left. It is not a measurement of travel time,
and calling it one would manufacture evidence out of a scheduling artifact.

`SameTerminalOracle` is therefore the only oracle shipped here. It permits a
vehicle to continue from a terminal it is already standing at, subject to a
frozen minimum layover, and declares every cross-terminal connection UNKNOWN.
A fleet computed under it is a strict **upper bound**: no interlining is
allowed, so any real deadhead model can only reduce it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from .blocks import block_concurrency
from .firewall.core import digest


class BlockingError(ValueError):
    """A blocking that cannot mean what it says."""


class DeadheadUnknown(LookupError):
    """The oracle has no value for this connection. It is NOT zero."""


# ---------------------------------------------------------------------------
# 1. timetable materialisation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MaterializedTrip:
    trip_id: str
    route_id: str
    pattern_id: str
    direction_id: int
    origin_terminal: str
    destination_terminal: str
    departure_sec: float
    arrival_sec: float
    runtime_min: float
    period: str

    def payload(self) -> dict:
        return {"trip_id": self.trip_id, "route_id": self.route_id,
                "pattern_id": self.pattern_id,
                "direction_id": self.direction_id,
                "origin_terminal": self.origin_terminal,
                "destination_terminal": self.destination_terminal,
                "departure_sec": self.departure_sec,
                "arrival_sec": self.arrival_sec,
                "runtime_min": self.runtime_min, "period": self.period}


@dataclass(frozen=True)
class TripTable:
    trips: tuple[MaterializedTrip, ...]
    source: str
    digest: str

    def __len__(self) -> int:
        return len(self.trips)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame([t.payload() for t in self.trips])


def materialize_timetable(network, frequency_plan: Mapping[tuple[str, str], float],
                          periods: Mapping[str, tuple[float, float]],
                          first_dep_sec_by_period: Mapping[str, float],
                          *, source: str = "candidate") -> TripTable:
    """Concrete trips from a frequency plan. Deterministic, order-independent.

    Uses the SAME frequency interpretation `exp4_assemble` already applies --
    a period's trips begin at that period's `first_dep_sec` and repeat every
    `headway` minutes while they still start inside the window -- rather than
    inventing a second reading of what a headway means.

    An OFF route-period (infinite headway) contributes no trips at all, which
    is the point of OFF: it consumes no service resource and carries nobody.
    """
    out: list[MaterializedTrip] = []
    # sorted iteration everywhere: the result may not depend on dict order
    for (route_id, period) in sorted(frequency_plan):
        headway = float(frequency_plan[(route_id, period)])
        if not math.isfinite(headway) or headway >= 1e5 or headway <= 0:
            continue                              # OFF, or not a service
        if period not in periods:
            raise BlockingError(
                f"route-period ({route_id}, {period}) names a period that is "
                f"not in the frozen period set {sorted(periods)}")
        h0, h1 = periods[period]
        win_start = float(first_dep_sec_by_period[period])
        win_end = h1 * 3600.0
        if win_end <= h0 * 3600.0:               # owl wraps past midnight
            win_end += 24 * 3600.0
        pats = _patterns_for(network, route_id)
        if not pats:
            raise BlockingError(
                f"route {route_id!r} has no pattern in the candidate network, "
                f"so its trips cannot be materialised")
        for pattern_id, direction_id, o_term, d_term, runtime_min in pats:
            t = win_start
            n = 0
            while t < win_end:
                arr = t + runtime_min * 60.0
                out.append(MaterializedTrip(
                    trip_id=f"{route_id}|{period}|{pattern_id}|{n:04d}",
                    route_id=str(route_id), pattern_id=str(pattern_id),
                    direction_id=int(direction_id),
                    origin_terminal=str(o_term),
                    destination_terminal=str(d_term),
                    departure_sec=float(t), arrival_sec=float(arr),
                    runtime_min=float(runtime_min), period=str(period)))
                n += 1
                t += headway * 60.0
    trips = tuple(sorted(out, key=lambda x: (x.departure_sec, x.trip_id)))
    return TripTable(trips=trips, source=source,
                     digest=digest([t.payload() for t in trips]))


def _patterns_for(network, route_id: str):
    """(pattern_id, direction, origin terminal, destination terminal, runtime)."""
    got = []
    for pid, pat in sorted(getattr(network, "patterns", {}).items()):
        if str(getattr(pat, "route_id", "")) != str(route_id):
            continue
        stops = list(getattr(pat, "stops", []))
        if len(stops) < 2:
            continue
        rt = sum(float(getattr(sg, "run_time_sec", 0.0))
                 for sg in getattr(pat, "segments", [])) / 60.0
        got.append((str(pid), int(getattr(pat, "direction_id", 0)),
                    str(stops[0]), str(stops[-1]), rt))
    return got


# ---------------------------------------------------------------------------
# 2. the deadhead interface. No model lives in this module.
# ---------------------------------------------------------------------------

class DeadheadOracle:
    """Deadhead travel time between terminals. An interface, not a model.

    Implementations must raise `DeadheadUnknown` when they have no value.
    Returning 0.0 for an unknown connection is the failure this interface
    exists to prevent.
    """

    name: str = "abstract"
    version: str = "0"

    def time_sec(self, from_terminal: str, to_terminal: str,
                 departure_sec: float) -> float:
        raise NotImplementedError

    def reachable_origins(self, from_terminal: str) -> set[str] | None:
        """Origins to which a finite deadhead MIGHT exist, or None.

        A performance hint only, and it must be a **superset** of the origins
        `time_sec` will answer for -- returning too few would silently delete
        feasible connections, which is the same class of error as a missing
        deadhead treated as zero. None means "no hint; test everything".
        """
        return None

    @property
    def provenance(self) -> dict:
        return {"deadhead_source": self.name, "version": self.version,
                "time_dependent": False}

    @property
    def digest(self) -> str:
        return digest(self.provenance)


@dataclass
class SameTerminalOracle(DeadheadOracle):
    """Permits continuation only where the vehicle already stands.

    Every cross-terminal connection is UNKNOWN, because this project has no
    defensible source for deadhead travel time:

      * `walk_speed_m_per_min` is a pedestrian speed;
      * the NTD 12.20 mph figure is IN-SERVICE speed, with stops and dwell,
        and deadhead runs are neither;
      * `linkgraph.ObservedLink` covers stop-to-stop movements that are
        actually operated in revenue service, and a deadhead between two
        routes' terminals is generally not one of them;
      * the slack between consecutive trips in published blocks proves a
        connection happened and bounds deadhead from above by whatever the
        scheduler left. It is not a travel time.

    So a fleet computed under this oracle is a strict UPPER BOUND: no
    interlining is permitted at all, and any real deadhead model can only
    lower it.
    """

    min_layover_sec: float = 300.0
    name: str = "same_terminal_only"
    version: str = "1"

    def reachable_origins(self, from_terminal: str) -> set[str] | None:
        return {from_terminal}

    def time_sec(self, from_terminal: str, to_terminal: str,
                 departure_sec: float) -> float:
        if from_terminal == to_terminal:
            return 0.0
        raise DeadheadUnknown(
            f"no deadhead time is known from {from_terminal!r} to "
            f"{to_terminal!r}. This oracle has no cross-terminal data and will "
            f"not invent any; the connection is infeasible, not free.")

    @property
    def provenance(self) -> dict:
        return {"deadhead_source": self.name, "version": self.version,
                "time_dependent": False,
                "min_layover_sec": self.min_layover_sec,
                "cross_terminal": "UNKNOWN -- every such connection infeasible",
                "consequence": ("fleet computed under this oracle is an UPPER "
                                "BOUND; no interlining is permitted")}


@dataclass
class TableDeadheadOracle(DeadheadOracle):
    """A real oracle backed by an explicit table. Nothing is inferred.

    Provided so that a defensible deadhead source can be dropped in without
    touching the solver. A pair absent from the table is UNKNOWN.
    """

    table: Mapping[tuple[str, str], float]
    min_layover_sec: float = 300.0
    name: str = "table"
    version: str = "0"
    source_note: str = ""

    def reachable_origins(self, from_terminal: str) -> set[str] | None:
        return {from_terminal} | {b for (a, b) in self.table
                                  if a == from_terminal}

    def time_sec(self, from_terminal: str, to_terminal: str,
                 departure_sec: float) -> float:
        if from_terminal == to_terminal:
            return 0.0
        try:
            return float(self.table[(from_terminal, to_terminal)])
        except KeyError:
            raise DeadheadUnknown(
                f"no deadhead entry for ({from_terminal!r}, {to_terminal!r})")

    @property
    def provenance(self) -> dict:
        return {"deadhead_source": self.name, "version": self.version,
                "time_dependent": False, "n_pairs": len(self.table),
                "min_layover_sec": self.min_layover_sec,
                "source_note": self.source_note}


@dataclass
class ZeroDeadheadRelaxation(DeadheadOracle):
    """A RELAXATION, not a deadhead model. It exists to produce a LOWER bound.

    Every pair of terminals is connected in zero seconds. That is physically
    false -- it lets a bus cross Columbus instantly -- and it is declared false
    here rather than hidden. Its only legitimate use is as a bound:

        no real deadhead time is negative, so any true oracle can only make
        connections HARDER, never easier. The minimum fleet under this
        relaxation is therefore a valid LOWER bound on the minimum fleet under
        any real deadhead model.

    Together with `SameTerminalOracle` -- which forbids every cross-terminal
    connection and so gives an UPPER bound -- it brackets the true requirement
    without anybody inventing a travel time in between. That is the whole
    point: a bracket is honest about the missing input, an interpolation
    inside it would not be.

    It must never certify a plan, and `is_bound_only` says so in the payload.
    """

    min_layover_sec: float = 300.0
    name: str = "zero_deadhead_relaxation"
    version: str = "1"
    is_bound_only: bool = True

    def reachable_origins(self, from_terminal: str) -> set[str] | None:
        return None                      # everything; no hint, test all pairs

    def time_sec(self, from_terminal: str, to_terminal: str,
                 departure_sec: float) -> float:
        return 0.0

    @property
    def provenance(self) -> dict:
        return {"deadhead_source": self.name, "version": self.version,
                "time_dependent": False,
                "min_layover_sec": self.min_layover_sec,
                "cross_terminal": "ZERO -- deliberately and knowingly false",
                "is_bound_only": True,
                "consequence": ("fleet computed under this relaxation is a "
                                "LOWER BOUND and may never certify a plan"),
                "NOT": ("not a deadhead estimate, not a model, and not "
                        "evidence about Columbus geography")}


def period_lower_bounds(table: "TripTable",
                        periods: Mapping[str, tuple[float, float]],
                        min_layover_sec: float = 300.0
                        ) -> tuple[dict[str, int], int, int]:
    """Per-period fleet LOWER bounds that no choice of blocking can escape.

    A vehicle running trip i is unavailable for anything else over
    ``[departure, arrival + min_layover)`` however the trips are chained,
    because deadhead is non-negative. The peak of that occupancy inside a
    period is therefore a lower bound on the vehicles that period needs.

    This exists because the per-period concurrency of a *particular* minimum
    path cover does not: many maximum matchings of equal size chain the same
    trips differently and give different per-period numbers. This quantity is
    matching-independent, so it is the one that may be compared to an
    envelope.

    Returns (by_period, system_peak, system_peak_minute).
    """
    if len(table) == 0:
        return {p: 0 for p in periods}, 0, 0
    dep = np.asarray([t.departure_sec for t in table.trips], dtype=float)
    arr = np.asarray([t.arrival_sec for t in table.trips],
                     dtype=float) + float(min_layover_sec)
    _c, _m, peak, peak_min, by_period = block_concurrency(dep, arr, periods)
    return ({k: int(v) for k, v in by_period.items()},
            int(peak), int(peak_min))


# ---------------------------------------------------------------------------
# 3. connection rule
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConnectionRule:
    """When may one vehicle serve trip j after trip i? Frozen and declared."""

    min_layover_sec: float = 300.0
    name: str = "arrival_plus_deadhead_plus_layover"
    version: str = "1"

    def feasible(self, i: MaterializedTrip, j: MaterializedTrip,
                 oracle: DeadheadOracle) -> tuple[bool, str, float]:
        """(feasible, why_not, deadhead_sec). Never guesses a missing time."""
        if j.departure_sec < i.arrival_sec:
            return False, "time runs backward", 0.0
        try:
            dh = oracle.time_sec(i.destination_terminal, j.origin_terminal,
                                 i.arrival_sec)
        except DeadheadUnknown as e:
            return False, f"deadhead unknown: {e}", float("nan")
        need = i.arrival_sec + dh + self.min_layover_sec
        if j.departure_sec + 1e-9 < need:
            return (False,
                    f"needs {need - i.arrival_sec:.0f}s (deadhead {dh:.0f} + "
                    f"layover {self.min_layover_sec:.0f}) but only "
                    f"{j.departure_sec - i.arrival_sec:.0f}s available", dh)
        return True, "", dh

    @property
    def payload(self) -> dict:
        return {"connection_rule": self.name, "version": self.version,
                "min_layover_sec": self.min_layover_sec,
                "definition": ("j is reachable from i iff "
                               "j.departure >= i.arrival + deadhead(i.dest, "
                               "j.origin) + min_layover, and the deadhead is "
                               "KNOWN")}


# ---------------------------------------------------------------------------
# 4-5. the solver: DAG minimum path cover, and the chains it implies
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CandidateBlock:
    block_index: int
    trip_ids: tuple[str, ...]
    start_sec: float
    end_sec: float
    connections: tuple[dict, ...]

    def payload(self) -> dict:
        return {"block_index": self.block_index,
                "trip_ids": list(self.trip_ids),
                "start_sec": self.start_sec, "end_sec": self.end_sec,
                "n_trips": len(self.trip_ids),
                "connections": [dict(c) for c in self.connections]}


@dataclass(frozen=True)
class CandidateBlockResult:
    """Deliberately NOT named a reconstruction. This is a requirement."""

    minimum_blocks: int
    blocks: tuple[CandidateBlock, ...]
    fleet_by_period: Mapping[str, int]
    system_peak: int
    system_peak_minute: int
    n_trips: int
    n_feasible_edges: int
    source: str = "candidate_block_solver"
    deadhead_provenance: Mapping[str, Any] = field(default_factory=dict)
    connection_rule: Mapping[str, Any] = field(default_factory=dict)
    is_upper_bound: bool = False
    is_lower_bound: bool = False
    terminal_identity: Mapping[str, Any] = field(default_factory=dict)
    fleet_by_period_stable: bool | None = None
    fleet_by_period_alternate: Mapping[str, int] | None = None
    notes: str = ""

    def payload(self) -> dict:
        return {"source": self.source,
                "minimum_blocks": self.minimum_blocks,
                "fleet_by_period": dict(sorted(self.fleet_by_period.items())),
                "system_peak": self.system_peak,
                "system_peak_time":
                    f"{self.system_peak_minute // 60:02d}:"
                    f"{self.system_peak_minute % 60:02d}",
                "n_trips": self.n_trips,
                "n_feasible_edges": self.n_feasible_edges,
                "n_blocks": len(self.blocks),
                "deadhead_provenance": dict(self.deadhead_provenance),
                "connection_rule": dict(self.connection_rule),
                "is_upper_bound": self.is_upper_bound,
                "is_lower_bound": self.is_lower_bound,
                "terminal_identity": dict(self.terminal_identity),
                "fleet_by_period_is_matching_dependent": True,
                "fleet_by_period_stable": self.fleet_by_period_stable,
                "fleet_by_period_alternate":
                    (dict(sorted(self.fleet_by_period_alternate.items()))
                     if self.fleet_by_period_alternate is not None else None),
                "CERTIFICATION": (
                    "`minimum_blocks` is the matching number and is a graph "
                    "invariant. `fleet_by_period` is the concurrency of ONE "
                    "maximum matching among many of equal size and is NOT "
                    "invariant; it is a diagnostic and may not decide "
                    "feasibility. Use `period_lower_bounds` for a "
                    "matching-independent per-period quantity."),
                "NOT": ("this is a minimum-fleet REQUIREMENT under a stated "
                        "connection model, not a reconstruction of any "
                        "published block assignment"),
                "notes": self.notes,
                "model_digest": digest({
                    "deadhead": dict(self.deadhead_provenance),
                    "connection": dict(self.connection_rule)})}


def _hopcroft_karp(n_left: int, adj: list[list[int]]) -> list[int]:
    """Maximum bipartite matching. Deterministic given sorted adjacency."""
    INF = float("inf")
    match_l = [-1] * n_left
    match_r = [-1] * n_left
    while True:
        dist = [INF] * n_left
        queue = [u for u in range(n_left) if match_l[u] == -1]
        for u in queue:
            dist[u] = 0
        qi = 0
        found = False
        while qi < len(queue):
            u = queue[qi]
            qi += 1
            for v in adj[u]:
                w = match_r[v]
                if w == -1:
                    found = True
                elif dist[w] == INF:
                    dist[w] = dist[u] + 1
                    queue.append(w)
        if not found:
            return match_l

        def try_kuhn(u: int) -> bool:
            for v in adj[u]:
                w = match_r[v]
                if w == -1 or (dist[w] == dist[u] + 1 and try_kuhn(w)):
                    match_l[u] = v
                    match_r[v] = u
                    return True
            dist[u] = INF
            return False

        progressed = False
        for u in range(n_left):
            if match_l[u] == -1 and try_kuhn(u):
                progressed = True
        if not progressed:
            return match_l


def block_candidate_schedule(table: TripTable, oracle: DeadheadOracle,
                             periods: Mapping[str, tuple[float, float]],
                             rule: ConnectionRule | None = None,
                             *, max_edges: int | None = None,
                             stability_probe: bool = True
                             ) -> CandidateBlockResult:
    """Minimum fleet for a schedule with no block_id, and the chains behind it.

    Minimum path cover on the DAG of feasible connections:

        minimum_blocks = n_trips - maximum_matching

    Matching, not min-cost flow: counting buses does not need costs, and a flow
    formulation would invite a secondary objective nobody has preregistered.

    Determinism: trips are processed in `(departure_sec, trip_id)` order and
    every adjacency list is built in that same order, so the matching -- and
    therefore the chains -- are reproducible.
    """
    rule = rule or ConnectionRule(
        min_layover_sec=getattr(oracle, "min_layover_sec", 300.0))
    trips = list(table.trips)
    n = len(trips)
    if n == 0:
        return CandidateBlockResult(
            0, (), {p: 0 for p in periods}, 0, 0, 0, 0,
            deadhead_provenance=oracle.provenance,
            connection_rule=rule.payload, notes="no trips")

    order = sorted(range(n), key=lambda i: (trips[i].departure_sec,
                                            trips[i].trip_id))
    pos = {i: k for k, i in enumerate(order)}
    adj: list[list[int]] = [[] for _ in range(n)]
    n_edges = 0
    for a in range(n):
        i = order[a]
        row: list[int] = []
        hint = oracle.reachable_origins(trips[i].destination_terminal)
        for b in range(a + 1, n):
            j = order[b]
            if hint is not None and trips[j].origin_terminal not in hint:
                continue          # the oracle has already said it cannot help
            ok, _why, _dh = rule.feasible(trips[i], trips[j], oracle)
            if ok:
                row.append(j)
                n_edges += 1
                if max_edges and n_edges > max_edges:
                    raise BlockingError(
                        f"connection graph exceeded {max_edges} edges; refuse "
                        f"rather than silently truncate the feasible set")
        adj[i] = row

    match_l = _hopcroft_karp(n, adj)
    succ = {i: match_l[i] for i in range(n) if match_l[i] != -1}
    pred = {v: u for u, v in succ.items()}
    minimum_blocks = n - len(succ)

    # --- materialise the chains -------------------------------------------
    heads = [i for i in order if i not in pred]
    blocks: list[CandidateBlock] = []
    seen: set[int] = set()
    for bi, h in enumerate(heads):
        chain = [h]
        seen.add(h)
        cur = h
        while cur in succ:
            nxt = succ[cur]
            if nxt in seen:
                raise BlockingError("cycle in a DAG matching; solver is wrong")
            chain.append(nxt)
            seen.add(nxt)
            cur = nxt
        conns = []
        for u, v in zip(chain, chain[1:]):
            ok, why, dh = rule.feasible(trips[u], trips[v], oracle)
            if not ok:
                raise BlockingError(
                    f"chain uses an infeasible connection {trips[u].trip_id} "
                    f"-> {trips[v].trip_id}: {why}")
            conns.append({"from": trips[u].trip_id, "to": trips[v].trip_id,
                          "deadhead_sec": dh,
                          "layover_sec": trips[v].departure_sec
                                         - trips[u].arrival_sec - dh})
        blocks.append(CandidateBlock(
            block_index=bi,
            trip_ids=tuple(trips[k].trip_id for k in chain),
            start_sec=trips[chain[0]].departure_sec,
            end_sec=trips[chain[-1]].arrival_sec,
            connections=tuple(conns)))

    # --- §5 rejection conditions, checked rather than assumed --------------
    covered = [t for b in blocks for t in b.trip_ids]
    if len(covered) != n:
        raise BlockingError(f"{n} trips but {len(covered)} appear in blocks")
    if len(set(covered)) != n:
        raise BlockingError("a trip appears in more than one block")
    if len(blocks) != minimum_blocks:
        raise BlockingError(
            f"{len(blocks)} chains against a path cover of {minimum_blocks}")
    for b in blocks:
        if b.end_sec < b.start_sec:
            raise BlockingError(f"block {b.block_index} ends before it starts")
        for c in b.connections:
            if not math.isfinite(c["deadhead_sec"]):
                raise BlockingError("a chain claims a deadhead the oracle "
                                    "never supplied")

    _c, _m, peak, peak_min, by_period = block_concurrency(
        [b.start_sec for b in blocks], [b.end_sec for b in blocks], periods)

    # --- is the per-period figure a property of the SCHEDULE, or only of the
    #     particular maximum matching this run happened to find? -----------
    #
    # `minimum_blocks` is the matching number: a graph invariant, the same for
    # every maximum matching. The chain SPANS are not. Two maximum matchings
    # of identical size can chain the same trips differently, and a longer
    # chain holds a vehicle nominally in service across an idle midday it
    # never actually worked. Reporting one draw as though it were the answer
    # would be the same species of error as the concurrency proxy this module
    # exists to replace, so measure the instability instead of hiding it.
    stable: bool | None = None
    by_period_alt: dict[str, int] | None = None
    if stability_probe:
        alt_l = _hopcroft_karp(n, [list(reversed(r)) for r in adj])
        a_succ = {i: alt_l[i] for i in range(n) if alt_l[i] != -1}
        a_pred = {v: u for u, v in a_succ.items()}
        if n - len(a_succ) != minimum_blocks:
            raise BlockingError(
                f"two runs of the same matching on the same graph gave "
                f"{minimum_blocks} and {n - len(a_succ)} blocks; the solver is "
                f"not returning a maximum matching")
        starts, ends = [], []
        for h in (i for i in order if i not in a_pred):
            cur = h
            while cur in a_succ:
                cur = a_succ[cur]
            starts.append(trips[h].departure_sec)
            ends.append(trips[cur].arrival_sec)
        _c2, _m2, _pk2, _pm2, alt = block_concurrency(starts, ends, periods)
        by_period_alt = {k: int(v) for k, v in alt.items()}
        stable = ({k: int(v) for k, v in by_period.items()} == by_period_alt)

    _upper = getattr(oracle, "name", "") == "same_terminal_only"
    _lower = bool(getattr(oracle, "is_bound_only", False))
    _ti = terminal_identity(table)
    return CandidateBlockResult(
        minimum_blocks=minimum_blocks, blocks=tuple(blocks),
        fleet_by_period=by_period, system_peak=peak,
        system_peak_minute=peak_min, n_trips=n, n_feasible_edges=n_edges,
        deadhead_provenance=oracle.provenance,
        connection_rule=rule.payload,
        is_upper_bound=_upper, is_lower_bound=_lower, terminal_identity=_ti,
        fleet_by_period_stable=stable, fleet_by_period_alternate=by_period_alt,
        notes=("computed under an oracle that forbids every cross-terminal "
               "connection, so this is an UPPER BOUND on the fleet requirement"
               if _upper else
               "computed under a RELAXATION that moves a vehicle across the "
               "city in zero seconds, so this is a LOWER BOUND and certifies "
               "nothing" if _lower else ""))


def minimum_block_fleet(table: TripTable, oracle: DeadheadOracle,
                        periods: Mapping[str, tuple[float, float]],
                        rule: ConnectionRule | None = None) -> int:
    """Just the number, for callers that want only the count."""
    return block_candidate_schedule(table, oracle, periods, rule).minimum_blocks


# ---------------------------------------------------------------------------
# 7. audit: are the PUBLISHED transitions feasible under the new oracle?
# ---------------------------------------------------------------------------

def audit_published_transitions(tstats: pd.DataFrame, oracle: DeadheadOracle,
                                rule: ConnectionRule | None = None,
                                terminal_of=None) -> dict:
    """Every consecutive pair inside a published block, checked.

    A published transition the oracle calls impossible is a contradiction that
    must be surfaced, not smoothed. Under `SameTerminalOracle` the expected
    contradictions are exactly the cross-terminal ones, and counting them
    measures the size of the missing deadhead input rather than hiding it.
    """
    rule = rule or ConnectionRule(
        min_layover_sec=getattr(oracle, "min_layover_sec", 300.0))
    if "block_id" not in tstats.columns:
        raise BlockingError("tstats carries no block_id; nothing to audit")
    t = tstats.dropna(subset=["block_id"]).sort_values(
        ["block_id", "first_dep_sec", "trip_id"])
    total = same_term = cross_unknown = infeasible_time = ok = 0
    examples: list[dict] = []
    for _, grp in t.groupby("block_id", sort=True):
        rows = grp.to_dict("records")
        for a, b in zip(rows, rows[1:]):
            total += 1
            ta = terminal_of(a) if terminal_of else (None, None)
            tb = terminal_of(b) if terminal_of else (None, None)
            if ta[1] is None or tb[0] is None:
                cross_unknown += 1
                continue
            if ta[1] == tb[0]:
                same_term += 1
                gap = float(b["first_dep_sec"]) - float(a["last_arr_sec"])
                if gap + 1e-9 < rule.min_layover_sec:
                    infeasible_time += 1
                    if len(examples) < 8:
                        examples.append({
                            "block_id": str(a["block_id"]),
                            "from": str(a["trip_id"]), "to": str(b["trip_id"]),
                            "gap_sec": gap,
                            "why": (f"same terminal but only {gap:.0f}s, under "
                                    f"the {rule.min_layover_sec:.0f}s minimum "
                                    f"layover")})
                else:
                    ok += 1
            else:
                cross_unknown += 1
                if len(examples) < 8:
                    examples.append({
                        "block_id": str(a["block_id"]),
                        "from": str(a["trip_id"]), "to": str(b["trip_id"]),
                        "why": "cross-terminal; the oracle has no deadhead"})
    return {"transitions_examined": total,
            "same_terminal": same_term,
            "same_terminal_feasible": ok,
            "same_terminal_under_min_layover": infeasible_time,
            "cross_terminal_or_unknown": cross_unknown,
            "share_needing_deadhead_data": (cross_unknown / total
                                            if total else None),
            "oracle": oracle.provenance,
            "connection_rule": rule.payload,
            "examples": examples,
            "interpretation": (
                "a same-terminal transition the oracle refuses is a real "
                "contradiction with the published schedule. A cross-terminal "
                "one is not a contradiction -- it measures how much of COTA's "
                "actual blocking depends on deadhead data this project does "
                "not yet have")}


# ---------------------------------------------------------------------------
# 8. the operational-recourse rule, preregistered
# ---------------------------------------------------------------------------

OPERATIONAL_RECOURSE = {
    "rule": ("Reblocking is permitted as operational recourse. A candidate "
             "network or frequency plan may receive a NEW block assignment, "
             "but no additional fleet beyond the experiment's frozen "
             "per-period fleet envelope."),
    "why": ("geometry changes can make the historical block_id assignment "
            "literally impossible to preserve, so requiring it would reject "
            "candidates for a scheduling artifact rather than a resource one"),
    "the_blocker_may": ["find a new feasible blocking of the candidate's trips"],
    "the_blocker_may_not": ["change the fleet caps", "change the network",
                            "change the frequency plan",
                            "change the deadhead assumptions",
                            "change the layover assumptions"],
    "version": 1,
}
OPERATIONAL_RECOURSE_DIGEST = digest(OPERATIONAL_RECOURSE)


# ---------------------------------------------------------------------------
# 9. production feasibility against a frozen envelope
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProductionFeasibility:
    """Can this candidate be operated inside the frozen envelope?

    Three verdicts, not two. `INFEASIBLE` and `FEASIBLE` are claims; the third
    is `UNDECIDABLE`, and it exists because the per-period arm of the test as
    originally specified -- `candidate_fleet[p] <= envelope.fleet[p]` for all
    six periods -- turns out not to be a well-posed question.

    The reason is measured, not suspected. `fleet_by_period` is the concurrency
    of ONE maximum matching, and reversing the adjacency order produces a
    different maximum matching of the same size whose per-period concurrency
    differs by up to 26 vehicles on the real baseline. A test whose answer
    changes when you reverse a list is not a test.

    So this class refuses the per-period arm while the matching is unstable and
    reports UNDECIDABLE, rather than returning whichever verdict the current
    tie-break happens to produce. What survives is still worth having:

      * the invariant per-period LOWER bound can REFUTE. No blocking whatever
        can beat it, so exceeding the cap there is a real infeasibility.
      * vehicle-hours is a property of the timetable and not of the blocking,
        so that arm is decidable outright.
      * `minimum_blocks` is a graph invariant and can be compared against the
        BASELINE measured with the same instrument -- which is the comparison
        that is actually apples to apples, since the envelope's 197 is a peak
        concurrency of published blocks and not a path-cover count.
    """

    status: str
    feasible: bool | None
    reasons: tuple[str, ...]
    per_period: Mapping[str, Any]
    vehicle_hours: Mapping[str, Any]
    system: Mapping[str, Any]
    envelope_digest: str = ""
    deadhead_provenance: Mapping[str, Any] = field(default_factory=dict)
    provenance_certification_grade: bool = False
    provenance_note: str = ""
    contract_digest: str = ""

    def payload(self) -> dict:
        return {"status": self.status, "feasible": self.feasible,
                "reasons": list(self.reasons),
                "per_period": dict(self.per_period),
                "vehicle_hours": dict(self.vehicle_hours),
                "system": dict(self.system),
                "envelope_digest": self.envelope_digest,
                "deadhead_provenance": dict(self.deadhead_provenance),
                "provenance_certification_grade":
                    self.provenance_certification_grade,
                "provenance_note": self.provenance_note,
                "contract_digest": self.contract_digest,
                "verdicts": ["FEASIBLE", "INFEASIBLE", "UNDECIDABLE"],
                "amendment": ("AMENDMENT 1 removed the per-period arm as a "
                              "gate; per-period figures here are diagnostic")}


def provenance_is_certification_grade(prov: Mapping[str, Any]) -> tuple[bool, str]:
    """May a fleet result from this oracle APPROVE a candidate?

    Only an oracle that can answer for cross-terminal movement from a declared
    source. The two bracket oracles cannot: one forbids every such movement and
    the other grants it for free. Each can REFUTE -- a plan that fails even the
    generous relaxation fails for real -- and neither can approve.
    """
    src = str(prov.get("deadhead_source", ""))
    if prov.get("is_bound_only"):
        return False, (f"{src} is a relaxation that moves a vehicle across the "
                       f"city in zero seconds; it bounds from below and "
                       f"certifies nothing")
    if src == "same_terminal_only":
        return False, ("same_terminal_only forbids every cross-terminal "
                       "connection, so its answer is an upper bound. A plan "
                       "it rejects is rejected; a plan it accepts is only "
                       "accepted under an assumption nobody has evidence for")
    if src == "table":
        if not str(prov.get("source_note", "")).strip():
            return False, ("the deadhead table carries no source_note, so "
                           "nothing states where its travel times came from")
        return True, f"table deadhead oracle, {prov.get('n_pairs', 0)} pairs"
    if not src or src == "abstract":
        return False, "no deadhead oracle is declared"
    return False, f"unrecognised deadhead source {src!r}"


def production_feasible(candidate: CandidateBlockResult,
                        envelope_fleet: Mapping[str, int],
                        table: TripTable,
                        periods: Mapping[str, tuple[float, float]],
                        *,
                        envelope_vehicle_hours: float | None = None,
                        candidate_vehicle_hours: float | None = None,
                        baseline_minimum_blocks: int | None = None,
                        baseline_bound: CandidateFleetBound | None = None,
                        candidate_bound: CandidateFleetBound | None = None,
                        min_layover_sec: float = 300.0,
                        envelope_digest: str = "") -> ProductionFeasibility:
    """§9 as amended: existential, three-valued, and unable to bluff.

    Every route to INFEASIBLE runs through a matching-independent quantity, so
    a refutation cannot be an artifact of which maximum matching turned up.
    The route to FEASIBLE runs through the deadhead oracle's provenance, which
    is why it is currently closed.
    """
    reasons: list[str] = []
    infeasible = False

    if len(envelope_fleet) < 2:
        raise BlockingError(
            "a one-entry fleet envelope is a scalar cap in a dict costume; "
            "the envelope is a six-period vector")

    ok_prov, prov_why = provenance_is_certification_grade(
        candidate.deadhead_provenance)

    # ---- refutation 1: vehicle-hours. A property of the timetable, not of
    #      the blocking, so this arm is well posed whatever the oracle says.
    vh: dict[str, Any] = {"decidable": False}
    if envelope_vehicle_hours is not None and candidate_vehicle_hours is not None:
        within = candidate_vehicle_hours <= envelope_vehicle_hours + 1e-9
        vh = {"decidable": True, "candidate": float(candidate_vehicle_hours),
              "envelope": float(envelope_vehicle_hours), "within": within,
              "matching_independent": True,
              "note": ("revenue vehicle-hours is a property of the timetable, "
                       "not of the blocking")}
        if not within:
            infeasible = True
            reasons.append(
                f"revenue vehicle-hours {candidate_vehicle_hours:.4f} exceeds "
                f"the frozen envelope {envelope_vehicle_hours:.4f}")

    # ---- refutation 2: the per-period lower bound. No blocking can beat it.
    lower, lower_peak, lower_min = period_lower_bounds(table, periods,
                                                       min_layover_sec)
    over = {p: (lower[p], int(envelope_fleet[p]))
            for p in sorted(envelope_fleet)
            if lower.get(p, 0) > int(envelope_fleet[p])}
    if over:
        infeasible = True
        reasons.append(
            "the matching-independent per-period LOWER bound exceeds the "
            "envelope in " + ", ".join(f"{p} ({a} > {b})"
                                       for p, (a, b) in over.items())
            + " -- no choice of blocking can fix this")

    # ---- refutation 3: block counts, compared only against block counts.
    system: dict[str, Any] = {
        "candidate_minimum_blocks": int(candidate.minimum_blocks),
        "is_upper_bound": bool(candidate.is_upper_bound),
        "is_lower_bound": bool(candidate.is_lower_bound),
        "baseline_minimum_blocks": baseline_minimum_blocks,
        "candidate_bound": (candidate_bound.payload() if candidate_bound
                            else None),
        "baseline_bound": baseline_bound.payload() if baseline_bound else None,
        "comparison": ("instrument-consistent: both sides are path-cover "
                       "counts under the same oracle and connection rule. The "
                       "envelope's peak-vehicle figure is a concurrency of "
                       "published blocks and is NOT this quantity")}
    # Terminal identity gates every terminal-DEPENDENT comparison below. A
    # timetable whose trips mostly end where nothing starts forces one block
    # per trip by construction, so its upper bound is arithmetic about missing
    # terminal identity and not evidence about fleet -- in either direction.
    # The lower bounds above are untouched: they never look at a terminal.
    ti = dict(candidate.terminal_identity or {})
    degenerate = bool(ti.get("degenerate"))
    system_note = ""
    if degenerate:
        system_note = (
            f"terminal identity is unresolved for this timetable: "
            f"{ti.get('trips_whose_destination_is_never_an_origin')} of "
            f"{ti.get('n_trips')} trips "
            f"({ti.get('share_stranded', 0):.1%}) end at a terminal that is "
            f"never any trip's origin, so a same-terminal oracle forces them "
            f"into their own blocks whatever the schedule is. Every "
            f"terminal-dependent comparison is withheld")
        reasons.append(system_note)

    if baseline_minimum_blocks is not None and not degenerate:
        system["within_baseline"] = (candidate.minimum_blocks
                                     <= baseline_minimum_blocks)
        if not system["within_baseline"]:
            infeasible = True
            reasons.append(
                f"the candidate needs {candidate.minimum_blocks} blocks where "
                f"the baseline needs {baseline_minimum_blocks} under the same "
                f"instrument")
    if (candidate_bound is not None and baseline_bound is not None
            and not degenerate):
        # A candidate whose most generous case still exceeds the baseline's
        # least generous case is refuted whatever the deadhead truth turns
        # out to be -- both ends move together when the oracle improves.
        if candidate_bound.lower > baseline_bound.upper:
            infeasible = True
            reasons.append(
                f"the candidate needs at least {candidate_bound.lower} blocks "
                f"even when every deadhead is free, against a baseline that "
                f"needs at most {baseline_bound.upper} with no interlining at "
                f"all; no deadhead model can reconcile that")
        system["bracket_refutation_applies"] = (
            candidate_bound.lower > baseline_bound.upper)
    system["terminal_identity"] = ti
    system["terminal_identity_degenerate"] = degenerate
    if system_note:
        system["terminal_comparisons_withheld"] = system_note

    # ---- the removed arm, computed as a DIAGNOSTIC and marked as one -------
    literal = {p: (int(candidate.fleet_by_period.get(p, 0)),
                   int(envelope_fleet[p])) for p in sorted(envelope_fleet)}
    stable = candidate.fleet_by_period_stable
    if stable is False:
        reasons.append(
            "the per-period figure is a property of the maximum matching "
            "found, not of the schedule: an equally maximum matching gives "
            f"{dict(sorted((candidate.fleet_by_period_alternate or {}).items()))}"
            ". It is reported as a diagnostic and gates nothing (AMENDMENT 1)")

    # ---- verdict ----------------------------------------------------------
    # Every reason feasibility cannot be PROVEN, not just the first one found.
    # A caller who fixes one and re-runs should not discover the next in
    # sequence; that is how a blocker list becomes a queue.
    blockers: list[str] = []
    if degenerate:
        blockers.append(
            "TERMINAL IDENTITY PROVENANCE is OPEN for this timetable, a "
            "second missing input alongside deadhead, and it is not "
            "substituted for here")
    if not ok_prov:
        blockers.append(f"feasibility cannot be PROVEN: {prov_why}")
    if not vh["decidable"]:
        blockers.append("vehicle-hours were not supplied, so a required "
                        "constraint was never evaluated")

    if infeasible:
        status, feasible = "INFEASIBLE", False
    elif blockers:
        status, feasible = "UNDECIDABLE", None
        reasons.extend(blockers)
        reasons.append(
            "not refuted by any matching-independent bound, which is not the "
            "same as being feasible")
    else:
        status, feasible = "FEASIBLE", True
        reasons.append(
            f"proven under an oracle whose provenance satisfies the "
            f"certification contract ({prov_why}): vehicle-hours within the "
            f"envelope, and no matching-independent bound violated")

    return ProductionFeasibility(
        status=status, feasible=feasible, reasons=tuple(reasons),
        per_period={"REMOVED_AS_A_GATE": FLEET_ARM_AMENDMENT_1["text"],
                    "diagnostic_only": True,
                    "superseded_test": literal,
                    "matching_stable": stable,
                    "invariant_lower_bound": lower,
                    "invariant_lower_bound_peak": lower_peak,
                    "invariant_lower_bound_peak_minute": lower_min,
                    "envelope": {p: int(v) for p, v in
                                 sorted(envelope_fleet.items())},
                    "lower_bound_exceeds_envelope": {p: list(v) for p, v
                                                     in over.items()}},
        vehicle_hours=vh, system=system, envelope_digest=envelope_digest,
        deadhead_provenance=dict(candidate.deadhead_provenance),
        provenance_certification_grade=ok_prov,
        provenance_note=prov_why,
        contract_digest=BLOCKING_CONTRACT_DIGEST)



# ---------------------------------------------------------------------------
# 10. four fleet numbers that are not the same number
# ---------------------------------------------------------------------------
#
# 197, 180-212, 176.132352 and a future provenance-complete minimum_blocks are
# produced by four different instruments and mean four different things. Held
# as plain floats in one field they are one `if` away from being compared, and
# the whole envelope-provenance episode began with exactly that: a cap read off
# an evaluated plan because both numbers were floats named something like fleet.
#
# So they are typed. A `FleetQuantity` refuses `float()`, refuses ordering, and
# refuses equality against a quantity of a different kind. Reading the number
# requires naming the purpose, which puts the intended comparison in the diff.

class FleetSemanticsViolation(TypeError):
    """Two fleet numbers from different instruments were about to be compared."""


_FLEET_WHY = (
    "these fleet quantities come from different instruments and are not "
    "interchangeable: PUBLISHED_BLOCK_PEAK is the concurrency of COTA's own "
    "blocking (197 at 17:13); CANDIDATE_BLOCK_BOUND is a path-cover count "
    "under an incomplete deadhead oracle (180-212); LEGACY_CONCURRENCY_PROXY "
    "is the frequency model's output (176.132352) and is barred from Exp 4 "
    "fleet certification entirely; CERTIFIED_MINIMUM_BLOCKS does not exist "
    "yet and will not until deadhead provenance is complete. Comparing two of "
    "them is how the 1.307 'interlining factor' came to look like an exchange "
    "rate. Read one with its own named accessor instead.")

FLEET_KINDS = ("PUBLISHED_BLOCK_PEAK", "CANDIDATE_BLOCK_BOUND",
               "LEGACY_CONCURRENCY_PROXY", "CERTIFIED_MINIMUM_BLOCKS")


class FleetQuantity:
    """A fleet number that knows which instrument produced it, and says no."""

    __slots__ = ("_v", "_kind", "_instrument", "_provenance")

    def __init__(self, value: float, kind: str, instrument: str,
                 provenance: str) -> None:
        if kind not in FLEET_KINDS:
            raise FleetSemanticsViolation(
                f"unknown fleet kind {kind!r}; one of {FLEET_KINDS}")
        self._v = float(value)
        self._kind = str(kind)
        self._instrument = str(instrument)
        self._provenance = str(provenance)

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def instrument(self) -> str:
        return self._instrument

    @property
    def provenance(self) -> str:
        return self._provenance

    def value_for(self, purpose: str) -> float:
        """Read the number, having named what it is for.

        `purpose` is recorded, not validated -- the point is that a reader of
        the diff can see which comparison was intended, not that this method
        can police it.
        """
        if not purpose:
            raise FleetSemanticsViolation(
                "name the purpose you are reading this fleet number for")
        if self._kind == "LEGACY_CONCURRENCY_PROXY" and "certif" in \
                purpose.lower():
            raise FleetSemanticsViolation(
                "the legacy concurrency proxy may not participate in "
                "Experiment 4 fleet certification. " + _FLEET_WHY)
        return self._v

    def same_kind_as(self, other: "FleetQuantity") -> bool:
        return isinstance(other, FleetQuantity) and other._kind == self._kind

    def compare_same_kind(self, other: "FleetQuantity") -> float:
        """self - other, permitted only within one instrument."""
        if not self.same_kind_as(other):
            raise FleetSemanticsViolation(_FLEET_WHY)
        return self._v - other._v

    def payload(self) -> dict:
        return {"value": self._v, "kind": self._kind,
                "instrument": self._instrument, "provenance": self._provenance}

    def __repr__(self) -> str:
        return f"FleetQuantity({self._v!r}, kind={self._kind!r})"

    def _refuse(self, *_a: Any, **_k: Any):
        raise FleetSemanticsViolation(_FLEET_WHY)

    __float__ = _refuse
    __int__ = _refuse
    __index__ = _refuse
    __lt__ = _refuse
    __le__ = _refuse
    __gt__ = _refuse
    __ge__ = _refuse
    __eq__ = _refuse
    __ne__ = _refuse
    __hash__ = None                      # type: ignore[assignment]
    __add__ = __radd__ = _refuse
    __sub__ = __rsub__ = _refuse
    __mul__ = __rmul__ = _refuse
    __truediv__ = __rtruediv__ = _refuse
    __floordiv__ = __rfloordiv__ = _refuse
    __mod__ = __rmod__ = _refuse
    __pow__ = __rpow__ = _refuse
    __neg__ = __pos__ = __abs__ = _refuse
    __round__ = __trunc__ = __floor__ = __ceil__ = _refuse
    __bool__ = _refuse
    __format__ = _refuse


def published_block_peak(value: float) -> FleetQuantity:
    """The envelope's fleet figure. The VALUE IS NOT DEFAULTED ON PURPOSE:
    a resource cap is read from outputs/CANONICAL_ENVELOPE.json or from the
    production `baseline` sentinel, never retyped into a module."""
    return FleetQuantity(
        value, "PUBLISHED_BLOCK_PEAK", "blocks.reconstruct",
        "concurrency of COTA's published block assignment, 197 @ 17:13 over "
        "284 blocks; the frozen envelope's fleet figure")


def legacy_concurrency_proxy(value: float) -> FleetQuantity:
    """Wraps the proxy so it can be CARRIED without being usable. Not
    defaulted: this module does not hold the proxy's value either."""
    return FleetQuantity(
        value, "LEGACY_CONCURRENCY_PROXY", "FitnessVector.peak_vehicles",
        "an evaluated plan's peak concurrency. An OUTPUT, never a cap, and "
        "barred from Experiment 4 fleet certification")


@dataclass(frozen=True)
class CandidateFleetBound:
    """The bracket, carried as one object so neither end escapes alone.

    Returning 180 or 212 as a bare number invites it being read as "the"
    candidate fleet requirement. It is not; it is one end of an interval whose
    width is the price of the missing deadhead source.
    """

    lower: int
    upper: int
    lower_oracle: str
    upper_oracle: str
    deadhead_provenance: str = "OPEN"
    n_trips: int = 0

    def __post_init__(self) -> None:
        if self.lower > self.upper:
            raise BlockingError(
                f"fleet bracket [{self.lower}, {self.upper}] is inverted; the "
                f"relaxation cannot need more buses than the strict oracle")

    def contains(self, n: float) -> bool:
        return self.lower <= n <= self.upper

    def certified_value(self) -> int:
        raise FleetSemanticsViolation(
            "a bracket is not a certified fleet requirement. Its width is the "
            "missing deadhead source; supply a TableDeadheadOracle with real "
            "provenance and the two ends collapse to one number. " + _FLEET_WHY)

    def payload(self) -> dict:
        return {"lower": self.lower, "upper": self.upper,
                "lower_oracle": self.lower_oracle,
                "upper_oracle": self.upper_oracle,
                "deadhead_provenance": self.deadhead_provenance,
                "n_trips": self.n_trips,
                "kind": "CANDIDATE_BLOCK_BOUND",
                "NOT": ("not a certified fleet requirement; neither end may be "
                        "reported as the candidate's fleet number")}


# ---------------------------------------------------------------------------
# 11. the §9 amendment, with the original preserved
# ---------------------------------------------------------------------------
#
# The per-period blocking arm was preregistered and is being removed BEFORE any
# Experiment 4 execution. That is legitimate; quietly rewriting the design so
# it reads as though this was always the plan would not be. Both versions are
# carried here, digested, and asserted by tests.

FLEET_ARM_ORIGINAL = {
    "section": "§9 production feasibility",
    "status": "SUPERSEDED BY AMENDMENT 1",
    "preregistered_text": (
        "Production feasibility: candidate_fleet[p] <= envelope.fleet[p] for "
        "all six periods AND vehicle-hours."),
    "why_it_was_written": (
        "the frozen envelope is a six-period vector, so a six-period test "
        "looked like the faithful way to enforce it"),
    "what_validation_showed": (
        "candidate_fleet[p] is the concurrency of ONE maximum matching. "
        "Reversing adjacency order on the stripped-block baseline yields a "
        "different maximum matching with the SAME minimum block count of 212 "
        "while per-period concurrency moves by as much as 15 vehicles -- "
        "midday 199 -> 210, am_peak 195 -> 210. The quantity is a property of "
        "one equally optimal blocking realisation, not of the candidate "
        "timetable."),
    "rejected_repair": (
        "canonicalising the adjacency order, sorting edges, or otherwise "
        "forcing one deterministic matching. That would make the statistic "
        "reproducible without making it operationally meaningful, which is the "
        "worse failure: a number that is stable and means nothing."),
}

FLEET_ARM_AMENDMENT_1 = {
    "amendment": 1,
    "date": "2026-09-07",
    "before_any_experiment_4_execution": True,
    "text": (
        "The preregistered per-period blocking arm was removed before "
        "Experiment 4 execution because validation demonstrated that it was "
        "not invariant to the choice among equally optimal maximum matchings. "
        "Under the experiment's OPERATIONAL_RECOURSE assumption, fleet "
        "feasibility is instead evaluated using matching-independent "
        "block-count bounds and, once deadhead provenance is complete, "
        "minimum path-cover cardinality under the declared deadhead oracle."),
    "question_now_asked": (
        "EXISTENTIAL: does there exist a feasible blocking of the candidate "
        "timetable within the allowed fleet envelope?"),
    "question_no_longer_asked": (
        "what period-by-period fleet profile happens to be produced by one "
        "arbitrary maximum matching?"),
    "invariant_quantity": "minimum_blocks = n_trips - maximum_matching",
    "conditional_on": (
        "the compatibility graph being built with a provenance-complete "
        "deadhead oracle"),
    "not_permitted": [
        "min-cost flow or any further optimisation layer introduced to rescue "
        "the rejected per-period statistic -- that answers a different "
        "question",
        "a canonical adjacency order adopted to make the rejected statistic "
        "reproducible",
        "reporting either end of the bracket as the candidate's fleet number",
    ],
    "deferred_to_a_separate_experiment": (
        "whether there exists a MINIMUM-fleet blocking that also satisfies "
        "additional period-specific concurrency constraints. That is a "
        "constrained-blocking problem, not this one."),
    "per_period_figures_are_now": "DIAGNOSTIC ONLY",
}

BLOCKING_CONTRACT = {
    "name": "EXP4_BLOCKING",
    "version": 2,
    "supersedes": "version 1, whose §9 carried the per-period arm as a gate",
    "sections": {
        "materialisation": "deterministic, order-independent, content-addressed",
        "deadhead": ("strict oracle; DeadheadUnknown makes a connection "
                     "infeasible and never zero"),
        "solver": "DAG minimum path cover by maximum bipartite matching",
        "recourse": "OPERATIONAL_RECOURSE",
        "feasibility": "three-valued: FEASIBLE / INFEASIBLE / UNDECIDABLE",
    },
    "original_fleet_arm": FLEET_ARM_ORIGINAL,
    "amendments": [FLEET_ARM_AMENDMENT_1],
}
BLOCKING_CONTRACT_DIGEST = digest(BLOCKING_CONTRACT)


# ---------------------------------------------------------------------------
# 12. terminal identity: a SECOND missing input, found by running the thing
# ---------------------------------------------------------------------------
#
# The oracle asks whether a bus finishing at terminal X can start at terminal
# Y. Even the same-terminal case needs to know when X and Y are the same place,
# and in this feed that is not always answerable:
#
#   * `parent_station` is present as a column and empty in all 2,949 rows, so
#     GTFS supplies no station grouping at all;
#   * a candidate line's outbound pattern ends at HIGHALS while its inbound
#     starts at HIGHALN -- two sides of one street, two stop_ids;
#   * "SPRING ST TERMINAL BAY 3" and "BAY 4" are one terminal with two ids.
#
# Grouping them by distance would be inventing a threshold; grouping them by
# stop_name prefix would be inferring geography from a label. Both are the same
# class of move as estimating deadhead from block slack, so neither is made.
#
# The consequence is measured instead of assumed. On the published feed the
# problem barely arises -- COTA's own trips chain through matching stop_ids.
# On synthesised pool lines it dominates, and an upper bound computed there is
# close to "every trip is its own block", which is true and nearly useless.
# `terminal_identity` says so, and callers can refuse to read a degenerate
# bound as evidence.

TERMINAL_IDENTITY_PROVENANCE = {
    "status": "OPEN",
    "what_is_missing": ("a statement of which stop_ids denote the same "
                        "physical terminal"),
    "why_gtfs_does_not_answer": ("parent_station is empty in all 2,949 stop "
                                 "rows and location_type is unset"),
    "forbidden_substitutes": [
        "grouping stops within some distance of each other -- the threshold "
        "would be invented and the answer would move with it",
        "grouping stops by shared stop_name prefix or by a BAY suffix -- that "
        "infers geography from a label",
        "assuming a route's two directions share a terminal because they are "
        "the same route",
    ],
    "consequence": ("where it is unresolved, a same-terminal oracle cannot "
                    "chain a route's own two directions, and its upper bound "
                    "approaches one block per trip"),
    "acceptable_source": ("an operator-supplied terminal/garage table, the "
                          "same artifact that would carry deadhead times"),
}
TERMINAL_IDENTITY_DIGEST = digest(TERMINAL_IDENTITY_PROVENANCE)


def terminal_identity(table: TripTable, *,
                      degenerate_at: float = 0.5) -> dict:
    """How much of this timetable can a same-terminal oracle even see?

    A trip whose destination terminal is never any trip's origin can never be
    followed by anything under that oracle, whatever the schedule looks like.
    When most trips are in that position the resulting "upper bound" is
    arithmetic about missing terminal identity, not about fleet.
    """
    if len(table) == 0:
        return {"n_trips": 0, "degenerate": False,
                "provenance": TERMINAL_IDENTITY_PROVENANCE}
    origins = {t.origin_terminal for t in table.trips}
    dests = {t.destination_terminal for t in table.trips}
    stranded = [t for t in table.trips if t.destination_terminal not in origins]
    share = len(stranded) / len(table)
    return {
        "n_trips": len(table),
        "n_origin_terminals": len(origins),
        "n_destination_terminals": len(dests),
        "n_shared_terminals": len(origins & dests),
        "trips_whose_destination_is_never_an_origin": len(stranded),
        "share_stranded": share,
        "degenerate": share >= degenerate_at,
        "degenerate_at": degenerate_at,
        "meaning": (
            "a stranded trip can never be followed by anything under a "
            "same-terminal oracle, so each one forces its own block. Where "
            "the share is high the upper bound measures unresolved terminal "
            "identity rather than fleet"),
        "provenance": TERMINAL_IDENTITY_PROVENANCE,
    }
