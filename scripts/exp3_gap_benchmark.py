#!/usr/bin/env python3
"""Optimization-gap benchmark — how far is the Gen1 heuristic from optimal?

Corrective plan sections 4-7. This exists because the corrected census has no
materiality threshold: under `starts="both"` at discovery effort the pipeline is
deterministic, so replicate spread is exactly zero and bounds solver VARIANCE
rather than solver ERROR (D32, and
`decisions/2026-08-31-replicate-spread-is-not-a-materiality-floor.md`).

Why exhaustive enumeration and not a MILP
-----------------------------------------
Section 5 warns against silently simplifying the passenger objective to obtain
an exact solver. The Gen1 objective resists linearization honestly: a path's
waiting cost depends on the COMBINED frequency of every same-route pattern
serving its boarding stop then its alighting stop, in that order (Model B), so
the cost of a path is a function of several route-period headways jointly and
does not separate. A MILP would require either linearizing that coupling or
dropping it, and then the benchmark would measure a different objective than
the one under test — which is exactly the substitution section 5 forbids.

So the problem is reduced instead of the objective. All but *N* route-periods
are frozen at their incumbent value by giving them a one-rung ladder; the free
ones keep *K* rungs around theirs. Every one of the K^N combinations is priced
with the REAL evaluator, and the best feasible one is the exact optimum **of
that reduced problem, under the production objective**. The relationship between
benchmark objective and production objective is therefore identity, and the
approximation is confined entirely to the size of the decision space — which is
stated, not hidden.

What it must answer
-------------------
1. the absolute heuristic gap against the exact reference;
2. the distribution of that gap across geometries;
3. whether the gap changes **systematically between control and treatment**;
4. therefore the treatment effect distinguishable from treatment-correlated
   solver error.

Question 3 is the one that matters. If both arms sit the same distance from
optimum in the same direction, their difference is clean however large the gap.
If one arm is 0.4% off and the other 0.1%, a 0.3% artifact is available and no
census margin below that means anything. **A generic mean or maximum gap is not
an effect floor**, and this script does not emit one.

    python scripts/exp3_gap_benchmark.py --list
    python scripts/exp3_gap_benchmark.py --cell control:peak:8
"""
from __future__ import annotations

import argparse
import itertools
import json
import logging
import os
import pickle
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cota_opt import exp3, geo                                    # noqa: E402
from cota_opt.cache import cache_dir, key_of                      # noqa: E402
from cota_opt.contract import ContractLimits                      # noqa: E402
from cota_opt.geometry import SegmentTimeModel, apply_edits       # noqa: E402
from cota_opt.harness import build_harness                        # noqa: E402
from cota_opt.mutate import edit_from_record                      # noqa: E402
from exp3_pin_envelope import load as pin_load                    # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("gap")
OUT = ROOT / "outputs" / "exp3"
ROWS = OUT / "gap_benchmark.jsonl"

LAM = exp3.PRIMARY_LAMBDA
SEED = 20260825
K_RUNGS = 3                 # ladder rungs kept per free route-period
SIZES = (6, 8, 10)          # free route-periods; K^N = 729 / 6561 / 59049

#: Networks to benchmark. The control plus one treatment from each direction,
#: because the question is whether the gap MOVES with the treatment, and
#: lengthening and shortening edits are the two directions D27 separated.
NETWORKS = {
    "control": None,
    "lengthen_add_stop": "add_stop-010",
    "lengthen_extend": "extend-025",
    "shorten_truncate": None,        # filled from the pool at runtime
    "shorten_straighten": None,
}

#: How the free route-periods are chosen. Stated before any gap is measured,
#: and deliberately not all easy: a benchmark that samples only well-behaved
#: subproblems reports a gap that means nothing about the ones under test.
STRATA = ("peak", "offpeak", "common_lines", "weak_interaction", "seeded_random")


def pool_index() -> dict:
    pool = json.loads((OUT / "mutation_pool.json").read_text())
    return {m["id"]: m for m in pool["mutations"]}


def resolve(spec: str | None, idx: dict):
    if spec is None:
        return []
    key = spec.split("#")[0]
    hit = idx.get(spec) or idx.get(key) or next(
        (m for m in idx.values() if m["id"].split("#")[0] == key), None)
    if hit is None:
        raise SystemExit(f"no pool entry for {spec!r}")
    return [edit_from_record(hit)]


