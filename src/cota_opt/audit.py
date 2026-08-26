"""A full, auditable record for every geometry candidate.

A screening rank is one number, and one number is not enough to decide which
proposals get expensive evaluation. A candidate can score well because it
genuinely improves access, or because it quietly deleted service, or because it
was priced with running time nobody has observed. Those look identical in a
sorted column and completely different in a table that shows what changed.

So every candidate gets a row carrying what it did to the network (stops,
running time, vehicle-hours, the headway rescaling needed to put the budget
back), what evidence supports it (observed versus modelled links, demand gained
versus demand that loses its direct service), what it scored, and what a
planner would immediately object to. The evidence class is derived here, from
the ACCEPTANCE.md threshold fixed before any results were seen.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from .candidates import StopContext
from .geometry import EditedNetwork, GeometryEdit

log = logging.getLogger(__name__)

#: modelled-link share at or below which a candidate may define the headline
#: Experiment 2 frontier. Fixed in ACCEPTANCE.md before results.
PRIMARY_MAX_MODELLED_PCT = 2.0


def _route_stops(net, routes: set[str]) -> set[str]:
    return {s for p in net.patterns.values() if p.route_id in routes
            for s in p.stops}


def _route_runtime_min(net, routes: set[str]) -> float:
    """Mean pattern running time over the routes' patterns."""
    vals = [sum(s.run_time_sec for s in p.segments) / 60.0
            for p in net.patterns.values() if p.route_id in routes]
    return float(np.mean(vals)) if vals else float("nan")


def concerns(edit: GeometryEdit, ed: EditedNetwork, ctx: StopContext,
             lost: set[str], gained: set[str], big_routes: set[str],
             modelled_pct: float, headway_scale: float) -> list[str]:
    """What a planner would object to, stated before anyone sees the score."""
    out = []
    r = ed.report.as_dict()
    if modelled_pct > PRIMARY_MAX_MODELLED_PCT:
        out.append(f"{modelled_pct:.1f}% of segments priced by the running-time "
                   "model rather than the schedule")
    orphaned = [s for s in lost if ctx.n_routes.get(s, 0) <= 1]
    if orphaned:
        out.append(f"{len(orphaned)} stop(s) lose their only service")
    if edit.routes_touched() & big_routes:
        out.append("touches a top-10 route by vehicle-hours")
    if r["veh_hours_freed"] > 0.02 * ed.report.baseline_veh_hours_before:
        out.append(f"frees {r['veh_hours_freed']:.0f} vehicle-hours "
                   f"({100 * r['veh_hours_freed'] / ed.report.baseline_veh_hours_before:.1f}%) "
                   "— check this is service redeployed, not service deleted")
    if headway_scale < 0.97:
        out.append(f"needs headways cut {100 * (1 - headway_scale):.1f}% to spend "
                   "the budget back — most of any gain may be the extra frequency")
    if not gained and lost:
        out.append("removes coverage without adding any")
    if r["stops_dropped"] > 25:
        out.append(f"{r['stops_dropped']} stops removed — large for a limited edit")
    for note in r.get("notes", []):
        if "dropped" in note:
            out.append(note)
    return out


def audit_row(edit: GeometryEdit, ed: EditedNetwork, ctx: StopContext,
              base_net, base_tstats: pd.DataFrame,
              baseline_headways: dict[tuple[str, str], float],
              screen: Any | None, big_routes: set[str]) -> dict[str, Any]:
    r = ed.report.as_dict()
    touched = edit.routes_touched()
    before_stops = _route_stops(base_net, touched)
    # a splice renames its routes, so the merged id has to be picked up too
    after_routes = {p.route_id for p in ed.network.patterns.values()
                    if p.route_id in touched
                    or any(t in p.route_id.split("+") for t in touched)}
    after_stops = _route_stops(ed.network, after_routes)
    lost, gained = before_stops - after_stops, after_stops - before_stops

    demand_lost = sum(ctx.exclusive_weight(s) for s in lost)
    demand_gained = sum(ctx.exclusive_weight(s) for s in gained)
    transfer_pts = sum(1 for s in (lost | gained) if ctx.n_routes.get(s, 0) > 1)

    old_rt = _route_runtime_min(base_net, touched)
    new_rt = _route_runtime_min(ed.network, after_routes)
    hw = [v for k, v in baseline_headways.items() if k[0] in touched]
    modelled_pct = float(r["modelled_share_pct"])
    scale = float(getattr(screen, "headway_scale", np.nan)) if screen else np.nan

    cls = ("primary" if modelled_pct <= PRIMARY_MAX_MODELLED_PCT
           else "novel_link")
    issues = concerns(edit, ed, ctx, lost, gained, big_routes, modelled_pct,
                      scale if np.isfinite(scale) else 1.0)

    return {
        "candidate_id": edit.key,
        "kind": edit.kind,
        "routes": "+".join(sorted(touched)),
        "description": edit.description,
        # what changed on the ground
        "stops_added": r["stops_added"],
        "stops_removed": r["stops_dropped"],
        "stop_count_change": r["stops_added"] - r["stops_dropped"],
        "old_runtime_min": old_rt,
        "new_runtime_min": new_rt,
        "runtime_change_min": new_rt - old_rt,
        "runtime_change_pct": (100 * (new_rt - old_rt) / old_rt
                               if old_rt else np.nan),
        # supply bookkeeping, before and after the budget is restored
        "veh_hours_before": r["baseline_veh_hours_before"],
        "veh_hours_after_raw": r["baseline_veh_hours_after"],
        "veh_hours_freed_raw": r["veh_hours_freed"],
        "headway_scale_to_restore_budget": scale,
        # evidence
        "segments_observed": r["segments_kept"],
        "segments_modelled": r["segments_modelled"],
        "observed_share_pct": 100.0 - modelled_pct,
        "modelled_share_pct": modelled_pct,
        "evidence_class": cls,
        # demand consequences
        "unique_demand_gained": demand_gained,
        "unique_demand_lost": demand_lost,
        "unique_demand_net": demand_gained - demand_lost,
        "stops_losing_only_service": sum(
            1 for s in lost if ctx.n_routes.get(s, 0) <= 1),
        "transfer_points_affected": transfer_pts,
        # service context
        "baseline_headway_min_mean": float(np.mean(hw)) if hw else np.nan,
        "baseline_headway_min_min": float(np.min(hw)) if hw else np.nan,
        "route_periods_affected": len(hw),
        # screening outcome (a rank, not a measurement)
        "screen_gc_change_pct": getattr(screen, "gc_change_pct", np.nan)
        if screen else np.nan,
        "screen_unserved_change_pct": getattr(screen, "unserved_change_pct",
                                              np.nan) if screen else np.nan,
        "screen_error": getattr(screen, "error", None) if screen else None,
        # what a planner would say
        "n_concerns": len(issues),
        "operational_concerns": "; ".join(issues) if issues else "",
    }


def audit_table(rows: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(
        ["evidence_class", "screen_unserved_change_pct", "screen_gc_change_pct"],
        na_position="last").reset_index(drop=True)


def top_routes_by_veh_hours(tstats: pd.DataFrame, n: int = 10) -> set[str]:
    vh = tstats.groupby("route_id")["runtime_min"].sum() / 60.0
    return set(vh.sort_values(ascending=False).head(n).index.astype(str))
