#!/usr/bin/env python3
"""Experiment 2B / D22 — joint search over SETS of geometry edits.

D20 found that four individually beneficial splices are jointly worse than
making no change at all, and that the second edit already costs half the
benefit of the first. That kills the obvious way to answer "which edits should
COTA make?": ranking candidates and taking the top N does not give the best set
of N, because the effect of a set is not the sum of its members' effects.

So this does not rank and compose. It enumerates.

The frozen 12-candidate set admits **240 structurally feasible subsets**, because
a splice consumes both of its routes -- `geometry.apply_edits` removes them from
its live set and raises if a later edit names one -- so any two splices sharing
a route cannot coexist. That constraint is severe enough to make the whole
space enumerable, which is a much better position than heuristic search: there
is no candidate ordering to defend, no greedy path to justify, and no way for
the answer to be an artifact of where the search started.

Three stages, so that compute is spent in proportion to what a number is used
for:

* **Stage A — discovery.** Every feasible subset, lambda=2, frequency
  re-optimized inside the pinned envelope, scored by the frozen Model B
  evaluator, at exactly the effort the singles were measured at so the two are
  comparable. Ranks sets and sizes nothing.
* **Stage B — robustness.** The promoted sets across lambda in {1, 2, 4}. Path
  sets are content-cached from Stage A, so this is nearly free on the build
  side.
* **Stage C — certification.** Full effort and three seeds, on the winner and
  on the incumbent it has to beat, and on nothing else.

Every subset is checkpointed as its own cell, so a killed run resumes at the
subset boundary rather than the beginning. Subsets are visited in ascending
cardinality, so an interrupted run leaves complete evidence for the small sets
rather than partial evidence everywhere.

Interaction is computed for every set: measured effect minus the sum of its
members' measured single effects. That number is the experiment's actual
subject. A set whose interaction term is zero would mean D20 was a fluke of the
particular four edits it tested; a set whose members cancel tells COTA which
interventions are substitutes for each other.
"""
from __future__ import annotations

import argparse
import itertools
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from cota_opt import geo
from cota_opt.cache import ResultStore, digest
from cota_opt.candidates import generate_all, stop_context
from cota_opt.configs import load_constraints, load_cost_weights, service_periods
from cota_opt.cost import CostWeights
from cota_opt.exp2 import build_setup as path_level_setup
from cota_opt.experiment import Experiment
from cota_opt.frequency import optimize_frequencies
from cota_opt.geometry import SegmentTimeModel, apply_edits

sys.path.insert(0, str(ROOT / "scripts"))
from exp2_treatments import DiskPathsets, _Baseline, fit_incumbent, pinned, key_str

log = logging.getLogger("exp2b")
OUT = ROOT / "outputs"


def feasible_subsets(cands: list[str],
                     incompatible: set[tuple[str, str]]) -> list[tuple[str, ...]]:
    """Every subset no two of whose members share a route, smallest first."""
    out: list[tuple[str, ...]] = []
    for r in range(len(cands) + 1):
        for combo in itertools.combinations(cands, r):
            if any((a, b) in incompatible
                   for a, b in itertools.combinations(combo, 2)):
                continue
            out.append(combo)
    return out


def set_key(combo: tuple[str, ...]) -> str:
    """Canonical name for a subset: sorted, so member order cannot make two
    names for one set and cannot make the cache miss on a permutation."""
    return "+".join(sorted(combo)) if combo else "<none>"