def build_judge(edits, H, sg, stm, CONS):
    """Returns (judge, incumbent, network) — the network for the strata."""
    """The same setup `score_state` builds, with disk-cached path sets."""
    from exp2_treatments import _Baseline, fit_incumbent
    from cota_opt.configs import period_of_seconds, service_periods
    from cota_opt.exp2 import build_setup as path_level_setup
    from cota_opt.odmatrix import build_zone_system
    from cota_opt.raptor import build_raptor_network
    from cota_opt.routeclass import classify_routes

    a = H.assumptions
    pa = a["path_assignment"]
    periods = service_periods(a)
    net, ts = H.baseline.network, H.baseline.tstats
    if edits:
        ed = apply_edits(net, ts, stm, list(edits))
        net, ts = ed.network, ed.tstats
    rn = build_raptor_network(H.baseline.feed, net, ts, sg,
                              walk_radius_m=float(pa["walk_radius_m"]),
                              walk_speed_m_per_min=float(pa["walk_speed_m_per_min"]),
                              periods=periods, with_timetable=False)
    zs = build_zone_system(H.baseline.demand["bg_frame"], sg,
                           radius_m=float(pa["access_radius_m"]),
                           walk_speed_m_per_min=float(pa["walk_speed_m_per_min"]),
                           stop_index=rn.stop_index)
    tp = ts.copy()
    tp["period"] = tp["first_dep_sec"].map(lambda x: period_of_seconds(x, periods))
    rcls = classify_routes(tp.dropna(subset=["period"]), H.baseline.routes)
    b_ed = _Baseline(H.baseline, net, ts)

    ps_key = key_of("exp3_pathsets",
                    exp3.pathset_cache_params(edits, SEED, "same_route"))
    ps_path = cache_dir() / f"{ps_key}.pkl"
    psc = {}
    if ps_path.exists():
        try:
            psc = pickle.loads(ps_path.read_bytes())
        except Exception:
            psc = {}
    fresh = not psc

    def setup(cache):
        return path_level_setup(b_ed, rn, zs, H.od, seed=SEED, route_classes=rcls,
                                with_crowding=False, lock_classes=("peak_express",),
                                constraints=CONS, n_random_scenarios=0,
                                pathset_cache=cache, common_lines="same_route")

    judge = setup(psc)
    if fresh and psc:
        try:
            ps_path.write_bytes(pickle.dumps(psc, protocol=pickle.HIGHEST_PROTOCOL))
        except Exception as e:
            log.warning("could not cache path sets: %s", e)
    incumbent, _ = fit_incumbent(judge, judge.budget.revenue_veh_hours)
    return judge, incumbent, net


def choose_free(judge, stratum: str, n: int, net=None) -> list:
    """Which route-periods the subproblem may move. Rule stated per stratum.

    Frozen route-periods are not removed from the model -- removing them would
    change the objective. They are pinned to one ladder rung, so the reduced
    problem is a genuine restriction of the real one rather than a different
    problem that resembles it.
    """
    keys = [k for k in judge.model.keys if k in judge.ladders
            and len(judge.ladders[k]) > 1]
    dem = judge.model.demand
    load = {k: float(dem.by_route_period.get(k, 0.0))
            if hasattr(dem, "by_route_period") else 0.0 for k in keys}
    if not any(load.values()):                      # fall back to service level
        load = {k: 1.0 / max(judge.baseline_plan.headways.get(k, 60.0), 1e-9)
                for k in keys}

    if stratum == "peak":
        peak = [k for k in keys if k[1] in ("am_peak", "pm_peak")] or keys
        return sorted(peak, key=lambda k: -load[k])[:n]
    if stratum == "offpeak":
        off = [k for k in keys if k[1] in ("midday", "evening", "owl")] or keys
        return sorted(off, key=lambda k: -load[k])[:n]
    if stratum in ("common_lines", "weak_interaction"):
        # How many other routes share a stop with this one: the coupling that
        # makes Model B's waiting term non-separable, and therefore the axis
        # the heuristic is most likely to mishandle.
        #
        # Exp2Setup carries no network -- it is model, plan, budget, ladders,
        # path sets and checks -- so the network is passed in by the caller
        # that built it, rather than reached for through an attribute that
        # does not exist.
        if net is None:
            raise ValueError("the common-lines strata need the network the "
                             "judge was built from")
        stops = {}
        for p in net.patterns.values():
            stops.setdefault(p.route_id, set()).update(
                s.from_stop for s in p.segments)
        overlap = {}
        for r, ss in stops.items():
            overlap[r] = sum(1 for r2, s2 in stops.items()
                             if r2 != r and ss & s2)
        rev = stratum == "weak_interaction"
        return sorted(keys, key=lambda k: (overlap.get(k[0], 0) * (1 if rev else -1),
                                           str(k)))[:n]
    rng = np.random.default_rng([SEED, n])
    pick = rng.choice(len(keys), size=min(n, len(keys)), replace=False)
    return [keys[int(i)] for i in sorted(pick)]


