"""Crowding that binds where crowding actually binds: the peak load point.

Experiment 1 applied crowding to a route's *average* passengers per trip. On a
radial bus route the busiest segment typically carries several times the route
average, so an average-based test never triggers and nothing pushes back on
cutting a trunk route. With path-based assignment the real link loads are
recoverable: every assigned trip rides a known span of a known pattern, so
segment volumes can be accumulated and the maximum taken.

Doing that inside the optimizer would be costly, but it is not necessary. Route
geometry and the candidate path structure are both fixed, so the *shape* of a
route's load profile is fixed too. What changes with frequency is how many
people ride it. So the peak-load factor

    peak_load_factor = (volume on the busiest segment) / (boardings)

is computed once from the baseline assignment and held constant, and only the
boarding count is recomputed per evaluation. The factor is derived from data,
not assumed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from .pathset import PathSet
from .raptor import RaptorNetwork

log = logging.getLogger(__name__)


@dataclass
class LoadProfile:
    """Per-route-period boarding volumes and peak-load factors."""

    rp_keys: list[tuple[str, str]]
    boardings: np.ndarray          # passengers boarding, baseline assignment
    peak_volume: np.ndarray        # volume on the busiest segment
    peak_load_factor: np.ndarray   # peak_volume / boardings, 1.0 where unknown

    def as_dict(self) -> dict[tuple[str, str], dict]:
        return {k: {"boardings": float(self.boardings[i]),
                    "peak_volume": float(self.peak_volume[i]),
                    "peak_load_factor": float(self.peak_load_factor[i])}
                for i, k in enumerate(self.rp_keys)}


def segment_loads(ps: PathSet, rn: RaptorNetwork, path_flow: np.ndarray
                  ) -> tuple[np.ndarray, np.ndarray]:
    """Accumulate passenger volume on every pattern segment.

    ``path_flow`` is the demand assigned to each path. Returns
    ``(segment_volume, boardings_by_rp)`` where segment volume is indexed by the
    flat pattern-stop array (one entry per segment, i.e. per stop except the
    last of each pattern).
    """
    if ps.leg_pattern is None:
        raise ValueError("path set carries no ride-leg geometry")
    n_slots = int(rn.pat_offsets[-1])
    vol = np.zeros(n_slots)
    ride = (ps.leg_rp >= 0) & (ps.leg_pattern >= 0) & (ps.leg_board_pos >= 0)
    flows = path_flow[ps.leg_path[ride]]
    pats = ps.leg_pattern[ride]
    bp = ps.leg_board_pos[ride]
    ap = ps.leg_alight_pos[ride]
    base = rn.pat_offsets[pats]
    # a ride occupies segments [board, alight) of its pattern; a difference
    # array turns each span into two point updates instead of a loop
    diff = np.zeros(n_slots + 1)
    np.add.at(diff, base + bp, flows)
    np.add.at(diff, base + ap, -flows)
    vol = np.cumsum(diff)[:n_slots]

    boardings = np.bincount(ps.leg_rp[ride], weights=flows,
                            minlength=len(ps.rp_keys))
    return vol, boardings


def build_load_profile(ps: PathSet, rn: RaptorNetwork, path_flow: np.ndarray,
                       ) -> LoadProfile:
    """Peak-load factor per route-period from a baseline assignment."""
    vol, boardings = segment_loads(ps, rn, path_flow)
    n_rp = len(ps.rp_keys)
    peak = np.zeros(n_rp)
    # map each pattern slot to its route-period via the ride legs that use it
    ride = (ps.leg_rp >= 0) & (ps.leg_pattern >= 0)
    pat_rp: dict[int, int] = {}
    for pi, rp in zip(ps.leg_pattern[ride], ps.leg_rp[ride]):
        pat_rp.setdefault(int(pi), int(rp))
    for pi, rp in pat_rp.items():
        a, b = int(rn.pat_offsets[pi]), int(rn.pat_offsets[pi + 1])
        if b > a:
            peak[rp] = max(peak[rp], float(vol[a:b - 1].max()) if b - 1 > a else 0.0)
    factor = np.ones(n_rp)
    ok = boardings > 1e-9
    factor[ok] = np.maximum(peak[ok] / boardings[ok], 1e-6)
    log.info("load profile: %d route-periods, peak-load factor median %.2f, "
             "p90 %.2f", int(ok.sum()),
             float(np.median(factor[ok])) if ok.any() else 0.0,
             float(np.percentile(factor[ok], 90)) if ok.any() else 0.0)
    return LoadProfile(list(ps.rp_keys), boardings, peak, factor)


class CrowdingModel:
    """Prices crowding at each route-period's peak load point."""

    def __init__(self, profile: LoadProfile, capacity: float, penalty: float,
                 trips_at_baseline: np.ndarray, ivt_per_rp: np.ndarray):
        self.profile = profile
        self.capacity = float(capacity)
        self.penalty = float(penalty)
        self.trips_baseline = trips_at_baseline
        self.ivt = ivt_per_rp

    def excess_cost(self, boardings: np.ndarray, trips: np.ndarray) -> np.ndarray:
        """Generalized-cost penalty per route-period, in weighted minutes.

        Passengers on an over-capacity segment pay a penalty proportional to the
        excess load factor, applied to the in-vehicle time they spend on it.
        """
        peak_volume = boardings * self.profile.peak_load_factor
        with np.errstate(divide="ignore", invalid="ignore"):
            per_trip = np.where(trips > 0, peak_volume / trips, 0.0)
        load = per_trip / self.capacity
        excess = np.maximum(load - 1.0, 0.0)
        return self.penalty * excess * self.ivt * boardings
