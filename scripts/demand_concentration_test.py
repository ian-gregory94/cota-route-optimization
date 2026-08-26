#!/usr/bin/env python3
"""Skeptic test: does the Experiment 1 prescription survive a sharper demand model?

The LODES-derived proxy measures *spatial access* — workers and jobs within a
600 m stop catchment, split evenly among the routes serving each stop. Real bus
ridership is far more concentrated on trunk routes than access is, so the proxy
is expected to be too flat. If the optimizer's prescription ("move hours from
frequent trunk routes to infrequent coverage routes") reverses once demand is
concentrated, then the prescription is an artifact of the proxy, not a finding.

Three demand models are compared:
  access      — the LODES proxy as built (the experiment's default)
  sharpened   — proxy ** alpha, renormalized (alpha > 1 concentrates)
  revealed    — blended with baseline service level as a revealed-preference
                signal: COTA already runs more service where more people ride
"""
from __future__ import annotations

import copy
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from cota_opt.baseline import build_baseline
from cota_opt.exp1 import build_setup, plan_diff
from cota_opt.frequency import PassengerDemand, optimize_frequencies

UPLOADS = Path("/mnt/user-data/uploads/Downloads")
DEMAND_FILES = {"rac": UPLOADS / "oh_rac_S000_JT00_2022.csv.gz",
                "wac": UPLOADS / "oh_wac_S000_JT00_2022.csv.gz",
                "centroids": UPLOADS / "CenPop2020_Mean_BG39.txt"}
SEED = 20260825


def gini(x: np.ndarray) -> float:
    x = np.sort(np.asarray(x, float))
    n = len(x)
    if n == 0 or x.sum() == 0:
        return 0.0
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


def reweight(setup, mode: str, alpha: float = 1.0) -> PassengerDemand:
    base = setup.model.demand.by_route_period
    total = sum(base.values())
    if mode == "access":
        return setup.model.demand
    if mode == "sharpened":
        new = {k: v ** alpha for k, v in base.items()}
    elif mode == "revealed":
        # blend access with baseline trips (revealed service allocation)
        trips = {k: setup.model.services[k].baseline_trips for k in base}
        tmax = max(trips.values())
        amax = max(base.values()) or 1.0
        new = {k: (base[k] / amax) ** (1 - alpha) * (trips[k] / tmax) ** alpha
               for k in base}
    else:
        raise ValueError(mode)
    s = sum(new.values())
    new = {k: v * total / s for k, v in new.items()}
    return PassengerDemand(new, source=f"{mode}(alpha={alpha})")


def run(setup, demand, label: str) -> dict:
    m = copy.copy(setup.model)
    m.demand = demand
    m._build_arrays()
    bf = m.evaluate(setup.baseline_plan)
    res = {}
    for lam in (0.5, 1.0):
        r = optimize_frequencies(m, setup.budget, ladder=[], unserved_multiplier=lam,
                                 local_search_iterations=400_000, seed=SEED,
                                 ladders=setup.ladders, initial=setup.baseline_plan,
                                 n_restarts=12)
        d = pd.DataFrame([
            {"key": k, "baseline": setup.baseline_plan.headways[k],
             "opt": r.plan.headways[k],
             "demand": demand.by_route_period.get(k, 0.0)}
            for k in r.plan.headways])
        d["chg"] = d["opt"] - d["baseline"]
        d["band"] = pd.cut(d["baseline"], [0, 15, 30, 60, 1e9],
                           labels=["<=15", "15-30", "30-60", ">60"])
        by_band = d.groupby("band", observed=True)["chg"].mean()
        res[lam] = {
            "gc_change_pct": (r.fitness.generalized_cost / bf.generalized_cost - 1) * 100,
            "unserved_change_pct": (r.fitness.unserved_demand / bf.unserved_demand - 1) * 100
            if bf.unserved_demand else float("nan"),
            "mean_hw_chg_frequent": float(by_band.get("<=15", np.nan)),
            "mean_hw_chg_infrequent": float(by_band.get(">60", np.nan)),
        }
    return res


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    b = build_baseline(demand_files=DEMAND_FILES, write=False)
    setup = build_setup(b)

    models = [
        ("access (as built)", reweight(setup, "access")),
        ("sharpened alpha=1.5", reweight(setup, "sharpened", 1.5)),
        ("sharpened alpha=2.0", reweight(setup, "sharpened", 2.0)),
        ("sharpened alpha=3.0", reweight(setup, "sharpened", 3.0)),
        ("revealed blend 0.5", reweight(setup, "revealed", 0.5)),
        ("revealed blend 0.8", reweight(setup, "revealed", 0.8)),
    ]
    rows = []
    for name, dem in models:
        vals = np.array(list(dem.by_route_period.values()))
        g = gini(vals)
        out = run(setup, dem, name)
        for lam, r in out.items():
            rows.append({"demand_model": name, "gini": g, "lambda": lam, **r})
        print(f"{name:22s} gini={g:.3f}  "
              f"λ=0.5 gc {out[0.5]['gc_change_pct']:+6.2f}% uns {out[0.5]['unserved_change_pct']:+7.2f}%  "
              f"Δhw frequent {out[0.5]['mean_hw_chg_frequent']:+6.1f} "
              f"infrequent {out[0.5]['mean_hw_chg_infrequent']:+7.1f}")
    df = pd.DataFrame(rows)
    out = ROOT / "outputs" / "demand_concentration_test.csv"
    df.to_csv(out, index=False)
    print(f"\nwrote {out}")
    print("\nΔhw > 0 on frequent routes = service moved AWAY from trunks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
