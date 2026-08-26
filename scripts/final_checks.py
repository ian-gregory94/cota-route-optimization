#!/usr/bin/env python3
"""The two checks the converged matrix still owes.

1. SEED STABILITY. The matrix used one seed. If the exchange search lands in
   materially different local optima across seeds, the reported frontier is
   noise rather than a frontier.

2. PATH-SET ADEQUACY UNDER THE CONVERGED PLANS. The candidate path sets were
   enumerated at baseline headways plus five scenarios. That was verified
   against a mildly-changed plan; the converged plans move much further, so the
   cache may no longer hold each OD pair's best journey. Full RAPTOR is re-run
   under the actual optimized headways and compared, per OD pair.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from cota_opt.cache import ResultStore
from cota_opt.cost import CostWeights
from cota_opt.frequency import FrequencyPlan, optimize_frequencies
from cota_opt.harness import build_harness
from cota_opt.odmatrix import ODTable
from cota_opt.raptor import generalized_cost, pattern_headways

log = logging.getLogger("final")
EFFORT = dict(local_search_iterations=150_000, n_restarts=5, candidate_width=48)
SEEDS = [20260825, 20260826, 20260827, 20260828]


def adequacy(h, setup, plan: FrequencyPlan, period: str, label: str) -> dict:
    """Compare the cached path set against a fresh RAPTOR run under `plan`."""
    a = h.assumptions
    pa = a["path_assignment"]
    w = setup.model.w
    wk = dict(random_arrival_threshold_min=float(a["waiting"]["random_arrival_threshold_min"]),
              schedule_coefficient=float(a["waiting"]["schedule_coefficient"]))
    ev = setup.model.evaluators[period]
    ps = ev.ps
    sub = np.array([plan.headways[k] for k in ps.rp_keys])
    cached = ev.od_costs(sub)

    hw = dict(plan.headways)
    ph = pattern_headways(h.raptor, hw, period)
    share = float(a["demand_proxy"]["period_shares"][period])
    od = h.od
    srt = np.lexsort((od.dest, od.origin))
    o_s, d_s = od.origin[srt], od.dest[srt]
    origins = np.unique(o_s)
    starts = np.searchsorted(o_s, origins, side="left")
    ends = np.searchsorted(o_s, origins, side="right")
    fresh = np.full(len(o_s), np.inf)
    for z, s0, s1 in zip(origins, starts, ends):
        a_stops, a_walk = h.zones.access_of(int(z))
        if len(a_stops) == 0:
            continue
        cost, _, _ = generalized_cost(
            h.raptor, [h.raptor.stop_ids[s] for s in a_stops], ph, w, wk,
            max_rounds=int(pa["max_rounds"]),
            source_costs=[w.walking * x for x in a_walk])
        for oi in range(s0, s1):
            e_stops, e_walk = h.zones.access_of(int(d_s[oi]))
            if len(e_stops) == 0:
                continue
            fresh[oi] = float(np.min(cost[e_stops] + w.walking * e_walk))

    both = np.isfinite(cached) & np.isfinite(fresh)
    gap = cached[both] - fresh[both]
    flow = ps.od_flow[both]
    return {
        "plan": label, "period": period,
        "od_pairs": int(both.sum()),
        "mean_overstatement_min": float((gap * flow).sum() / flow.sum()),
        "mean_overstatement_pct": float((gap * flow).sum()
                                        / (cached[both] * flow).sum() * 100),
        "pairs_improvable": int((gap > 1e-6).sum()),
        "pairs_improvable_pct": float((gap > 1e-6).mean() * 100),
        "flow_weighted_improvable_pct": float(flow[gap > 1e-6].sum() / flow.sum() * 100),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    h = build_harness()
    setup = h.setup(True, ("peak_express",))
    model, base = setup.model, setup.baseline_plan
    bf = model.evaluate(base)
    store = ResultStore(ROOT / "outputs" / "final_checks.jsonl")
    out: dict = {}

    # ---- 1. seed stability ----------------------------------------------
    stab = []
    for lam in (1.0, 2.0):
        for seed in SEEDS:
            cell = f"seed|lam={lam}|seed={seed}"
            if store.has(cell):
                stab.append(store.get(cell))
                continue
            t = time.time()
            r = optimize_frequencies(model, setup.budget, ladder=[],
                                     unserved_multiplier=lam, seed=seed,
                                     ladders=setup.ladders, initial=base,
                                     greedy_start=False, **EFFORT)
            rec = {"lambda": lam, "seed": seed, "seconds": time.time() - t,
                   "gc_change_pct": (r.fitness.generalized_cost / bf.generalized_cost - 1) * 100,
                   "unserved_change_pct": (r.fitness.unserved_demand / bf.unserved_demand - 1) * 100}
            store.put(cell, rec)
            stab.append(rec)
            log.info("  seed %d lam=%s: gc %+.2f%% uns %+.2f%%", seed, lam,
                     rec["gc_change_pct"], rec["unserved_change_pct"])
    sdf = pd.DataFrame(stab)
    out["seed_stability"] = (sdf.groupby("lambda")
                             .agg(gc_mean=("gc_change_pct", "mean"),
                                  gc_sd=("gc_change_pct", "std"),
                                  uns_mean=("unserved_change_pct", "mean"),
                                  uns_sd=("unserved_change_pct", "std"))
                             .round(4).reset_index().to_dict(orient="records"))

    # ---- 2. path-set adequacy under the converged plans -----------------
    pdir = ROOT / "outputs" / "matrix_plans"
    checks = []
    for label, fn in (("baseline", None),
                      ("C lam=1 (both objectives improve)", "C_lam1.0_seed20260825.csv"),
                      ("C lam=0.25 (most aggressive)", "C_lam0.25_seed20260825.csv")):
        if fn is None:
            plan = base
        else:
            p = pdir / fn
            if not p.exists():
                continue
            df = pd.read_csv(p, dtype={"route_id": str})
            hw = dict(base.headways)
            for r in df.itertuples():
                k = (r.route_id, r.period)
                if k in hw:
                    hw[k] = float(r.headway_min)
            plan = FrequencyPlan(hw)
        for per in ("am_peak", "midday"):
            rec = adequacy(h, setup, plan, per, label)
            checks.append(rec)
            log.info("  adequacy %-34s %-8s: overstates %.3f min (%.2f%%), "
                     "%.1f%% of flow improvable", label, per,
                     rec["mean_overstatement_min"], rec["mean_overstatement_pct"],
                     rec["flow_weighted_improvable_pct"])
    out["path_set_adequacy"] = checks

    (ROOT / "outputs" / "final_checks.json").write_text(json.dumps(out, indent=2))
    print("\n" + "=" * 88)
    print("SEED STABILITY (converged effort)")
    print(pd.DataFrame(out["seed_stability"]).to_string(index=False))
    print("\nPATH-SET ADEQUACY under the converged plans")
    print(pd.DataFrame(checks).round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
