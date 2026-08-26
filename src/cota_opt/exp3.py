"""Experiment 2 — does route geometry bind, once frequency is already optimal?

Evaluating a geometry edit properly means re-optimizing frequency on the edited
network, because moving a route changes where the vehicle-hour budget is best
spent. That costs a path-set enumeration and a full solve per candidate, which
is far too expensive to run over every proposal. So evaluation is a funnel:

**Screen** (seconds per candidate). Apply the edit, rebuild the router, and
price passengers with full RAPTOR at headways scaled so the edited network
spends *exactly* the same vehicle-hours as COTA does today. No path set, no
optimizer. This answers "at equal cost, does this geometry move anyone closer
to their destination?" It cannot answer "how much", because frequency has not
been reallocated, and a screen number must never be reported as a result.

**Evaluate** (minutes per candidate). Full path set on the edited network,
frequency re-optimized inside the same budget, scored the same way Experiment 1
was. This is the comparison that counts, and it is reserved for candidates the
screen says are worth it.

The benchmark for both is the Experiment 1 frequency-only frontier, not today's
schedule. A geometry edit that merely recovers what frequency redistribution
already offers is not a finding about geometry.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .configs import service_periods
from .cost import CostWeights
from .geometry import EditedNetwork, GeometryEdit, SegmentTimeModel, apply_edits
from .odmatrix import ODTable, ZoneSystem, build_zone_system
from .retention import Retention, score as retention_score
from .raptor import build_raptor_network, generalized_cost, pattern_headways

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# supply bookkeeping on an edited network
# ---------------------------------------------------------------------------

def baseline_headways(tstats: pd.DataFrame,
                      periods: dict[str, tuple[float, float]],
                      ) -> tuple[dict[tuple[str, str], float], float]:
    """Observed headways on this network, and the vehicle-hours they cost.

    Uses Experiment 1's calibration-preserving definition ``h = k*T/n`` so that
    the headways reproduce the trip count, and therefore the vehicle-hours,
    exactly.
    """
    from .configs import period_of_seconds
    ts = tstats.copy()
    ts["period"] = ts["first_dep_sec"].map(lambda s: period_of_seconds(s, periods))
    ts = ts.dropna(subset=["period"])
    hw, vh = {}, 0.0
    for (rid, per), grp in ts.groupby(["route_id", "period"]):
        k = int(grp["direction_id"].nunique())
        T = (periods[per][1] - periods[per][0]) * 60.0
        n = len(grp)
        hw[(str(rid), str(per))] = k * T / n
        vh += float(grp["runtime_min"].sum() / 60.0)
    return hw, vh


def scale_to_budget(hw: dict[tuple[str, str], float], vh_at_hw: float,
                    budget_vh: float) -> tuple[dict[tuple[str, str], float], float]:
    """Stretch or compress every headway until the plan costs exactly ``budget_vh``.

    Vehicle-hours are inversely proportional to headway at fixed geometry, so
    one scalar does it. This is deliberately the dumbest possible frequency
    plan: it holds today's *relative* service pattern and changes only the
    level, which is what makes the screen a comparison of geometry rather than
    a comparison of two different frequency allocations.
    """
    if vh_at_hw <= 0 or budget_vh <= 0:
        return dict(hw), 1.0
    k = vh_at_hw / budget_vh
    return {key: v * k for key, v in hw.items()}, k


# ---------------------------------------------------------------------------
# screening
# ---------------------------------------------------------------------------

@dataclass
class ScreenResult:
    key: str
    kind: str
    description: str
    generalized_cost: float = float("nan")
    #: retention-adjusted, and therefore the same quantity the production
    #: evaluator and every reported frontier use
    unserved_flow: float = float("nan")
    served_flow: float = float("nan")
    #: binary coverage: demand with no path at all. A real and separate
    #: question, never called "unserved"
    unreachable_flow: float = float("nan")
    discouraged_flow: float = float("nan")
    gc_change_pct: float = float("nan")
    unserved_change_pct: float = float("nan")
    unreachable_change_pct: float = float("nan")
    headway_scale: float = float("nan")
    veh_hours_at_baseline: float = float("nan")
    edit_report: dict[str, Any] = field(default_factory=dict)
    seconds: float = 0.0
    error: str | None = None


@dataclass
class Screener:
    """Fixed-budget, fixed-relative-frequency comparison of network geometries."""

    feed: Any
    stops_projected: Any
    assumptions: dict
    weights: CostWeights
    wait_kwargs: dict
    od: ODTable
    bg_frame: pd.DataFrame
    budget_vh: float
    periods: dict[str, tuple[float, float]]
    screen_periods: tuple[str, ...] = ("am_peak", "midday")
    origin_sample: int = 0          # 0 = every origin zone with access
    max_rounds: int = 3
    retention: Retention | None = None
    _origins: np.ndarray | None = None

    def __post_init__(self) -> None:
        # the screen must use the production retention curve, not its own copy
        if self.retention is None:
            self.retention = Retention.from_assumptions(self.assumptions)

    def _period_od(self, per: str) -> ODTable:
        share = float(self.assumptions["demand_proxy"]["period_shares"][per])
        return ODTable(self.od.origin, self.od.dest, self.od.flow * share,
                       self.od.source, self.od.notes)

    def choose_origins(self) -> np.ndarray:
        """The origin zones the screen prices, largest commute flow first.

        Sampling origins is what makes the screen cheap. It biases nothing
        between candidates because every candidate is priced on the same
        origins, but it does mean a screen figure is not a system total.
        """
        if self._origins is not None:
            return self._origins
        flow = np.zeros(int(self.od.origin.max()) + 1)
        np.add.at(flow, self.od.origin, self.od.flow)
        order = np.argsort(-flow)
        keep = order[flow[order] > 0]
        if self.origin_sample:
            keep = keep[:self.origin_sample]
        self._origins = np.sort(keep)
        return self._origins

    def price(self, net, tstats, label: str = "") -> dict[str, float]:
        """Score one network at budget-matched headways, the production way.

        Returns the same quantities the production evaluator reports -- a
        retention-adjusted ``unserved_demand`` alongside a separately named
        ``unreachable_demand`` -- so a screening rank and a production result
        are at least measuring the same concept, even though the screen holds
        frequency fixed and the production run does not.
        """
        rn = build_raptor_network(
            self.feed, net, tstats, self.stops_projected,
            walk_radius_m=float(self.assumptions["path_assignment"]["walk_radius_m"]),
            walk_speed_m_per_min=float(
                self.assumptions["path_assignment"]["walk_speed_m_per_min"]),
            periods=self.periods, with_timetable=False)
        zs = build_zone_system(
            self.bg_frame, self.stops_projected,
            radius_m=float(self.assumptions["path_assignment"]["access_radius_m"]),
            walk_speed_m_per_min=float(
                self.assumptions["path_assignment"]["walk_speed_m_per_min"]),
            stop_index=rn.stop_index)

        hw, vh = baseline_headways(tstats, self.periods)
        hw, k = scale_to_budget(hw, vh, self.budget_vh)

        origins = self.choose_origins()
        costs: list[np.ndarray] = []
        flows: list[np.ndarray] = []
        for per in self.screen_periods:
            od_p = self._period_od(per)
            ph = pattern_headways(rn, hw, per)
            order = np.lexsort((od_p.dest, od_p.origin))
            o_s, d_s, f_s = od_p.origin[order], od_p.dest[order], od_p.flow[order]
            lo = np.searchsorted(o_s, origins, side="left")
            hi = np.searchsorted(o_s, origins, side="right")
            for z, a, b in zip(origins, lo, hi):
                if a == b:
                    continue
                stops, walk = zs.access_of(int(z))
                n = b - a
                if len(stops) == 0:
                    costs.append(np.full(n, np.inf))
                    flows.append(f_s[a:b])
                    continue
                cost, _, _ = generalized_cost(
                    rn, [rn.stop_ids[s] for s in stops], ph, self.weights,
                    self.wait_kwargs, max_rounds=self.max_rounds,
                    source_costs=[self.weights.walking * x for x in walk])
                block = np.empty(n)
                for i in range(a, b):
                    e_stops, e_walk = zs.access_of(int(d_s[i]))
                    block[i - a] = (
                        np.min(cost[e_stops] + self.weights.walking * e_walk)
                        if len(e_stops) else np.inf)
                costs.append(block)
                flows.append(f_s[a:b])

        if not costs:
            return {"generalized_cost": 0.0, "unserved_demand": 0.0,
                    "unreachable_demand": 0.0, "discouraged_demand": 0.0,
                    "served_demand": 0.0, "headway_scale": k}
        out = retention_score(np.concatenate(costs), np.concatenate(flows),
                              self.retention)
        out["headway_scale"] = k
        if label:
            log.info("screen %-28s gc=%.6e unserved=%.0f unreachable=%.0f "
                     "served=%.0f (h x%.4f)", label, out["generalized_cost"],
                     out["unserved_demand"], out["unreachable_demand"],
                     out["served_demand"], k)
        return out

    def screen(self, net, tstats, model: SegmentTimeModel,
               edits: list[GeometryEdit], base: dict[str, float],
               key: str = "", kind: str = "", description: str = ""
               ) -> ScreenResult:
        t = time.time()
        try:
            ed = apply_edits(net, tstats, model, edits)
        except Exception as exc:                      # a proposal can be invalid
            return ScreenResult(key, kind, description,
                                seconds=time.time() - t,
                                error=f"{type(exc).__name__}: {exc}")
        s = self.price(ed.network, ed.tstats)

        def pct(now: float, was: float) -> float:
            return (now / was - 1) * 100 if was else float("nan")

        return ScreenResult(
            key=key, kind=kind, description=description,
            generalized_cost=s["generalized_cost"],
            unserved_flow=s["unserved_demand"],
            served_flow=s["served_demand"],
            unreachable_flow=s["unreachable_demand"],
            discouraged_flow=s["discouraged_demand"],
            gc_change_pct=pct(s["generalized_cost"], base["generalized_cost"]),
            unserved_change_pct=pct(s["unserved_demand"],
                                    base["unserved_demand"]),
            unreachable_change_pct=pct(s["unreachable_demand"],
                                       base["unreachable_demand"]),
            headway_scale=s["headway_scale"],
            veh_hours_at_baseline=ed.report.baseline_veh_hours_after,
            edit_report=ed.report.as_dict(), seconds=time.time() - t)


def screen_frame(results: list[ScreenResult]) -> pd.DataFrame:
    rows = []
    for r in results:
        rows.append({
            "key": r.key, "kind": r.kind,
            "gc_change_pct": r.gc_change_pct,
            "unserved_change_pct": r.unserved_change_pct,
            "unreachable_change_pct": r.unreachable_change_pct,
            "headway_scale": r.headway_scale,
            "veh_hours_at_baseline": r.veh_hours_at_baseline,
            "modelled_share_pct": r.edit_report.get("modelled_share_pct"),
            "veh_hours_freed": r.edit_report.get("veh_hours_freed"),
            "seconds": r.seconds, "error": r.error,
            "description": r.description})
    df = pd.DataFrame(rows)
    if "gc_change_pct" in df:
        df = df.sort_values(["unserved_change_pct", "gc_change_pct"])
    return df.reset_index(drop=True)