def restricted_ladders(judge, free: list, k_rungs: int, anchor: dict) -> dict:
    """One rung for every frozen route-period, k around the anchor for free.

    The anchor decides what the benchmark measures, so it is a parameter and
    not a convenience:

    ``solution``
        the plan Gen1 actually delivered on the FULL problem. The reduced
        problem is then a neighbourhood of the answer the experiment reports,
        and exhaustive enumeration asks the question that matters -- is
        anything better sitting next to what we shipped? This is the
        optimization ERROR of the delivered result.

    ``baseline``
        the network's own schedule. This asks whether the solver can solve a
        small problem well, which is a capability test and a weaker question:
        a solver can be excellent on a fresh six-dimensional problem and still
        deliver a suboptimal answer on the real one.

    Default is ``solution``, because the census margins under suspicion are
    differences between delivered answers.
    """
    out = {}
    for key in judge.model.keys:
        lad = sorted(judge.ladders[key])
        cur = float(anchor.get(key, judge.baseline_plan.headways.get(
            key, lad[len(lad) // 2])))
        i = min(range(len(lad)), key=lambda j: abs(lad[j] - cur))
        if key not in free:
            out[key] = [lad[i]]
            continue
        lo = max(0, min(i - k_rungs // 2, len(lad) - k_rungs))
        out[key] = lad[lo:lo + k_rungs] or [lad[i]]
    return out


def exact(judge, ladders: dict) -> tuple[float, np.ndarray, int]:
    """Best feasible objective over the whole reduced space, by enumeration.

    Exhaustive, with the production evaluator. No relaxation, no surrogate: the
    number this returns is the optimum of the reduced problem under exactly the
    objective the experiment reports.
    """
    from cota_opt.frequency import _feasible
    keys = list(judge.model.keys)
    lads = [sorted(ladders[k]) for k in keys]
    free = [i for i, l in enumerate(lads) if len(l) > 1]
    base = np.array([l[0] for l in lads], dtype=float)
    w_uns = judge.model.w.unserved

    best, best_h, n = float("inf"), None, 0
    for combo in itertools.product(*[lads[i] for i in free]):
        h = base.copy()
        for i, v in zip(free, combo):
            h[i] = v
        fit = judge.model.evaluate_array(h)
        n += 1
        if not _feasible(judge.model, fit, judge.budget):
            continue
        o = fit.scalarized(w_uns, LAM)
        if o < best:
            best, best_h = o, h.copy()
    return best, best_h, n


def full_solution(judge, incumbent) -> tuple[dict, float]:
    """What Gen1 delivers on the WHOLE problem — the thing under test."""
    from cota_opt.frequency import optimize_frequencies, repair_to_ladder
    fixed, _ = repair_to_ladder(judge.model, judge.budget, judge.ladders,
                                incumbent)
    r = optimize_frequencies(
        judge.model, judge.budget, ladder=[], unserved_multiplier=LAM,
        local_search_iterations=60_000, seed=SEED, ladders=judge.ladders,
        initial=fixed if fixed is not None else incumbent,
        n_restarts=2, candidate_width=32, greedy_start=True)
    keys = list(judge.model.keys)
    h = np.array([float(r.plan.headways[k]) for k in keys])
    fit = judge.model.evaluate_array(h)
    return (dict(r.plan.headways),
            fit.scalarized(judge.model.w.unserved, LAM))


def heuristic(judge, ladders: dict, incumbent) -> tuple[float, int]:
    """Gen1's optimizer on the identical reduced problem, identical settings."""
    from cota_opt.frequency import optimize_frequencies, repair_to_ladder
    fixed, _ = repair_to_ladder(judge.model, judge.budget, ladders, incumbent)
    r = optimize_frequencies(
        judge.model, judge.budget, ladder=[], unserved_multiplier=LAM,
        local_search_iterations=60_000, seed=SEED, ladders=ladders,
        initial=fixed if fixed is not None else incumbent,
        n_restarts=2, candidate_width=32, greedy_start=True)
    keys = list(judge.model.keys)
    h = np.array([float(r.plan.headways[k]) for k in keys])
    fit = judge.model.evaluate_array(h)
    return fit.scalarized(judge.model.w.unserved, LAM), int(r.meta.get("evaluations", 0))


def cells() -> list[str]:
    return [f"{net}:{s}:{n}" for net in NETWORKS for s in STRATA for n in SIZES]


def done() -> set[str]:
    out = set()
    if ROWS.exists():
        for line in ROWS.open():
            line = line.strip()
            if not line:
                continue
            try:
                out.add(json.loads(line)["cell"])
            except Exception:
                pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", help="network:stratum:size")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--deadline-seconds", type=float, default=1400.0)
    ap.add_argument("--max-combos", type=int, default=80_000)
    ap.add_argument("--anchor", choices=("solution", "baseline"),
                    default="solution",
                    help="what the free route-periods vary AROUND; see "
                         "restricted_ladders")
    args = ap.parse_args()
    deadline = time.time() + args.deadline_seconds

    idx = pool_index()
    nets = dict(NETWORKS)
    for name, want in (("shorten_truncate", "truncate"),
                       ("shorten_straighten", "straighten")):
        if nets.get(name) is None:
            hit = next((m["id"] for m in idx.values()
                        if m["id"].startswith(want)), None)
            nets[name] = hit
    have = done()
    todo = [c for c in cells() if c not in have]
    if args.list:
        for c in todo:
            print(c)
        return 0
    if args.cell:
        todo = [args.cell]
    if not todo:
        print("all cells done")
        return 0

    H = build_harness(seed=SEED, common_lines="same_route", with_pathsets=False)
    sg = geo.stops_gdf(H.baseline.feed, H.assumptions["crs"]["projected"])
    stm = SegmentTimeModel.fit(H.baseline.network, sg)
    CONS = pin_load()
    judges: dict[str, tuple] = {}

    for cell in todo:
        net_name, stratum, n = cell.split(":")
        n = int(n)
        if K_RUNGS ** n > args.max_combos:
            log.info("%s: %d combinations exceeds the cap, skipping",
                     cell, K_RUNGS ** n)
            continue
        if time.time() + 60 > deadline:
            log.info("stopping cleanly before %s", cell)
            break
        if net_name not in judges:
            j, inc, jnet = build_judge(resolve(nets[net_name], idx),
                                       H, sg, stm, CONS)
            if args.anchor == "solution":
                plan, obj = full_solution(j, inc)
                log.info("%s: Gen1 full-problem solution %.6f", net_name, obj)
            else:
                plan, obj = dict(j.baseline_plan.headways), None
            judges[net_name] = (j, inc, plan, obj, jnet)
        judge, incumbent, anchor, anchor_obj, jnet = judges[net_name]
        free = choose_free(judge, stratum, n, net=jnet)
        lads = restricted_ladders(judge, free, K_RUNGS, anchor)

        t0 = time.time()
        exact_obj, _, n_eval = exact(judge, lads)
        t_exact = time.time() - t0
        t1 = time.time()
        heur_obj, h_eval = heuristic(judge, lads, incumbent)
        t_heur = time.time() - t1

        # The gap that matters is between the DELIVERED answer and the exact
        # optimum of its own neighbourhood. The reduced-problem heuristic run
        # is reported too, as a check that the solver is not simply failing on
        # the restricted instance.
        delivered = anchor_obj if anchor_obj is not None else heur_obj
        gap = delivered - exact_obj
        row = {"cell": cell, "network": net_name, "stratum": stratum,
               "n_free": n, "k_rungs": K_RUNGS,
               "free_route_periods": [f"{a}|{b}" for a, b in free],
               "anchor": args.anchor,
               "combinations": n_eval, "exact_objective": exact_obj,
               "delivered_objective": delivered,
               "reduced_heuristic_objective": heur_obj,
               "gap_absolute": gap,
               "gap_pct": 100.0 * gap / exact_obj if exact_obj else None,
               "reduced_gap_pct": (100.0 * (heur_obj - exact_obj) / exact_obj
                                   if exact_obj else None),
               "heuristic_evaluations": h_eval,
               "seconds_exact": round(t_exact, 1),
               "seconds_heuristic": round(t_heur, 1),
               "lambda": LAM, "seed": SEED,
               "methodology_generation": "gen1"}
        with ROWS.open("a") as f:
            f.write(json.dumps(row) + "\n")
            f.flush()
            os.fsync(f.fileno())
        log.info("%-30s exact %.4f  delivered %.4f  gap %+.4f (%+.5f%%)  "
                 "%d combos in %.0fs", cell, exact_obj, delivered, gap,
                 row["gap_pct"], n_eval, t_exact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
