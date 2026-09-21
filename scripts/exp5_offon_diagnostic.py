#!/usr/bin/env python3
"""Exp 5 pre-flight diagnostic: is the ~36-37% hour utilisation the objective
or the neighbourhood?

DIAGNOSTIC ONLY. Does not launch Experiment 5. Does not modify the optimizer,
any Experiment 4 artifact, the canonical envelope, or the Experiment 5 design.
Reads outputs/exp4/run/ read-only and writes only under outputs/exp5_diag/.

Method: rebuild the certified leader's network and evaluation setup exactly as
`certify` does, reproduce its certified objective as a precondition, then hold
the certified plan fixed and move ONE OFF route-period at a time to each legal
finite rung of its own ladder, scoring every perturbation with the same exact
evaluator. No approximate/discovery score is used anywhere.
"""
from __future__ import annotations

import json, math, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

RUN = ROOT / "outputs" / "exp4" / "run"
OUT = ROOT / "outputs" / "exp5_diag"
LEADER = "exp4|exp4-pool-v1|65lines#ecb2ffc4bcce"
LEADER_OBJ = 3511184.5657525407
LAM, SEED = 2.0, 20260825
K_RUNGS = 3          # mirrors exp4_certify.K_RUNGS; not imported to avoid drift


def restricted_window(lad_sorted, cur, k):
    """Verbatim re-implementation of exp4_certify._restricted for ONE free key."""
    def dist(v):
        if math.isinf(v) and math.isinf(cur):
            return 0.0
        if math.isinf(v) or math.isinf(cur):
            return float("inf")
        return abs(v - cur)
    i = min(range(len(lad_sorted)), key=lambda j: dist(lad_sorted[j]))
    lo = max(0, min(i - k // 2, len(lad_sorted) - k))
    return i, (lad_sorted[lo:lo + k] or [lad_sorted[i]])


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    from cota_opt.configs import load_constraints
    from cota_opt.exp3_score import solve_on_network
    from cota_opt.exp4_assemble import assemble
    from cota_opt.exp4_network import Exp4Selection
    from exp4_c10_fixtures import POOL_VERSION, _BY_RID, _boot, _first_dep_by_period

    prop = json.loads((RUN / "proposals.json").read_text())["proposals"]
    lines = {p["state_key"]: p["lines"] for p in prop}[LEADER]
    cert = None
    for p in (RUN / "certified").glob("*.json"):
        d = json.load(open(p))
        if d.get("state_key") == LEADER:
            cert = d
            break
    if cert is None:
        print("FATAL: leader certified record not found"); return 2

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
    start = solve_on_network(built.network, built.tstats, harness=H,
                             stops_gdf=sg, lam=LAM, seed=SEED,
                             iterations=20_000, restarts=1, width=0,
                             constraints=cons, waiting_model="same_route",
                             starts="greedy", allow_off=True, solver="gen1",
                             include_setup=True)
    judge = start["judge"]; model = judge.model
    ladders = {k: sorted(judge.ladders[k]) for k in model.keys}
    w_uns = model.w.unserved
    print(f"setup built in {time.time() - t0:.0f}s; {len(model.keys)} route-periods")

    # ---- reconstruct the certified plan on this model's key order ----------
    raw = cert["plan_EXACT"]
    plan = {}
    for kk, v in raw.items():
        r, _, p = kk.partition("|")
        plan[(r, p)] = math.inf if (v is None or (isinstance(v, str)) or
                                    (isinstance(v, float) and
                                     (math.isinf(v) or v >= 1e5))) else float(v)
    missing = [k for k in model.keys if k not in plan]
    if missing:
        print(f"FATAL: {len(missing)} model keys absent from plan_EXACT"); return 2

    import numpy as np
    base_h = np.array([plan[k] for k in model.keys], float)
    base_fit = model.evaluate_array(base_h)
    base_obj = float(base_fit.scalarized(w_uns, LAM))
    rel = abs(base_obj - LEADER_OBJ) / LEADER_OBJ
    print(f"certified objective  {LEADER_OBJ:.6f}")
    print(f"reproduced objective {base_obj:.6f}   rel err {rel:.3e}")
    repro_ok = rel < 1e-9
    print("REPRODUCTION:", "OK" if repro_ok else "FAILED -- probes are not comparable")

    # ---- reachability trace -----------------------------------------------
    off_keys = [k for k in model.keys if math.isinf(base_h[model.key_index[k]])]
    reach = []
    for k in off_keys:
        lad = ladders[k]
        n = len(lad)
        off_idx = n - 1 if math.isinf(lad[-1]) else None
        finite = [h for h in lad if not math.isinf(h)]
        first_on = max(finite) if finite else None          # rung adjacent to OFF
        first_on_idx = lad.index(first_on) if first_on is not None else None
        i, window = restricted_window(lad, math.inf, K_RUNGS)
        reach.append({
            "key": f"{k[0]}|{k[1]}", "n_rungs": n, "off_index": off_idx,
            "first_on_headway": first_on, "first_on_index": first_on_idx,
            "rung_distance_off_to_first_on": (None if first_on_idx is None
                                              else off_idx - first_on_idx),
            "anchor_index_selected": i,
            "window_k3": [None if math.isinf(x) else x for x in window],
            "n_finite_in_window": sum(1 for x in window if not math.isinf(x)),
            "best_headway_in_window": (min([x for x in window
                                            if not math.isinf(x)], default=None)),
            "best_headway_in_ladder": (min(finite) if finite else None),
        })

    # ---- exact perturbation probes ----------------------------------------
    probes = []
    t1 = time.time()
    for k in off_keys:
        idx = model.key_index[k]
        lad = ladders[k]
        finite = [h for h in lad if not math.isinf(h)]
        _i, window = restricted_window(lad, math.inf, K_RUNGS)
        win_finite = {h for h in window if not math.isinf(h)}
        for h in finite:
            hh = base_h.copy(); hh[idx] = h
            fit = model.evaluate_array(hh)
            obj = float(fit.scalarized(w_uns, LAM))
            probes.append({
                "key": f"{k[0]}|{k[1]}", "headway": h,
                "rung_index": lad.index(h),
                "in_k3_window": h in win_finite,
                "objective": obj,
                "delta_objective": obj - base_obj,
                "improves": obj < base_obj - 1e-9,
                "veh_hours": float(fit.revenue_veh_hours),
                "delta_veh_hours": float(fit.revenue_veh_hours)
                                   - float(base_fit.revenue_veh_hours),
                "under_cap": float(fit.revenue_veh_hours) <= VH_CAP,
                "unserved": float(fit.unserved_demand),
                "generalized_cost": float(fit.generalized_cost),
            })
    print(f"{len(probes)} exact probes over {len(off_keys)} OFF route-periods "
          f"in {time.time() - t1:.0f}s")

    imp = [p for p in probes if p["improves"]]
    imp.sort(key=lambda p: p["delta_objective"])
    payload = {
        "diagnostic": "exp5_offon_reachability_and_improvement",
        "leader": LEADER, "lam": LAM, "seed": SEED, "k_rungs": K_RUNGS,
        "veh_hour_cap": VH_CAP,
        "reproduction": {"certified": LEADER_OBJ, "recomputed": base_obj,
                         "rel_err": rel, "ok": repro_ok},
        "baseline": {"objective": base_obj,
                     "veh_hours": float(base_fit.revenue_veh_hours),
                     "veh_hours_pct_of_cap":
                         float(base_fit.revenue_veh_hours) / VH_CAP * 100.0,
                     "unserved_demand": float(base_fit.unserved_demand),
                     "generalized_cost": float(base_fit.generalized_cost),
                     "n_route_periods": len(model.keys),
                     "n_off": len(off_keys),
                     "pct_off": len(off_keys) / len(model.keys) * 100.0},
        "n_probes": len(probes),
        "n_improving": len(imp),
        "n_improving_in_k3_window": sum(1 for p in imp if p["in_k3_window"]),
        "n_improving_outside_k3_window": sum(1 for p in imp
                                             if not p["in_k3_window"]),
        "best_improving": imp[0] if imp else None,
        "reachability": reach,
        "probes": probes,
    }
    (OUT / "offon_probe.json").write_text(json.dumps(payload, indent=1))
    print(f"wrote {OUT / 'offon_probe.json'}")
    print(f"improving probes: {len(imp)} of {len(probes)}")
    if imp:
        b = imp[0]
        print(f"best: {b['key']} -> {b['headway']} min, "
              f"delta {b['delta_objective']:,.4f}, in_k3_window={b['in_k3_window']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
