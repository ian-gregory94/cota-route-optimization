"""Can the corrected model find the paths the correction makes attractive?

Model B fixes how a ride leg's waiting time is priced. It does not change how
paths are *found*: RAPTOR still searches with per-pattern headways, which is
Model A's valuation. So a route sequence can be genuinely cheap under Model B
while RAPTOR, searching under Model A, never had reason to explore it — and the
candidate set would be missing a path the model itself would want to use.

This is a different failure from the one the fixpoint fixes. The fixpoint asks
whether the candidate set contains the paths that new *headway scenarios* make
attractive. This asks whether it contains the paths the corrected *valuation*
makes attractive. A set can pass one and fail the other.

The test is exact rather than heuristic, in two steps.

**Bound.** Re-run RAPTOR with *route-level* headways: every pattern priced at
its route's whole frequency, as if all of it served every movement. A Model B
multiplier is ``1 / sum_q(n_trips(q)/n_dir_trips(q))`` over patterns that
qualify, and the qualifying set is a subset of the direction, so the multiplier
is at least 1 and route-level pricing is a **lower bound** on any Model B path
cost. Where that bound does not beat the candidate set, no omission is possible
and the pair is cleared outright — no reconstruction needed.

**Confirm.** Where the bound does beat it, reconstruct the bound-optimal
journey and price it *exactly* under Model B. That converts "might be omitted"
into "is omitted, by this much, on this route sequence".

The bound is loose by construction, so it over-selects suspects and never
misses one. The confirmation step is what produces the number.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .cost import CostWeights, expected_wait_min
from .pathset import PathSet, PathSetEvaluator, common_lines_multiplier
from .raptor import (RaptorNetwork, generalized_cost, reconstruct,
                     route_level_headways as _route_level)

log = logging.getLogger(__name__)


def route_level_headways(rn: RaptorNetwork, headway_by_route_period: dict,
                         period: str, fallback: float = np.inf) -> np.ndarray:
    """Every pattern at its route's full frequency -- the optimistic bound.

    Re-exported from :mod:`cota_opt.raptor` so this diagnostic and the path
    enumeration that answers it cannot drift apart.
    """
    return _route_level(rn, headway_by_route_period, period, fallback)


def price_journey_model_b(j, rn: RaptorNetwork, headways: dict, period: str,
                          w: CostWeights, wait_kwargs: dict,
                          access_walk_min: float, egress_walk_min: float,
                          cl_cache: dict | None = None
                          ) -> tuple[float, tuple[str, ...], int] | None:
    """Exact Model B cost of a reconstructed journey, plus its route sequence."""
    pid_index = {p: i for i, p in enumerate(rn.pattern_ids)}
    total = w.walking * (access_walk_min + egress_walk_min)
    routes: list[str] = []
    boardings = 0
    for leg in j.legs:
        if leg.kind == "walk":
            total += w.walking * float(leg.walk_min)
            continue
        h_route = headways.get((leg.route_id, period))
        if h_route is None or not np.isfinite(h_route):
            return None
        pi = pid_index.get(leg.pattern_id, -1)
        if pi < 0:
            return None
        a, b = rn.pat_offsets[pi], rn.pat_offsets[pi + 1]
        stops = list(rn.pat_stops[a:b])
        try:
            bpos = stops.index(rn.stop_index[leg.from_stop])
            apos = stops.index(rn.stop_index[leg.to_stop], bpos + 1)
        except (ValueError, KeyError):
            return None
        mult = common_lines_multiplier(rn, pi, bpos, apos, period, cl_cache)
        ew = expected_wait_min(h_route * mult, **wait_kwargs)
        is_xfer = boardings > 0
        total += w.in_vehicle * float(leg.in_vehicle_min)
        total += (w.transfer_wait * ew + w.transfer_penalty) if is_xfer \
            else w.waiting * ew
        routes.append(leg.route_id)
        boardings += 1
    if not routes:
        return None
    return total, tuple(routes), boardings


def _route_sequences_in_set(ps: PathSet, oi: int) -> set[tuple[str, ...]]:
    out = set()
    for p in range(ps.od_offsets[oi], ps.od_offsets[oi + 1]):
        a, b = ps.path_offsets[p], ps.path_offsets[p + 1]
        rp = ps.leg_rp[a:b]
        out.add(tuple(ps.rp_keys[int(k)][0] for k in rp[rp >= 0]))
    return out


@dataclass
class DiscoveryResult:
    rows: pd.DataFrame
    summary: dict[str, Any]
    by_route: pd.DataFrame
    case: str
    explanation: str


def probe(rn: RaptorNetwork, zs, ps: PathSet, ev: PathSetEvaluator,
          headways: dict[tuple[str, str], float], period: str,
          w: CostWeights, wait_kwargs: dict, max_rounds: int,
          od_indices: np.ndarray,
          min_gain_min: float = 1.0,
          min_gain_frac: float = 0.01) -> pd.DataFrame:
    """Test the given OD indices for route sequences Model B would prefer."""
    sub = np.array([headways[k] for k in ps.rp_keys])
    cached = ev.od_costs(sub)
    ph_bound = route_level_headways(rn, headways, period)
    cl_cache: dict = {}

    order = np.argsort(ps.od_origin[od_indices])
    tested = od_indices[order]
    rows = []
    origins = np.unique(ps.od_origin[tested])
    for z in origins:
        a_stops, a_walk = zs.access_of(int(z))
        if len(a_stops) == 0:
            continue
        src = [rn.stop_ids[s] for s in a_stops]
        init = [w.walking * float(x) for x in a_walk]
        cost, rounds, par = generalized_cost(
            rn, src, ph_bound, w, wait_kwargs, max_rounds=max_rounds,
            source_costs=init, trace=True)
        src_set = set(src)
        walk_of = {s: float(x) for s, x in zip(a_stops, a_walk)}

        for oi in tested[ps.od_origin[tested] == z]:
            oi = int(oi)
            e_stops, e_walk = zs.access_of(int(ps.od_dest[oi]))
            if len(e_stops) == 0:
                continue
            tot = cost[e_stops] + w.walking * e_walk
            k = int(np.argmin(tot))
            bound = float(tot[k])
            best = float(cached[oi])
            # the bound cannot beat the set, so nothing can: cleared exactly
            if not np.isfinite(bound) or bound >= best - 1e-9:
                continue
            j = reconstruct(rn, par, rn.stop_ids[e_stops[k]],
                            int(rounds[e_stops[k]]), src_set)
            if j is None:
                continue
            first = rn.stop_index.get(j.legs[0].from_stop, -1)
            priced = price_journey_model_b(
                j, rn, headways, period, w, wait_kwargs,
                walk_of.get(first, 0.0), float(e_walk[k]), cl_cache)
            if priced is None:
                continue
            exact, seq, boardings = priced
            gain = best - exact
            if gain < min_gain_min or gain < min_gain_frac * best:
                continue
            rows.append({
                "period": period,
                "od_index": oi,
                "origin_zone": int(ps.od_origin[oi]),
                "dest_zone": int(ps.od_dest[oi]),
                "flow": float(ps.od_flow[oi]),
                "best_in_set_min": best,
                "bound_min": bound,
                "omitted_path_min": exact,
                "improvement_min": gain,
                "improvement_pct": 100.0 * gain / best,
                "flow_weighted_improvement": gain * float(ps.od_flow[oi]),
                "route_sequence": "+".join(seq),
                "n_boardings": boardings,
                "sequence_already_in_set": seq in _route_sequences_in_set(ps, oi),
            })
    return pd.DataFrame(rows)


def classify(rows: pd.DataFrame, tested_flow: float, tested_gc: float,
             flow_negligible: float = 0.01, flow_material: float = 0.03,
             gc_negligible: float = 0.0025, gc_material: float = 0.01
             ) -> DiscoveryResult:
    """Apply the decision rule fixed in ACCEPTANCE.md before this ran."""
    if rows.empty:
        return DiscoveryResult(
            rows, {"n_omitted": 0, "flow_share": 0.0, "gc_share": 0.0,
                   "tested_flow": tested_flow, "tested_generalized_cost": tested_gc},
            pd.DataFrame(), "A",
            "no tested OD-period has a Model B path cheaper than the candidate "
            "set; per-pattern enumeration is adequate for the corrected model")

    flow_share = float(rows["flow"].sum() / tested_flow) if tested_flow else 0.0
    fw = float(rows["flow_weighted_improvement"].sum())
    gc_share = fw / tested_gc if tested_gc else 0.0
    summary = {
        "n_omitted": int(len(rows)),
        "n_sequences_already_in_set": int(rows["sequence_already_in_set"].sum()),
        "flow_affected": float(rows["flow"].sum()),
        "tested_flow": tested_flow,
        "flow_share": flow_share,
        "flow_weighted_improvement_min": fw,
        "tested_generalized_cost": tested_gc,
        "gc_share": gc_share,
        "median_improvement_min": float(rows["improvement_min"].median()),
        "p95_improvement_min": float(rows["improvement_min"].quantile(0.95)),
        "median_improvement_pct": float(rows["improvement_pct"].median()),
    }
    exploded = rows.assign(r=rows["route_sequence"].str.split("+")).explode("r")
    by_route = (exploded.groupby("r")
                .agg(n_od=("od_index", "size"), flow=("flow", "sum"),
                     fw_improvement=("flow_weighted_improvement", "sum"))
                .reset_index().rename(columns={"r": "route"})
                .sort_values("fw_improvement", ascending=False))

    if flow_share >= flow_material or gc_share >= gc_material:
        case = "C"
        why = (f"{100 * flow_share:.2f}% of tested flow and "
               f"{100 * gc_share:.2f}% of tested generalized cost have a "
               "materially cheaper Model B path outside the candidate set. "
               "The yardstick must not be frozen: augment candidate generation "
               "around the affected corridors and re-run this diagnostic")
    elif flow_share >= flow_negligible or gc_share >= gc_negligible:
        case = "B"
        why = (f"{100 * flow_share:.2f}% of tested flow and "
               f"{100 * gc_share:.2f}% of tested generalized cost are affected: "
               "real, concentrated, and too small to shift the frontier. Record "
               "as a named residual rather than rebuilding the search")
    else:
        case = "A"
        why = (f"{100 * flow_share:.2f}% of tested flow and "
               f"{100 * gc_share:.2f}% of tested generalized cost are affected, "
               "both under the negligible thresholds; per-pattern enumeration "
               "is adequate for the corrected model")
    return DiscoveryResult(rows, summary, by_route, case, why)


def high_exposure_od(ps: PathSet, ev: PathSetEvaluator,
                     headways: dict[tuple[str, str], float],
                     rn: RaptorNetwork, period: str,
                     focus_routes: set[str], top_n: int = 4000,
                     ) -> np.ndarray:
    """OD pairs whose chosen path rides a route with real common-lines exposure.

    Targeting is the point: brute-forcing the whole network buys little, because
    the failure can only happen where a route runs several patterns that overlap
    on a movement. Selection is by the routes the common-lines diagnostic named,
    ranked by flow, so the diagnostic stresses exactly the situation in which
    per-pattern discovery is most likely to fail.
    """
    from .attribution import best_paths

    sub = np.array([headways[k] for k in ps.rp_keys])
    idx, _ = best_paths(ev, sub)
    keep = []
    for oi in np.flatnonzero(idx >= 0):
        p = int(idx[oi])
        a, b = ps.path_offsets[p], ps.path_offsets[p + 1]
        rp = ps.leg_rp[a:b]
        routes = {ps.rp_keys[int(k)][0] for k in rp[rp >= 0]}
        if routes & focus_routes:
            keep.append(oi)
    keep = np.array(keep, dtype=np.int64)
    if len(keep) > top_n:
        keep = keep[np.argsort(-ps.od_flow[keep])[:top_n]]
    return np.sort(keep)
