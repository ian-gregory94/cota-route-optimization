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


#: The benchmark spaces, DISCOVERED rather than hand-tuned.
#:
#: `scripts/exp4_find_deceptive.py` scanned 45 candidate spaces built from short
#: pool lines under binding envelopes, enumerated each exhaustively with the
#: production evaluator, and ran add-only greedy against the result. 14 of 45
#: defeated greedy on OBJECTIVE (a different network of equal objective is a
#: flat optimum, not a deception, and is not counted). The five frozen here are
#: one per structural mechanism, so the suite is not five versions of one trick.
#:
#: Each records the optimum the oracle found at discovery time. The benchmark
#: re-derives it rather than trusting it -- a frozen expectation that is never
#: recomputed is a number nobody checks.
CASES = [
    {
        "name": "greedy_finds_nothing",
        "complementarity": "add-only greedy reaches no feasible network at all from its seed, while three lines together fit the envelope: the first line it adds consumes the budget and every extension is infeasible",
        "lines": [
            "syn-e7c589431bb22c3b",
            "syn-91cfb5fd76db5ab6",
            "syn-a13da236edef295b",
            "syn-2663c6d04f289b58",
            "syn-9a1726e4c4a0670b"
        ],
        "max_lines": 3,
        "min_lines": 1,
        "effort": [
            20000,
            1,
            0
        ],
        "veh_hour_budget": 160.0,
        "peak_vehicle_budget": 10.0,
        "seed": [
            "syn-e7c589431bb22c3b"
        ],
        "discovered_as_space": 2,
        "expected_optimum": [
            "syn-91cfb5fd76db5ab6",
            "syn-9a1726e4c4a0670b",
            "syn-a13da236edef295b"
        ],
        "expected_optimum_objective": 3632624.1165919495,
        "greedy_objective_when_found": None
    },
    {
        "name": "large_gap",
        "complementarity": "the largest measured deception: greedy stops two lines short of an optimum worth 18,901 more in objective, because the pair it needs is only worth adding together",
        "lines": [
            "syn-e8ce379fa4507794",
            "syn-47ece08f5664f6eb",
            "syn-f3421db8fc18598a",
            "syn-0811e763f266fdf9",
            "syn-8352b3f4b3bcd2f2"
        ],
        "max_lines": 3,
        "min_lines": 1,
        "effort": [
            20000,
            1,
            0
        ],
        "veh_hour_budget": 160.0,
        "peak_vehicle_budget": 18.0,
        "seed": [
            "syn-e8ce379fa4507794"
        ],
        "discovered_as_space": 27,
        "expected_optimum": [
            "syn-0811e763f266fdf9",
            "syn-47ece08f5664f6eb",
            "syn-f3421db8fc18598a"
        ],
        "expected_optimum_objective": 3623241.1731768716,
        "greedy_objective_when_found": 3642142.0740542635
    },
    {
        "name": "moderate_gap",
        "complementarity": "greedy settles for two lines where three fit; the third is unattractive until the other two are present",
        "lines": [
            "syn-91cfb5fd76db5ab6",
            "syn-fc6d21f652a0cc01",
            "syn-2663c6d04f289b58",
            "syn-60f95ff936eeeacd",
            "syn-e7c589431bb22c3b"
        ],
        "max_lines": 3,
        "min_lines": 1,
        "effort": [
            20000,
            1,
            0
        ],
        "veh_hour_budget": 120.0,
        "peak_vehicle_budget": 18.0,
        "seed": [
            "syn-91cfb5fd76db5ab6"
        ],
        "discovered_as_space": 11,
        "expected_optimum": [
            "syn-60f95ff936eeeacd",
            "syn-91cfb5fd76db5ab6",
            "syn-fc6d21f652a0cc01"
        ],
        "expected_optimum_objective": 3628620.6269035037,
        "greedy_objective_when_found": 3636395.894030559
    },
    {
        "name": "greedy_overbuilds",
        "complementarity": "greedy takes MORE lines than the optimum and is worse for it -- adding service inside a binding envelope forces frequency down elsewhere",
        "lines": [
            "syn-2663c6d04f289b58",
            "syn-e8ce379fa4507794",
            "syn-d5325fe875cf4d92",
            "syn-cc10538c6cdfdd3d",
            "syn-60f95ff936eeeacd"
        ],
        "max_lines": 3,
        "min_lines": 1,
        "effort": [
            20000,
            1,
            0
        ],
        "veh_hour_budget": 200.0,
        "peak_vehicle_budget": 18.0,
        "seed": [
            "syn-2663c6d04f289b58"
        ],
        "discovered_as_space": 8,
        "expected_optimum": [
            "syn-cc10538c6cdfdd3d",
            "syn-e8ce379fa4507794"
        ],
        "expected_optimum_objective": 3642142.0740542635,
        "greedy_objective_when_found": 3645546.069348904
    },
    {
        "name": "weak_junction",
        "complementarity": "the smallest stop overlap in the suite (6 shared stops), so the complementarity is thin and the gap is only 633 -- included because a suite of only dramatic cases would not test the margin",
        "lines": [
            "syn-dcef27a3822e47f8",
            "syn-ffe3ea8843390b99",
            "syn-edf252439b3ffff1",
            "syn-d0292863e848ff46",
            "syn-0a0e2e5cac7df60e"
        ],
        "max_lines": 3,
        "min_lines": 1,
        "effort": [
            20000,
            1,
            0
        ],
        "veh_hour_budget": 90.0,
        "peak_vehicle_budget": 10.0,
        "seed": [
            "syn-dcef27a3822e47f8"
        ],
        "discovered_as_space": 22,
        "expected_optimum": [
            "syn-0a0e2e5cac7df60e",
            "syn-d0292863e848ff46",
            "syn-ffe3ea8843390b99"
        ],
        "expected_optimum_objective": 3636083.6261476353,
        "greedy_objective_when_found": 3636716.735227376
    }
]
