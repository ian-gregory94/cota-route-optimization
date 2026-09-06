#!/usr/bin/env python3
"""Validate the two blocking instruments against the real feed.

Test A  `blocks.reconstruct` on the PUBLISHED blocks must still reproduce the
        canonical envelope exactly -- [135, 187, 173, 197, 178, 149] and
        197 @ 17:13. This is the provenance test, and it also guards the
        refactor that made both instruments share one concurrency counter.

Test B  the SAME baseline trips with their block_ids stripped, fed through the
        candidate solver. Equality to 197 is NOT required and is not sought:
        this is an independently derived feasible reblocking requirement, not a
        recreation of COTA's historical assignment. Reported, never calibrated.

Audit   every consecutive transition inside a published block, checked against
        the connection oracle. A same-terminal transition the oracle refuses is
        a real contradiction. A cross-terminal one is not -- it measures how
        much of COTA's blocking depends on deadhead data this project does not
        have.

Bracket the deadhead nobody has is bounded rather than guessed. The strict
        oracle forbids every cross-terminal connection and gives an UPPER
        bound; the zero-deadhead relaxation permits all of them for free and
        gives a LOWER bound. Any real deadhead model lands between them, and
        the width of the bracket is the price of the missing input.

Stability
        a maximum matching is not unique. `minimum_blocks` is the matching
        number and is invariant; the per-period concurrency of the chains is
        not. This run measures that instability instead of reporting one draw
        from it as the answer.

    python scripts/exp4_blocking_validate.py --json outputs/exp4/blocking_validation.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

CANONICAL = {"early": 135, "am_peak": 187, "midday": 173,
             "pm_peak": 197, "evening": 178, "owl": 149}
CANONICAL_PEAK = 197
CANONICAL_PEAK_TIME = "17:13"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--skip-candidate", action="store_true")
    ap.add_argument("--skip-relaxation", action="store_true",
                    help="skip the zero-deadhead LOWER bound solve (slow: the "
                         "relaxation makes nearly every pair an edge)")
    a = ap.parse_args()

    from cota_opt.blocks import reconstruct
    from cota_opt.configs import service_periods
    from cota_opt.exp4_blocking import (ConnectionRule, MaterializedTrip,
                                        SameTerminalOracle, TripTable,
                                        ZeroDeadheadRelaxation,
                                        audit_published_transitions,
                                        block_candidate_schedule,
                                        period_lower_bounds,
                                        production_feasible)
    from cota_opt.firewall.core import digest
    from exp4_c10_fixtures import _boot

    st = _boot()
    H = st["H"]
    periods = service_periods(H.assumptions)
    trips = H.baseline.feed.trips
    tstats = H.baseline.tstats
    out: dict = {"periods": {k: list(v) for k, v in sorted(periods.items())}}

    # ---------------------------------------------------------------- A ----
    print("TEST A — published-block reconstruction (provenance)\n")
    prof = reconstruct(trips, tstats, periods)
    got = {k: int(v) for k, v in prof.peak_by_period.items()}
    peak_time = f"{prof.peak_minute // 60:02d}:{prof.peak_minute % 60:02d}"
    a_ok = (got == CANONICAL and int(prof.peak_vehicles) == CANONICAL_PEAK
            and peak_time == CANONICAL_PEAK_TIME)
    for k in sorted(CANONICAL):
        flag = "ok" if got.get(k) == CANONICAL[k] else "MISMATCH"
        print(f"    {k:<9} {got.get(k)}  (canonical {CANONICAL[k]})  {flag}")
    print(f"    system peak {prof.peak_vehicles} @ {peak_time} "
          f"(canonical {CANONICAL_PEAK} @ {CANONICAL_PEAK_TIME})")
    print(f"  TEST A: {'PASS' if a_ok else 'FAIL'}")
    out["test_a"] = {"fleet_by_period": got, "system_peak": int(prof.peak_vehicles),
                     "peak_time": peak_time, "n_blocks": int(len(prof.blocks)),
                     "canonical": CANONICAL, "pass": a_ok,
                     "instrument": "blocks.reconstruct (published block_id)"}

    # ---- terminals, for the audit and the candidate solve -----------------
    cols = list(tstats.columns)
    out["tstats_columns"] = cols
    term_cols = [c for c in cols if "stop" in c.lower() or "term" in c.lower()]
    print(f"\n  tstats terminal-bearing columns: {term_cols or 'NONE'}")

    # Terminals are not in tstats, but they are IN THE FEED: the first and last
    # stop of each trip's stop_times. That is measured data, not an assumption,
    # so deriving it is legitimate where inventing a deadhead time would not be.
    term_by_trip: dict[str, tuple[str, str]] = {}
    stimes = getattr(H.baseline.feed, "stop_times", None)
    if stimes is not None and len(stimes):
        stx = stimes.sort_values(["trip_id", "stop_sequence"])
        first = stx.groupby("trip_id")["stop_id"].first()
        last = stx.groupby("trip_id")["stop_id"].last()
        term_by_trip = {str(k): (str(first[k]), str(last[k])) for k in
                        first.index}
        print(f"  terminals derived from stop_times for "
              f"{len(term_by_trip)} trips")

    def terminal_of(row):
        return term_by_trip.get(str(row.get("trip_id")), (None, None))

    have_terminals = bool(term_by_trip)

    # ------------------------------------------------------------ audit ----
    print("\nAUDIT — published transitions against the connection oracle\n")
    oracle = SameTerminalOracle(min_layover_sec=300.0)
    rule = ConnectionRule(min_layover_sec=300.0)
    t = tstats.copy()
    if "block_id" not in t.columns:
        t = t.merge(trips[["trip_id", "block_id"]], on="trip_id", how="left")
    aud = audit_published_transitions(t, oracle, rule,
                                      terminal_of=terminal_of)
    print(f"    transitions examined            : {aud['transitions_examined']}")
    print(f"    same terminal, feasible         : {aud['same_terminal_feasible']}")
    print(f"    same terminal, under min layover: "
          f"{aud['same_terminal_under_min_layover']}  <-- real contradictions")
    print(f"    cross-terminal / unknown        : "
          f"{aud['cross_terminal_or_unknown']}")
    if aud["share_needing_deadhead_data"] is not None:
        print(f"    share needing deadhead data     : "
              f"{aud['share_needing_deadhead_data']:.1%}")
    if not have_terminals:
        print("    NOTE: tstats carries no terminal columns, so every "
              "transition\n          counts as unknown. The audit cannot "
              "distinguish a real\n          contradiction from missing "
              "terminal data here.")
    out["audit"] = {**aud, "terminals_available": have_terminals}

    # ---------------------------------------------------------------- B ----
    print("\nTEST B — stripped-block candidate solve")
    if a.skip_candidate or not have_terminals:
        why = ("terminals are not available in tstats, so the candidate solver "
               "cannot decide any connection and every trip would become its "
               "own block -- a vacuous answer, not a measurement")
        print(f"    NOT RUN: {why}")
        out["test_b"] = {"run": False, "why": why}
    else:
        t0 = time.time()
        mt = []
        for r in t.dropna(subset=["block_id"]).to_dict("records"):
            o, d = terminal_of(r)
            mt.append(MaterializedTrip(
                trip_id=str(r["trip_id"]), route_id=str(r.get("route_id", "")),
                pattern_id=str(r.get("pattern_id", "")),
                direction_id=int(r.get("direction_id", 0) or 0),
                origin_terminal=o, destination_terminal=d,
                departure_sec=float(r["first_dep_sec"]),
                arrival_sec=float(r["last_arr_sec"]),
                runtime_min=float(r.get("runtime_min", 0.0)),
                period=str(r.get("period", ""))))
        tbl = TripTable(tuple(sorted(mt, key=lambda x: (x.departure_sec,
                                                        x.trip_id))),
                        "baseline_stripped",
                        digest([x.payload() for x in mt]))
        print(f"    {len(tbl)} trips, block_ids discarded; solving ...")
        res = block_candidate_schedule(tbl, oracle, periods, rule)
        print(f"    solved in {time.time() - t0:.0f}s")
        for k in sorted(CANONICAL):
            c = res.fleet_by_period.get(k, 0)
            print(f"    {k:<9} candidate {c:>4}   published {CANONICAL[k]:>4}   "
                  f"diff {c - CANONICAL[k]:+5d}  "
                  f"({(c - CANONICAL[k]) / CANONICAL[k]:+.1%})")
        print(f"    system minimum fleet: {res.minimum_blocks} "
              f"(published blocking uses {CANONICAL_PEAK})")
        print(f"    UPPER BOUND: {res.is_upper_bound} — no cross-terminal "
              f"connection was permitted")
        stab = res.fleet_by_period_stable
        print(f"    per-period figure matching-stable: {stab}")
        if stab is False:
            print(f"      an equally maximum matching gives "
                  f"{dict(sorted((res.fleet_by_period_alternate or {}).items()))}")
            print("      -> the per-period arm of the feasibility test is not "
                  "well posed; minimum_blocks is the invariant answer")

        out["test_b"] = {"run": True, **res.payload(),
                         "published_for_reference": CANONICAL,
                         "difference_by_period": {
                             k: res.fleet_by_period.get(k, 0) - CANONICAL[k]
                             for k in sorted(CANONICAL)},
                         "invariant": (
                             "an independently derived feasible reblocking "
                             "requirement, NOT a recreation of COTA's "
                             "historical block assignment. Not calibrated "
                             "toward the published figure in either direction.")}

        # ------------------------------------------------------ bracket ----
        print("\nBRACKET — the deadhead nobody has, bounded from both sides\n")
        lb, lb_peak, lb_min = period_lower_bounds(tbl, periods, 300.0)
        print(f"    analytic LOWER bound (zero deadhead, 300s layover): "
              f"{lb_peak} @ {lb_min // 60:02d}:{lb_min % 60:02d}")
        out["bracket"] = {
            "lower_analytic": {"by_period": lb, "system_peak": lb_peak,
                               "peak_minute": lb_min},
            "upper_solved": res.minimum_blocks,
            "published_peak_for_reference": CANONICAL_PEAK,
            "meaning": (
                "any real deadhead model lies between the bound that forbids "
                "every cross-terminal connection and the relaxation that "
                "grants them all for free. The published figure is a peak "
                "concurrency of published blocks and is shown for reference "
                "only -- it is not the same quantity as a path-cover count.")}

        if not a.skip_relaxation:
            t1 = time.time()
            rlx = block_candidate_schedule(tbl, ZeroDeadheadRelaxation(300.0),
                                           periods, rule)
            print(f"    solved LOWER bound  : {rlx.minimum_blocks} "
                  f"({time.time() - t1:.0f}s)")
            agree = rlx.minimum_blocks == lb_peak
            print(f"    Dilworth cross-check: solver {rlx.minimum_blocks} vs "
                  f"analytic {lb_peak} -- {'AGREE' if agree else 'DISAGREE'}")
            if not agree:
                print("      the relaxation's reachability is transitively "
                      "closed, so its minimum path cover MUST equal the peak "
                      "interval concurrency. A disagreement is a solver bug, "
                      "not a modelling choice.")
            out["bracket"]["lower_solved"] = rlx.minimum_blocks
            out["bracket"]["dilworth_cross_check"] = {
                "solver": rlx.minimum_blocks, "analytic": lb_peak,
                "agree": agree,
                "why_it_must_hold": (
                    "under zero deadhead the reachability relation is "
                    "transitively closed, so minimum chain cover = maximum "
                    "antichain (Dilworth) = peak interval concurrency. This "
                    "checks the Hopcroft-Karp implementation on real data at "
                    "scale, independently of any transit assumption.")}
        print(f"\n    {out['bracket'].get('lower_solved', lb_peak)} "
              f"<= true minimum fleet <= {res.minimum_blocks}")

        # ------------------------------------------- production feasibility --
        print("\n§9 — production feasibility of the BASELINE against the "
              "frozen envelope\n")
        vh = float(sum(x.runtime_min for x in tbl.trips)) / 60.0
        can = json.loads((ROOT / "outputs" / "CANONICAL_ENVELOPE.json")
                         .read_text()) if (
            ROOT / "outputs" / "CANONICAL_ENVELOPE.json").exists() else None
        if can:
            fb = production_feasible(
                res, {k: int(v) for k, v in
                      can["peak_vehicles_by_period"].items()},
                tbl, periods,
                envelope_vehicle_hours=float(
                    can["weekday_revenue_vehicle_hours"]),
                candidate_vehicle_hours=vh,
                envelope_digest=can["envelope_digest"])
            print(f"    revenue vehicle-hours: {vh:.6f} against "
                  f"{can['weekday_revenue_vehicle_hours']:.6f}")
            print(f"    STATUS: {fb.status}")
            for r in fb.reasons:
                print(f"      - {r}")
            out["production_feasibility"] = fb.payload()

    out["verdict"] = {
        "test_a_pass": a_ok,
        "candidate_blocker_implemented": True,
        "deadhead_provenance": "OPEN — no defensible cross-terminal source",
        "bracket": out.get("bracket"),
        "per_period_candidate_figure_is_decision_grade": (
            out.get("test_b", {}).get("fleet_by_period_stable")),
        "status": ("EXP 4 BLOCKED — CANDIDATE BLOCKER IMPLEMENTED, "
                   "DEADHEAD PROVENANCE OPEN")}
    print(f"\n{'=' * 70}\n  {out['verdict']['status']}")

    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(out, indent=1, default=str))
        print(f"  wrote {a.json}")
    return 0 if a_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
