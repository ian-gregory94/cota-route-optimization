"""Why was the original candidate path set inadequate?

Raising the per-OD candidate cap from four to six added under 1% more paths, so
the cap was never the binding constraint. The remaining hypothesis is that the
*scenarios* the enumerator swept — today's headways, a uniformly frequent
network, a uniformly infrequent one, three random ladders — never produced the
service pattern an optimized plan actually creates, and so never produced the
paths that pattern makes attractive.

This module tests that by diffing two path sets priced under the *same*
headways. Any OD pair the newer set can serve more cheaply is a pair the older
set was overcharging, and the path that does it can be named: which routes, how
many boardings, how much cheaper, how much flow rides on it.

Each improvement is then attributed to a mechanism:

``route_substitution``   the new path rides routes the old best path never used
``transfer_reduction``   same routes available, but the new path boards fewer times
``transfer_addition``    the new path accepts an extra boarding to save more time
``stop_relocation``      same routes and boardings, different boarding points

"The fixpoint converged" is a fact about the loop. This is the fact about the
network, and it is the one that transfers to anyone else's model.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .pathset import PathSet, PathSetEvaluator

log = logging.getLogger(__name__)


def path_costs(ev: PathSetEvaluator, headways: np.ndarray) -> np.ndarray:
    """Generalized cost of every path in the set, under these headways."""
    ps = ev.ps
    if ps.n_paths == 0:
        return np.zeros(0)
    wait = ev._wait(headways[ev.ride_rp] * ev.ride_mult)
    wcost = np.where(ev.ride_is_xfer, ev.w.transfer_wait * wait,
                     ev.w.waiting * wait)
    return ev.path_const + np.bincount(ev.ride_path, weights=wcost,
                                       minlength=ps.n_paths)


def best_paths(ev: PathSetEvaluator, headways: np.ndarray
               ) -> tuple[np.ndarray, np.ndarray]:
    """Cheapest path index and its cost per OD pair (-1 where none exists)."""
    ps = ev.ps
    cost = path_costs(ev, headways)
    idx = np.full(ps.n_od, -1, dtype=np.int64)
    val = np.full(ps.n_od, np.inf)
    if not len(ev._starts):
        return idx, val
    gmin = np.minimum.reduceat(cost, ev._starts)
    attains = cost <= np.repeat(gmin, ev._group_sizes) + 1e-12
    keyed = np.where(attains, ev._path_index, np.iinfo(np.int64).max)
    chosen = np.minimum.reduceat(keyed, ev._starts)
    idx[ev._oi] = chosen
    val[ev._oi] = gmin
    return idx, val


def describe_path(ps: PathSet, p: int) -> dict[str, Any]:
    """Routes ridden, boardings taken, and time split for one path."""
    if p < 0:
        return {"routes": (), "n_boardings": 0, "ivt_min": np.nan,
                "walk_min": np.nan, "board_stops": ()}
    a, b = ps.path_offsets[p], ps.path_offsets[p + 1]
    rp = ps.leg_rp[a:b]
    ride = rp >= 0
    routes = tuple(ps.rp_keys[int(k)][0] for k in rp[ride])
    return {
        "routes": routes,
        "n_boardings": int(ps.leg_is_boarding[a:b].sum()),
        "ivt_min": float(ps.leg_ivt[a:b].sum()),
        "walk_min": float(ps.leg_walk[a:b].sum()),
        "board_stops": tuple(int(x) for x in
                             (ps.leg_board_pos[a:b][ride]
                              if ps.leg_board_pos is not None else ())),
    }


def _mechanism(old: dict[str, Any], new: dict[str, Any]) -> str:
    if not old["routes"]:
        return "newly_reachable"
    if set(new["routes"]) != set(old["routes"]):
        return "route_substitution"
    if new["n_boardings"] < old["n_boardings"]:
        return "transfer_reduction"
    if new["n_boardings"] > old["n_boardings"]:
        return "transfer_addition"
    return "stop_relocation"


@dataclass
class Attribution:
    rows: pd.DataFrame
    summary: dict[str, Any]
    by_period: pd.DataFrame
    by_mechanism: pd.DataFrame
    by_route: pd.DataFrame


def diff_sets(old_ev: PathSetEvaluator, new_ev: PathSetEvaluator,
              headways: dict[tuple[str, str], float], period: str,
              iteration: int | None = None, lam: float | None = None,
              min_improvement_min: float = 1e-6,
              top_n: int = 4000) -> pd.DataFrame:
    """OD pairs the newer set serves more cheaply, with the path that does it.

    Both sets are priced under the same headways, so a difference is purely a
    difference in what was enumerated. The two sets must share an OD ordering,
    which they do when they come from the same OD table.
    """
    ops, nps = old_ev.ps, new_ev.ps
    if ops.n_od != nps.n_od:
        raise ValueError("path sets cover different OD tables")

    h_old = np.array([headways[k] for k in ops.rp_keys])
    h_new = np.array([headways[k] for k in nps.rp_keys])
    old_idx, old_cost = best_paths(old_ev, h_old)
    new_idx, new_cost = best_paths(new_ev, h_new)

    old_cost = np.minimum(old_cost, ops.od_walk_only)
    new_cost = np.minimum(new_cost, nps.od_walk_only)
    gain = old_cost - new_cost
    improved = np.flatnonzero(np.isfinite(new_cost)
                              & (gain > min_improvement_min))
    if len(improved) == 0:
        return pd.DataFrame()

    # rank by flow-weighted improvement: a tenth of a minute on a pair nobody
    # travels is not what broke the model
    weight = gain[improved] * nps.od_flow[improved]
    improved = improved[np.argsort(-weight)][:top_n]

    rows = []
    for oi in improved:
        o = describe_path(ops, int(old_idx[oi]))
        n = describe_path(nps, int(new_idx[oi]))
        rows.append({
            "period": period,
            "iteration": iteration,
            "lambda": lam,
            "od_index": int(oi),
            "origin_zone": int(nps.od_origin[oi]) if nps.od_origin is not None else -1,
            "dest_zone": int(nps.od_dest[oi]) if nps.od_dest is not None else -1,
            "flow": float(nps.od_flow[oi]),
            "old_cost_min": float(old_cost[oi]),
            "new_cost_min": float(new_cost[oi]),
            "improvement_min": float(gain[oi]),
            "flow_weighted_improvement": float(gain[oi] * nps.od_flow[oi]),
            "old_routes": "+".join(o["routes"]),
            "new_routes": "+".join(n["routes"]),
            "old_boardings": o["n_boardings"],
            "new_boardings": n["n_boardings"],
            "old_ivt_min": o["ivt_min"],
            "new_ivt_min": n["ivt_min"],
            "mechanism": _mechanism(o, n),
        })
    return pd.DataFrame(rows)


def summarize(rows: pd.DataFrame, total_flow: float) -> Attribution:
    if rows.empty:
        empty = pd.DataFrame()
        return Attribution(rows, {"n_improved_od": 0}, empty, empty, empty)

    fw = rows["flow_weighted_improvement"].sum()
    summary = {
        "n_improved_od": int(len(rows)),
        "flow_touched": float(rows["flow"].sum()),
        "flow_share_touched": float(rows["flow"].sum() / total_flow)
        if total_flow else np.nan,
        "total_flow_weighted_improvement_min": float(fw),
        "mean_improvement_min": float(rows["improvement_min"].mean()),
        "p95_improvement_min": float(rows["improvement_min"].quantile(0.95)),
        # concentration: if a handful of OD pairs carry the whole correction,
        # the adequacy problem was local, not systemic
        "top_1pct_share_of_improvement": float(
            rows.nlargest(max(1, len(rows) // 100),
                          "flow_weighted_improvement")
            ["flow_weighted_improvement"].sum() / fw) if fw > 0 else np.nan,
        "top_10pct_share_of_improvement": float(
            rows.nlargest(max(1, len(rows) // 10),
                          "flow_weighted_improvement")
            ["flow_weighted_improvement"].sum() / fw) if fw > 0 else np.nan,
    }

    def agg(df, by):
        g = (df.groupby(by, observed=True)
             .agg(n_od=("od_index", "size"),
                  flow=("flow", "sum"),
                  mean_improvement_min=("improvement_min", "mean"),
                  flow_weighted_improvement=("flow_weighted_improvement", "sum"))
             .reset_index())
        g["share_of_improvement"] = g["flow_weighted_improvement"] / fw
        return g.sort_values("flow_weighted_improvement", ascending=False)

    by_period = agg(rows, "period")
    by_mech = agg(rows, "mechanism")

    # which routes the corrections newly ride: the corridors the original
    # scenario sweep never made attractive
    exploded = rows.assign(route=rows["new_routes"].str.split("+")).explode("route")
    exploded = exploded[exploded["route"].astype(bool)]
    by_route = agg(exploded, "route").head(25)
    return Attribution(rows, summary, by_period, by_mech, by_route)
