"""Is the cached candidate path set good enough for the plan being scored?

The path-based model prices every OD pair against a fixed set of candidate
paths enumerated in advance. That is what makes the optimizer affordable, and
it is also its main structural error: if an optimized plan makes some path
attractive that was never enumerated, the model charges passengers for a
detour they would not actually take, and the plan's cost is overstated.

The check is direct. Re-run full RAPTOR under the plan's own headways and
compare, OD pair by OD pair, against what the cached set says. RAPTOR is the
optimum over the whole network, so it can only ever be cheaper; the gap is the
overstatement, and its flow-weighted share is the number that has to go to zero
for the path set to be adequate.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from .cost import CostWeights
from .pathset import PathSet, PathSetEvaluator
from .raptor import RaptorNetwork, generalized_cost, pattern_headways

log = logging.getLogger(__name__)


def adequacy(rn: RaptorNetwork, zs, ps: PathSet, ev: PathSetEvaluator,
             headways: dict[tuple[str, str], float], weights: CostWeights,
             wait_kwargs: dict, max_rounds: int) -> dict[str, Any]:
    """Compare cached-set OD costs against fresh RAPTOR under ``headways``."""
    if ps.od_origin is None or ps.od_dest is None:
        raise ValueError("path set predates origin/dest recording; rebuild it")

    sub = np.array([headways[k] for k in ps.rp_keys])
    cache_cost = ev.od_costs(sub)
    ph = pattern_headways(rn, headways, ps.period)

    fresh = np.full(ps.n_od, np.inf)
    origins = np.unique(ps.od_origin)
    starts = np.searchsorted(ps.od_origin, origins, side="left")
    ends = np.searchsorted(ps.od_origin, origins, side="right")
    for z, s0, s1 in zip(origins, starts, ends):
        a_stops, a_walk = zs.access_of(int(z))
        if len(a_stops) == 0:
            continue
        cost, _, _ = generalized_cost(
            rn, [rn.stop_ids[s] for s in a_stops], ph, weights, wait_kwargs,
            max_rounds=max_rounds,
            source_costs=[weights.walking * x for x in a_walk])
        for oi in range(s0, s1):
            e_stops, e_walk = zs.access_of(int(ps.od_dest[oi]))
            if len(e_stops) == 0:
                continue
            fresh[oi] = float(np.min(cost[e_stops] + weights.walking * e_walk))

    both = np.isfinite(cache_cost) & np.isfinite(fresh)
    gap = np.zeros(ps.n_od)
    gap[both] = cache_cost[both] - fresh[both]
    gap = np.maximum(gap, 0.0)          # RAPTOR is the optimum; negatives are noise
    flow = ps.od_flow
    improvable = gap > 1e-6
    fw = flow[both].sum()
    return {
        "period": ps.period,
        "od_pairs_compared": int(both.sum()),
        "flow_share_improvable": float(flow[improvable & both].sum() / fw)
        if fw > 0 else 0.0,
        "mean_overstatement_min": float((gap[both] * flow[both]).sum() / fw)
        if fw > 0 else 0.0,
        "mean_overstatement_pct": float(
            (gap[both] * flow[both]).sum()
            / (cache_cost[both] * flow[both]).sum() * 100) if fw > 0 else 0.0,
        "p95_overstatement_min": float(np.percentile(gap[both], 95))
        if both.any() else 0.0,
        "max_overstatement_min": float(gap[both].max()) if both.any() else 0.0,
        "pairs_improvable": int((improvable & both).sum()),
        "pairs_reachable_only_by_raptor": int(
            (np.isfinite(fresh) & ~np.isfinite(cache_cost)).sum()),
    }
