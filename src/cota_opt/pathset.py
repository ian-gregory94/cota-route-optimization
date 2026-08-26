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
from .raptor import RaptorNetwork, generalized_cost, pattern_headways, reconstruct

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

    @property
    def n_paths(self) -> int:
        return len(self.path_od)

    @property
    def n_legs(self) -> int:
        return len(self.leg_path)


def _plan_scenarios(rp_keys, baseline: dict, rng, n_random: int = 3,
                    ladder=(5, 10, 15, 20, 30, 45, 60)):
    """Diverse headway vectors used only to widen the candidate path set."""
    scen = [("baseline", dict(baseline))]
    scen.append(("frequent", {k: min(baseline[k], 10.0) for k in rp_keys}))
    scen.append(("infrequent", {k: max(baseline[k], 45.0) for k in rp_keys}))
    for i in range(n_random):
        scen.append((f"random{i}",
                     {k: float(rng.choice(ladder)) for k in rp_keys}))
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
) -> PathSet:
    """Enumerate candidate paths for every OD pair in ``od``."""
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

    scenarios = _plan_scenarios(rp_keys, baseline_headways, rng, n_random_scenarios)
    origins = np.unique(o_sorted)
    log.info("path enumeration: %d OD pairs, %d origin zones, %d scenarios",
             n_od, len(origins), len(scenarios))

    dest_by_origin: dict[int, np.ndarray] = {}
    starts = np.searchsorted(o_sorted, origins, side="left")
    ends = np.searchsorted(o_sorted, origins, side="right")
    for z, a, b in zip(origins, starts, ends):
        dest_by_origin[int(z)] = np.arange(a, b)

    for sname, hw in scenarios:
        ph = pattern_headways(rn, hw, period)
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
                legs = _legs_from_journey(j, route_of_pat, rn, rp_index, period)
                if legs is None:
                    continue
                # access and egress walking attach to the ends
                access_walk = float(a_walk[list(a_stops).index(
                    rn.stop_index[j.legs[0].from_stop])]) \
                    if rn.stop_index[j.legs[0].from_stop] in list(a_stops) else 0.0
                legs = ([("walk", -1, 0.0, access_walk, False, False)] if access_walk else []) \
                    + legs \
                    + ([("walk", -1, 0.0, float(e_walk[k]), False, False)]
                       if e_walk[k] > 0 else [])
                sig = tuple((l[0], l[1], round(l[2], 3), round(l[3], 3)) for l in legs)
                if len(found[oi]) < max_paths_per_od or sig in found[oi]:
                    found[oi][sig] = legs

    # walk-only fallback where origin and destination share an access stop
    for oi in range(n_od):
        oz, dz = int(o_sorted[oi]), int(d_sorted[oi])
        if oz == dz:
            walk_only[oi] = 0.0

    return _flatten(found, o_sorted, d_sorted, f_sorted, walk_only,
                    rp_keys, period)


def _legs_from_journey(j, route_of_pat, rn, rp_index, period):
    """Journey -> leg tuples, or None if any ride leg has no priceable headway."""
    out = []
    first_ride = True
    for l in j.legs:
        if l.kind == "walk":
            out.append(("walk", -1, 0.0, float(l.walk_min), False, False))
            continue
        key = (l.route_id, period)
        idx = rp_index.get(key)
        if idx is None:
            return None
        out.append(("ride", idx, float(l.in_vehicle_min), 0.0,
                    True, not first_ride))
        first_ride = False
    return out if any(l[0] == "ride" for l in out) else None


def _flatten(found, o_sorted, d_sorted, f_sorted, walk_only, rp_keys, period):
    leg_path, leg_rp, leg_ivt, leg_walk = [], [], [], []
    leg_board, leg_xfer = [], []
    path_od, path_offsets = [], [0]
    od_offsets = np.zeros(len(o_sorted) + 1, dtype=np.int64)

    pid = 0
    for oi in range(len(o_sorted)):
        for legs in found[oi].values():
            for kind, rp, ivt, walk, board, xfer in legs:
                leg_path.append(pid)
                leg_rp.append(rp)
                leg_ivt.append(ivt)
                leg_walk.append(walk)
                leg_board.append(board)
                leg_xfer.append(xfer)
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
        path_od=np.asarray(path_od, dtype=np.int64),
        path_offsets=np.asarray(path_offsets, dtype=np.int64),
        od_offsets=od_offsets,
        od_flow=np.asarray(f_sorted, float),
        od_walk_only=walk_only,
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
        self.has_path = np.diff(ps.od_offsets) > 0
        self.total_flow = float(ps.od_flow.sum())

    def _wait(self, h: np.ndarray) -> np.ndarray:
        return np.where(h <= self.t, h / 2.0, self.t / 2.0 + self.c * (h - self.t))

    def od_costs(self, headways: np.ndarray) -> np.ndarray:
        """Least generalized cost per OD pair (inf where no path is usable)."""
        ps = self.ps
        if ps.n_paths == 0:
            return np.full(ps.n_od, np.inf)
        wait = self._wait(headways)
        # first boarding pays the waiting weight; later boardings the transfer-wait weight
        wcost = np.where(self.ride_is_xfer,
                         self.w.transfer_wait * wait[self.ride_rp],
                         self.w.waiting * wait[self.ride_rp])
        path_wait = np.bincount(self.ride_path, weights=wcost,
                                minlength=ps.n_paths)
        path_cost = self.path_const + path_wait
        od = np.full(ps.n_od, np.inf)
        idx = ps.od_offsets[:-1][self.has_path]
        od[self.has_path] = np.minimum.reduceat(path_cost, idx)[
            np.arange(len(idx))] if len(idx) else np.zeros(0)
        return np.minimum(od, ps.od_walk_only)

    def retention(self, cost: np.ndarray) -> np.ndarray:
        """Share of an OD's travellers who still make the trip at this cost."""
        frac = np.clip((cost - self.ret_full) / (self.ret_zero - self.ret_full),
                       0.0, 1.0)
        return 1.0 - frac * (1.0 - self.ret_floor)

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