def analyse(df: pd.DataFrame, floor: float) -> pd.DataFrame:
    """Derive the comparison and interaction columns from the raw scores.

    Kept out of ``main`` so it can be tested without a 22-hour sweep in front
    of it. Everything here is arithmetic on columns the solve already wrote;
    nothing is re-solved, and nothing is inferred.
    """
    # every derived column exists before anything fills it: a stage that
    # filters out the zero-edit row (or a run cut short before it) must leave
    # the comparison MISSING rather than crash on the subtraction below, and a
    # missing comparison must not be mistaken for a measured zero
    for c in ("gc_vs_noedit_pct", "unserved_vs_noedit_pct",
              "served_vs_noedit_pct", "gc_per_trip_vs_noedit_pct",
              "sum_of_singles_unserved_pct", "sum_of_singles_gc_pct"):
        if c not in df:
            df[c] = float("nan")
    if df.empty:
        for c in ("interaction_unserved_pts", "interaction_gc_pts"):
            df[c] = float("nan")
        df["interaction_class"] = ""
        return df

    for m in df["lambda"].unique():
        sel = df["lambda"] == m
        base = df[sel & (df["set_key"] == "<none>")]
        if base.empty:
            log.warning("no zero-edit row at lambda=%s; the vs-no-edit "
                        "comparison is unavailable for it", m)
            continue
        b = base.iloc[0]
        for col, ref in (("gc", "modelB_gc"),
                         ("unserved", "modelB_unserved"),
                         ("served", "modelB_served"),
                         ("gc_per_trip", "modelB_gc_per_trip")):
            df.loc[sel, f"{col}_vs_noedit_pct"] = (
                df.loc[sel, ref] / float(b[ref]) - 1) * 100

    for m in df["lambda"].unique():
        sel = df["lambda"] == m
        one = df[sel & (df["cardinality"] == 1)]
        singles = {r["set_key"]: r["unserved_vs_noedit_pct"]
                   for _, r in one.iterrows()}
        gsingles = {r["set_key"]: r["gc_vs_noedit_pct"]
                    for _, r in one.iterrows()}

        def _sum(members, tab):
            vals = [tab.get(k) for k in members]
            return (float(np.sum(vals)) if vals and all(
                v is not None and np.isfinite(v) for v in vals)
                else float("nan"))

        idx = df.index[sel]
        df.loc[idx, "sum_of_singles_unserved_pct"] = [
            _sum(df.at[i, "members"], singles) for i in idx]
        df.loc[idx, "sum_of_singles_gc_pct"] = [
            _sum(df.at[i, "members"], gsingles) for i in idx]

    df["interaction_unserved_pts"] = (df["unserved_vs_noedit_pct"]
                                      - df["sum_of_singles_unserved_pct"])
    df["interaction_gc_pts"] = (df["gc_vs_noedit_pct"]
                                - df["sum_of_singles_gc_pct"])

    def _interp(row) -> str:
        v = row["interaction_unserved_pts"]
        if not np.isfinite(v) or row["cardinality"] < 2:
            return ""
        if abs(v) < floor:
            return "additive within measurement"
        # unserved demand is a cost, so a POSITIVE interaction term means the
        # set delivered LESS than its members promised separately
        return "substituting" if v > 0 else "synergistic"

    df["interaction_class"] = df.apply(_interp, axis=1)
    return df


