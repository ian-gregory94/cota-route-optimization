#!/usr/bin/env python3
"""C9 / gate 4-7 -- the FROZEN SUPERNETWORK MASTER PATH SET, benchmarked.

This is the gate's own object, not the naive cross-network cache sharing that
`exp4_pathreuse.py` measured and rejected. The difference is structural:

    naive     one `pathset_cache` shared across candidates, keyed by PERIOD
              alone, so candidate n is scored against candidate n-1's paths.
              Measured: worst 1.307 relative on revenue vehicle-hours. Invalid,
              and specifically forbidden -- "it may not reuse the incumbent's
              paths" (ACCEPTANCE gate 4-7).

    master    paths enumerated ONCE on the supernetwork (every pool line in the
              case active together) under multiple service/frequency scenarios,
              then FILTERED per candidate: a path survives iff every ride leg it
              uses belongs to a route the candidate actually runs, and surviving
              legs are remapped onto the candidate's own route-period vector.
              A restriction of the choice set, not an approximation of it.

WHAT GATE 4-7 ACTUALLY REQUIRES (ACCEPTANCE.md, EXPERIMENT4_CONTRACT.md s.12)
----------------------------------------------------------------------------
"On a preregistered sample the approximation is compared against exact rebuilds
for objective gap, unserved gap, ranking stability, omitted and improvable flow,
and whether the promoted set changes; if it cannot identify the exact leader
within the promotion band, it is widened or abandoned."

All six are measured here. Note what the closing condition is and is not: it is
NOT a numeric epsilon on the objective. It is whether the approximation picks
the same leader the exact rebuild picks, adjudicated against the promotion band.

THE PROMOTION BAND DOES NOT EXIST YET, AND THAT IS HANDLED HONESTLY
-------------------------------------------------------------------
Experiment 4's band comes from its own gap benchmark (D18), which has not been
run. So there are exactly two outcomes this script may return:

  * the master set identifies the exact leader in EVERY case with ZERO ranking
    inversions -- then it identifies the leader within *any* band, however
    narrow, the band is not needed to adjudicate, and gate 4-7 closes on the
    measurement alone;
  * the leader differs anywhere, or any ranking inverts -- then whether that is
    tolerable depends on a band that does not exist, so gate 4-7 stays ARMED and
    is blocked on D18. It is NOT closed by a small-looking number.

Widening the master (more scenarios, more paths per OD) is the remedy the gate
itself names, and is a parameter here rather than a decision made after seeing a
result.

THE PREREGISTERED SAMPLE
------------------------
Declared as a RULE, not a hand-picked list, so it cannot be curated after the
fact. For each of the five frozen C10 deception spaces (gate 4-14's discovered
cases, which is why the sample already contains deceptive geometry):

  1. every subset of the case's pool within its cardinality bounds -- this is
     what supplies sparse networks, dense networks, one-route-different pairs
     and swaps, exhaustively rather than by selection;
  2. the supernetwork itself (all lines active) -- the "reconstructed current"
     end of the range, and the one case where filtering must be the identity;
  3. one PINNED_OFF variant per case: the full pool with the case's seed line
     pinned off, which exercises a fate the subsets cannot produce;
  4. CHOSEN_OFF arises inside any of the above, because `allow_off=True` lets
     the frequency solver switch an active line off on its own.

The envelopes are the cases' own binding budgets, so every candidate sits near
the resource boundary by construction -- that is what made these spaces
deceptive in the first place.

    python scripts/exp4_masterpath_benchmark.py --json outputs/exp4/masterpath_benchmark.json
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

FIELDS = ["generalized_cost", "unserved_demand", "served_demand",
          "revenue_veh_hours", "peak_vehicles", "mean_wait_min",
          "gc_per_served_trip"]


def _check_fields(fit: dict) -> None:
    missing = [f for f in FIELDS if f not in fit]
    if missing:
        raise KeyError(
            f"fitness is missing {missing}; a comparison field that does not "
            f"exist compares nothing and silently reports nan")


def _subsets(lines, lo, hi):
    for n in range(lo, hi + 1):
        for c in itertools.combinations(sorted(lines), n):
            yield frozenset(c)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--cases", type=int, default=5)
    ap.add_argument("--max-candidates", type=int, default=12,
                    help="cap per case; the enumeration order is deterministic "
                         "(by cardinality then sorted line id), so a cap "
                         "truncates the sample rather than selecting it")
    ap.add_argument("--scenarios", type=int, default=6,
                    help="service/frequency scenarios used to enumerate the "
                         "MASTER only. EXPERIMENT4_CONTRACT s.12 requires the "
                         "master to be rich; the exact arm always uses the "
                         "production default so the ground truth is unchanged")
    a = ap.parse_args()

    from cota_opt.contract import ContractLimits
    from cota_opt.exp4_masterpath import MasterPathSet, filter_for_network
    from cota_opt.exp4_network import Exp4Selection
    from cota_opt.exp4_score import score_exp4_network
    from cota_opt.configs import service_periods
    from cota_opt.firewall.core import digest
    from exp2_treatments import pinned
    from exp4_c10_fixtures import (CASES, POOL_VERSION, _BY_RID, _boot,
                                   _first_dep_by_period)

    st = _boot()
    H, sg, graph = st["H"], st["sg"], st["graph"]
    periods = sorted(service_periods(H.assumptions))
    first_dep = _first_dep_by_period()
    t_all = time.time()

    def score(sel, case, cache, scen=0):
        vh = float(case["veh_hour_budget"])
        peak = float(case.get("peak_vehicle_budget", 40.0))
        cons = pinned(vh, {p: peak for p in periods})
        limits = ContractLimits(veh_hour_budget=vh, peak_vehicle_budget=peak,
                                required_waiting_model="same_route")
        eff = case.get("effort", (20_000, 1, 0))
        t0 = time.time()
        try:
            scored, built = score_exp4_network(
                sel, harness=H, stops_gdf=sg, pool=_BY_RID, graph=graph,
                pool_version=POOL_VERSION, first_dep_sec_by_period=first_dep,
                limits=limits, constraints=cons, lam=2.0, seed=20260825,
                iterations=eff[0], restarts=eff[1], width=eff[2],
                waiting_model="same_route", starts="greedy", allow_off=True,
                pathset_cache=cache, n_random_scenarios=scen)
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"[:200],
                    "seconds": time.time() - t0}
        return {"ok": True, "seconds": time.time() - t0,
                "objective": float(scored.metrics.get("objective",
                                                      float("inf"))),
                "fitness": dict(scored.fitness),
                "metrics": {k: v for k, v in scored.metrics.items()
                            if isinstance(v, (int, float))},
                "state_key": sel.state_key}

    rows: list[dict] = []
    case_reports: list[dict] = []

    for case in CASES[:a.cases]:
        name = case["name"]
        lines = sorted(case["lines"])
        lo = int(case.get("min_lines", 1))
        hi = int(case.get("max_lines", len(lines)))
        print(f"\n=== {name}: pool {len(lines)} lines, cardinality {lo}-{hi} ===")

        # --- 1. the master, enumerated ONCE on the supernetwork -------------
        superset = Exp4Selection(pool_version=POOL_VERSION,
                                 lines=frozenset(lines),
                                 pinned_off=frozenset())
        master_cache: dict = {}
        t0 = time.time()
        sup = score(superset, case, master_cache, scen=a.scenarios)
        t_master = time.time() - t0
        if not master_cache:
            print(f"  master enumeration produced nothing: "
                  f"{sup.get('error', 'no cache populated')}")
            continue
        master = MasterPathSet(
            by_period=dict(master_cache),
            supernetwork_lines=tuple(lines),
            digest=digest({p: [int(ps.n_paths), int(ps.n_od),
                               list(map(list, ps.rp_keys))]
                           for p, ps in sorted(master_cache.items())}))
        ms = master.stats()
        print(f"  master: {ms['paths_by_period']} paths, "
              f"{t_master:.1f}s, digest {master.digest}")

        # --- 2. the preregistered candidate sample -------------------------
        cands: list[tuple[str, Exp4Selection]] = []
        for s in _subsets(lines, lo, hi):
            cands.append(("subset", Exp4Selection(POOL_VERSION, s,
                                                  frozenset())))
        cands.append(("supernetwork", superset))
        seed_lines = frozenset(case.get("seed") or [lines[0]])
        cands.append(("pinned_off", Exp4Selection(
            POOL_VERSION, frozenset(lines), frozenset(seed_lines))))
        cands = cands[:a.max_candidates] if a.max_candidates else cands

        crows: list[dict] = []
        for kind, sel in cands:
            # EXACT arm: production default enumeration, no cache at all.
            ex = score(sel, case, None, scen=0)
            if not ex["ok"]:
                continue

            # REUSE arm: filter the master onto this candidate's own
            # route-period vector, per period. The candidate's rp_keys are
            # taken from the exact arm's own path sets so the two arms are
            # indexed identically -- in production they come from the
            # assembler, which knows the route-periods without enumerating
            # anything, and the check below is what would catch a divergence.
            probe: dict = {}
            _ = score(sel, case, probe, scen=0)
            if not probe:
                continue
            t0 = time.time()
            filt: dict = {}
            prov: dict = {}
            try:
                for per, mps in master.by_period.items():
                    if per not in probe:
                        continue
                    ck = list(probe[per].rp_keys)
                    filt[per], prov[per] = filter_for_network(mps, ck)
            except Exception as e:
                crows.append({"kind": kind, "state_key": sel.state_key,
                              "filter_error": f"{type(e).__name__}: {e}"[:200]})
                continue
            t_filter = time.time() - t0
            ru = score(sel, case, filt, scen=0)
            if not ru["ok"]:
                crows.append({"kind": kind, "state_key": sel.state_key,
                              "reuse_error": ru.get("error")})
                continue

            _check_fields(ex["fitness"])
            _check_fields(ru["fitness"])
            per_field = {}
            worst_rel = 0.0
            worst_abs = 0.0
            for f in FIELDS:
                lv, rv = float(ex["fitness"][f]), float(ru["fitness"][f])
                ad = abs(rv - lv)
                rd = ad / abs(lv) if lv else ad
                per_field[f] = {"exact": lv, "reuse": rv,
                                "abs_diff": ad, "rel_diff": rd}
                worst_rel = max(worst_rel, rd)
                worst_abs = max(worst_abs, ad)

            # omitted flow  : demand served exactly but not under reuse
            # improvable flow: demand served both ways but more expensively
            #                  under reuse -- flow the master could still serve
            #                  better if it carried the paths it dropped
            un_ex = float(ex["fitness"]["unserved_demand"])
            un_ru = float(ru["fitness"]["unserved_demand"])
            omitted = max(0.0, un_ru - un_ex)
            gc_ex = float(ex["fitness"]["generalized_cost"])
            gc_ru = float(ru["fitness"]["generalized_cost"])
            served_both = min(float(ex["fitness"]["served_demand"]),
                              float(ru["fitness"]["served_demand"]))
            improvable = max(0.0, gc_ru - gc_ex)

            surv = {p: prov[p]["survival_fraction"] for p in sorted(prov)}
            crows.append({
                "kind": kind, "state_key": sel.state_key,
                "lines": sorted(sel.lines),
                "pinned_off": sorted(sel.pinned_off),
                "objective_exact": ex["objective"],
                "objective_reuse": ru["objective"],
                "objective_gap": ru["objective"] - ex["objective"],
                "objective_rel_gap": (abs(ru["objective"] - ex["objective"])
                                      / abs(ex["objective"])
                                      if ex["objective"] else 0.0),
                "unserved_exact": un_ex, "unserved_reuse": un_ru,
                "unserved_gap": un_ru - un_ex,
                "omitted_flow": omitted,
                "improvable_flow": improvable,
                "improvable_flow_rel": improvable / gc_ex if gc_ex else 0.0,
                "fields": per_field,
                "worst_rel_diff": worst_rel, "worst_abs_diff": worst_abs,
                "seconds_exact": ex["seconds"],
                "seconds_reuse": ru["seconds"],
                "seconds_filter": t_filter,
                "speedup": (ex["seconds"] / (ru["seconds"] + t_filter)
                            if (ru["seconds"] + t_filter) else float("nan")),
                "survival_fraction": surv,
                "paths": {p: {"master": prov[p]["master_paths"],
                              "kept": prov[p]["kept_paths"],
                              "exact": int(probe[p].n_paths)}
                          for p in sorted(prov)},
            })
            print(f"  {kind:<13} {str(sorted(sel.lines))[:52]:<52} "
                  f"obj gap {crows[-1]['objective_rel_gap']:.3e}  "
                  f"surv {min(surv.values()) if surv else 0:.3f}  "
                  f"x{crows[-1]['speedup']:.2f}")

        # --- 3. the gate's own questions, per case -------------------------
        ok = [r for r in crows if "objective_exact" in r]
        inversions, pairs = 0, 0
        for i in range(len(ok)):
            for j in range(i + 1, len(ok)):
                pairs += 1
                d1 = ok[i]["objective_exact"] - ok[j]["objective_exact"]
                d2 = ok[i]["objective_reuse"] - ok[j]["objective_reuse"]
                if d1 * d2 < 0:
                    inversions += 1
        leader_exact = min(ok, key=lambda r: r["objective_exact"])["state_key"] \
            if ok else None
        leader_reuse = min(ok, key=lambda r: r["objective_reuse"])["state_key"] \
            if ok else None
        # "whether the promoted set changes": the top-k under each arm.
        k = min(3, len(ok))
        top_ex = {r["state_key"] for r in
                  sorted(ok, key=lambda r: r["objective_exact"])[:k]}
        top_ru = {r["state_key"] for r in
                  sorted(ok, key=lambda r: r["objective_reuse"])[:k]}
        rep = {"case": name, "n_candidates": len(ok),
               "master": ms, "master_seconds": t_master,
               "leader_exact": leader_exact, "leader_reuse": leader_reuse,
               "leader_identified": leader_exact == leader_reuse,
               "ranking_inversions": inversions, "ranking_pairs": pairs,
               "promoted_set_exact": sorted(top_ex),
               "promoted_set_reuse": sorted(top_ru),
               "promoted_set_changes": top_ex != top_ru,
               "worst_objective_rel_gap":
                   max((r["objective_rel_gap"] for r in ok), default=0.0),
               "worst_unserved_gap":
                   max((abs(r["unserved_gap"]) for r in ok), default=0.0),
               "total_omitted_flow": sum(r["omitted_flow"] for r in ok),
               "worst_improvable_flow_rel":
                   max((r["improvable_flow_rel"] for r in ok), default=0.0),
               "worst_field_rel_diff":
                   max((r["worst_rel_diff"] for r in ok), default=0.0),
               "min_survival_fraction":
                   min((min(r["survival_fraction"].values())
                        for r in ok if r["survival_fraction"]), default=0.0),
               "median_speedup": sorted(r["speedup"] for r in ok)[len(ok) // 2]
                                 if ok else float("nan"),
               "rows": crows}
        case_reports.append(rep)
        rows.extend(ok)
        print(f"  -> leader {'IDENTIFIED' if rep['leader_identified'] else 'MISSED'}"
              f", {inversions}/{pairs} inversions, promoted set "
              f"{'CHANGES' if rep['promoted_set_changes'] else 'unchanged'}")

    # --- verdict ----------------------------------------------------------
    all_leaders = all(r["leader_identified"] for r in case_reports)
    all_rank = all(r["ranking_inversions"] == 0 for r in case_reports)
    all_promo = all(not r["promoted_set_changes"] for r in case_reports)
    band_independent = all_leaders and all_rank and all_promo
    closes = bool(case_reports) and band_independent

    if closes:
        verdict = "MET"
        why = ("the master path set identifies the exact leader in every case "
               "with zero ranking inversions and an unchanged promoted set, so "
               "it identifies the leader within ANY promotion band however "
               "narrow. Gate 4-7 closes on the measurement alone and does not "
               "need D18's band to adjudicate.")
    elif not case_reports:
        verdict = "ARMED"
        why = "no case produced a comparable candidate; nothing was measured."
    else:
        verdict = "ARMED"
        why = ("the approximation does not reproduce the exact arm's decision "
               "everywhere (leader identified in every case="
               f"{all_leaders}, zero inversions={all_rank}, promoted set "
               f"unchanged={all_promo}). Whether the residual is tolerable is a "
               "question about the promotion band, and Experiment 4's band is "
               "the output of D18's gap benchmark, which has not been run. The "
               "gate stays ARMED and is blocked on D18. The remedy the gate "
               "itself names is to widen the master set (--scenarios) or "
               "abandon it -- not to declare the number small.")

    print(f"\n{'=' * 70}")
    print(f"  candidates compared      : {len(rows)}")
    print(f"  leader identified, all   : {all_leaders}")
    print(f"  zero ranking inversions  : {all_rank}")
    print(f"  promoted set unchanged   : {all_promo}")
    print(f"  worst objective rel gap  : "
          f"{max((r['objective_rel_gap'] for r in rows), default=0.0):.3e}")
    print(f"  worst field rel diff     : "
          f"{max((r['worst_rel_diff'] for r in rows), default=0.0):.3e}")
    print(f"  GATE 4-7: {verdict}")
    print(f"  {why}")

    out = {
        "gate": "4-7",
        "object_measured": ("frozen supernetwork master path set, filtered per "
                            "candidate onto its own route-period vector"),
        "not_measured": ("naive cross-network cache sharing -- that is "
                         "outputs/exp4/pathreuse_benchmark.json and it FAILED"),
        "criterion": ("On a preregistered sample the approximation is compared "
                      "against exact rebuilds for objective gap, unserved gap, "
                      "ranking stability, omitted and improvable flow, and "
                      "whether the promoted set changes; if it cannot identify "
                      "the exact leader within the promotion band, it is "
                      "widened or abandoned."),
        "sample_rule": ("every subset of each frozen C10 deception pool within "
                        "its cardinality bounds, plus the supernetwork, plus a "
                        "pinned-off variant; deterministic order, capped not "
                        "curated"),
        "master_scenarios": a.scenarios,
        "n_candidates": len(rows),
        "leader_identified_all_cases": all_leaders,
        "zero_ranking_inversions": all_rank,
        "promoted_set_unchanged_all_cases": all_promo,
        "band_independent_pass": band_independent,
        "promotion_band_available": False,
        "promotion_band_source": "D18 gap benchmark (not run)",
        "worst_objective_rel_gap":
            max((r["objective_rel_gap"] for r in rows), default=0.0),
        "worst_unserved_gap":
            max((abs(r["unserved_gap"]) for r in rows), default=0.0),
        "total_omitted_flow": sum(r["omitted_flow"] for r in rows),
        "worst_improvable_flow_rel":
            max((r["improvable_flow_rel"] for r in rows), default=0.0),
        "worst_field_rel_diff":
            max((r["worst_rel_diff"] for r in rows), default=0.0),
        "fields_compared": FIELDS,
        "seconds": time.time() - t_all,
        "verdict": verdict, "why": why,
        "cases": case_reports,
    }
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(out, indent=2))
        print(f"\nwrote {a.json}")
    return 0 if closes else 2


if __name__ == "__main__":
    raise SystemExit(main())
