"""How much does "board whichever bus comes first" actually matter here?

The assignment model puts each traveller on one chosen pattern and charges them
that pattern's wait. Real riders standing where two acceptable lines serve the
same trip board whichever arrives first, and wait on the *combined* frequency:
two 20-minute routes on a shared corridor feel like a 10-minute route. Ignoring
that overstates waiting, and it overstates it most exactly where a network has
overlapping trunk service.

Building a proper optimal-strategy assignment is a large piece of work, so the
first question is whether it would change anything. This module answers that
with an upper bound rather than a model: for every ride leg on every chosen
path, find the alternative patterns that would carry the same traveller from
the same boarding stop to the same alighting stop at a comparable in-vehicle
time, and re-price the wait on the combined headway of that whole attractive
set.

It is an upper bound in three ways, all of which push the same direction:

* every attractive line is assumed perfectly interchangeable, so no rider ever
  declines the first bus because the other is faster downstream;
* arrivals are assumed random and independent, which is the most favourable
  case for combined frequency;
* nothing is charged for the reliability cost of a rider planning around two
  timetables instead of one.

So if the bound is small, the omission is genuinely small. If the bound is
large, it does not prove the effect is large -- it proves the question has to
be settled properly before any strong claim rests on the current waits.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .cost import CostWeights
from .pathset import PathSet, PathSetEvaluator
from .raptor import RaptorNetwork

log = logging.getLogger(__name__)


@dataclass
class HyperpathBound:
    per_leg: pd.DataFrame
    summary: dict[str, Any]
    by_route: pd.DataFrame
    verdict: str
    explanation: str


def _alternatives(rn: RaptorNetwork, pat: int, bpos: int, apos: int,
                  ivt_tolerance: float) -> list[tuple[int, float]]:
    """Patterns carrying the same stop-to-stop movement at comparable speed.

    Returns ``(pattern index, in-vehicle seconds)`` including the chosen
    pattern itself, so the caller can combine frequencies over the whole
    attractive set.
    """
    off = rn.pat_offsets
    b_stop = int(rn.pat_stops[off[pat] + bpos])
    a_stop = int(rn.pat_stops[off[pat] + apos])
    own_ivt = float(rn.pat_cumsec[off[pat] + apos] - rn.pat_cumsec[off[pat] + bpos])
    if own_ivt <= 0:
        return []

    out = [(pat, own_ivt)]
    s0, s1 = rn.stop_pat_offsets[b_stop], rn.stop_pat_offsets[b_stop + 1]
    for k in range(s0, s1):
        q = int(rn.stop_pat_idx[k])
        if q == pat:
            continue
        qb = int(rn.stop_pat_pos[k])
        qa, qb_end = off[q], off[q + 1]
        # does q reach the alighting stop after the boarding stop?
        seq = rn.pat_stops[qa + qb + 1:qb_end]
        hit = np.flatnonzero(seq == a_stop)
        if len(hit) == 0:
            continue
        qapos = qb + 1 + int(hit[0])
        q_ivt = float(rn.pat_cumsec[qa + qapos] - rn.pat_cumsec[qa + qb])
        if 0 < q_ivt <= own_ivt * ivt_tolerance:
            out.append((q, q_ivt))
    return out


def _wait(h: np.ndarray | float, t: float, c: float):
    return np.where(h <= t, h / 2.0, t / 2.0 + c * (h - t))


def bound(ps: PathSet, ev: PathSetEvaluator, rn: RaptorNetwork,
          headways: dict[tuple[str, str], float], period: str,
          weights: CostWeights, wait_kwargs: dict,
          ivt_tolerance: float = 1.25,
          max_legs: int = 200_000) -> pd.DataFrame:
    """Per-leg wait saving if riders boarded the first acceptable bus."""
    from .attribution import best_paths

    if ps.leg_pattern is None or ps.leg_board_pos is None:
        raise ValueError("path set carries no ride geometry; rebuild it")

    h = np.array([headways[k] for k in ps.rp_keys])
    idx, _ = best_paths(ev, h)
    chosen = idx[idx >= 0]
    if len(chosen) == 0:
        return pd.DataFrame()

    t = float(wait_kwargs.get("random_arrival_threshold_min", 12.0))
    c = float(wait_kwargs.get("schedule_coefficient", 0.25))
    # headway seen by a pattern, not by its route: a route running three
    # patterns does not give any one of them the route's frequency
    rp_of_key = {k: i for i, k in enumerate(ps.rp_keys)}
    pat_h = np.full(rn.n_patterns, np.inf)
    for p in range(rn.n_patterns):
        key = (rn.pattern_route[p], period)
        i = rp_of_key.get(key)
        if i is None:
            continue
        n_pat = rn.pattern_trips_period.get((rn.pattern_ids[p], period), 0)
        n_dir = rn.direction_trips_period.get(
            (rn.pattern_route[p], rn.pattern_direction[p], period), 0)
        mult = float(n_dir) / float(n_pat) if n_pat > 0 and n_dir > 0 else 1.0
        pat_h[p] = h[i] * mult

    rows = []
    seen = 0
    for oi, p in zip(np.flatnonzero(idx >= 0), chosen):
        a, b = ps.path_offsets[p], ps.path_offsets[p + 1]
        flow = float(ps.od_flow[oi])
        for li in range(a, b):
            if ps.leg_rp[li] < 0 or ps.leg_pattern[li] < 0:
                continue
            seen += 1
            if seen > max_legs:
                break
            pat = int(ps.leg_pattern[li])
            bpos, apos = int(ps.leg_board_pos[li]), int(ps.leg_alight_pos[li])
            if bpos < 0 or apos <= bpos:
                continue
            alts = _alternatives(rn, pat, bpos, apos, ivt_tolerance)
            if len(alts) <= 1:
                continue
            ok = [(q, iv) for q, iv in alts
                  if np.isfinite(pat_h[q]) and pat_h[q] > 0]
            if len(ok) <= 1:
                continue
            hs = np.array([pat_h[q] for q, _ in ok])
            own_route = rn.pattern_route[pat]
            n_same_route = sum(1 for q, _ in ok
                               if rn.pattern_route[q] == own_route)
            # Same-route alternatives are a different problem from hyperpaths:
            # a rider at a stop served by four patterns of route 10 is already
            # choosing among one route's departures, and charging them one
            # pattern's headway is a pattern-aggregation error the current
            # model could fix cheaply. Cross-route alternatives are the actual
            # optimal-strategy question. They are counted separately because
            # the fixes are different and so are the costs.
            hs_cross = np.array([pat_h[q] for q, _ in ok
                                 if rn.pattern_route[q] != own_route
                                 or q == pat])
            combined = 1.0 / np.sum(1.0 / hs)
            combined_cross = (1.0 / np.sum(1.0 / hs_cross)
                              if len(hs_cross) else pat_h[pat])
            w_now = float(_wait(pat_h[pat], t, c))
            w_hyp = float(_wait(combined, t, c))
            w_cross = float(_wait(combined_cross, t, c))
            if w_hyp >= w_now - 1e-9:
                continue
            wt = (weights.transfer_wait if ps.leg_is_transfer[li]
                  else weights.waiting)
            rows.append({
                "period": period,
                "od_index": int(oi),
                "flow": flow,
                "route": ps.rp_keys[int(ps.leg_rp[li])][0],
                "n_attractive_lines": int(len(hs)),
                "n_same_route_patterns": int(n_same_route),
                "n_other_routes": int(len({rn.pattern_route[q] for q, _ in ok})
                                      - 1),
                "own_headway_min": float(pat_h[pat]),
                "combined_headway_min": float(combined),
                "wait_now_min": w_now,
                "wait_hyperpath_min": w_hyp,
                "saving_min": (w_now - w_hyp) * wt,
                "flow_weighted_saving": (w_now - w_hyp) * wt * flow,
                "saving_cross_route_only_min": (w_now - w_cross) * wt,
                "flow_weighted_saving_cross_route": (w_now - w_cross) * wt * flow,
            })
        if seen > max_legs:
            log.warning("hyperpath bound truncated at %d legs", max_legs)
            break
    return pd.DataFrame(rows)


def summarize(per_leg: pd.DataFrame, baseline_gc: float,
              exp1_effect_pct: float = 2.0) -> HyperpathBound:
    """Classify the omission against the size of the effect being claimed."""
    if per_leg.empty:
        return HyperpathBound(
            per_leg, {"n_legs_with_alternatives": 0,
                      "bound_share_of_generalized_cost_pct": 0.0},
            pd.DataFrame(), "negligible",
            "no chosen ride leg has an alternative line carrying the same "
            "movement at comparable speed")

    total = float(per_leg["flow_weighted_saving"].sum())
    share = 100.0 * total / baseline_gc if baseline_gc else np.nan
    cross = float(per_leg.get("flow_weighted_saving_cross_route",
                              pd.Series(dtype=float)).sum())
    cross_share = 100.0 * cross / baseline_gc if baseline_gc else np.nan
    summary = {
        "n_legs_with_alternatives": int(len(per_leg)),
        "flow_touched": float(per_leg["flow"].sum()),
        "total_bound_min": total,
        "bound_share_of_generalized_cost_pct": share,
        "median_saving_min": float(per_leg["saving_min"].median()),
        "p95_saving_min": float(per_leg["saving_min"].quantile(0.95)),
        "median_lines_available": float(per_leg["n_attractive_lines"].median()),
        # the split that decides which problem this actually is
        "cross_route_bound_min": cross,
        "cross_route_share_of_generalized_cost_pct": cross_share,
        "same_route_pattern_share_of_bound_pct":
            100.0 * (1 - cross / total) if total else np.nan,
        "legs_whose_alternatives_are_all_same_route": int(
            (per_leg.get("n_other_routes", pd.Series(dtype=int)) == 0).sum()),
        "exp1_effect_pct_compared_against": exp1_effect_pct,
    }
    by_route = (per_leg.groupby("route")
                .agg(n_legs=("od_index", "size"),
                     flow=("flow", "sum"),
                     bound_min=("flow_weighted_saving", "sum"),
                     median_lines=("n_attractive_lines", "median"))
                .reset_index().sort_values("bound_min", ascending=False))
    by_route["share_of_bound"] = by_route["bound_min"] / total if total else np.nan

    share = cross_share if np.isfinite(cross_share) else share
    if share < 0.25 * exp1_effect_pct:
        v = "negligible"
        why = (f"the whole upper bound is {share:.2f}% of generalized cost, "
               f"under a quarter of the {exp1_effect_pct:.1f}% effect being "
               "claimed; single-line waiting cannot be carrying the result")
    elif share < exp1_effect_pct:
        v = "locally_meaningful"
        why = (f"the bound is {share:.2f}% of generalized cost against a "
               f"{exp1_effect_pct:.1f}% claimed effect: too small to overturn "
               "the direction, large enough to matter for corridor-level "
               "numbers on the routes listed")
    else:
        v = "potentially_frontier_changing"
        why = (f"the bound is {share:.2f}% of generalized cost, at or above "
               f"the {exp1_effect_pct:.1f}% effect being claimed; proper "
               "optimal-strategy assignment is required before any strong "
               "claim rests on these waits")
    return HyperpathBound(per_leg, summary, by_route, v, why)
