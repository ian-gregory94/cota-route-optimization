#!/usr/bin/env python3
"""Two checks the path-based experiment owes.

1. **Path-set adequacy.** The optimizer chooses among cached candidate paths.
   If the optimized plan makes some path attractive that was never enumerated,
   the reported cost is too high. Full RAPTOR is re-run under the optimized
   headways and compared against the cached-set answer, OD pair by OD pair.

2. **Does crowding actually bind?** Peak-load-point passengers per bus are
   reported for the busiest route-periods, so "crowding never binds" is settled
   with numbers rather than asserted.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from cota_opt import geo
from cota_opt.baseline import CENTRAL_OHIO_FIPS, build_baseline
from cota_opt.configs import load_cost_weights, service_periods
from cota_opt.cost import CostWeights
from cota_opt.crowding import build_load_profile, segment_loads
from cota_opt.exp1 import build_setup as exp1_setup
from cota_opt.odmatrix import (_top_k, ODTable, build_zone_system,
                               filter_to_accessible, from_lodes_od, scale_to)
from cota_opt.pathset import PathSetEvaluator, build_pathset
from cota_opt.raptor import build_raptor_network, generalized_cost, pattern_headways
from cota_opt.registry import Registry

log = logging.getLogger("verify")

UPLOADS = Path("/mnt/user-data/uploads/Downloads")
DEMAND_FILES = {"rac": UPLOADS / "oh_rac_S000_JT00_2022.csv.gz",
                "wac": UPLOADS / "oh_wac_S000_JT00_2022.csv.gz",
                "centroids": UPLOADS / "CenPop2020_Mean_BG39.txt"}
PERIOD = "am_peak"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    b = build_baseline(demand_files=DEMAND_FILES, write=False)
    a = b.assumptions
    pa = a["path_assignment"]
    periods = service_periods(a)
    sg = geo.stops_gdf(b.feed, a["crs"]["projected"])
    rn = build_raptor_network(b.feed, b.network, b.tstats, sg,
                              walk_radius_m=float(pa["walk_radius_m"]),
                              walk_speed_m_per_min=float(pa["walk_speed_m_per_min"]),
                              periods=periods, with_timetable=False)
    zs = build_zone_system(b.demand["bg_frame"], sg,
                           radius_m=float(pa["access_radius_m"]),
                           walk_speed_m_per_min=float(pa["walk_speed_m_per_min"]),
                           stop_index=rn.stop_index)
    reg = Registry()
    od = _top_k(filter_to_accessible(
        from_lodes_od(reg.path_for("lodes_od_oh"), zs,
                      county_fips=CENTRAL_OHIO_FIPS), zs), int(pa["od_top_k"]))
    od = scale_to(od, float(a["demand_proxy"]["assumed_weekday_linked_trips"]))
    share = float(a["demand_proxy"]["period_shares"][PERIOD])
    od_p = ODTable(od.origin, od.dest, od.flow * share, od.source, od.notes)

    e1 = exp1_setup(b)
    services = e1.model.services
    base_hw = {k: v.baseline_headway_min for k, v in services.items()}
    w = CostWeights.from_config(load_cost_weights())
    wk = dict(random_arrival_threshold_min=float(a["waiting"]["random_arrival_threshold_min"]),
              schedule_coefficient=float(a["waiting"]["schedule_coefficient"]))

    ps = build_pathset(rn, zs, od_p, PERIOD, base_hw, w, wk,
                       max_rounds=int(pa["max_rounds"]),
                       max_paths_per_od=int(pa["max_paths_per_od"]),
                       n_random_scenarios=int(pa["n_random_scenarios"]), seed=20260825)
    ev = PathSetEvaluator(ps, w, wk, float(load_cost_weights()["unserved"]),
                          retention_full_min=float(pa["cost_retention_full_min"]),
                          retention_zero_min=float(pa["cost_retention_zero_min"]),
                          retention_floor=float(pa["cost_retention_floor"]))

    # -- load the optimized plan from the ablation -------------------------
    exps = sorted((ROOT / "outputs" / "experiments").glob("exp3_ablation_*"))
    plan_csv = exps[-1] / "plan_diff_C.csv"
    diff = pd.read_csv(plan_csv, dtype={"route_id": str})
    opt_hw = dict(base_hw)
    for r in diff.itertuples():
        opt_hw[(r.route_id, r.period)] = float(r.optimized_headway_min)

    out: dict = {"period": PERIOD, "plan_source": str(plan_csv)}

    # -- check 1: path-set adequacy ---------------------------------------
    for label, hw in (("baseline", base_hw), ("optimized", opt_hw)):
        sub = np.array([hw[k] for k in ps.rp_keys])
        cached = ev.od_costs(sub)
        ph = pattern_headways(rn, hw, PERIOD)

        fresh = np.full(ps.n_od, np.inf)
        order = np.lexsort((ps.od_flow * 0, np.arange(ps.n_od)))  # keep order
        o_sorted = np.array([0])  # placeholder
        # one RAPTOR run per origin zone, exactly as the enumerator does
        origins = np.unique(od_p.origin)
        pos = {}
        srt = np.lexsort((od_p.dest, od_p.origin))
        o_s, d_s = od_p.origin[srt], od_p.dest[srt]
        starts = np.searchsorted(o_s, origins, side="left")
        ends = np.searchsorted(o_s, origins, side="right")
        for z, s0, s1 in zip(origins, starts, ends):
            a_stops, a_walk = zs.access_of(int(z))
            if len(a_stops) == 0:
                continue
            cost, _, _ = generalized_cost(
                rn, [rn.stop_ids[s] for s in a_stops], ph, w, wk,
                max_rounds=int(pa["max_rounds"]),
                source_costs=[w.walking * x for x in a_walk])
            for oi in range(s0, s1):
                e_stops, e_walk = zs.access_of(int(d_s[oi]))
                if len(e_stops) == 0:
                    continue
                fresh[oi] = float(np.min(cost[e_stops] + w.walking * e_walk))

        both = np.isfinite(cached) & np.isfinite(fresh)
        gap = cached[both] - fresh[both]
        flow = ps.od_flow[both]
        newly = int((np.isfinite(fresh) & ~np.isfinite(cached)).sum())
        out[f"adequacy_{label}"] = {
            "od_pairs_compared": int(both.sum()),
            "mean_cost_overstatement_min": float((gap * flow).sum() / flow.sum()),
            "mean_cost_overstatement_pct": float(
                (gap * flow).sum() / (cached[both] * flow).sum() * 100),
            "p95_overstatement_min": float(np.percentile(gap, 95)),
            "max_overstatement_min": float(gap.max()),
            "pairs_where_raptor_beats_cache": int((gap > 1e-6).sum()),
            "pairs_reachable_only_by_raptor": newly,
        }
        log.info("%s: cached set overstates cost by %.3f min on average "
                 "(%.2f%%), %d/%d pairs improvable",
                 label, out[f"adequacy_{label}"]["mean_cost_overstatement_min"],
                 out[f"adequacy_{label}"]["mean_cost_overstatement_pct"],
                 out[f"adequacy_{label}"]["pairs_where_raptor_beats_cache"],
                 int(both.sum()))

    # -- check 2: does crowding bind? -------------------------------------
    sub = np.array([base_hw[k] for k in ps.rp_keys])
    pf = ev.path_flows(sub)
    lp = build_load_profile(ps, rn, pf)
    trips = np.array([services[k].n_directions
                      * (periods[k[1]][1] - periods[k[1]][0]) * 60.0 / base_hw[k]
                      for k in ps.rp_keys])
    peak_vol = lp.boardings * lp.peak_load_factor
    per_bus = np.divide(peak_vol, trips, out=np.zeros_like(peak_vol), where=trips > 0)
    cap = float(a["crowding"]["bus_capacity"])
    rows = []
    for i, k in enumerate(ps.rp_keys):
        if lp.boardings[i] <= 0:
            continue
        rows.append({"route_id": k[0], "period": k[1],
                     "boardings_modelled": lp.boardings[i],
                     "peak_segment_volume": peak_vol[i],
                     "trips": trips[i],
                     "peak_point_pax_per_bus": per_bus[i],
                     "load_factor_vs_capacity": per_bus[i] / cap})
    load_df = pd.DataFrame(rows).sort_values("peak_point_pax_per_bus", ascending=False)
    load_df.to_csv(ROOT / "outputs" / "peak_loads_am_peak.csv", index=False)
    out["crowding"] = {
        "capacity": cap,
        "route_periods_with_load": int(len(load_df)),
        "max_peak_point_pax_per_bus": float(load_df["peak_point_pax_per_bus"].max()),
        "max_load_factor": float(load_df["load_factor_vs_capacity"].max()),
        "n_over_capacity": int((load_df["load_factor_vs_capacity"] > 1).sum()),
        "total_modelled_boardings": float(lp.boardings.sum()),
    }

    (ROOT / "outputs" / "pathset_verification.json").write_text(
        json.dumps(out, indent=2, default=str))

    print("\n" + "=" * 84)
    print(f"PATH-SET ADEQUACY — {PERIOD}")
    print("=" * 84)
    for label in ("baseline", "optimized"):
        d = out[f"adequacy_{label}"]
        print(f"{label:10s} overstatement {d['mean_cost_overstatement_min']:+.3f} min "
              f"({d['mean_cost_overstatement_pct']:+.2f}%), "
              f"p95 {d['p95_overstatement_min']:.2f}, max {d['max_overstatement_min']:.2f}; "
              f"{d['pairs_where_raptor_beats_cache']}/{d['od_pairs_compared']} pairs")
    print("\nDOES CROWDING BIND?")
    print(f"  capacity {cap:.0f} pax/bus; busiest modelled route-period carries "
          f"{out['crowding']['max_peak_point_pax_per_bus']:.1f} pax/bus "
          f"({out['crowding']['max_load_factor'] * 100:.1f}% of capacity)")
    print(f"  route-periods over capacity: {out['crowding']['n_over_capacity']}")
    print("\n  top 12 by peak-point load:")
    print(load_df.head(12).round(2).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
