#!/usr/bin/env python3
"""Experiment 2, evaluation tier: geometry with frequency actually re-optimized.

The screen ranked candidates at fixed relative frequency. That is not the
comparison that counts, because moving a route changes where the vehicle-hour
budget is best spent -- a truncation that frees twenty vehicle-hours is only
worth something if those hours go somewhere useful. So each candidate here gets
its own path set on the edited network and its own frequency optimization
inside **today's** envelope, and is compared against the unedited network
solved the same way at the same effort.

Two things make that comparison fair rather than flattering:

* the budget is pinned to the *unedited* network's 2,517 revenue vehicle-hours
  and today's peak vehicle requirement, not to whatever the edited network
  happens to cost at its own baseline -- otherwise a candidate that shortens
  routes would quietly be granted a smaller budget and score well for spending
  less;
* the zero-edit rung runs through exactly the same reduced path-set
  construction and the same solver effort, so any difference is geometry and
  not enumeration or search.

Everything here is exploratory until the Experiment 1 fixpoint freezes the
yardstick. The path sets are built with the reduced scenario sweep to keep a
candidate affordable, which is precisely the approximation the fixpoint exists
to correct, so these numbers rank and diagnose; they do not measure.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from cota_opt import geo
from cota_opt.audit import PRIMARY_MAX_MODELLED_PCT
from cota_opt.cache import ResultStore
from cota_opt.candidates import generate_all, stop_context
from cota_opt.configs import (load_constraints, load_cost_weights,
                              period_of_seconds, service_periods)
from cota_opt.exp2 import build_setup
from cota_opt.experiment import Experiment
from cota_opt.frequency import FrequencyPlan, optimize_frequencies
from cota_opt.geometry import GeometryEdit, SegmentTimeModel, apply_edits, describe
from cota_opt.harness import build_harness
from cota_opt.odmatrix import build_zone_system
from cota_opt.raptor import build_raptor_network
from cota_opt.routeclass import classify_routes

log = logging.getLogger("exp2eval")
OUT = ROOT / "outputs"


def wait_for_memory(min_free_mb: int = 1800, tries: int = 40) -> None:
    """Do not start a path-set build that will get the other run OOM-killed.

    Two large jobs on an 8 GB box already took each other down once. A build
    that waits is slower than one that does not; a build that kills the
    authoritative run costs an hour.
    """
    for _ in range(tries):
        try:
            info = dict(
                (p[0].rstrip(":"), int(p[1]))
                for p in (l.split() for l in
                          Path("/proc/meminfo").read_text().splitlines()) if p)
            free_mb = info.get("MemAvailable", 0) // 1024
        except Exception:
            return
        if free_mb >= min_free_mb:
            return
        log.warning("only %d MB available, waiting before the next build", free_mb)
        time.sleep(30)
    log.warning("proceeding despite low memory after waiting")


def pinned_constraints(vh: float, peak: dict[str, float]) -> dict:
    cons = load_constraints()
    cons = {**cons, "resource": {**cons["resource"],
                                 "weekday_revenue_vehicle_hours": float(vh),
                                 "peak_fleet_by_period": {k: float(v)
                                                          for k, v in peak.items()}}}
    return cons


def build_edited(H, model, edits, a, cons, seed, n_random_scenarios):
    """Edited network -> router -> zones -> path sets -> configured model."""
    ed = (apply_edits(H.baseline.network, H.baseline.tstats, model, edits)
          if edits else None)
    net = ed.network if ed else H.baseline.network
    ts = ed.tstats if ed else H.baseline.tstats
    pa = a["path_assignment"]
    periods = service_periods(a)
    sg = geo.stops_gdf(H.baseline.feed, a["crs"]["projected"])

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
    tp["period"] = tp["first_dep_sec"].map(lambda x: period_of_seconds(x, periods))
    classes = classify_routes(tp.dropna(subset=["period"]), H.baseline.routes)

    setup = build_setup(_Baseline(H.baseline, net, ts), rn, zs, H.od, seed=seed,
                        route_classes=classes, with_crowding=False,
                        lock_classes=("peak_express",), constraints=cons,
                        n_random_scenarios=n_random_scenarios)
    return setup, ed


def fit_incumbent(setup, budget_vh: float, label: str = ""):
    """Scale the edited network's own schedule until it fits the pinned budget.

    A splice lengthens a route, so running the merged line at today's headways
    costs more vehicle-hours than today's network does. The incumbent start is
    then infeasible, ``optimize_frequencies`` discards it, and the edited
    network is solved from the greedy build while the unedited one is solved
    from the incumbent. That is not a geometry comparison -- it is a comparison
    of starting points, and it showed up as ``exchanges=0`` on the first
    candidate that hit it.

    Vehicle-hours are linear in 1/headway, so one scale factor fixes it. The
    factor is reported: it is the honest price of the edit at today's
    frequencies, and a candidate needing a large one is buying its geometry
    with service.
    """
    plan = setup.baseline_plan
    fit = setup.model.evaluate(plan)
    k = fit.revenue_veh_hours / budget_vh
    if k <= 1.0:
        return plan, 1.0
    # scale, then walk up in small steps: the optimizer snaps to the headway
    # ladder, and snapping can put a just-feasible plan back over the line
    for bump in (1.0, 1.01, 1.02, 1.05, 1.10, 1.20):
        scaled = FrequencyPlan({key: h * k * bump
                                for key, h in plan.headways.items()})
        f = setup.model.evaluate(scaled)
        if f.revenue_veh_hours <= budget_vh:
            log.info("  %s incumbent rescaled x%.4f to fit the envelope "
                     "(%.1f -> %.1f veh-hours)", label, k * bump,
                     fit.revenue_veh_hours, f.revenue_veh_hours)
            return scaled, k * bump
    log.warning("  %s incumbent could not be scaled into the envelope", label)
    return plan, k


class _Baseline:
    """A Baseline view over an edited network, sharing everything else."""

    def __init__(self, b, net, tstats):
        self._b = b
        self.network = net
        self.tstats = tstats

    def __getattr__(self, k):
        return getattr(self._b, k)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=8,
                    help="how many screened candidates to evaluate singly")
    ap.add_argument("--lambdas", type=str, default="1,2")
    ap.add_argument("--iterations", type=int, default=60_000)
    ap.add_argument("--restarts", type=int, default=2)
    ap.add_argument("--width", type=int, default=32)
    ap.add_argument("--scenarios", type=int, default=0,
                    help="random enumeration scenarios on top of the three fixed")
    ap.add_argument("--ladder", type=str, default="1,2,4")
    ap.add_argument("--primary-only", action="store_true", default=True)
    ap.add_argument("--seed", type=int, default=20260825)
    ap.add_argument("--common-lines", type=str, default=None,
                    choices=[None, "pattern", "same_route"],
                    help="waiting model; same_route is Model B, the corrected one")
    ap.add_argument("--noise-seeds", type=str, default="",
                    help="extra seeds for the ZERO-EDIT rung only, to measure "
                         "the search's own spread at this effort. D17 found "
                         "the optimum is flat, so a geometry effect smaller "
                         "than a few times that spread is not measurable and "
                         "must not be reported as one")
    ap.add_argument("--ladder-from", type=str, default="",
                    help="an eval CSV whose MEASURED singles order the ladder, "
                         "instead of the screen's order. The screen ranks "
                         "candidates and cannot size them, and D16 found it "
                         "cannot reliably order splices either -- composing a "
                         "ladder from screen rank put the two candidates that "
                         "make things WORSE into the first two rungs")
    ap.add_argument("--ladder-metric", type=str,
                    default="unserved_vs_noedit_pct_lam2.0")
    ap.add_argument("--include-file", type=str, default="",
                    help="file of candidate keys, one per line, forced into "
                         "the shortlist regardless of screen rank. A file "
                         "rather than a flag because candidate keys contain "
                         "pipes (splice|002|011|HIGFITN) and passing them "
                         "through a shell command line invites exactly the "
                         "kind of silent truncation this project keeps finding")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    lams = [float(x) for x in args.lambdas.split(",")]

    exp = Experiment(name="exp2_geometry_eval", seed=args.seed,
                     algorithm="edited network + frequency re-optimization "
                               "inside today's envelope",
                     config_files=["assumptions.yaml", "cost_weights.yaml",
                                   "constraints.yaml", "sources.yaml"])
    log.info("experiment %s", exp.experiment_id)
    store = ResultStore(OUT / "exp2_eval.jsonl")

    H = build_harness(seed=args.seed, common_lines=args.common_lines)
    log.info("waiting model: %s", H.common_lines)
    a = H.assumptions
    sg = geo.stops_gdf(H.baseline.feed, a["crs"]["projected"])
    model = SegmentTimeModel.fit(H.baseline.network, sg)

    # today's envelope, measured once on the unedited network
    base_vh = float(H.baseline.tstats["runtime_min"].sum() / 60.0)
    base_setup = H.setup(with_crowding=False, lock_classes=("peak_express",))
    base_fit = base_setup.model.evaluate(base_setup.baseline_plan)
    peak = dict(base_fit.peak_by_period)
    cons = pinned_constraints(base_vh, peak)
    log.info("envelope pinned: %.1f revenue veh-hours, peak %s", base_vh,
             {k: round(v, 1) for k, v in peak.items()})
    del base_setup, base_fit

    # candidate shortlist, ordered by the screen, filtered by evidence class
    audit = pd.read_csv(OUT / "exp2_audit.csv")
    ok = audit.dropna(subset=["screen_gc_change_pct"])
    if args.primary_only:
        ok = ok[ok["evidence_class"] == "primary"]
    ok = ok.sort_values(["screen_unserved_change_pct", "screen_gc_change_pct"])
    shortlist = ok.head(args.top)["candidate_id"].tolist()
    # candidates the bracket promoted are carried in even if the Model A screen
    # buried them -- adding a candidate is the conservative error (D16)
    inc = []
    if args.include_file:
        f = Path(args.include_file)
        f = f if f.is_absolute() else (ROOT / args.include_file)
        if f.exists():
            inc = [x.strip() for x in f.read_text().splitlines()
                   if x.strip() and not x.startswith("#")]
        else:
            log.warning("include file %s not found", f)
    for k in inc:
        if k not in shortlist:
            shortlist.append(k)
            log.info("forced into the shortlist: %s", k)
    log.info("shortlist (%d, primary=%s): %s", len(shortlist),
             args.primary_only, shortlist)

    zone_flow = np.zeros(H.zones.n)
    np.add.at(zone_flow, H.od.origin, H.od.flow)
    np.add.at(zone_flow, H.od.dest, H.od.flow)
    ctx = stop_context(H.baseline.network, H.zones, H.raptor.stop_ids, model)
    express = {r for r, c in H.classes.items() if c.klass == "peak_express"}
    trips_by_route = H.baseline.tstats.groupby("route_id").size().to_dict()
    all_cands = generate_all(H.baseline.network, ctx, H.zones, H.raptor.stop_ids,
                             zone_flow, trips_by_route, exclude_routes=express,
                             per_kind=12)
    by_key = {c.key: c for c in all_cands}

    # the ladder composes the shortlist greedily on disjoint routes, so "two
    # edits" is two independent interventions rather than two bites at one route
    ladder_sets: list[tuple[str, list[GeometryEdit]]] = [("0 edits", [])]
    ladder_order = shortlist
    if args.ladder_from:
        f = Path(args.ladder_from)
        f = f if f.is_absolute() else (OUT / args.ladder_from)
        if f.exists():
            ev = pd.read_csv(f)
            ev = ev[ev["label"].astype(str).str.startswith("single:")].copy()
            ev["key"] = ev["label"].str.replace("single:", "", regex=False)
            ev = ev.dropna(subset=[args.ladder_metric]).sort_values(
                args.ladder_metric)
            ladder_order = [k for k in ev["key"] if k in set(shortlist)]
            log.info("ladder ordered by MEASURED %s, best first: %s",
                     args.ladder_metric, ladder_order[:6])
        else:
            log.warning("ladder-from %s not found; falling back to screen order", f)
    chosen: list[GeometryEdit] = []
    used: set[str] = set()
    for key in ladder_order:
        c = by_key.get(key)
        if c is None or (c.routes_touched() & used):
            continue
        chosen.append(c)
        used |= c.routes_touched()
    for n in [int(x) for x in args.ladder.split(",")]:
        if len(chosen) >= n:
            ladder_sets.append((f"{n} edits", chosen[:n]))

    jobs: list[tuple[str, list[GeometryEdit]]] = list(ladder_sets)
    for key in shortlist:
        c = by_key.get(key)
        if c is not None:
            jobs.append((f"single:{key}", [c]))
    # replicate the zero-edit rung under other seeds: its spread IS the noise
    # floor at this effort, and D17 showed that floor is not small
    noise_seeds = [int(x) for x in args.noise_seeds.split(",") if x.strip()]
    for sd_ in noise_seeds:
        jobs.append((f"0 edits seed{sd_}", []))

    rows = []
    for label, edits in jobs:
        # a replicate rung carries its seed in its label; everything else uses
        # the run's seed, so a candidate and the zero rung it is compared with
        # are searched identically
        job_seed = (int(label.rsplit("seed", 1)[1]) if "seed" in label
                    else args.seed)
        tag = "m" if (args.ladder_from and label.endswith("edits")) else "s"
        cell = (f"eval|{label}|{tag}|"
                f"{args.iterations}/{args.restarts}/{args.width}")
        if store.has(cell):
            rows.append(store.get(cell))
            log.info("%-38s resumed from checkpoint", label)
            continue
        wait_for_memory()
        t0 = time.time()
        try:
            setup, ed = build_edited(H, model, edits, a, cons, args.seed,
                                     args.scenarios)   # set is seed-independent
        except Exception as exc:
            log.warning("%s failed to build: %s: %s", label,
                        type(exc).__name__, exc)
            store.put(cell, {"label": label, "error": f"{type(exc).__name__}: {exc}",
                             "n_edits": len(edits)})
            continue
        incumbent, hw_scale = fit_incumbent(
            setup, setup.budget.revenue_veh_hours, label)
        bf = setup.model.evaluate(setup.baseline_plan)
        rec: dict = {
            "incumbent_headway_scale": hw_scale,
            "label": label, "seed": job_seed, "n_edits": len(edits),
            "edits": describe(edits),
            "edit_keys": [e.key for e in edits],
            "n_paths": sum(p.n_paths for p in setup.pathsets.values()),
            "edited_baseline_vh": (ed.report.baseline_veh_hours_after
                                   if ed else base_vh),
            "modelled_share_pct": (ed.report.as_dict()["modelled_share_pct"]
                                   if ed else 0.0),
            "build_seconds": time.time() - t0,
        }
        for m in lams:
            t = time.time()
            r = optimize_frequencies(
                setup.model, setup.budget, ladder=[], unserved_multiplier=m,
                local_search_iterations=args.iterations, seed=job_seed,
                ladders=setup.ladders, initial=incumbent,
                n_restarts=args.restarts, candidate_width=args.width,
                greedy_start=False)
            rec[f"gc_lam{m}"] = r.fitness.generalized_cost
            rec[f"unserved_lam{m}"] = r.fitness.unserved_demand
            rec[f"served_lam{m}"] = r.fitness.served_demand
            rec[f"vh_lam{m}"] = r.fitness.revenue_veh_hours
            rec[f"vh_vs_budget_pct_lam{m}"] = (
                r.fitness.revenue_veh_hours / setup.budget.revenue_veh_hours - 1) * 100
            rec[f"seconds_lam{m}"] = time.time() - t
            pd.DataFrame([{"route_id": k[0], "period": k[1], "headway_min": v}
                          for k, v in r.plan.headways.items()]).to_csv(
                OUT / "exp2_eval_plans" / f"{label.replace(':', '_')}_lam{m}.csv"
                if (OUT / "exp2_eval_plans").mkdir(parents=True, exist_ok=True)
                or True else None, index=False)
            log.info("  %-34s lam=%-4s %4.0fs gc=%.6e unserved=%.0f",
                     label, m, rec[f"seconds_lam{m}"], rec[f"gc_lam{m}"],
                     rec[f"unserved_lam{m}"])
        rec["baseline_gc_on_this_network"] = bf.generalized_cost
        rec["baseline_unserved_on_this_network"] = bf.unserved_demand
        store.put(cell, rec)
        rows.append(rec)
        del setup
        log.info("%-38s done in %.0fs (%d paths)", label,
                 time.time() - t0, rec["n_paths"])

    df = pd.DataFrame(rows)
    if df.empty:
        log.warning("nothing evaluated")
        return 1

    # everything is compared against the zero-edit rung solved identically
    zero = df[df["label"] == "0 edits"]
    if not zero.empty:
        z = zero.iloc[0]
        for m in lams:
            df[f"gc_vs_noedit_pct_lam{m}"] = (
                df[f"gc_lam{m}"] / z[f"gc_lam{m}"] - 1) * 100
            df[f"unserved_vs_noedit_pct_lam{m}"] = (
                df[f"unserved_lam{m}"] / z[f"unserved_lam{m}"] - 1) * 100

    # the noise floor: how far the SAME network moves when only the seed
    # changes. D17 measured 26% of route-periods and 0.13 points of unserved
    # at full effort on Experiment 1; at this effort it will be larger, and a
    # geometry effect inside it is not an effect.
    noise = {}
    reps = df[df["label"].str.startswith("0 edits")]
    if len(reps) > 1:
        for m in lams:
            v = reps[f"unserved_lam{m}"].to_numpy(float)
            g = reps[f"gc_lam{m}"].to_numpy(float)
            noise[str(m)] = {
                "n_replicates": int(len(v)),
                "unserved_sd_pct": float(np.std(v / z[f"unserved_lam{m}"] * 100,
                                                ddof=1)),
                "gc_sd_pct": float(np.std(g / z[f"gc_lam{m}"] * 100, ddof=1)),
            }
            df[f"measurable_lam{m}"] = (
                df[f"unserved_vs_noedit_pct_lam{m}"].abs()
                >= 3.0 * noise[str(m)]["unserved_sd_pct"])
        log.info("noise floor at this effort: %s", noise)
    else:
        log.warning("no zero-edit replicates: pass --noise-seeds, or every "
                    "effect below is unjudgeable against search noise")

    df.to_csv(exp.artifact_path("eval.csv"), index=False)
    df.to_csv(OUT / "exp2_eval.csv", index=False)

    lad = df[df["label"].str.endswith("edits")].copy()
    if not lad.empty and f"gc_vs_noedit_pct_lam{lams[-1]}" in lad:
        lad["improvement_vs_exp1"] = -lad[f"gc_vs_noedit_pct_lam{lams[-1]}"]
        lad[["n_edits", "improvement_vs_exp1"]].to_csv(
            OUT / "exp2_ladder.csv", index=False)

    exp.log_metrics(noise_floor=noise, waiting_model=H.common_lines,
                    envelope_vh=base_vh, peak=peak, lambdas=lams,
                    effort=f"{args.iterations}/{args.restarts}/{args.width}",
                    scenarios=args.scenarios, shortlist=shortlist,
                    primary_only=args.primary_only,
                    primary_threshold_pct=PRIMARY_MAX_MODELLED_PCT,
                    n_jobs=len(jobs))
    exp.save()

    pd.set_option("display.width", 220)
    print("\n" + "=" * 104)
    print("EXPERIMENT 2 EVALUATION — geometry WITH frequency re-optimized, "
          "same 2,517 vehicle-hours")
    print("Candidate path sets use the reduced scenario sweep and the solver "
          "runs at low effort, so these RANK candidates; the noise floor below "
          "says which differences are real at this effort.")
    print("=" * 104)
    cols = ["label", "n_edits", "n_paths", "modelled_share_pct"] + [
        c for m in lams for c in (f"gc_vs_noedit_pct_lam{m}",
                                  f"unserved_vs_noedit_pct_lam{m}",
                                  f"measurable_lam{m}")
        if c in df.columns]
    print(df[cols].round(3).to_string(index=False))
    if noise:
        print("\n  search noise at this effort, from the zero-edit replicates:")
        for m, v in noise.items():
            print(f"    lambda={m}: unserved sd {v['unserved_sd_pct']:.3f} pts "
                  f"over {v['n_replicates']} seeds -> anything under "
                  f"{3 * v['unserved_sd_pct']:.3f} pts is not measurable")
    else:
        print("\n  NO NOISE FLOOR MEASURED — every number above is "
              "unjudgeable against search noise. Re-run with --noise-seeds.")
    print(f"\nartifacts: {exp.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
