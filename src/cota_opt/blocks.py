"""Peak vehicle requirement from GTFS vehicle blocks.

Equal daily vehicle-hours do not mean equal buses. A plan can spend exactly
today's service hours and still need more vehicles standing on the street at
8am, which is a capital cost the hours budget never sees. Calling such a plan
"cost-neutral" would be wrong in the way that matters to an agency.

COTA's feed carries a complete ``block_id`` on all 5,435 trips, so the true
requirement can be read rather than approximated: a block is one vehicle's
whole day, the vehicle is out from its block's first departure to its last
arrival, and the peak requirement is the largest number of blocks in service at
once. That number includes layover and interlining, which the usual
cycle-time-over-headway formula does not.

The formula is still needed, because an *optimized plan* has headways rather
than blocks -- nobody has cut new blocks for it. So the two are measured
against each other on the baseline, and the ratio between them, the interlining
factor, carries forward as the correction on candidate plans. That is a proxy
and is labelled as one: it assumes a re-blocked network would interline about
as efficiently as today's, which is a scheduler's judgement, not a fact.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


@dataclass
class BlockProfile:
    blocks: pd.DataFrame          # one row per block: span, trips, routes
    concurrency: pd.DataFrame     # minute-by-minute vehicles in service
    peak_vehicles: int
    peak_minute: int
    peak_by_period: dict[str, int]
    interline_share: float        # share of blocks serving more than one route
    layover_share: float          # share of block span not spent running

    def summary(self) -> dict[str, Any]:
        return {
            "n_blocks": int(len(self.blocks)),
            "peak_vehicles": self.peak_vehicles,
            "peak_time": f"{self.peak_minute // 60:02d}:{self.peak_minute % 60:02d}",
            "peak_by_period": self.peak_by_period,
            "interline_share": self.interline_share,
            "layover_share": self.layover_share,
            "block_span_hours_median": float(self.blocks["span_hours"].median()),
            "trips_per_block_median": float(self.blocks["n_trips"].median()),
        }


def reconstruct(trips: pd.DataFrame, tstats: pd.DataFrame,
                periods: dict[str, tuple[float, float]] | None = None,
                ) -> BlockProfile:
    """Vehicle blocks for one service day, and the concurrency they imply.

    ``trips`` needs ``trip_id`` and ``block_id``; ``tstats`` supplies each
    trip's first departure, last arrival and running time for the representative
    weekday, so only that day's trips are counted.
    """
    if "block_id" not in trips.columns:
        raise ValueError("feed has no block_id; peak fleet cannot be read from blocks")
    t = tstats.merge(trips[["trip_id", "block_id"]], on="trip_id", how="left")
    missing = int(t["block_id"].isna().sum())
    if missing:
        log.warning("%d of %d weekday trips have no block_id", missing, len(t))
    t = t.dropna(subset=["block_id"])
    if t.empty:
        raise ValueError("no weekday trips carry a block_id")

    g = t.groupby("block_id")
    blocks = pd.DataFrame({
        "start_sec": g["first_dep_sec"].min(),
        "end_sec": g["last_arr_sec"].max(),
        "n_trips": g.size(),
        "run_minutes": g["runtime_min"].sum(),
        "n_routes": g["route_id"].nunique(),
        "routes": g["route_id"].apply(lambda s: "+".join(sorted(set(s.astype(str))))),
    }).reset_index()
    blocks["span_hours"] = (blocks["end_sec"] - blocks["start_sec"]) / 3600.0
    blocks["layover_minutes"] = (
        (blocks["end_sec"] - blocks["start_sec"]) / 60.0 - blocks["run_minutes"])

    # minute-by-minute count of blocks in service, over a 30-hour day so that
    # trips past midnight are not wrapped on top of the morning peak
    horizon = int(np.ceil(blocks["end_sec"].max() / 60.0)) + 1
    delta = np.zeros(horizon + 2, dtype=np.int64)
    s = np.floor(blocks["start_sec"] / 60.0).astype(int).to_numpy()
    e = np.ceil(blocks["end_sec"] / 60.0).astype(int).to_numpy()
    np.add.at(delta, s, 1)
    np.add.at(delta, np.minimum(e, horizon + 1), -1)
    conc = np.cumsum(delta)[:horizon]
    minutes = np.arange(horizon)
    concurrency = pd.DataFrame({"minute": minutes, "vehicles": conc})

    peak = int(conc.max())
    peak_min = int(minutes[int(np.argmax(conc))])

    peak_by_period: dict[str, int] = {}
    if periods:
        for name, (h0, h1) in periods.items():
            a, b = int(h0 * 60), int(h1 * 60)
            if b <= a:                       # owl window wraps past midnight
                b += 24 * 60
            window = conc[a:min(b, horizon)]
            peak_by_period[name] = int(window.max()) if len(window) else 0

    return BlockProfile(
        blocks=blocks, concurrency=concurrency, peak_vehicles=peak,
        peak_minute=peak_min, peak_by_period=peak_by_period,
        interline_share=float((blocks["n_routes"] > 1).mean()),
        layover_share=float(blocks["layover_minutes"].sum()
                            / max(1e-9, (blocks["end_sec"] - blocks["start_sec"]).sum()
                                  / 60.0)))


def routewise_peak(services: dict, plan_headways: dict,
                   periods: dict[str, Any]) -> dict[str, float]:
    """The cycle-time-over-headway approximation, per period.

    This is what the optimizer's own budget uses. It counts a vehicle for every
    route independently, so it cannot see that one bus finishes route 8 and
    starts route 35 twenty minutes later.
    """
    out: dict[str, float] = {}
    for (rid, per), svc in services.items():
        h = plan_headways.get((rid, per))
        if not h or h <= 0:
            continue
        cycle = getattr(svc, "cycle_min", None)
        if cycle is None:
            cycle = svc.runtime_min * svc.n_directions
        out[per] = out.get(per, 0.0) + cycle / h
    return out


def interlining_factor(block_peak: int, routewise: dict[str, float]) -> float:
    """How much better real blocking does than the per-route formula.

    Below 1 means today's schedule interlines: fewer buses are needed than the
    formula's route-by-route sum. Applied to a candidate plan it assumes the
    candidate could be blocked about as well, which a scheduler would have to
    confirm.
    """
    approx = max(routewise.values()) if routewise else 0.0
    return float(block_peak / approx) if approx > 0 else float("nan")


def fleet_estimate(services: dict, plan_headways: dict, periods: dict,
                   factor: float) -> dict[str, Any]:
    """Peak-fleet proxy for a plan, and where any increase comes from."""
    rw = routewise_peak(services, plan_headways, periods)
    approx = max(rw.values()) if rw else 0.0
    per_route: dict[str, float] = {}
    peak_period = max(rw, key=rw.get) if rw else None
    for (rid, per), svc in services.items():
        if per != peak_period:
            continue
        h = plan_headways.get((rid, per))
        if not h or h <= 0:
            continue
        cycle = getattr(svc, "cycle_min", None) or svc.runtime_min * svc.n_directions
        per_route[rid] = cycle / h
    return {
        "routewise_peak_by_period": rw,
        "routewise_peak": approx,
        "blocked_peak_proxy": approx * factor,
        "interlining_factor": factor,
        "peak_period": peak_period,
        "per_route_at_peak": per_route,
    }
