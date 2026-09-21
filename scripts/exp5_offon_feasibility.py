#!/usr/bin/env python3
"""Exp 5 diagnostic, pass 2: re-score every OFF->ON probe against the FULL
feasibility test the search actually applies, not the hours cap alone.

Pass 1 (`exp5_offon_diagnostic.py`) tested `revenue_veh_hours <= cap` only.
`frequency._feasible` ALSO tests `fit.peak_by_period[p] <= budget.peak_cap(p)`
for every period the budget names. If that arm binds, an "improving" probe is
not a move the search declined -- it is a move the search was never allowed to
make, and the diagnosis is completely different.

DIAGNOSTIC ONLY. Nothing is modified. Writes only under outputs/exp5_diag/.
"""
from __future__ import annotations
import json, math, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
RUN = ROOT / "outputs" / "exp4" / "run"
OUT = ROOT / "outputs" / "exp5_diag"
LEADER = "exp4|exp4-pool-v1|65lines#ecb2ffc4bcce"
LEADER_OBJ = 3511184.5657525407
LAM, SEED, K_RUNGS = 2.0, 20260825, 3


def main() -> int:
    from cota_opt.configs import load_constraints
    from cota_opt.exp3_score import solve_on_network
    from cota_opt.exp4_assemble import assemble
    from cota_opt.exp4_network import Exp4Selection
    from cota_opt.frequency import _feasible
    from exp4_c10_fixtures import POOL_VERSION, _BY_RID, _boot, _first_dep_by_period
    import numpy as np

    prop = json.loads((RUN / "proposals.json").read_text())["proposals"]
    lines = {p["state_key"]: p["lines"] for p in prop}[LEADER]
    cert = next(json.load(open(p)) for p in (RUN / "certified").glob("*.json")
                if json.load(open(p)).get("state_key") == LEADER)

    st = _boot(); H, sg, graph = st["H"], st["sg"], st["graph"]
    env = json.loads((ROOT / "outputs" / "CANONICAL_ENVELOPE.json").read_text())
    VH_CAP = float(env["weekday_revenue_vehicle_hours"])
    _c = load_constraints()
    cons = {**_c, "resource": {**_c["resource"],
                               "weekday_revenue_vehicle_hours": VH_CAP}}
    sel = Exp4Selection(POOL_VERSION, frozenset(lines), frozenset())
    built = assemble(sel, _BY_RID, graph, H.baseline.network.stops,
                     pool_version=POOL_VERSION,
                     first_dep_sec_by_period=_first_dep_by_period())
    t0 = time.time()
    start = solve_on_network(built.network, built.tstats, harness=H, stops_gdf=sg,
                             lam=LAM, seed=SEED, iterations=20_000, restarts=1,
                             width=0, constraints=cons,
                             waiting_model="same_route", starts="greedy",
                             allow_off=True, solver="gen1", include_setup=True)
    judge = start["judge"]; model = judge.model; budget = judge.budget
    ladders = {k: sorted(judge.ladders[k]) for k in model.keys}
    w_uns = model.w.unserved
    print(f"setup {time.time()-t0:.0f}s")
    print("BUDGET ACTUALLY IN FORCE:")
    print(f"  revenue_veh_hours {budget.revenue_veh_hours:.6f} "
          f"(vh_cap with tolerance {budget.vh_cap():.6f})")
    print(f"  tolerance {budget.tolerance}")
    print(f"  peak_vehicles_by_period {json.dumps({k: round(float(v),4) for k,v in sorted(budget.peak_vehicles_by_period.items())})}")

    raw = cert["plan_EXACT"]
    plan = {}
    for kk, v in raw.items():
        r, _, p = kk.partition("|")
        plan[(r, p)] = (math.inf if (v is None or isinstance(v, str)
                        or (isinstance(v, float) and (math.isinf(v) or v >= 1e5)))
                        else float(v))
    base_h = np.array([plan[k] for k in model.keys], float)
    base_fit = model.evaluate_array(base_h)
    base_obj = float(base_fit.scalarized(w_uns, LAM))
    print(f"reproduced {base_obj:.6f} vs certified {LEADER_OBJ:.6f} "
          f"rel {abs(base_obj-LEADER_OBJ)/LEADER_OBJ:.3e}")
    print(f"baseline feasible under the FULL test: {_feasible(model, base_fit, budget)}")
    print("baseline peak_by_period vs cap:")
    for p in sorted(budget.peak_vehicles_by_period):
        print(f"   {p:<9} used {float(base_fit.peak_by_period.get(p,0.0)):8.3f}  "
              f"cap {budget.peak_cap(p):8.3f}")

    def restricted_window(lad, cur, k):
        def dist(v):
            if math.isinf(v) and math.isinf(cur): return 0.0
            if math.isinf(v) or math.isinf(cur): return float("inf")
            return abs(v - cur)
        i = min(range(len(lad)), key=lambda j: dist(lad[j]))
        lo = max(0, min(i - k // 2, len(lad) - k))
        return lad[lo:lo + k] or [lad[i]]

    off_keys = [k for k in model.keys if math.isinf(base_h[model.key_index[k]])]
    probes = []
    for k in off_keys:
        idx = model.key_index[k]; lad = ladders[k]
        win = {h for h in restricted_window(lad, math.inf, K_RUNGS)
               if not math.isinf(h)}
        for h in [x for x in lad if not math.isinf(x)]:
            hh = base_h.copy(); hh[idx] = h
            fit = model.evaluate_array(hh)
            obj = float(fit.scalarized(w_uns, LAM))
            feas = bool(_feasible(model, fit, budget))
            binding = [p for p in budget.peak_vehicles_by_period
                       if float(fit.peak_by_period.get(p, 0.0)) > budget.peak_cap(p)]
            probes.append({
                "key": f"{k[0]}|{k[1]}", "headway": h, "rung_index": lad.index(h),
                "in_k3_window": h in win,
                "objective": obj, "delta_objective": obj - base_obj,
                "improves": obj < base_obj - 1e-9,
                "feasible_full_test": feas,
                "hours_ok": float(fit.revenue_veh_hours) <= budget.vh_cap(),
                "peak_periods_violated": binding,
                "veh_hours": float(fit.revenue_veh_hours),
                "delta_veh_hours": float(fit.revenue_veh_hours)
                                   - float(base_fit.revenue_veh_hours),
            })
    adm = [p for p in probes if p["improves"] and p["feasible_full_test"]]
    adm.sort(key=lambda p: p["delta_objective"])
    payload = {
        "diagnostic": "exp5_offon_full_feasibility",
        "leader": LEADER, "lam": LAM, "k_rungs": K_RUNGS,
        "budget_in_force": {
            "revenue_veh_hours": budget.revenue_veh_hours,
            "vh_cap_with_tolerance": budget.vh_cap(),
            "tolerance": budget.tolerance,
            "peak_vehicles_by_period": {k: float(v) for k, v in
                                        sorted(budget.peak_vehicles_by_period.items())},
            "peak_cap_with_tolerance": {p: budget.peak_cap(p) for p in
                                        sorted(budget.peak_vehicles_by_period)},
        },
        "baseline": {
            "objective": base_obj, "reproduced_exactly":
                abs(base_obj - LEADER_OBJ) / LEADER_OBJ < 1e-9,
            "veh_hours": float(base_fit.revenue_veh_hours),
            "peak_by_period": {k: float(v) for k, v in
                               sorted(base_fit.peak_by_period.items())},
            "feasible_full_test": bool(_feasible(model, base_fit, budget)),
            "n_route_periods": len(model.keys), "n_off": len(off_keys),
        },
        "n_probes": len(probes),
        "n_improving_any": sum(1 for p in probes if p["improves"]),
        "n_improving_and_admissible": len(adm),
        "n_improving_but_infeasible": sum(1 for p in probes
                                          if p["improves"] and not p["feasible_full_test"]),
        "n_improving_admissible_in_k3_window":
            sum(1 for p in adm if p["in_k3_window"]),
        "best_improving_admissible": adm[0] if adm else None,
        "best_improving_admissible_in_window":
            next((p for p in adm if p["in_k3_window"]), None),
        "probes": probes,
    }
    (OUT / "offon_full_feasibility.json").write_text(json.dumps(payload, indent=1))
    print()
    print(f"probes {len(probes)}  improving {payload['n_improving_any']}  "
          f"improving AND admissible {len(adm)}  "
          f"improving but INFEASIBLE {payload['n_improving_but_infeasible']}")
    print(f"improving+admissible inside the k=3 window: "
          f"{payload['n_improving_admissible_in_k3_window']}")
    if adm:
        b = adm[0]
        print(f"best admissible: {b['key']} -> {b['headway']} min "
              f"delta {b['delta_objective']:,.4f} in_window={b['in_k3_window']}")
    w = payload["best_improving_admissible_in_window"]
    if w:
        print(f"best admissible IN WINDOW: {w['key']} -> {w['headway']} min "
              f"delta {w['delta_objective']:,.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
