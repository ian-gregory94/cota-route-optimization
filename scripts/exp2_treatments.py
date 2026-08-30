#!/usr/bin/env python3
"""Experiment 2: does a path-level decision representation beat a route-level one?

The causal question, unchanged by the Model B remediation:

    Does the more granular path-based decision representation uncover materially
    better feasible service plans than the simpler route-level representation,
    when both are given comparable opportunities and evaluated under the same
    corrected passenger waiting model?

Two treatments, one shared candidate universe, one evaluator:

* **route-level** — frequencies chosen against an aggregate model with no path
  assignment, so passengers cannot re-route when a headway moves;
* **path-level** — frequencies chosen against the Model B path model.

Both then have their plans **reconstructed and independently re-scored by the
frozen Model B evaluator on the same network**, and only those independent
scores are compared. An optimizer's own objective is never compared across
treatments: the route-level optimizer's objective is not the same function as
the path-level one, so comparing them would measure the disagreement between
two yardsticks rather than the quality of two plans. That is exactly the error
D3 caught, and it is worth 15 percentage points of apparent unserved reduction.

The gap between what an optimizer claims and what the independent evaluator
says is *recorded per plan*, not silently discarded, because its size is the
finding: a route-level optimizer that believes it saved 22% and delivers 7% is
not a slightly-optimistic optimizer, it is a different experiment.

Representation asymmetry, stated rather than hidden: the route-level treatment
has no path candidate set, because it has no paths. Both treatments see the same
*geometry* candidates and the same operating envelope. Nothing here interprets
an advantage arising from unequal candidate access as a treatment effect —
there is no such access to be unequal about, and the path sets exist only inside
the evaluator both treatments are scored by.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from types import SimpleNamespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from cota_opt import geo
from cota_opt.cache import ResultStore, cached, digest
from cota_opt.configs import load_constraints, load_cost_weights, service_periods
from cota_opt.cost import CostWeights
from cota_opt.exp1 import build_setup as route_level_setup
from cota_opt.exp2 import build_setup as path_level_setup
from cota_opt.experiment import Experiment
from cota_opt.frequency import FrequencyPlan, optimize_frequencies
from cota_opt.geometry import SegmentTimeModel, apply_edits
from cota_opt.candidates import generate_all, stop_context

log = logging.getLogger("exp2treat")
OUT = ROOT / "outputs"
SEP = "::"


def key_str(k) -> str:
    return f"{k[0]}{SEP}{k[1]}"


class DiskPathsets:
    """A ``pathset_cache`` for :func:`cota_opt.exp2.build_setup` that survives
    process death.

    Every edited network is outside the ordinary cache key scheme, so each
    candidate paid ~7 minutes rebuilding six periods of path sets — and paid it
    again from scratch every time the run was restarted. That is why a run that
    died twice had banked nothing but the control cells.

    The key is a content hash of the RAPTOR network, the zone system, the OD
    table and the enumeration parameters: exactly the inputs
    :func:`build_pathset` reads. It is deliberately *not* the candidate's name.
    Keying a path-set cache by name is the bug that silently reused the wrong
    path sets once already; a content key cannot make that mistake, because a
    network that differs at all produces a different key.
    """

    def __init__(self, netsig: str, params: dict):
        self.netsig = netsig
        self.params = params

    def _key(self, per: str) -> tuple[str, dict]:
        return "edited-pathset", {"net": self.netsig, "period": per,
                                  **self.params}

    def __contains__(self, per: str) -> bool:
        from cota_opt.cache import cache_dir, key_of
        name, params = self._key(per)
        return (cache_dir() / f"{key_of(name, params)}.pkl").exists()

    def __getitem__(self, per: str):
        name, params = self._key(per)
        def _absent():
            raise KeyError(per)          # __contains__ said it was there
        return cached(name, params, _absent)

    def __setitem__(self, per: str, ps) -> None:
        name, params = self._key(per)
        cached(name, params, lambda: ps)


class _Baseline:
    """A Baseline view over an edited network, sharing everything else."""

    def __init__(self, b, net, tstats):
        self._b, self.network, self.tstats = b, net, tstats

    def __getattr__(self, k):
        return getattr(self._b, k)


def pinned(vh: float, peak: dict) -> dict:
    c = load_constraints()
    return {**c, "resource": {**c["resource"],
                              "weekday_revenue_vehicle_hours": float(vh),
                              "peak_fleet_by_period": {k: float(v)
                                                       for k, v in peak.items()}}}


def fit_incumbent(setup, budget_vh: float, label: str = ""):
    """Scale a network's own schedule until it fits the pinned budget.

    Both treatments must start from equivalent plans or the comparison measures
    starting points. A splice lengthens a route, so the edited network's own
    schedule can cost more than the envelope allows -- by as little as 0.4
    vehicle-hours, which is enough for the optimizer to discard the incumbent
    and fall back to a greedy build.
    """
    plan = setup.baseline_plan
    fit = setup.model.evaluate(plan)
    k = fit.revenue_veh_hours / budget_vh
    if k <= 1.0:
        return plan, 1.0
    for bump in (1.0, 1.01, 1.02, 1.05, 1.10, 1.20):
        scaled = FrequencyPlan({key: h * k * bump
                                for key, h in plan.headways.items()})
        if setup.model.evaluate(scaled).revenue_veh_hours <= budget_vh:
            log.info("    %s incumbent rescaled x%.4f", label, k * bump)
            return scaled, k * bump
    return plan, k


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lambdas", type=str, default="1,2,4")
    ap.add_argument("--iterations", type=int, default=60_000)
    ap.add_argument("--restarts", type=int, default=2)
    ap.add_argument("--width", type=int, default=32)
    ap.add_argument("--seed", type=int, default=20260825)
    ap.add_argument("--candidates", type=str, default="exp2_candidate_set.json")
    ap.add_argument("--max-candidates", type=int, default=0,
                    help="0 = every member of the frozen set")
    ap.add_argument("--control-only", action="store_true",
                    help="unedited network only: the treatment question on its own")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    lams = [float(x) for x in args.lambdas.split(",")]

    frozen = json.loads((OUT / args.candidates).read_text())
    members = list(frozen["members"])
    if args.max_candidates:
        members = members[:args.max_candidates]
    log.info("shared candidate universe: %d (%s)", len(members),
             frozen["rule"].split(".")[0])

    exp = Experiment(
        name="exp2_treatments", seed=args.seed,
        algorithm="route-level vs path-level decision representation, both "
                  "plans independently re-scored by the frozen Model B evaluator",
        config_files=["assumptions.yaml", "cost_weights.yaml",
                      "constraints.yaml", "sources.yaml"])
    store = ResultStore(OUT / "exp2_treatments.jsonl")

    from cota_opt.harness import build_harness
    H = build_harness(seed=args.seed, common_lines="same_route")
    a = H.assumptions
    w = CostWeights.from_config(load_cost_weights())
    sg = geo.stops_gdf(H.baseline.feed, a["crs"]["projected"])
    stm = SegmentTimeModel.fit(H.baseline.network, sg)
    periods = service_periods(a)

    base_vh = float(H.baseline.tstats["runtime_min"].sum() / 60.0)
    ctrl = H.setup(with_crowding=False, lock_classes=("peak_express",))
    peak = dict(ctrl.model.evaluate(ctrl.baseline_plan).peak_by_period)
    cons = pinned(base_vh, peak)
    log.info("envelope pinned: %.1f veh-hours; waiting model %s", base_vh,
             H.common_lines)
    del ctrl

    zf = np.zeros(H.zones.n)
    np.add.at(zf, H.od.origin, H.od.flow)
    np.add.at(zf, H.od.dest, H.od.flow)
    ctx = stop_context(H.baseline.network, H.zones, H.raptor.stop_ids, stm)
    express = {r for r, c in H.classes.items() if c.klass == "peak_express"}
    trips = H.baseline.tstats.groupby("route_id").size().to_dict()
    by_key = {c.key: c for c in generate_all(
        H.baseline.network, ctx, H.zones, H.raptor.stop_ids, zf, trips,
        exclude_routes=express, per_kind=12)}

    jobs = [("control", [])]
    if not args.control_only:
        jobs += [(k, [by_key[k]]) for k in members if k in by_key]

    rows = []
    # Only the evaluator's `checks` are kept, not the evaluator: holding a
    # judge alive would pin six periods of path sets past the gc that exists
    # to release them.
    last_checks: dict | None = None
    effort = f"{args.iterations}/{args.restarts}/{args.width}"

    def cells_for(label: str) -> list[str]:
        return [f"t|{label}|{t}|lam{m}|{effort}"
                for t in ("route_level", "path_level") for m in lams]

    for label, edits in jobs:
        # A finished network must not be rebuilt. Each edited network costs
        # ~7 minutes of uncached path enumeration before a single cell is
        # solved, so a run that is restarted (this one has been, twice) spent
        # all its time re-deriving results it had already banked. Check the
        # store first and skip the build outright.
        banked = cells_for(label)
        if all(store.has(c) for c in banked):
            for c in banked:
                rows.append({k: v for k, v in store.get(c).items()
                             if k not in ("cell", "plan")})
            log.info("%-26s all %d cells already banked, skipping build",
                     label, len(banked))
            continue

        net = H.baseline.network
        ts = H.baseline.tstats
        if edits:
            ed = apply_edits(net, ts, stm, edits)
            net, ts = ed.network, ed.tstats
        b_ed = _Baseline(H.baseline, net, ts)

        # the evaluator both treatments are judged by, built once per network
        from cota_opt.raptor import build_raptor_network
        from cota_opt.odmatrix import build_zone_system
        from cota_opt.configs import period_of_seconds
        from cota_opt.routeclass import classify_routes
        pa = a["path_assignment"]
        rn = build_raptor_network(
            H.baseline.feed, net, ts, sg,
            walk_radius_m=float(pa["walk_radius_m"]),
            walk_speed_m_per_min=float(pa["walk_speed_m_per_min"]),
            periods=periods, with_timetable=False)
        zs = build_zone_system(
            H.baseline.demand["bg_frame"], sg,
            radius_m=float(pa["access_radius_m"]),
            walk_speed_m_per_min=float(pa["walk_speed_m_per_min"]),
            stop_index=rn.stop_index)
        tp = ts.copy()
        tp["period"] = tp["first_dep_sec"].map(
            lambda x: period_of_seconds(x, periods))
        classes = classify_routes(tp.dropna(subset=["period"]), H.baseline.routes)

        # path sets for an edited network are outside the ordinary cache key
        # scheme, so key them on the content of what they are built from
        psc = DiskPathsets(
            digest((rn, zs, H.od, ts[["route_id", "direction_id",
                                      "first_dep_sec", "runtime_min"]])),
            {"seed": args.seed, "n_random_scenarios": 0,
             "common_lines": "same_route", "with_crowding": False,
             "lock_classes": ["peak_express"], "shares": dict(
                 a["demand_proxy"]["period_shares"]),
             "max_rounds": int(a["path_assignment"]["max_rounds"]),
             "max_paths_per_od": int(a["path_assignment"]["max_paths_per_od"]),
             "weights": w.as_dict() if hasattr(w, "as_dict") else repr(w),
             "waiting": dict(a["waiting"])})

        judge = path_level_setup(b_ed, rn, zs, H.od, seed=args.seed,
                                 route_classes=classes, with_crowding=False,
                                 lock_classes=("peak_express",),
                                 constraints=cons, n_random_scenarios=0,
                                 pathset_cache=psc,
                                 common_lines="same_route")
        rl = route_level_setup(b_ed, constraints=cons, weights=w)
        base_fit = judge.model.evaluate(judge.baseline_plan)
        last_checks = dict(judge.checks)

        for treat, setup in (("route_level", rl), ("path_level", judge)):
            inc, scale = fit_incumbent(setup, setup.budget.revenue_veh_hours,
                                       f"{label}/{treat}")
            for m in lams:
                cell = f"t|{label}|{treat}|lam{m}|{effort}"
                if store.has(cell):
                    rows.append({k: v for k, v in store.get(cell).items()
                                 if k not in ("cell", "plan")})
                    continue
                t0 = time.time()
                r = optimize_frequencies(
                    setup.model, setup.budget, ladder=[], unserved_multiplier=m,
                    local_search_iterations=args.iterations, seed=args.seed,
                    ladders=setup.ladders, initial=inc,
                    n_restarts=args.restarts, candidate_width=args.width,
                    greedy_start=False)

                # reconstruct the plan on the judge's own key order and score it
                hw = dict(judge.baseline_plan.headways)
                for k, v in r.plan.headways.items():
                    if k in hw:
                        hw[k] = float(v)
                f = judge.model.evaluate_array(
                    np.array([hw[k] for k in judge.model.keys]))

                rec = {
                    "network": label, "treatment": treat, "lambda": m,
                    "seconds": time.time() - t0, "incumbent_scale": scale,
                    "claimed_gc": r.fitness.generalized_cost,
                    "claimed_unserved": r.fitness.unserved_demand,
                    "modelB_gc": f.generalized_cost,
                    "modelB_unserved": f.unserved_demand,
                    "modelB_served": f.served_demand,
                    "modelB_gc_per_trip": f.gc_per_served_trip,
                    "modelB_veh_hours": f.revenue_veh_hours,
                    "gc_vs_base_pct": (f.generalized_cost
                                       / base_fit.generalized_cost - 1) * 100,
                    "unserved_vs_base_pct": (f.unserved_demand
                                             / base_fit.unserved_demand - 1) * 100,
                    "served_vs_base_pct": (f.served_demand
                                           / base_fit.served_demand - 1) * 100,
                    "gc_per_trip_vs_base_pct": (f.gc_per_served_trip
                                                / base_fit.gc_per_served_trip - 1) * 100,
                    "vh_vs_budget_pct": (f.revenue_veh_hours
                                         / judge.budget.revenue_veh_hours - 1) * 100,
                    # the optimizer's own claim against the independent score:
                    # recorded because its size is the finding, not an aside
                    "claim_gap_unserved_pct": (
                        (r.fitness.unserved_demand / f.unserved_demand - 1) * 100
                        if f.unserved_demand else float("nan")),
                    "n_route_periods_moved": int(sum(
                        1 for k, v in r.plan.headways.items()
                        if k in hw and abs(v - judge.baseline_plan.headways[k]) > 1e-9)),
                }
                store.put(cell, {**rec, "plan": {key_str(k): float(v)
                                                 for k, v in hw.items()}})
                rows.append(rec)
                log.info("  %-26s %-11s lam=%-4s %4.0fs  Model B gc %+7.3f%% "
                         "unserved %+7.3f%%  (optimizer claimed %+7.3f%%)",
                         label, treat, m, rec["seconds"], rec["gc_vs_base_pct"],
                         rec["unserved_vs_base_pct"], rec["claim_gap_unserved_pct"])
        del judge, rl

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "exp2_treatments.csv", index=False)
    df.to_csv(exp.artifact_path("treatments.csv"), index=False)

    ctl = df[df["network"] == "control"]
    piv = ctl.pivot_table(index="lambda", columns="treatment",
                          values=["unserved_vs_base_pct", "gc_vs_base_pct",
                                  "gc_per_trip_vs_base_pct"])
    if last_checks is not None:
        exp.declare_evaluator(SimpleNamespace(checks=last_checks),
                              expected="same_route")
    exp.log_metrics(lambdas=lams, n_networks=len(jobs),
                    effort=f"{args.iterations}/{args.restarts}/{args.width}",
                    candidate_set=args.candidates, rows=rows)
    exp.save()

    pd.set_option("display.width", 200)
    print("\n" + "=" * 100)
    print("EXPERIMENT 2 — route-level vs path-level decision representation")
    print("both plans independently re-scored by the frozen Model B evaluator")
    print("=" * 100)
    print("\nUNEDITED NETWORK (the treatment question on its own)")
    print(ctl[["treatment", "lambda", "gc_vs_base_pct", "unserved_vs_base_pct",
               "served_vs_base_pct", "gc_per_trip_vs_base_pct",
               "claim_gap_unserved_pct"]].round(3).to_string(index=False))
    print("\n  claim_gap_unserved_pct = how much LESS unserved demand the "
          "optimizer believed it had than Model B measures.")
    if len(jobs) > 1:
        print("\nBY CANDIDATE NETWORK, lambda=2")
        s = df[(df["lambda"] == 2.0) & (df["network"] != "control")]
        print(s[["network", "treatment", "gc_vs_base_pct",
                 "unserved_vs_base_pct"]].round(3).to_string(index=False))
    print(f"\nartifacts: {exp.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