def noise_floor(default: float = 0.288) -> float:
    """The floor committed before the single-candidate evaluations ran."""
    try:
        cl = json.loads((OUT / "exp2_candidate_classes.json").read_text())
        return float(cl["rule"]["noise_floor_pts"])
    except Exception:
        log.warning("using the default %.3f-point floor", default)
        return default


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["A", "B"], default="A")
    ap.add_argument("--lambdas", type=str, default="")
    ap.add_argument("--iterations", type=int, default=60_000)
    ap.add_argument("--restarts", type=int, default=2)
    ap.add_argument("--width", type=int, default=32)
    ap.add_argument("--seed", type=int, default=20260825)
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after this many subsets; for smoke-testing the "
                         "pipeline before committing the full enumeration")
    ap.add_argument("--max-cardinality", type=int, default=0,
                    help="0 = every feasible subset; otherwise stop at this size")
    ap.add_argument("--promote", type=int, default=12,
                    help="stage B: how many stage-A sets to carry forward, on "
                         "top of every cardinality winner")
    ap.add_argument("--cache-pathsets", action="store_true",
                    help="persist each edited network's path sets. Off in "
                         "stage A: 240 subsets would be ~14 GB. On in stage B, "
                         "where the same dozen networks are revisited across "
                         "three lambdas.")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    lams = ([float(x) for x in args.lambdas.split(",")] if args.lambdas
            else ([2.0] if args.stage == "A" else [1.0, 2.0, 4.0]))
    if args.stage == "B":
        args.cache_pathsets = True

    classes = json.loads((OUT / "exp2_candidate_classes.json").read_text())
    cands = list(classes["rule"]["eligible_for_2B"])
    incompat = set()
    for pr in classes["incompatible_pairs"]:
        incompat.add((pr["a"], pr["b"]))
        incompat.add((pr["b"], pr["a"]))

    subsets = feasible_subsets(cands, incompat)
    if args.max_cardinality:
        subsets = [c for c in subsets if len(c) <= args.max_cardinality]
    if args.limit:
        subsets = subsets[:args.limit]

    if args.stage == "B":
        sa = pd.read_csv(OUT / "exp2b_stageA.csv")
        sa = sa.sort_values("unserved_vs_noedit_pct")
        keep = list(sa.head(args.promote)["set_key"])
        for k, grp in sa.groupby("cardinality"):
            best = grp.sort_values("unserved_vs_noedit_pct").iloc[0]["set_key"]
            if best not in keep:
                keep.append(best)
        want = set(keep)
        subsets = [c for c in subsets if set_key(c) in want]
        log.info("stage B on %d promoted sets: %s", len(subsets), keep)

    by_size: dict[int, int] = {}
    for c in subsets:
        by_size[len(c)] = by_size.get(len(c), 0) + 1
    log.info("stage %s: %d subsets, by cardinality %s, lambdas %s, effort %d/%d/%d",
             args.stage, len(subsets), dict(sorted(by_size.items())), lams,
             args.iterations, args.restarts, args.width)

    exp = Experiment(
        name=f"exp2b_subsets_stage{args.stage}", seed=args.seed,
        algorithm="exhaustive enumeration of structurally feasible geometry "
                  "edit subsets; frequency re-optimized per subset inside one "
                  "pinned envelope; every plan scored by the frozen Model B "
                  "evaluator",
        config_files=["assumptions.yaml", "cost_weights.yaml",
                      "constraints.yaml", "sources.yaml"])
    store = ResultStore(OUT / "exp2b_subsets.jsonl")

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
    missing = [k for k in cands if k not in by_key]
    if missing:
        raise SystemExit(f"candidate(s) not reproducible from the generator: "
                         f"{missing}")

    effort = f"{args.iterations}/{args.restarts}/{args.width}"
    rows: list[dict] = []
    t_start = time.time()

    # Two different comparisons, and conflating them would answer the wrong
    # question. `*_vs_base_pct` measures a set against ITS OWN network with
    # baseline frequencies -- how much frequency re-optimization gains on that
    # geometry. That is not what 2B is asking. "Which set of edits is best"
    # compares a set's optimized outcome against the UNEDITED network's
    # optimized outcome, which is `*_vs_noedit_pct` below and is the column
    # everything is ranked on. Unserved demand and generalized cost are both
    # totals over the same OD table under the same evaluator, so they are
    # directly comparable across networks; that is the same comparison
    # run_exp2_eval.py makes, so 2B's singles line up with the singles already
    # measured there.
    noedit: dict[str, dict[str, float]] = {}
    for m in lams:
        c = f"b|<none>|lam{m}|{effort}"
        if store.has(c):
            r0 = store.get(c)
            noedit[str(m)] = {k: float(r0[k]) for k in
                              ("modelB_gc", "modelB_unserved", "modelB_served",
                               "modelB_gc_per_trip")}

    for i, combo in enumerate(subsets, 1):
        name = set_key(combo)
        want = [f"b|{name}|lam{m}|{effort}" for m in lams]
        if all(store.has(c) for c in want):
            for c in want:
                rows.append({k: v for k, v in store.get(c).items()
                             if k not in ("cell", "plan")})
            continue

        edits = [by_key[k] for k in sorted(combo)]
        net, ts = H.baseline.network, H.baseline.tstats
        if edits:
            ed = apply_edits(net, ts, stm, edits)
            net, ts = ed.network, ed.tstats

        b_ed = _Baseline(H.baseline, net, ts)
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
        rcls = classify_routes(tp.dropna(subset=["period"]), H.baseline.routes)

        psc = None
        if args.cache_pathsets:
            psc = DiskPathsets(
                digest((rn, zs, H.od, ts[["route_id", "direction_id",
                                          "first_dep_sec", "runtime_min"]])),
                {"seed": args.seed, "n_random_scenarios": 0,
                 "common_lines": "same_route", "with_crowding": False,
                 "lock_classes": ["peak_express"],
                 "shares": dict(a["demand_proxy"]["period_shares"]),
                 "max_rounds": int(pa["max_rounds"]),
                 "max_paths_per_od": int(pa["max_paths_per_od"]),
                 "weights": repr(w), "waiting": dict(a["waiting"])})

        judge = path_level_setup(b_ed, rn, zs, H.od, seed=args.seed,
                                 route_classes=rcls, with_crowding=False,
                                 lock_classes=("peak_express",),
                                 constraints=cons, n_random_scenarios=0,
                                 pathset_cache=psc, common_lines="same_route")
        # the reference every set is measured against is the SAME network with
        # no frequency change, so an edit's own vehicle-hour cost is charged to
        # it rather than showing up as a free improvement
        base_fit = judge.model.evaluate(judge.baseline_plan)
        inc, scale = fit_incumbent(judge, judge.budget.revenue_veh_hours, name)

        for m in lams:
            cell = f"b|{name}|lam{m}|{effort}"
            if store.has(cell):
                rows.append({k: v for k, v in store.get(cell).items()
                             if k not in ("cell", "plan")})
                continue
            t0 = time.time()
            r = optimize_frequencies(
                judge.model, judge.budget, ladder=[], unserved_multiplier=m,
                local_search_iterations=args.iterations, seed=args.seed,
                ladders=judge.ladders, initial=inc,
                n_restarts=args.restarts, candidate_width=args.width,
                greedy_start=False)
            hw = dict(judge.baseline_plan.headways)
            for k, v in r.plan.headways.items():
                if k in hw:
                    hw[k] = float(v)
            f = judge.model.evaluate_array(
                np.array([hw[k] for k in judge.model.keys]))
            rec = {
                "set_key": name, "cardinality": len(combo),
                "members": list(sorted(combo)), "lambda": m,
                "seconds": time.time() - t0, "incumbent_scale": scale,
                "edited_baseline_vh": float(ts["runtime_min"].sum() / 60.0),
                "modelB_gc": f.generalized_cost,
                "modelB_unserved": f.unserved_demand,
                "modelB_served": f.served_demand,
                "modelB_gc_per_trip": f.gc_per_served_trip,
                "modelB_veh_hours": f.revenue_veh_hours,
                "base_gc_this_network": base_fit.generalized_cost,
                "base_unserved_this_network": base_fit.unserved_demand,
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
                "claim_gap_unserved_pct": (
                    (r.fitness.unserved_demand / f.unserved_demand - 1) * 100
                    if f.unserved_demand else float("nan")),
            }
            ne = noedit.get(str(m))
            if name == "<none>" and ne is None:
                ne = {"modelB_gc": f.generalized_cost,
                      "modelB_unserved": f.unserved_demand,
                      "modelB_served": f.served_demand,
                      "modelB_gc_per_trip": f.gc_per_served_trip}
                noedit[str(m)] = ne
            if ne:
                rec["gc_vs_noedit_pct"] = (
                    f.generalized_cost / ne["modelB_gc"] - 1) * 100
                rec["unserved_vs_noedit_pct"] = (
                    f.unserved_demand / ne["modelB_unserved"] - 1) * 100
                rec["served_vs_noedit_pct"] = (
                    f.served_demand / ne["modelB_served"] - 1) * 100
                rec["gc_per_trip_vs_noedit_pct"] = (
                    f.gc_per_served_trip / ne["modelB_gc_per_trip"] - 1) * 100
            store.put(cell, {**rec, "plan": {key_str(k): float(v)
                                             for k, v in hw.items()}})
            rows.append(rec)
            el = time.time() - t_start
            log.info("[%3d/%3d] %-46s k=%d lam=%-4s %4.0fs  vs no-edit: "
                     "unserved %+7.3f%%  gc %+7.3f%%  (elapsed %.1fh, "
                     "~%.1fh left)",
                     i, len(subsets), name[:46], len(combo), m, rec["seconds"],
                     rec.get("unserved_vs_noedit_pct", float("nan")),
                     rec.get("gc_vs_noedit_pct", float("nan")),
                     el / 3600, el / 3600 * (len(subsets) - i) / max(i, 1))
        del judge

    df = analyse(pd.DataFrame(rows), floor := noise_floor())
    tag = f"stage{args.stage}"
    df.to_csv(OUT / f"exp2b_{tag}.csv", index=False)
    df.to_csv(exp.artifact_path(f"{tag}.csv"), index=False)
    exp.log_metrics(stage=args.stage, lambdas=lams, n_subsets=len(subsets),
                    effort=effort, by_cardinality=by_size, rows=rows)
    exp.save()

    pd.set_option("display.width", 220)
    print("\n" + "=" * 104)
    print(f"EXPERIMENT 2B / D22 — joint geometry subset search, stage {args.stage}")
    print(f"{len(subsets)} structurally feasible subsets, effort {effort}, "
          f"frozen Model B evaluator")
    print("=" * 104)
    for m in lams:
        d = df[df["lambda"] == m].sort_values("unserved_vs_noedit_pct")
        print(f"\nlambda={m}: best 12 by measured unserved demand, "
              f"against the UNEDITED network")
        print(d.head(12)[["set_key", "cardinality", "unserved_vs_noedit_pct",
                          "gc_vs_noedit_pct", "gc_per_trip_vs_noedit_pct"]]
              .round(4).to_string(index=False))
        print(f"\nlambda={m}: interaction, measured effect minus the sum of "
              f"member singles (floor {floor:.3f} pts)")
        it = d[d["cardinality"] >= 2].dropna(subset=["interaction_unserved_pts"])
        if not it.empty:
            print(it["interaction_class"].value_counts().to_string())
            print("  most substituting:")
            print(it.nlargest(5, "interaction_unserved_pts")[
                ["set_key", "cardinality", "unserved_vs_noedit_pct",
                 "sum_of_singles_unserved_pct", "interaction_unserved_pts"]]
                .round(4).to_string(index=False))
            print("  most synergistic:")
            print(it.nsmallest(5, "interaction_unserved_pts")[
                ["set_key", "cardinality", "unserved_vs_noedit_pct",
                 "sum_of_singles_unserved_pct", "interaction_unserved_pts"]]
                .round(4).to_string(index=False))

        print(f"\nlambda={m}: best set at each cardinality (NOT required to "
              f"be nested)")
        w_ = d.sort_values("unserved_vs_noedit_pct").groupby("cardinality").head(1)
        print(w_[["cardinality", "set_key", "unserved_vs_noedit_pct",
                  "gc_vs_noedit_pct"]].round(4).to_string(index=False))
    print(f"\nartifacts: {exp.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
