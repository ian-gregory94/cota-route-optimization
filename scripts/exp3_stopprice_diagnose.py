#!/usr/bin/env python3
"""Why COTA's schedule cannot price a stop — the specific reason, not the symptom.

`exp3_audit.py` already returned the verdict: pooled −157 seconds per extra
stop across 11 comparisons, which no dwell penalty can produce, so the feed
cannot price a stop. That is the right conclusion and the wrong stopping point.
"the estimate came out inverted" is a symptom, and a symptom leaves open the
possibility that a better estimator, a longer feed or a wider filter would fix
it. This asks what the surviving comparisons are actually made of.

They are made of five stops. Three are bays on one platform at Spring St
Terminal, nine to thirty-seven metres apart. The other two are downtown
intersection corners about sixty-four metres from the stop they are being
distinguished from. Serving "an extra stop" in every one of these eleven
comparisons means pulling into a different bay at a terminal the bus is already
standing in, or turning through a downtown intersection on the other side of
the street. None of them is a wayside stop, so none of them can carry a
wayside stop's cost, and the running-time difference is a routing difference
measured in minutes.

The diagnostic then asks the question that decides Experiment 3's design: does
the feed contain wayside natural experiments that the filter is throwing away?
It re-runs the search with every threshold relaxed and classifies each
surviving comparison by where its extra stops are. If relaxing finds wayside
comparisons, the filter is the problem. If it does not, the feed is, and
Experiment 3 must price a stop by assumption and report the break-even value
rather than pretending to measure one.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from cota_opt import geo
from cota_opt.configs import period_of_seconds, service_periods
from cota_opt.experiment import Experiment
from cota_opt.harness import build_harness
from cota_opt.stopevidence import find_comparisons

log = logging.getLogger("exp3diag")
OUT = ROOT / "outputs"

# A stop this close to another stop on the same route cannot be a wayside stop
# whose service costs a bus measurable time: it is a second bay, the far corner
# of one intersection, or a paired stop across a divided street. 80 m is
# deliberately generous -- COTA's own median stop spacing is 331 m.
COLOCATED_M = 80.0


def metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    R = 6_371_000.0
    la1, lo1, la2, lo2 = map(np.radians, [a[0], a[1], b[0], b[1]])
    return float(2 * R * np.arcsin(np.sqrt(
        np.sin((la2 - la1) / 2) ** 2
        + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2)))


def classify(stop_ids: list[str], coords: dict[str, tuple[float, float]],
             names: dict[str, str]) -> tuple[str, float, str]:
    """Nearest other stop in the feed, and what that implies."""
    worst = ("", float("inf"), "")
    for s in stop_ids:
        if s not in coords:
            continue
        d, near = min(((metres(coords[s], c), t)
                       for t, c in coords.items() if t != s),
                      default=(float("inf"), ""))
        if d < worst[1]:
            worst = (s, d, near)
    s, d, near = worst
    if not s:
        return "unknown", float("nan"), ""
    kind = "co-located" if d <= COLOCATED_M else "wayside"
    return kind, d, f"{names.get(s, s)} -> {names.get(near, near)} ({d:.0f} m)"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    H = build_harness(seed=20260825, common_lines="same_route")
    a = H.assumptions
    net, ts = H.baseline.network, H.baseline.tstats
    sg = geo.stops_gdf(H.baseline.feed, a["crs"]["projected"])

    coords = {r.stop_id: (float(r.lat), float(r.lon))
              for r in net.stops.values()}
    names = {r.stop_id: r.name for r in net.stops.values()}

    periods = service_periods(a)
    tp = ts.copy()
    tp["period"] = tp["first_dep_sec"].map(lambda x: period_of_seconds(x, periods))
    pop = (tp.dropna(subset=["period"]).groupby("pattern_id")["period"]
           .apply(lambda s: set(s)).to_dict())

    settings = {
        "committed": dict(min_shared_stops=2, min_segment_sec=120.0,
                          max_skipped=12, require_shared_period=True),
        "relaxed-period": dict(min_shared_stops=2, min_segment_sec=120.0,
                               max_skipped=12, require_shared_period=False),
        "relaxed-all": dict(min_shared_stops=2, min_segment_sec=30.0,
                            max_skipped=40, require_shared_period=False),
    }

    out: dict[str, dict] = {}
    frames = []
    for label, kw in settings.items():
        df = find_comparisons(net, ts, periods_of_pattern=pop, **kw)
        if df.empty:
            out[label] = {"n_comparisons": 0}
            log.info("%-16s 0 comparisons", label)
            continue
        cls = df["extra_stops"].map(
            lambda s: classify(str(s).split("+"), coords, names))
        df = df.copy()
        df["setting"] = label
        df["extra_stop_kind"] = [c[0] for c in cls]
        df["nearest_other_stop_m"] = [c[1] for c in cls]
        df["closest_pair"] = [c[2] for c in cls]
        frames.append(df)

        wayside = df[df["extra_stop_kind"] == "wayside"]
        out[label] = {
            "n_comparisons": int(len(df)),
            "n_routes": int(df["route_id"].nunique()),
            "n_wayside": int(len(wayside)),
            "share_wayside_pct": round(100 * len(wayside) / len(df), 2),
            "pooled_sec_per_stop": round(float(
                df["seconds_difference"].sum() / df["n_extra_stops"].sum()), 2),
            "pooled_sec_per_stop_wayside_only": (
                round(float(wayside["seconds_difference"].sum()
                            / wayside["n_extra_stops"].sum()), 2)
                if not wayside.empty and wayside["n_extra_stops"].sum() else None),
            "median_nearest_other_stop_m": round(
                float(df["nearest_other_stop_m"].median()), 1),
        }
        log.info("%-16s %3d comparisons, %d routes, %d wayside (%.0f%%), "
                 "pooled %+.0f s/stop",
                 label, len(df), df["route_id"].nunique(), len(wayside),
                 out[label]["share_wayside_pct"], out[label]["pooled_sec_per_stop"])

    all_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not all_df.empty:
        all_df.to_csv(OUT / "exp3_stopprice_diagnosis.csv", index=False)

    committed = out.get("committed", {})
    relaxed = out.get("relaxed-all", {})
    filter_is_the_problem = bool(relaxed.get("n_wayside", 0) >= 8)
    verdict = {
        "colocated_threshold_m": COLOCATED_M,
        "median_stop_spacing_m": 330.8,
        "settings": out,
        "filter_is_the_problem": filter_is_the_problem,
        "conclusion": (
            "Relaxing every threshold produces wayside comparisons, so the "
            "committed filter -- not the feed -- is what starved the estimate. "
            "Re-derive the stop penalty from the wayside subset before "
            "designing Experiment 3."
            if filter_is_the_problem else
            "Relaxing every threshold -- dropping the period control, cutting "
            "the minimum segment to 30 seconds and allowing 40 skipped stops "
            "-- still does not produce enough wayside comparisons to price a "
            "stop. The scarcity is in the feed, not in the filter. Same-route "
            "pattern pairs that differ by stop SET while sharing endpoints are "
            "downtown routing variants: which terminal bay, which corner of an "
            "intersection. COTA does not run wayside skip-stop service outside "
            "the peak-express class, so the schedule contains no natural "
            "experiment on the quantity Experiment 3 needs. Experiment 3 must "
            "therefore price a stop by ASSUMPTION and report the break-even "
            "penalty at which consolidation stops paying, labelled as such -- "
            "not estimate one and present it as measured."),
    }
    (OUT / "exp3_stopprice_diagnosis.json").write_text(json.dumps(verdict, indent=2))

    pd.set_option("display.width", 220)
    pd.set_option("display.max_colwidth", 52)
    print("\n" + "=" * 100)
    print("EXPERIMENT 3 FOUNDATION — what the stop-price comparisons are made of")
    print("=" * 100)
    if not all_df.empty:
        c = all_df[all_df["setting"] == "committed"]
        print(f"\nthe {len(c)} committed comparisons, by what their extra stops are:")
        print(c[["route_id", "n_extra_stops", "extra_stops", "seconds_per_extra_stop",
                 "extra_stop_kind", "closest_pair"]].to_string(index=False))
    print("\nby filter setting:")
    print(pd.DataFrame(out).T.to_string())
    print("\n" + verdict["conclusion"])
    print("\nartifacts:", OUT / "exp3_stopprice_diagnosis.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
