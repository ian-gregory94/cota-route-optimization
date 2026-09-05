"""Tiny production-evaluator spaces for the C10 / gate 4-14 benchmark.

Real pool lines over the real observed-link graph, scored by the real evaluator
through `exp4_score.score_exp4_network`. Small enough to enumerate exhaustively.

The complementarity that makes these deceptive is a property of the objective,
not of the fixtures: the evaluator prices a JOURNEY, so two lines meeting at a
common stop create transfer opportunities worth more than either line carries
alone. Whether a given space actually defeats greedy is TESTED, never assumed --
`exp4_c10_benchmark.py` runs add-only greedy and requires it to miss.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

_POOL = json.loads((ROOT / "outputs/exp4/route_pool.json").read_text())
_BY_RID = {r["rid"]: r for r in _POOL["routes"]}
POOL_VERSION = _POOL["pool_version"]

_state: dict = {}


def _boot():
    """Build the harness once; every case reuses it."""
    if _state:
        return _state
    from cota_opt import geo
    from cota_opt.harness import build_harness
    from cota_opt.linkgraph import LinkGraph, ObservedLink
    from exp3_pin_envelope import load as pin_load

    H = build_harness(seed=20260825, common_lines="same_route",
                      with_pathsets=False)
    sg = geo.stops_gdf(H.baseline.feed, H.assumptions["crs"]["projected"])

    # the observed-link graph, rebuilt from the audited artifact's own source:
    # every consecutive stop pair on every legacy pattern, at its observed time
    links: dict = {}
    for p in H.baseline.network.patterns.values():
        for s in p.segments:
            k = (s.from_stop, s.to_stop)
            if k not in links:
                links[k] = ObservedLink(s.from_stop, s.to_stop,
                                        float(s.run_time_sec), 1, (), 0.0)
    graph = LinkGraph(links=links, out={},
                      stops=tuple(sorted(H.baseline.network.stops)))

    _state.update(H=H, sg=sg, graph=graph, cons=pin_load())
    return _state


def _periods():
    from cota_opt.configs import service_periods
    return sorted(service_periods(_boot()["H"].assumptions))


def _first_dep_by_period() -> dict[str, float]:
    """A departure second INSIDE each period's own window.

    Passing 0.0 for every period put every synthetic trip in `owl`
    (period_of_seconds(0.0) -> owl), so a 2-line network produced 2
    route-periods instead of 12 and the other five periods had no service at
    all. The midpoint of each window is unambiguous and lands the trip where it
    belongs.
    """
    from cota_opt.configs import service_periods
    sp = service_periods(_boot()["H"].assumptions)
    return {name: (lo + hi) / 2.0 * 3600.0 for name, (lo, hi) in sp.items()}


def make_scorer(case: dict):
    """Return (scorer, lines, periods) for one case.

    The scorer runs the PRODUCTION evaluator. It returns
    ``(objective, fitness, feasible, plan)`` where objective is the lambda=2
    scalarization Experiments 1-3 use, so a lower number is better and the
    quantity is the one every previous experiment reported.
    """
    st = _boot()
    from cota_opt.contract import ContractLimits
    from cota_opt.exp4_network import Exp4Selection
    from cota_opt.exp4_score import score_exp4_network

    H, sg, graph = st["H"], st["sg"], st["graph"]
    periods = _periods()
    first_dep = _first_dep_by_period()

    # The envelope is a parameter OF THE SPACE, not of the evaluator, and it
    # has to bind or the space has no tension: with the full legacy budget of
    # ~2,507 vehicle-hours a three-line network uses ~295 and every additional
    # line is free, so more is always better and greedy cannot fail. A binding
    # envelope is what forces the trade-off complementarity can exploit.
    from exp2_treatments import pinned
    vh = float(case["veh_hour_budget"])
    peak = {p: float(case.get("peak_vehicle_budget", 40.0)) for p in periods}
    cons = pinned(vh, peak)
    limits = ContractLimits(
        veh_hour_budget=vh,
        peak_vehicle_budget=float(case.get("peak_vehicle_budget", 40.0)),
        required_waiting_model="same_route")
    lam = 2.0
    eff = case.get("effort", (20_000, 1, 0))

    def scorer(sel: Exp4Selection):
        try:
            scored, _ = score_exp4_network(
                sel, harness=H, stops_gdf=sg, pool=_BY_RID, graph=graph,
                pool_version=POOL_VERSION, first_dep_sec_by_period=first_dep,
                limits=limits, constraints=cons, lam=lam, seed=20260825,
                iterations=eff[0], restarts=eff[1], width=eff[2],
                waiting_model="same_route", starts="greedy", allow_off=True)
        except Exception as e:                       # infeasible or refused
            return float("inf"), {"error": f"{type(e).__name__}: {e}"[:200]}, \
                False, {}
        m = scored.metrics
        obj = float(m.get("objective", float("inf")))
        return obj, {k: v for k, v in m.items()
                     if isinstance(v, (int, float))}, True, scored.plan

    return scorer, list(case["lines"]), periods


#: The spaces. Chosen for structural variety, not tuned to a wanted answer:
#: each names a different reason two lines might complement each other, and the
#: benchmark tests whether that reason actually defeats greedy.
CASES = [
    {
        "name": "shared_junction_pair",
        "complementarity": "two short lines crossing at shared stops: alone "
                           "each serves a corridor, together they open "
                           "transfers between both corridors",
        "lines": ["syn-9a1726e4c4a0670b", "syn-e8ce379fa4507794",
                  "syn-e33ebec18132c464", "syn-e7c589431bb22c3b",
                  "syn-2663c6d04f289b58"],
        "max_lines": 3, "min_lines": 1, "effort": (20_000, 1, 0),
        "veh_hour_budget": 200.0, "peak_vehicle_budget": 18.0,
        "seed": ["syn-9a1726e4c4a0670b"],
    },
    {
        "name": "trunk_plus_feeder",
        "complementarity": "a long trunk and a short feeder: the feeder alone "
                           "reaches little, the trunk alone misses the "
                           "feeder's catchment, together they chain",
        "lines": ["syn-2663c6d04f289b58", "syn-fc6d21f652a0cc01",
                  "syn-9a1726e4c4a0670b", "syn-60f95ff936eeeacd",
                  "syn-e7c589431bb22c3b"],
        "max_lines": 3, "min_lines": 1, "effort": (20_000, 1, 0),
        "veh_hour_budget": 160.0, "peak_vehicle_budget": 14.0,
        "seed": ["syn-2663c6d04f289b58"],
    },
    {
        "name": "legacy_vs_synthetic",
        "complementarity": "a reconstructed legacy line against synthetic "
                           "alternatives, so the incumbent-is-optimal case is "
                           "in the suite too",
        "lines": ["syn-0a0e2e5cac7df60e", "syn-e33ebec18132c464",
                  "syn-e7c589431bb22c3b", "syn-9a1726e4c4a0670b"],
        "max_lines": 3, "min_lines": 1, "effort": (20_000, 1, 0),
        "veh_hour_budget": 120.0, "peak_vehicle_budget": 10.0,
        "seed": ["syn-0a0e2e5cac7df60e"],
    },
]
