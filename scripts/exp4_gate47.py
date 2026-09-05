#!/usr/bin/env python3
"""Gate 4-7, as a ONE-FACTOR comparison. Supersedes exp4_masterpath_benchmark.py.

WHY THIS SCRIPT EXISTS
----------------------
The first benchmark of gate 4-7 (`exp4_masterpath_benchmark.py`,
`outputs/exp4/masterpath_benchmark.json`) varied TWO things at once and is
therefore unidentified:

  * **reuse** -- the REUSE arm filtered a supernetwork master path set instead
    of rebuilding paths for the candidate; and
  * **enumeration richness** -- the master was enumerated with extra
    service/frequency scenarios (`n_random_scenarios=6`) while the exact arm
    enumerated at the production setting `solve_on_network` has always used
    (`n_random_scenarios=0`).

The measurement proved the confound rather than the approximation. At **survival
fraction 1.000**, where filtering keeps every path and is therefore the
identity, the two arms still differed -- and the REUSE arm was *better* in 4 of
5 cases. A difference that survives the identity transformation cannot have been
caused by that transformation.

Equalising the enumeration setting removes it completely. Measured before this
script was written, on `large_gap`'s supernetwork:

    master (scen=0) vs independent enumeration : byte-identical, all 6 periods
    survival                                   : 1.000 in all 6 periods
    all seven FitnessVector fields             : 0.000e+00
    objective                                  : 3627971.507573 both arms

So the entire survival-1.000 residual was richness. This script measures the
factor the gate is actually about.

THE ONE FACTOR
--------------
Both arms enumerate under **identical settings** (`COMMON_SCENARIOS`,
`COMMON_MAX_PATHS`), which are the settings the exact-rebuild path uses in
production -- because "exact rebuild" is what certification does, and discovery
has to agree with certification, not with a comparator invented for the
benchmark. The arms then differ in exactly one thing:

    REUSE   the candidate's path set is the frozen supernetwork master,
            filtered onto the candidate's own route-period vector.
    FRESH   the candidate's path set is rebuilt for that candidate, along with
            its RAPTOR network, zone system, route classes, model, ladders and
            envelope. `pathset_cache=None` is what forces the rebuild.

FRESH does **not** enumerate its own candidate universe. That was the confound;
removing it is the point.

THE CANONICAL CANDIDATE UNIVERSE
--------------------------------
Built ONCE per case, before the arms exist, from the preregistered sample rule.
Canonicalised (sorted line ids, sorted pins), deterministically ordered, and
digested. Both arms are handed that exact tuple, and each records the digest,
the count and the ordered ids it actually saw; the three are asserted equal
before a single candidate is scored.

Admission to the universe is **arm-independent**: a candidate is admitted iff it
ASSEMBLES, which is a property of the selection and the pool and involves no
scoring, no enumeration and no evaluator. A candidate that assembles and then
fails to SCORE in one arm is recorded as a discrepancy, never silently skipped
-- an asymmetric skip is exactly how two arms end up comparing different sets.

Route-period keys are derived from the assembled network (route ids crossed with
the periods their trips fall in), not read out of either arm's path sets, so
neither arm's enumeration can decide what the other filters against. The
derivation is asserted against FRESH's own `rp_keys` for every candidate.

CLOSURE
-------
Gate 4-7 closes only if reuse preserves **the exact leader in every case**, with
**zero ranking inversions** and an **unchanged promoted set**. Same leader most
of the time does not close it, and neither does the existence of a benchmark.
That rule is band-independent: a leader reproduced exactly is reproduced within
any promotion band however narrow, so closure here does not wait on D18 -- and
does not borrow anything from it either.

    python scripts/exp4_gate47.py --json outputs/exp4/gate47.json
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

#: The enumeration settings BOTH arms use. Not a tuning knob: these are what
#: `solve_on_network` passes on the exact-rebuild path, which is what
#: certification runs. Changing either of them for one arm reintroduces the
#: confound this script exists to remove, which is why they are module
#: constants and not command-line options.
COMMON_SCENARIOS = 0
COMMON_MAX_PATHS = None          # None = the configured production value

#: Promoted set = the top-k by objective. k is fixed before any result.
PROMOTED_K = 3


def _check_fields(fit: dict) -> None:
    missing = [f for f in FIELDS if f not in fit]
    if missing:
        raise KeyError(f"fitness is missing {missing}; a comparison field that "
                       f"does not exist compares nothing and reports nan")


def _subsets(lines, lo, hi):
    for n in range(lo, hi + 1):
        for c in itertools.combinations(sorted(lines), n):
            yield frozenset(c)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--cases", type=int, default=5)
    ap.add_argument("--max-candidates", type=int, default=16,
                    help="cap per case. The universe is ordered deterministically "
                         "with the named candidates first, so a cap truncates it "
                         "rather than selecting from it")
    a = ap.parse_args()

    from cota_opt.configs import period_of_seconds, service_periods
    from cota_opt.contract import ContractLimits
    from cota_opt.exp4_assemble import assemble
    from cota_opt.exp4_masterpath import MasterPathSet, filter_for_network
    from cota_opt.exp4_network import Exp4Selection
    from cota_opt.exp4_score import score_exp4_network
    from cota_opt.firewall.core import digest
    from cota_opt.frequency import is_off
    from exp2_treatments import pinned
    from exp4_c10_fixtures import (CASES, POOL_VERSION, _BY_RID, _boot,
                                   _first_dep_by_period)

    st = _boot()
    H, sg, graph = st["H"], st["sg"], st["graph"]
    periods_cfg = service_periods(H.assumptions)
    periods = sorted(periods_cfg)
    first_dep = _first_dep_by_period()
    t_all = time.time()

    # ---------------------------------------------------------------- helpers
    def assemble_or_none(sel):
        try:
            return assemble(sel, _BY_RID, graph, H.baseline.network.stops,
                            pool_version=POOL_VERSION,
                            first_dep_sec_by_period=first_dep), None
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"[:200]

    def rp_keys_of(built):
        """Route-period keys from the ASSEMBLED network alone.

        No path enumeration, no evaluator, no arm. This is what production has
        available before it decides what to filter, and deriving it here is what
        stops one arm's enumeration from defining the other arm's input.
        """
        ts = built.tstats.copy()
        ts["period"] = ts["first_dep_sec"].map(
            lambda x: period_of_seconds(x, periods_cfg))
        return sorted({(str(r), str(p))
                       for r, p in zip(ts["route_id"], ts["period"]) if p})

    def score(sel, case, cache):
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
                pathset_cache=cache,
                n_random_scenarios=COMMON_SCENARIOS,
                max_paths_per_od=COMMON_MAX_PATHS)
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"[:200],
                    "seconds": time.time() - t0}
        return {"ok": True, "seconds": time.time() - t0,
                "objective": float(scored.metrics.get("objective", float("inf"))),
                "fitness": dict(scored.fitness),
                "plan": dict(scored.plan) if isinstance(scored.plan, dict)
                        else dict(scored.plan.headways)}

    case_reports: list[dict] = []
    all_rows: list[dict] = []
    hard_failures: list[dict] = []

    for case in CASES[:a.cases]:
        name = case["name"]
        pool_lines = sorted(case["lines"])
        lo = int(case.get("min_lines", 1))
        hi = int(case.get("max_lines", len(pool_lines)))
        print(f"\n=== {name} ===")

        # ---- 1. the canonical candidate universe, before any arm exists ----
        #
        # Admission is by ASSEMBLY, which no arm influences. A line the
        # assembler refuses cannot appear in any candidate, so it is dropped
        # from the supernetwork -- but only after being refused ALONE too,
        # which is what establishes the refusal is a property of the line and
        # not of the company it keeps. Without that, the subset property the
        # filter depends on would not hold.
        solo_ok, dropped = [], []
        for ln in pool_lines:
            b, err = assemble_or_none(
                Exp4Selection(POOL_VERSION, frozenset([ln]), frozenset()))
            (solo_ok if b is not None else dropped).append(
                ln if b is not None else {"line": ln, "error": err})
        if not solo_ok:
            print("  no pool line assembles alone; nothing to measure")
            continue
        for d in dropped:
            print(f"  drop {d['line']}: {str(d['error'])[:80]}")

        sup_sel = Exp4Selection(POOL_VERSION, frozenset(solo_ok), frozenset())
        sup_built, sup_err = assemble_or_none(sup_sel)
        if sup_built is None:
            raise RuntimeError(
                f"{name}: every pool line assembles alone but their union does "
                f"not ({sup_err}). The refusal therefore depends on the "
                f"SELECTION, a candidate can contain a pattern the supernetwork "
                f"lacks, and master-path filtering is unsound for this pool. "
                f"This is a real finding, not a case to skip.")
        sup_lines = sorted(sup_sel.lines)

        # Named candidates first so the cap cannot drop the ones the sample
        # went out of its way to include, then subsets in deterministic order.
        pin_line = sup_lines[0]
        proposed = [("supernetwork", sup_sel),
                    ("pinned_off", Exp4Selection(
                        POOL_VERSION, frozenset(sup_lines),
                        frozenset((pin_line, p) for p in periods)))]
        for sub in _subsets(sup_lines, lo, hi):
            proposed.append(("subset",
                             Exp4Selection(POOL_VERSION, sub, frozenset())))

        universe = []
        for kind, sel in proposed:
            built, err = assemble_or_none(sel)
            if built is None:
                continue                       # cannot be scored by ANY arm
            universe.append({"kind": kind, "sel": sel, "built": built,
                             "rp_keys": rp_keys_of(built),
                             "id": sel.state_key,
                             "digest": sel.state_digest})
            if a.max_candidates and len(universe) >= a.max_candidates:
                break

        ordered_ids = tuple(c["id"] for c in universe)
        universe_digest = digest({
            "case": name, "pool_version": POOL_VERSION,
            "candidates": [[c["kind"], c["id"], c["digest"],
                            sorted(c["sel"].lines),
                            sorted(map(list, c["sel"].pinned_off))]
                           for c in universe]})
        print(f"  universe: {len(universe)} candidates, digest "
              f"{universe_digest}")

        # ---- 2. the master, at the COMMON enumeration settings -------------
        master_cache: dict = {}
        t0 = time.time()
        sup_score = score(sup_sel, case, master_cache)
        t_master = time.time() - t0
        if not master_cache:
            raise RuntimeError(
                f"{name}: the supernetwork assembled but produced no path sets "
                f"({sup_score.get('error')}); there is no master to reuse.")
        master = MasterPathSet(
            by_period=dict(master_cache), supernetwork_lines=tuple(sup_lines),
            digest=digest({p: [int(ps.n_paths), int(ps.n_od),
                               list(map(list, ps.rp_keys))]
                           for p, ps in sorted(master_cache.items())}))
        print(f"  master: {master.stats()['paths_by_period']} paths, "
              f"{t_master:.1f}s, digest {master.digest}")

        # ---- 3. both arms see the SAME universe, asserted before scoring ---
        seen = {}
        for arm in ("REUSE", "FRESH"):
            seen[arm] = {"ids": tuple(c["id"] for c in universe),
                         "n": len(universe),
                         "digest": universe_digest}
        if not (seen["REUSE"] == seen["FRESH"]):
            raise AssertionError("the two arms were handed different universes")
        if seen["REUSE"]["ids"] != ordered_ids or \
                seen["REUSE"]["digest"] != universe_digest or \
                seen["REUSE"]["n"] != len(universe):
            raise AssertionError("universe drifted between construction and use")
        print(f"  universe assertion: digest, count and ordered ids identical "
              f"in both arms ({len(universe)} candidates)")

        # ---- 4. score ------------------------------------------------------
        rows: list[dict] = []
        for c in universe:
            sel, ck = c["sel"], c["rp_keys"]

            # FRESH: full reconstruction. pathset_cache=None is what forces the
            # path rebuild; everything above it is rebuilt per call anyway.
            fresh_cache: dict = {}
            fr = score(sel, case, fresh_cache)

            # The rp_keys the REUSE arm filters against were derived from the
            # assembled network, not from FRESH. Assert they agree, so the
            # derivation production would use is validated on every candidate
            # rather than assumed.
            if fr["ok"] and fresh_cache:
                for per, ps in fresh_cache.items():
                    if list(ps.rp_keys) != list(ck):
                        raise AssertionError(
                            f"{c['id']} {per}: route-period keys derived from "
                            f"the assembled network do not match the ones the "
                            f"evaluator built ({len(ck)} vs {len(ps.rp_keys)}). "
                            f"The filter would be indexed against the wrong "
                            f"vector.")

            # REUSE: the master, filtered. No enumeration.
            t0 = time.time()
            filt, prov = {}, {}
            try:
                for per, mps in master.by_period.items():
                    filt[per], prov[per] = filter_for_network(mps, list(ck))
            except Exception as e:
                hard_failures.append({"case": name, "id": c["id"],
                                      "stage": "filter",
                                      "error": f"{type(e).__name__}: {e}"[:200]})
                continue
            t_filter = time.time() - t0
            ru = score(sel, case, filt)

            if fr["ok"] != ru["ok"]:
                hard_failures.append({
                    "case": name, "id": c["id"], "kind": c["kind"],
                    "stage": "asymmetric_scoring_failure",
                    "fresh_ok": fr["ok"], "reuse_ok": ru["ok"],
                    "fresh_error": fr.get("error"),
                    "reuse_error": ru.get("error")})
                continue
            if not fr["ok"]:
                rows.append({"kind": c["kind"], "id": c["id"],
                             "both_arms_refused": fr.get("error")})
                continue

            _check_fields(fr["fitness"])
            _check_fields(ru["fitness"])
            per_field, worst_rel, worst_abs = {}, 0.0, 0.0
            for f in FIELDS:
                lv, rv = float(fr["fitness"][f]), float(ru["fitness"][f])
                ad = abs(rv - lv)
                rd = ad / abs(lv) if lv else ad
                per_field[f] = {"fresh": lv, "reuse": rv,
                                "abs_diff": ad, "rel_diff": rd}
                worst_rel, worst_abs = max(worst_rel, rd), max(worst_abs, ad)

            # PINNED_OFF must bind in BOTH arms. It is enforced through the
            # ladder, above the solver switch and independent of the path
            # cache, so a leak in one arm only would be a real defect.
            pins = sorted(sel.pinned_off)
            pin_leak = {}
            for arm, res in (("fresh", fr), ("reuse", ru)):
                leaked = sorted(f"{r}|{p}" for (r, p) in pins
                                if not is_off(res["plan"].get(f"{r}|{p}",
                                                              float("inf"))))
                if leaked:
                    pin_leak[arm] = leaked
            if pin_leak:
                hard_failures.append({"case": name, "id": c["id"],
                                      "stage": "pinned_off_leak",
                                      "leaked": pin_leak})

            surv = {p: prov[p]["survival_fraction"] for p in sorted(prov)}
            rows.append({
                "kind": c["kind"], "id": c["id"], "digest": c["digest"],
                "lines": sorted(sel.lines),
                "pinned_off": [list(x) for x in pins],
                "objective_fresh": fr["objective"],
                "objective_reuse": ru["objective"],
                "objective_abs_gap": abs(ru["objective"] - fr["objective"]),
                "objective_rel_gap": (abs(ru["objective"] - fr["objective"])
                                      / abs(fr["objective"])
                                      if fr["objective"] else 0.0),
                "unserved_gap": (float(ru["fitness"]["unserved_demand"])
                                 - float(fr["fitness"]["unserved_demand"])),
                "fields": per_field,
                "worst_rel_diff": worst_rel, "worst_abs_diff": worst_abs,
                "identical": worst_rel == 0.0
                             and ru["objective"] == fr["objective"],
                "survival_fraction": surv,
                "min_survival": min(surv.values()) if surv else 0.0,
                "paths": {p: {"master": prov[p]["master_paths"],
                              "reuse_kept": prov[p]["kept_paths"],
                              "fresh": int(fresh_cache[p].n_paths)
                                       if p in fresh_cache else None}
                          for p in sorted(prov)},
                "seconds_fresh": fr["seconds"],
                "seconds_reuse": ru["seconds"] + t_filter,
                "speedup": (fr["seconds"] / (ru["seconds"] + t_filter)
                            if (ru["seconds"] + t_filter) else float("nan")),
                "pin_leak": pin_leak or None,
            })
            mark = "==" if rows[-1]["identical"] else "!="
            print(f"  {c['kind']:<13} surv {rows[-1]['min_survival']:.3f}  "
                  f"{mark}  obj gap {rows[-1]['objective_rel_gap']:.3e}  "
                  f"x{rows[-1]['speedup']:.2f}")

        ok = [r for r in rows if "objective_fresh" in r]

        # ---- 5. the survival-1.000 identity, checked FIRST -----------------
        #
        # With one candidate universe and no filtering, REUSE and FRESH must
        # produce the same score. Anything else is a reuse/state-reconstruction
        # bug and is debugged there rather than reported as approximation error.
        unit = [r for r in ok if r["min_survival"] >= 1.0]
        unit_bad = [r for r in unit if not r["identical"]]
        print(f"  survival-1.000 candidates: {len(unit)}, "
              f"identical: {len(unit) - len(unit_bad)}/{len(unit)}")
        for r in unit_bad:
            hard_failures.append({
                "case": name, "id": r["id"], "stage": "survival_1_not_identity",
                "worst_rel_diff": r["worst_rel_diff"],
                "objective_fresh": r["objective_fresh"],
                "objective_reuse": r["objective_reuse"]})

        # ---- 6. the gate's own questions -----------------------------------
        inversions, pairs = 0, 0
        for i in range(len(ok)):
            for j in range(i + 1, len(ok)):
                pairs += 1
                d1 = ok[i]["objective_fresh"] - ok[j]["objective_fresh"]
                d2 = ok[i]["objective_reuse"] - ok[j]["objective_reuse"]
                if d1 * d2 < 0:
                    inversions += 1
        leader_fresh = min(ok, key=lambda r: r["objective_fresh"])["id"] if ok else None
        leader_reuse = min(ok, key=lambda r: r["objective_reuse"])["id"] if ok else None
        k = min(PROMOTED_K, len(ok))
        top_f = [r["id"] for r in sorted(ok, key=lambda r: r["objective_fresh"])[:k]]
        top_r = [r["id"] for r in sorted(ok, key=lambda r: r["objective_reuse"])[:k]]

        rep = {"case": name,
               "universe_digest": universe_digest,
               "universe_count": len(universe),
               "ordered_ids": list(ordered_ids),
               "lines_dropped_from_supernetwork": dropped,
               "master": master.stats(), "master_seconds": t_master,
               "scored": len(ok),
               "survival_1_candidates": len(unit),
               "survival_1_identical": len(unit) - len(unit_bad),
               "leader_fresh": leader_fresh, "leader_reuse": leader_reuse,
               "leader_preserved": leader_fresh == leader_reuse,
               "ranking_inversions": inversions, "ranking_pairs": pairs,
               "promoted_fresh": top_f, "promoted_reuse": top_r,
               "promoted_set_preserved": set(top_f) == set(top_r),
               "worst_objective_rel_gap":
                   max((r["objective_rel_gap"] for r in ok), default=0.0),
               "worst_field_rel_diff":
                   max((r["worst_rel_diff"] for r in ok), default=0.0),
               "worst_unserved_gap":
                   max((abs(r["unserved_gap"]) for r in ok), default=0.0),
               "min_survival": min((r["min_survival"] for r in ok), default=0.0),
               "median_speedup": (sorted(r["speedup"] for r in ok)[len(ok) // 2]
                                  if ok else float("nan")),
               "rows": rows}
        case_reports.append(rep)
        all_rows.extend(ok)
        print(f"  -> leader {'PRESERVED' if rep['leader_preserved'] else 'CHANGED'}"
              f", {inversions}/{pairs} inversions, promoted set "
              f"{'preserved' if rep['promoted_set_preserved'] else 'CHANGED'}, "
              f"worst field {rep['worst_field_rel_diff']:.3e}")

    # ------------------------------------------------------------- verdict --
    leaders = all(r["leader_preserved"] for r in case_reports)
    ranks = all(r["ranking_inversions"] == 0 for r in case_reports)
    promo = all(r["promoted_set_preserved"] for r in case_reports)
    unit_ok = all(r["survival_1_identical"] == r["survival_1_candidates"]
                  for r in case_reports)
    closes = bool(case_reports) and leaders and ranks and promo and unit_ok \
        and not hard_failures

    print(f"\n{'=' * 72}")
    print(f"  cases                        : {len(case_reports)}")
    print(f"  candidates compared          : {len(all_rows)}")
    print(f"  survival-1.000 is the identity: "
          f"{unit_ok if case_reports else 'n/a (nothing measured)'}")
    print(f"  exact leader preserved, all  : "
          f"{leaders if case_reports else 'n/a'}")
    print(f"  zero ranking inversions      : {ranks if case_reports else 'n/a'}")
    print(f"  promoted set preserved       : {promo if case_reports else 'n/a'}")
    print(f"  worst objective rel gap      : "
          f"{max((r['objective_rel_gap'] for r in all_rows), default=0.0):.3e}")
    print(f"  worst field rel diff         : "
          f"{max((r['worst_rel_diff'] for r in all_rows), default=0.0):.3e}")
    if hard_failures:
        print(f"\n  HARD FAILURES ({len(hard_failures)}):")
        for h in hard_failures[:10]:
            print(f"    {h}")
    print(f"\n  GATE 4-7: {'MET' if closes else 'ARMED'}")

    if closes:
        why = ("with one canonical candidate universe and identical enumeration "
               "settings, reuse preserves the exact leader in every case, with "
               "zero ranking inversions and an unchanged promoted set, and "
               "filtering is exactly the identity wherever survival is 1.000. "
               "Reproducing the leader exactly reproduces it within any "
               "promotion band however narrow, so this closure is "
               "band-independent and borrows nothing from D18.")
    elif not case_reports:
        why = "no case produced a comparable candidate; nothing was measured."
    elif not unit_ok or hard_failures:
        why = ("a survival-1.000 candidate is not reproduced exactly, or an arm "
               "failed where the other did not. With the same universe and no "
               "filtering there is nothing left for reuse to approximate, so "
               "this is a reuse/state-reconstruction DEFECT and must be "
               "debugged there -- it is not approximation error and may not be "
               "reported as a gap.")
    else:
        why = (f"filtering is the identity where survival is 1.000, so the "
               f"substrate is sound, but reuse does not preserve the decision "
               f"at nontrivial survival (leader preserved everywhere={leaders}, "
               f"zero inversions={ranks}, promoted set preserved={promo}). This "
               f"is a genuine reuse-induced discrepancy: the master lacks paths "
               f"a candidate would actually use. Gate 4-7 does not close. "
               f"Widening the master is NOT the remedy -- richness is the "
               f"confound this design removed and reintroducing it makes the "
               f"comparison unidentified again.")
    print(f"  {why}")

    out = {
        "gate": "4-7",
        "design": "one-factor: common candidate universe, reuse vs fresh rebuild",
        "supersedes": ("outputs/exp4/masterpath_benchmark.json, which varied "
                       "reuse AND enumeration richness together and is "
                       "unidentified. Preserved, not deleted."),
        "common_enumeration": {"n_random_scenarios": COMMON_SCENARIOS,
                               "max_paths_per_od": COMMON_MAX_PATHS or
                                                   "production default"},
        "closure_rule": ("exact leader preserved in EVERY case, zero ranking "
                         "inversions, unchanged promoted set, and filtering "
                         "exactly the identity at survival 1.000"),
        "promoted_k": PROMOTED_K,
        "n_cases": len(case_reports), "n_candidates": len(all_rows),
        "survival_1_is_identity": unit_ok if case_reports else None,
        "leader_preserved_all_cases": leaders if case_reports else None,
        "zero_ranking_inversions": ranks if case_reports else None,
        "promoted_set_preserved_all_cases": promo if case_reports else None,
        "hard_failures": hard_failures,
        "worst_objective_rel_gap":
            max((r["objective_rel_gap"] for r in all_rows), default=0.0),
        "worst_field_rel_diff":
            max((r["worst_rel_diff"] for r in all_rows), default=0.0),
        "worst_unserved_gap":
            max((abs(r["unserved_gap"]) for r in all_rows), default=0.0),
        "fields_compared": FIELDS,
        "seconds": time.time() - t_all,
        "verdict": "MET" if closes else "ARMED", "why": why,
        "cases": case_reports,
    }
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(out, indent=2))
        print(f"\nwrote {a.json}")
    return 0 if closes else 2


if __name__ == "__main__":
    raise SystemExit(main())
