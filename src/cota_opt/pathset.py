"""Candidate path sets: OD-level assignment that responds to frequency changes.

Running RAPTOR inside the optimizer is not affordable — one solve evaluates a
plan tens of thousands of times. So the work is split:

1. **Enumerate** (once). RAPTOR is run from every origin zone under several
   *diverse* frequency scenarios — today's schedule, uniformly frequent,
   uniformly infrequent, and randomized plans — and the distinct paths found
   are pooled. Diversity matters: a path that is only attractive when some
   route runs more often must already be in the set for the optimizer to
   discover it.

2. **Re-cost** (every evaluation). Each cached path is priced under the current
   headways with one vectorized pass, and every OD pair takes the cheapest of
   its own candidates. Path *structure* is fixed; path *choice* is not — which
   is exactly the re-routing behaviour that route-level assignment lacked.

3. **Validate** (once, afterwards). RAPTOR is re-run on the optimized plan and
   compared against the cached-set cost. The gap is the assignment error
   introduced by step 1, and it is reported rather than assumed away.

A path is stored as a sequence of legs. Ride legs carry the (route, period)
whose headway prices their boarding wait; walk legs carry fixed minutes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from .cost import CostWeights
from .odmatrix import ODTable, ZoneSystem
from .raptor import (RaptorNetwork, generalized_cost, pattern_headways,
                     reconstruct, route_level_headways)

log = logging.getLogger(__name__)


@dataclass
class PathSet:
    """Flattened candidate paths for one service period.

    Arrays are leg-major. ``leg_path`` maps each leg to its path; ``path_od``
    maps each path to its OD-pair index. Both are sorted so aggregation can use
    ``np.add.reduceat`` / ``np.minimum.reduceat``.
    """

    period: str
    n_od: int
    # per-leg
    leg_path: np.ndarray            # path index
    leg_rp: np.ndarray              # index into the route-period vector, -1 for walk
    leg_ivt: np.ndarray             # in-vehicle minutes
    leg_walk: np.ndarray            # walk minutes
    leg_is_boarding: np.ndarray     # bool: this leg starts a new ride
    leg_is_transfer: np.ndarray     # bool: boarding after the first
    # per-path
    path_od: np.ndarray             # OD index
    path_offsets: np.ndarray        # into the leg arrays (len n_paths + 1)
    od_offsets: np.ndarray          # into the path arrays (len n_od + 1)
    od_flow: np.ndarray             # daily trips per OD
    od_walk_only: np.ndarray        # walk-only fallback cost, inf if none
    rp_keys: list[tuple[str, str]] = field(default_factory=list)
    od_origin: np.ndarray | None = None     # origin zone id per OD index
    od_dest: np.ndarray | None = None       # destination zone id per OD index
    # ride-leg geometry, used to recover segment loads and peak load points
    leg_pattern: np.ndarray | None = None    # pattern index, -1 for walk legs
    leg_board_pos: np.ndarray | None = None  # position along the pattern
    leg_alight_pos: np.ndarray | None = None
    leg_headway_mult: np.ndarray | None = None   # pattern headway / route headway

    @property
    def n_paths(self) -> int:
        return len(self.path_od)

    @property
    def n_legs(self) -> int:
        return len(self.leg_path)


def _plan_scenarios(rp_keys, baseline: dict, rng, n_random: int = 3,
                    ladder=(5, 10, 15, 20, 30, 45, 60),
                    route_level: bool = False):
    """Diverse headway vectors used only to widen the candidate path set.

    Each entry is ``(name, headways, pricing)``. ``pricing`` selects how the
    search converts route-period headways into the per-pattern headways RAPTOR
    waits on: ``"pattern"`` applies the usual trips-share multiplier, ``"route"``
    prices every pattern at its route's whole frequency.

    The route-level scenario exists because of gate 11. RAPTOR searches under
    Model A's valuation, so a route sequence that only becomes attractive once
    several of a route's patterns are counted together is one the search has no
    reason to explore -- and the diagnostic found 4.88% of tested flow with
    exactly that shape. Route-level pricing is a strict *lower* bound on any
    Model B path cost, so a search under it explores the sequences that can win
    once patterns combine, for every OD pair rather than only the ones the
    diagnostic sampled. It is a search device and nothing else: whatever it
    finds is priced honestly by the evaluator afterwards.

    Whether to add it is the caller's policy, not this function's inference:
    it is on for Model B and off for Model A -- the preserved control, whose
    candidate set must not move, and under whose per-pattern valuation
    route-level pricing bounds nothing anyway. Passing it explicitly is what
    lets the augmented and un-augmented sets both be built, which is the only
    non-circular evidence that the augmentation mattered.
    """
    scen = [("baseline", dict(baseline), "pattern")]
    scen.append(("frequent", {k: min(baseline[k], 10.0) for k in rp_keys},
                 "pattern"))
    scen.append(("infrequent", {k: max(baseline[k], 45.0) for k in rp_keys},
                 "pattern"))
    for i in range(n_random):
        scen.append((f"random{i}",
                     {k: float(rng.choice(ladder)) for k in rp_keys}, "pattern"))
    if route_level:
        scen.append(("route_level", dict(baseline), "route"))
    return scen


def build_pathset(
    rn: RaptorNetwork,
    zs: ZoneSystem,
    od: ODTable,
    period: str,
    baseline_headways: dict[tuple[str, str], float],
    weights: CostWeights,
    wait_kwargs: dict,
    max_rounds: int = 3,
    max_paths_per_od: int = 4,
    n_random_scenarios: int = 3,
    seed: int = 0,
    extra_scenarios: list[tuple[str, dict]] | None = None,
    common_lines: str = "pattern",
    route_level_scenario: bool = False,
) -> PathSet:
    """Enumerate candidate paths for every OD pair in ``od``.

    ``extra_scenarios`` adds named headway vectors to the enumeration sweep on
    top of the standard baseline/frequent/infrequent/random set. Feeding an
    optimized plan back in this way is what closes the path-set fixpoint: the
    optimizer can only choose among paths that were enumerated, so a plan that
    makes some new path attractive must have that path added and then be
    re-solved until the set stops growing.
    """
    rng = np.random.default_rng(seed)
    rp_keys = sorted({k for k in baseline_headways})
    rp_index = {k: i for i, k in enumerate(rp_keys)}
    route_of_pat = rn.pattern_route

    # OD pairs grouped by origin zone, so each RAPTOR run serves many pairs
    order = np.lexsort((od.dest, od.origin))
    o_sorted, d_sorted, f_sorted = od.origin[order], od.dest[order], od.flow[order]
    od_index = {(int(o), int(d)): i for i, (o, d) in
                enumerate(zip(o_sorted, d_sorted))}
    n_od = len(o_sorted)

    # candidate paths keyed by OD -> {signature: legs}
    found: list[dict[tuple, list]] = [dict() for _ in range(n_od)]
    walk_only = np.full(n_od, np.inf)

    n_rejected = [0]
    cl_cache: dict = {}
    scenarios = _plan_scenarios(rp_keys, baseline_headways, rng,
                                n_random_scenarios, route_level=route_level_scenario)
    for name, hw in (extra_scenarios or []):
        missing = [k for k in rp_keys if k not in hw]
        if missing:
            raise ValueError(
                f"extra scenario {name!r} is missing {len(missing)} route-period "
                f"headways, e.g. {missing[:3]}")
        scenarios.append((name, {k: float(hw[k]) for k in rp_keys}, "pattern"))
    origins = np.unique(o_sorted)
    # Each scenario contributes at most one path per OD -- its own optimum. A
    # per-OD cap below the scenario count therefore silently discards whole
    # scenarios' worth of coverage on a first-come basis, which is one of the
    # ways a candidate set ends up inadequate under an optimized plan. The cap
    # is raised to the scenario count so every scenario's optimum is retained.
    cap = max(int(max_paths_per_od), len(scenarios))
    log.info("path enumeration: %d OD pairs, %d origin zones, %d scenarios, "
             "cap %d paths/OD", n_od, len(origins), len(scenarios), cap)

    dest_by_origin: dict[int, np.ndarray] = {}
    starts = np.searchsorted(o_sorted, origins, side="left")
    ends = np.searchsorted(o_sorted, origins, side="right")
    for z, a, b in zip(origins, starts, ends):
        dest_by_origin[int(z)] = np.arange(a, b)

    for sname, hw, pricing in scenarios:
        ph = (route_level_headways(rn, hw, period) if pricing == "route"
              else pattern_headways(rn, hw, period))
        for z in origins:
            a_stops, a_walk = zs.access_of(int(z))
            if len(a_stops) == 0:
                continue
            src = [rn.stop_ids[s] for s in a_stops]
            init = [weights.walking * wmin for wmin in a_walk]
            cost, rounds, par = generalized_cost(
                rn, src, ph, weights, wait_kwargs, max_rounds=max_rounds,
                source_costs=init, trace=True)
            src_set = set(src)
            for oi in dest_by_origin[int(z)]:
                dz = int(d_sorted[oi])
                e_stops, e_walk = zs.access_of(dz)
                if len(e_stops) == 0:
                    continue
                tot = cost[e_stops] + weights.walking * e_walk
                k = int(np.argmin(tot))
                if not np.isfinite(tot[k]):
                    continue
                stop = e_stops[k]
                j = reconstruct(rn, par, rn.stop_ids[stop],
                                int(rounds[stop]), src_set)
                if j is None:
                    continue
                legs = _legs_from_journey(j, route_of_pat, rn, rp_index,
                                          period, common_lines, cl_cache)
                if legs is None:
                    continue
                # access and egress walking attach to the ends
                access_walk = float(a_walk[list(a_stops).index(
                    rn.stop_index[j.legs[0].from_stop])]) \
                    if rn.stop_index[j.legs[0].from_stop] in list(a_stops) else 0.0
                legs = ([("walk", -1, 0.0, access_walk, False, False,
                          -1, -1, -1, 1.0, 1.0)] if access_walk else []) \
                    + legs \
                    + ([("walk", -1, 0.0, float(e_walk[k]), False, False,
                         -1, -1, -1, 1.0, 1.0)] if e_walk[k] > 0 else [])
                # Self-check: a stored path must re-price to the cost RAPTOR
                # reported for it. A path that prices cheaper than RAPTOR's
                # optimum is malformed (a truncated trace, a dropped leg) and
                # would silently flatter every result that used it.
                priced = _price_legs(legs, hw, weights, wait_kwargs, period,
                                     search_mult=1.0 if pricing == "route"
                                     else None)
                if priced < tot[k] - 1e-6 or priced > tot[k] + 1e-3:
                    n_rejected[0] += 1
                    continue
                # the path is sound; store it priced under the active model
                legs = [l[:9] + (l[10],) for l in legs]
                sig = tuple((l[0], l[1], round(l[2], 3), round(l[3], 3)) for l in legs)
                if len(found[oi]) < cap or sig in found[oi]:
                    found[oi][sig] = legs

    # walk-only fallback where origin and destination share an access stop
    for oi in range(n_od):
        oz, dz = int(o_sorted[oi]), int(d_sorted[oi])
        if oz == dz:
            walk_only[oi] = 0.0

    if n_rejected[0]:
        log.info("rejected %d malformed candidate paths that failed the "
                 "re-pricing check", n_rejected[0])
    return _flatten(found, o_sorted, d_sorted, f_sorted, walk_only,
                    rp_keys, period)


def _price_legs(legs, hw: dict, w: CostWeights, wait_kwargs: dict,
                period: str, search_mult: float | None = None) -> float:
    """Cost a candidate path exactly as the SEARCH that produced it priced it.

    The self-check that calls this compares against the cost RAPTOR reported,
    so it has to use the multiplier RAPTOR was waiting on -- Model A's
    per-pattern share for the ordinary scenarios, and a flat 1.0 for the
    route-level scenario, which prices every pattern at its route's whole
    frequency. Getting that wrong does not produce a wrong number; it produces
    a rejected path, which is how the route-level scenario was silently
    contributing nothing the first time it was wired in.
    """
    from .cost import expected_wait_min
    rp_keys = sorted(hw)
    total = 0.0
    for leg in legs:
        kind, rp, ivt, walk, board, xfer, _pat, _bp, _ap, mult = leg[:10]
        if search_mult is not None:
            mult = search_mult
        total += w.walking * walk + w.in_vehicle * ivt
        if rp >= 0:
            h = hw[rp_keys[rp]] * mult
            ew = expected_wait_min(h, **wait_kwargs)
            total += (w.transfer_wait * ew + w.transfer_penalty) if xfer \
                else w.waiting * ew
    return total


def _headway_multiplier(rn, pattern_id: str, route_id: str, direction: int,
                        period: str) -> float:
    """How much less frequent one pattern is than its route (**Model A**).

    A passenger riding a specific pattern only benefits from that pattern's
    trips, so its effective headway is the route's headway scaled by the share
    of the direction's trips the pattern carries. The ratio is structural — the
    trip mix between pattern variants is fixed with the geometry — so it is
    baked into the leg and multiplies whatever headway the optimizer chooses.

    This is right when the chosen pattern is the only one that can carry the
    movement, and wrong when it is not. See ``common_lines_multiplier``.
    """
    n_pat = rn.pattern_trips_period.get((pattern_id, period), 0)
    n_dir = rn.direction_trips_period.get((route_id, direction, period), 0)
    if n_pat <= 0 or n_dir <= 0:
        return 1.0
    return float(n_dir) / float(n_pat)


def qualifying_patterns(rn, pi: int, bpos: int, apos: int,
                        period: str) -> list[int]:
    """Patterns of the same route a passenger could board interchangeably.

    A pattern qualifies for a boarding-to-alighting movement only if it serves
    the boarding stop, serves the alighting stop, does so in that order, and
    runs in this period. Sharing a route id is not enough: a short-turn that
    stops before the destination cannot carry the passenger, and a pattern that
    passes both stops in the opposite order is going the other way.
    """
    off = rn.pat_offsets
    b_stop = int(rn.pat_stops[off[pi] + bpos])
    a_stop = int(rn.pat_stops[off[pi] + apos])
    route = rn.pattern_route[pi]
    out = []
    s0, s1 = rn.stop_pat_offsets[b_stop], rn.stop_pat_offsets[b_stop + 1]
    for k in range(s0, s1):
        q = int(rn.stop_pat_idx[k])
        if rn.pattern_route[q] != route:
            continue
        if rn.pattern_trips_period.get((rn.pattern_ids[q], period), 0) <= 0:
            continue
        qb = int(rn.stop_pat_pos[k])
        seq = rn.pat_stops[off[q] + qb + 1:off[q + 1]]
        if a_stop in seq:                      # reaches the destination, after
            out.append(q)
    return out


def common_lines_multiplier(rn, pi: int, bpos: int, apos: int, period: str,
                            cache: dict | None = None) -> float:
    """Headway multiplier over every same-route pattern that serves the movement.

    **Model B.** Where several of a route's patterns all carry a passenger from
    their boarding stop to their alighting stop, the passenger boards whichever
    arrives first and waits on the combined frequency. Charging one pattern's
    headway overstates the wait, and it does so worst on the high-frequency
    trunk routes that run the most pattern variants.

    The arithmetic stays inside the existing representation. A pattern's
    headway is ``h_route * n_direction_trips / n_pattern_trips``, so its
    frequency is ``n_pattern_trips / (h_route * n_direction_trips)``. Summing
    frequency over the qualifying set and inverting gives a multiplier on the
    same route headway the optimizer controls:

        mult = 1 / sum_q ( n_trips(q) / n_direction_trips(q) )

    With one qualifying pattern this is exactly ``n_dir / n_pat`` — Model A —
    so the correction is a strict generalisation rather than a different model.
    """
    key = (pi, bpos, apos, period)
    if cache is not None and key in cache:
        return cache[key]
    qs = qualifying_patterns(rn, pi, bpos, apos, period)
    total = 0.0
    for q in qs:
        n_pat = rn.pattern_trips_period.get((rn.pattern_ids[q], period), 0)
        n_dir = rn.direction_trips_period.get(
            (rn.pattern_route[q], rn.pattern_direction[q], period), 0)
        if n_pat > 0 and n_dir > 0:
            total += float(n_pat) / float(n_dir)
    mult = (1.0 / total) if total > 0 else 1.0
    if cache is not None:
        cache[key] = mult
    return mult


def _legs_from_journey(j, route_of_pat, rn, rp_index, period,
                       common_lines: str = "pattern",
                       cl_cache: dict | None = None):
    """Journey -> leg tuples, or None if any ride leg has no priceable headway.

    Ride legs carry the pattern and the board/alight positions so segment loads
    (and therefore each route-period's peak load point) can be recovered.
    """
    out = []
    first_ride = True
    pid_index = {p: i for i, p in enumerate(rn.pattern_ids)}
    for l in j.legs:
        if l.kind == "walk":
            out.append(("walk", -1, 0.0, float(l.walk_min), False, False,
                        -1, -1, -1, 1.0, 1.0))
            continue
        key = (l.route_id, period)
        idx = rp_index.get(key)
        if idx is None:
            return None
        pi = pid_index.get(l.pattern_id, -1)
        bpos = apos = -1
        if pi >= 0:
            a, b = rn.pat_offsets[pi], rn.pat_offsets[pi + 1]
            stops = list(rn.pat_stops[a:b])
            try:
                bpos = stops.index(rn.stop_index[l.from_stop])
                apos = stops.index(rn.stop_index[l.to_stop], bpos + 1)
            except (ValueError, KeyError):
                bpos = apos = -1
        # Model A's multiplier is kept alongside Model B's because the
        # re-pricing self-check below has to reproduce RAPTOR's own arithmetic
        # exactly, and RAPTOR prices per pattern. That check is what caught a
        # truncated-reconstruction bug once; weakening it to accommodate the
        # correction would trade a real integrity guarantee for convenience.
        mult_a = _headway_multiplier(
            rn, l.pattern_id, l.route_id,
            rn.pattern_direction[pi] if pi >= 0 else 0, period)
        mult_b = mult_a
        if common_lines == "same_route" and pi >= 0 and 0 <= bpos < apos:
            mult_b = common_lines_multiplier(rn, pi, bpos, apos, period,
                                             cl_cache)
        out.append(("ride", idx, float(l.in_vehicle_min), 0.0,
                    True, not first_ride, pi, bpos, apos, mult_a, mult_b))
        first_ride = False
    return out if any(l[0] == "ride" for l in out) else None


def _flatten(found, o_sorted, d_sorted, f_sorted, walk_only, rp_keys, period):
    leg_path, leg_rp, leg_ivt, leg_walk = [], [], [], []
    leg_board, leg_xfer = [], []
    leg_pat, leg_bp, leg_ap, leg_mult = [], [], [], []
    path_od, path_offsets = [], [0]
    od_offsets = np.zeros(len(o_sorted) + 1, dtype=np.int64)

    pid = 0
    for oi in range(len(o_sorted)):
        for legs in found[oi].values():
            for kind, rp, ivt, walk, board, xfer, pat, bp, ap, mult in legs:
                leg_path.append(pid)
                leg_rp.append(rp)
                leg_ivt.append(ivt)
                leg_walk.append(walk)
                leg_board.append(board)
                leg_xfer.append(xfer)
                leg_pat.append(pat)
                leg_bp.append(bp)
                leg_ap.append(ap)
                leg_mult.append(mult)
            path_od.append(oi)
            path_offsets.append(len(leg_path))
            pid += 1
        od_offsets[oi + 1] = pid

    ps = PathSet(
        period=period, n_od=len(o_sorted),
        leg_path=np.asarray(leg_path, dtype=np.int64),
        leg_rp=np.asarray(leg_rp, dtype=np.int64),
        leg_ivt=np.asarray(leg_ivt, float),
        leg_walk=np.asarray(leg_walk, float),
        leg_is_boarding=np.asarray(leg_board, bool),
        leg_is_transfer=np.asarray(leg_xfer, bool),
        leg_pattern=np.asarray(leg_pat, dtype=np.int64),
        leg_board_pos=np.asarray(leg_bp, dtype=np.int64),
        leg_alight_pos=np.asarray(leg_ap, dtype=np.int64),
        leg_headway_mult=np.asarray(leg_mult, float),
        path_od=np.asarray(path_od, dtype=np.int64),
        path_offsets=np.asarray(path_offsets, dtype=np.int64),
        od_offsets=od_offsets,
        od_flow=np.asarray(f_sorted, float),
        od_walk_only=walk_only,
        od_origin=np.asarray(o_sorted, dtype=np.int64),
        od_dest=np.asarray(d_sorted, dtype=np.int64),
        rp_keys=list(rp_keys))
    n_with = int((np.diff(od_offsets) > 0).sum())
    log.info("path set: %d paths over %d/%d OD pairs (%.1f%% of flow served), "
             "%d legs", ps.n_paths, n_with, ps.n_od,
             100 * ps.od_flow[np.diff(od_offsets) > 0].sum() / max(ps.od_flow.sum(), 1e-9),
             ps.n_legs)
    return ps


class PathSetEvaluator:
    """Prices a whole path set under any headway vector, vectorized."""

    def __init__(self, ps: PathSet, w: CostWeights, wait_kwargs: dict,
                 unserved_penalty_min: float,
                 retention_full_min: float = 60.0,
                 retention_zero_min: float = 210.0,
                 retention_floor: float = 0.10):
        self.ps = ps
        self.w = w
        self.t = float(wait_kwargs.get("random_arrival_threshold_min", 12.0))
        self.c = float(wait_kwargs.get("schedule_coefficient", 0.25))
        self.unserved_penalty = float(unserved_penalty_min)
        self.ret_full = float(retention_full_min)
        self.ret_zero = float(retention_zero_min)
        self.ret_floor = float(retention_floor)
        # constant part of every leg: walk + in-vehicle + transfer penalty
        self.leg_const = (w.walking * ps.leg_walk
                          + w.in_vehicle * ps.leg_ivt
                          + w.transfer_penalty * ps.leg_is_transfer)
        self.path_const = np.add.reduceat(
            self.leg_const, ps.path_offsets[:-1]) if ps.n_paths else np.zeros(0)
        self.ride_mask = ps.leg_rp >= 0
        self.ride_rp = ps.leg_rp[self.ride_mask]
        self.ride_path = ps.leg_path[self.ride_mask]
        self.ride_is_xfer = ps.leg_is_transfer[self.ride_mask]
        self.ride_mult = (ps.leg_headway_mult[self.ride_mask]
                          if ps.leg_headway_mult is not None
                          else np.ones(self.ride_mask.sum()))
        self.has_path = np.diff(ps.od_offsets) > 0
        self.total_flow = float(ps.od_flow.sum())
        # group structure, precomputed: OD pairs that own at least one path
        self._oi = np.flatnonzero(self.has_path)
        self._starts = ps.od_offsets[:-1][self.has_path]
        self._group_sizes = np.diff(ps.od_offsets)[self.has_path]
        self._path_index = np.arange(ps.n_paths, dtype=np.int64)

    def _wait(self, h: np.ndarray) -> np.ndarray:
        return np.where(h <= self.t, h / 2.0, self.t / 2.0 + self.c * (h - self.t))

    def od_costs(self, headways: np.ndarray) -> np.ndarray:
        """Least generalized cost per OD pair (inf where no path is usable)."""
        ps = self.ps
        if ps.n_paths == 0:
            return np.full(ps.n_od, np.inf)
        # each ride waits on its own pattern's frequency, not the route's
        wait = self._wait(headways[self.ride_rp] * self.ride_mult)
        # first boarding pays the waiting weight; later boardings the transfer-wait weight
        wcost = np.where(self.ride_is_xfer,
                         self.w.transfer_wait * wait,
                         self.w.waiting * wait)
        path_wait = np.bincount(self.ride_path, weights=wcost,
                                minlength=ps.n_paths)
        path_cost = self.path_const + path_wait
        od = np.full(ps.n_od, np.inf)
        if len(self._starts):
            od[self.has_path] = np.minimum.reduceat(path_cost, self._starts)
        return np.minimum(od, ps.od_walk_only)

    @property
    def retention_curve(self) -> "Retention":
        from .retention import Retention
        return Retention(self.ret_full, self.ret_zero, self.ret_floor)

    def retention(self, cost: np.ndarray) -> np.ndarray:
        """Share of an OD's travellers who still make the trip at this cost.

        Delegates to :mod:`cota_opt.retention` so the screening tier and the
        production evaluator cannot drift apart again.
        """
        return self.retention_curve.keep(cost)

    def path_flows(self, headways: np.ndarray,
                   path_cost: np.ndarray | None = None) -> np.ndarray:
        """Demand assigned to each path (all-or-nothing onto the cheapest one).

        Paths are stored grouped by OD, so the cheapest path per group is found
        with two ``reduceat`` passes rather than a full lexsort: one for the
        group minimum, one for the first path index attaining it. That matters
        because this runs inside the optimizer's inner loop.
        """
        ps = self.ps
        if ps.n_paths == 0:
            return np.zeros(0)
        if path_cost is None:
            path_cost = self.path_costs(headways)
        starts = self._starts
        gmin = np.minimum.reduceat(path_cost, starts)
        # index of the first path in each group that attains the group minimum
        attains = path_cost <= np.repeat(gmin, self._group_sizes) + 1e-12
        keyed = np.where(attains, self._path_index, np.iinfo(np.int64).max)
        chosen = np.minimum.reduceat(keyed, starts)

        oi = self._oi
        c = np.minimum(gmin, ps.od_walk_only[oi])
        keep = np.where(np.isfinite(c), self.retention(np.nan_to_num(c)), 0.0)
        out = np.zeros(ps.n_paths)
        # exactly one path is chosen per OD group, so the indices are unique and
        # a plain scatter is correct — np.add.at is unbuffered and far slower
        out[chosen] = ps.od_flow[oi] * keep
        return out

    def path_costs(self, headways: np.ndarray) -> np.ndarray:
        ps = self.ps
        if ps.n_paths == 0:
            return np.zeros(0)
        wait = self._wait(headways[self.ride_rp] * self.ride_mult)
        wcost = np.where(self.ride_is_xfer,
                         self.w.transfer_wait * wait,
                         self.w.waiting * wait)
        return self.path_const + np.bincount(self.ride_path, weights=wcost,
                                             minlength=ps.n_paths)

    def boardings_by_rp(self, headways: np.ndarray, path_flow=None) -> np.ndarray:
        """Passengers boarding each route-period under the current plan."""
        ps = self.ps
        pf = self.path_flows(headways) if path_flow is None else path_flow
        ride = ps.leg_rp >= 0
        return np.bincount(ps.leg_rp[ride], weights=pf[ps.leg_path[ride]],
                           minlength=len(ps.rp_keys))

    def evaluate(self, headways: np.ndarray) -> dict:
        """Flow-weighted generalized cost and unserved demand for a plan.

        Unserved demand has two distinct parts, reported separately:
        *structural* — the network offers no path at all within the round limit,
        which no frequency plan can fix; and *discouraged* — a path exists but
        its generalized cost is high enough that some travellers do not make the
        trip. Only the second responds to frequency.
        """
        ps = self.ps
        c = self.od_costs(headways)
        reachable = np.isfinite(c)
        flow = ps.od_flow
        structural = float(flow[~reachable].sum())

        keep = np.zeros_like(flow)
        keep[reachable] = self.retention(c[reachable])
        served = flow * keep
        discouraged = float(flow[reachable].sum() - served.sum())
        total_unserved = structural + discouraged
        gc = float((served[reachable] * c[reachable]).sum())
        flow_served = float(served.sum())
        return {
            "generalized_cost": gc + self.unserved_penalty * total_unserved,
            "generalized_cost_served_only": gc,
            "unserved_demand": total_unserved,
            "unserved_structural": structural,
            "unserved_discouraged": discouraged,
            "served_demand": flow_served,
            "mean_cost_per_served_trip": gc / flow_served if flow_served else np.inf,
        }
