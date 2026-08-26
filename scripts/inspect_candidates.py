#!/usr/bin/env python3
"""Look at the strongest geometry candidates instead of trusting their rank.

A screening score says a candidate helps. It does not say *what* it does, and a
proposal nobody can explain has no business being promoted to an expensive
evaluation — the score might be measuring a weakness of the model rather than a
property of the network. So each shortlisted candidate gets a written diff and
a before/after map, and the questions a planner would ask are answered in the
output rather than left to the reader.

Nothing here scores anything. It is for reading.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from cota_opt import geo
from cota_opt.candidates import generate_all, stop_context
from cota_opt.figures import THEMES, Theme, _style
from cota_opt.geometry import SegmentTimeModel, apply_edits
from cota_opt.harness import build_harness

log = logging.getLogger("inspect")
OUT = ROOT / "outputs"
MAPS = OUT / "figures" / "candidates"


def _patterns_of(net, routes: set[str]) -> list:
    return [p for p in net.patterns.values()
            if p.route_id in routes
            or any(t in p.route_id.split("+") for t in routes)]


def _xy(coords, stops):
    pts = [coords[s] for s in stops if s in coords]
    if not pts:
        return np.zeros(0), np.zeros(0)
    a = np.asarray(pts)
    return a[:, 0], a[:, 1]


def draw(t: Theme, edit, before_net, after_net, coords, names,
         all_stops_xy) -> plt.Figure:
    routes = edit.routes_touched()
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 5.6), sharex=True, sharey=True)
    before = _patterns_of(before_net, routes)
    after = _patterns_of(after_net, routes)
    b_stops = {s for p in before for s in p.stops}
    a_stops = {s for p in after for s in p.stops}
    removed, added = b_stops - a_stops, a_stops - b_stops

    for ax, pats, title, extra, extra_c, extra_lab in (
            (axes[0], before, "today", removed, t.series[1], "dropped"),
            (axes[1], after, "after the edit", added, t.series[2], "added")):
        ax.scatter(all_stops_xy[0], all_stops_xy[1], s=1.5, color=t.grid,
                   zorder=1, linewidths=0)
        for p in pats:
            x, y = _xy(coords, p.stops)
            if len(x):
                ax.plot(x, y, "-", color=t.series[0], lw=1.6, alpha=0.85,
                        zorder=3, solid_capstyle="round")
                ax.scatter(x, y, s=9, color=t.series[0], zorder=4,
                           linewidths=0)
        if extra:
            ex, ey = _xy(coords, sorted(extra))
            if len(ex):
                ax.scatter(ex, ey, s=42, facecolor="none", edgecolor=extra_c,
                           linewidth=1.8, zorder=5, label=extra_lab)
                ax.legend(loc="upper right", labelcolor=t.text_secondary)
        ax.set_title(title, loc="left", fontsize=11)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(visible=False)
        for sp in ax.spines.values():
            sp.set_visible(False)

    fig.suptitle(edit.description, x=0.005, ha="left", fontsize=11,
                 fontweight="600", color=t.text_primary, wrap=True)
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    return fig


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--primary-only", action="store_true", default=True)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    MAPS.mkdir(parents=True, exist_ok=True)

    H = build_harness()
    b, a = H.baseline, H.assumptions
    sg = geo.stops_gdf(b.feed, a["crs"]["projected"])
    model = SegmentTimeModel.fit(b.network, sg)
    names = dict(zip(b.feed.stops["stop_id"],
                     b.feed.stops.get("stop_name", b.feed.stops["stop_id"])))
    coords = model.coords
    served = sorted({s for p in b.network.patterns.values() for s in p.stops})
    all_xy = _xy(coords, served)

    ctx = stop_context(b.network, H.zones, H.raptor.stop_ids, model)
    zone_flow = np.zeros(H.zones.n)
    np.add.at(zone_flow, H.od.origin, H.od.flow)
    np.add.at(zone_flow, H.od.dest, H.od.flow)
    express = {r for r, c in H.classes.items() if c.klass == "peak_express"}
    trips = b.tstats.groupby("route_id").size().to_dict()
    by_key = {c.key: c for c in generate_all(
        b.network, ctx, H.zones, H.raptor.stop_ids, zone_flow, trips,
        exclude_routes=express, per_kind=12)}

    audit = pd.read_csv(OUT / "exp2_audit.csv")
    ok = audit.dropna(subset=["screen_gc_change_pct"])
    if args.primary_only:
        ok = ok[ok["evidence_class"] == "primary"]
    ok = ok.sort_values(["screen_unserved_change_pct", "screen_gc_change_pct"])
    shortlist = ok.head(args.top)

    lines: list[str] = [
        "# Strongest geometry candidates, inspected",
        "",
        "Screening rank got these here. Whether they survive is a question "
        "about what they actually do, which is what this file is for. "
        "Everything below is pre-fixpoint and exploratory.",
        "",
    ]
    for i, row in enumerate(shortlist.itertuples(), 1):
        e = by_key.get(row.candidate_id)
        if e is None:
            continue
        ed = apply_edits(b.network, b.tstats, model, [e])
        rep = ed.report.as_dict()
        routes = e.routes_touched()
        before = {s for p in _patterns_of(b.network, routes) for s in p.stops}
        after = {s for p in _patterns_of(ed.network, routes) for s in p.stops}
        removed, added = before - after, after - before

        def nm(ss):
            return ", ".join(f"{names.get(s, s)} ({s})" for s in sorted(ss)[:8]) \
                + (f" … and {len(ss) - 8} more" if len(ss) > 8 else "")

        lines += [
            f"## {i}. {e.description}",
            "",
            f"- **id** `{e.candidate_id if hasattr(e, 'candidate_id') else e.key}`"
            f" · **kind** {e.kind} · **routes** {'+'.join(sorted(routes))}",
            f"- **evidence** {row.evidence_class}, "
            f"{rep['modelled_share_pct']:.1f}% of segments priced by the "
            f"running-time model ({rep['segments_modelled']} of "
            f"{rep['segments_kept'] + rep['segments_modelled']})",
            f"- **supply** {rep['veh_hours_freed']:+.1f} vehicle-hours at "
            f"baseline ({row.old_runtime_min:.1f} → {row.new_runtime_min:.1f} min "
            f"per pattern, {row.runtime_change_pct:+.1f}%); headways then "
            f"rescaled ×{row.headway_scale_to_restore_budget:.4f} to spend the "
            "budget back",
            f"- **stops** −{len(removed)} / +{len(added)}; "
            f"{int(row.stops_losing_only_service)} would lose their only service; "
            f"{int(row.transfer_points_affected)} affected stops are served by "
            "more than one route",
            f"- **demand reached** {row.unique_demand_gained:,.0f} gained, "
            f"{row.unique_demand_lost:,.0f} lost (uniquely-served weight)",
            f"- **service today** mean headway "
            f"{row.baseline_headway_min_mean:.1f} min across "
            f"{int(row.route_periods_affected)} route-periods, best "
            f"{row.baseline_headway_min_min:.1f} min",
            f"- **screen** cost {row.screen_gc_change_pct:+.3f}%, unserved "
            f"{row.screen_unserved_change_pct:+.3f}% "
            "(frequency not reallocated — a rank, not a measurement)",
        ]
        if removed:
            lines.append(f"- **dropped**: {nm(removed)}")
        if added:
            lines.append(f"- **added**: {nm(added)}")
        raw = getattr(row, "operational_concerns", "")
        concerns = "" if raw is None or (isinstance(raw, float)) else str(raw).strip()
        lines.append(f"- **planner would object**: {concerns}" if concerns
                     else "- **planner would object**: nothing flagged")

        stem = e.key.replace("|", "_").replace(":", "_")
        for t in THEMES:
            with plt.rc_context(_style(t)):
                fig = draw(t, e, b.network, ed.network, coords, names, all_xy)
                fig.savefig(MAPS / f"{stem}.{t.name}.svg", bbox_inches="tight")
                plt.close(fig)
        lines += ["", f"![before and after](figures/candidates/{stem}.light.svg)",
                  ""]
        log.info("inspected %s", e.key)

    (OUT / "exp2_candidate_inspection.md").write_text("\n".join(lines))
    log.info("\nwrote %s and %d maps",
             OUT / "exp2_candidate_inspection.md", 2 * len(shortlist))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
