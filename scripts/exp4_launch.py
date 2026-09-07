#!/usr/bin/env python3
"""EXPERIMENT 4 — the production run.

    Gen2 multi-start discovery -> permissive deterministic promotion
    -> solve_exact certification -> exact-only conclusions

Every component here is the one C9 validated, unchanged. In particular the
proposal generator is the full preregistered multi-start family, not a cheaper
single-start configuration substituted after validation.

WHY DISCOVERY USES MASTER-PATH REUSE
------------------------------------
Because Experiment 4 is otherwise not runnable, and because gate 4-7 was
disposed of precisely to permit this. Measured on the real pool:

    active lines   patterns   ONE full-rebuild discovery evaluation
        10             20                  77.9 s
        25             50                 176.9 s
        41             82                 329.1 s

A 2000-evaluation proposal budget at 329 s is 7.6 days of discovery alone.
Reuse is ~6x faster, which is what makes the run possible.

Reuse is the BIASED path and that is not hidden: gate 4-7 measured the bias,
D18 measured the same shape in the frequency solver, and neither is claimed to
be absent. It is CONTAINED -- reuse output is a `ProposalScore` that cannot be
ordered, compared or converted to a float, and every promoted candidate is
re-certified by `solve_exact` with no path cache at all. C9 was re-run under
this exact configuration and still passes 6/6 with 100% frontier recall, so the
bias is established not to cost recall either.

CHECKPOINTING
-------------
Per the compute policy: a work unit is a candidate, its result is written the
instant it exists, and re-running is a no-op that reads the artifact. The
container is reclaimed on session idleness and this run is measured in days, so
resumability is not a nicety. `--max-hours` bounds one invocation.

    python scripts/exp4_launch.py --max-hours 6
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

OUT = ROOT / "outputs" / "exp4" / "run"

#: Cardinality bounds. Generous on both sides of the 41-line legacy network,
#: because gate 4-6 requires the bounds to be proved INACTIVE on the winner: a
#: result that sits on its own bound is censored, so the bound is set wide and
#: tested afterwards rather than tuned to taste.
MIN_LINES = 15
MAX_LINES = 65

#: The envelope is READ, never retyped. `2507.0` and a uniform `200.0` peak
#: stood here until 2026-09-07 and both were wrong: the first by ten hours
#: against the canonical 2517.183333, the second a scalar standing in for a
#: six-period vector. The rule from EXPERIMENT4_ENVELOPE_PROVENANCE.md is that
#: a resource cap is read from `outputs/CANONICAL_ENVELOPE.json` or from the
#: production `baseline` sentinel, and never from a constant in a script.
CANONICAL_ENVELOPE = ROOT / "outputs" / "CANONICAL_ENVELOPE.json"
BLOCKING_VALIDATION = ROOT / "outputs" / "exp4" / "blocking_validation.json"
READINESS_FROZEN = ROOT / "outputs" / "exp4" / "READINESS_FROZEN.json"


def _json_or_none(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None

#: The candidate blocking instrument's assumptions, frozen for the whole run.
MIN_LAYOVER_SEC = 300.0

#: The same-terminal connection graph is built pair-by-pair, so a large
#: timetable is quadratic. Refuse rather than truncate (the solver raises), and
#: record the refusal as an unavailable bound. Fleet is reported, not gated, so
#: an unavailable bound costs a diagnostic and never a candidate.
FLEET_MAX_EDGES = 4_000_000

LAM = 2.0
SEED = 20260825


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-hours", type=float, default=6.0)
    ap.add_argument("--stage", default="all",
                    choices=("all", "preflight", "master", "discover",
                             "certify", "fleet", "report"))
    ap.add_argument("--preflight-lines", type=int, default=6,
                    help="how many pool lines the preflight candidate uses")
    a = ap.parse_args()

    from cota_opt.configs import (load_constraints, period_of_seconds,
                                  service_periods)
    from cota_opt.contract import ContractLimits
    from cota_opt.exp4_assemble import assemble
    from cota_opt.exp4_blocking import (BLOCKING_CONTRACT,
                                        BLOCKING_CONTRACT_DIGEST,
                                        CandidateFleetBound, ConnectionRule,
                                        MaterializedTrip,
                                        OPERATIONAL_RECOURSE,
                                        OPERATIONAL_RECOURSE_DIGEST,
                                        SameTerminalOracle, TripTable,
                                        ZeroDeadheadRelaxation,
                                        block_candidate_schedule,
                                        materialize_timetable,
                                        period_lower_bounds,
                                        production_feasible,
                                        provenance_is_certification_grade,
                                        terminal_identity,
                                        TERMINAL_IDENTITY_DIGEST,
                                        TERMINAL_IDENTITY_PROVENANCE)
    from cota_opt.exp4_certify import (CERTIFICATION_CONTRACT,
                                       CERTIFICATION_DIGEST, certify)
    from cota_opt.exp4_inference import (Exp4Candidate, ProposalRecord,
                                         ProposalScore, TIE_BREAK_DIGEST,
                                         rank_certified)
    from cota_opt.exp4_masterpath import filter_for_network
    from cota_opt.exp4_network import Exp4Selection
    from cota_opt.exp4_promotion import (PROMOTION_DIGEST, PROMOTION_RULE,
                                         promote)
    from cota_opt.exp4_proposal import (N_DIVERSIFIED, PROPOSAL_DIGEST,
                                        PROPOSAL_RULE, TOTAL_EVAL_BUDGET,
                                        build_seed_family, diversified_starts,
                                        run_multi_start)
    from cota_opt.exp4_score import score_exp4_network
    from cota_opt.firewall.core import digest
    from exp2_treatments import pinned
    from exp4_c10_fixtures import (POOL_VERSION, _BY_RID, _boot,
                                   _first_dep_by_period)

    OUT.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    deadline = t_start + a.max_hours * 3600

    st = _boot()
    H, sg, graph = st["H"], st["sg"], st["graph"]
    periods_cfg = service_periods(H.assumptions)
    periods = sorted(periods_cfg)
    first_dep = _first_dep_by_period()

    # ------------------------------------------------------- the envelope --
    if not CANONICAL_ENVELOPE.exists():
        print("FATAL: outputs/CANONICAL_ENVELOPE.json is missing. Run "
              "scripts/exp4_freeze_envelope.py --write. This launcher does "
              "not carry a fallback cap, because every fallback cap this "
              "project has ever had was wrong.")
        return 2
    env = json.loads(CANONICAL_ENVELOPE.read_text())
    VEH_HOURS = float(env["weekday_revenue_vehicle_hours"])
    ENVELOPE_FLEET = {k: int(v) for k, v in
                      env["peak_vehicles_by_period"].items()}
    ENVELOPE_DIGEST = str(env["envelope_digest"])

    # The frequency solver's own resource constraint stays on the production
    # `baseline` sentinel for FLEET. That is deliberate and it is the point of
    # D23 check 4: the solver's peak is CONCURRENCY, a different instrument
    # from the block-derived envelope, and feeding it the block-derived vector
    # would be the right numbers on the wrong variable. Hours ARE the same
    # instrument on both sides, so hours are pinned to the canonical value.
    _c = load_constraints()
    cons = {**_c, "resource": {**_c["resource"],
                               "weekday_revenue_vehicle_hours": VEH_HOURS}}
    assert cons["resource"]["peak_fleet_by_period"] == "baseline"

    # peak_vehicle_budget is deliberately None. contract.py would otherwise
    # record `peak_fleet_check: NOT RUN` on every candidate -- a gate that
    # reports rather than gates. Fleet feasibility is decided below by the
    # blocking instrument, which can actually answer for it.
    limits = ContractLimits(veh_hour_budget=VEH_HOURS,
                            peak_vehicle_budget=None,
                            required_waiting_model="same_route")

    def assembles(sel):
        try:
            assemble(sel, _BY_RID, graph, H.baseline.network.stops,
                     pool_version=POOL_VERSION,
                     first_dep_sec_by_period=first_dep)
            return True
        except Exception:
            return False

    pool_path = OUT / "pool.json"
    if pool_path.exists():
        pool = json.loads(pool_path.read_text())["lines"]
    else:
        pool = [l for l in sorted(_BY_RID)
                if assembles(Exp4Selection(POOL_VERSION, frozenset([l]),
                                           frozenset()))]
        pool_path.write_text(json.dumps({"pool_version": POOL_VERSION,
                                         "n": len(pool), "lines": pool},
                                        indent=1))
    print(f"pool: {len(pool)} assembling lines of {len(_BY_RID)}, "
          f"cardinality {MIN_LINES}-{MAX_LINES}")
    print(f"envelope {ENVELOPE_DIGEST}: {VEH_HOURS:.6f} vh, block-derived "
          f"fleet {ENVELOPE_FLEET}")
    print(f"fleet gate: candidate blocking ({BLOCKING_CONTRACT['name']} v"
          f"{BLOCKING_CONTRACT['version']}, {BLOCKING_CONTRACT_DIGEST}); "
          f"recourse {OPERATIONAL_RECOURSE_DIGEST}")

    # The baseline measured with the SAME instrument. Read from the committed
    # validation artifact rather than recomputed here, for the same reason the
    # envelope is read rather than retyped: a number a launcher computes for
    # itself is a number nothing else can check.
    # The baseline bracket is a REPORTING input, not a launch precondition.
    # READINESS_FROZEN records the rule: only an error that makes candidate
    # construction or objective comparison invalid may stop the run, and a
    # missing fleet reference makes neither invalid. Absent it, fleet is
    # reported as unavailable and the search proceeds.
    baseline_bound = None
    if BLOCKING_VALIDATION.exists():
        try:
            _bv = json.loads(BLOCKING_VALIDATION.read_text())
            _br = _bv["bracket"]
            baseline_bound = CandidateFleetBound(
                lower=int(_br.get("lower_solved",
                                  _br["lower_analytic"]["system_peak"])),
                upper=int(_br["upper_solved"]),
                lower_oracle="zero_deadhead_relaxation",
                upper_oracle="same_terminal_only",
                deadhead_provenance="OPEN",
                n_trips=int(_bv["test_b"]["n_trips"]))
            print(f"baseline under the same instrument: "
                  f"[{baseline_bound.lower}, {baseline_bound.upper}] blocks "
                  f"over {baseline_bound.n_trips} trips; published peak "
                  f"{_bv['test_a']['system_peak']} @ "
                  f"{_bv['test_a']['peak_time']} is a DIFFERENT instrument "
                  f"and is not the comparison")
        except Exception as e:
            print(f"baseline fleet reference unreadable ({type(e).__name__}); "
                  f"fleet will be reported without it")
    else:
        print("baseline fleet reference absent; fleet will be reported "
              "without it. This does not gate the run.")
    print("FLEET IS REPORTED, NOT GATED: no fleet verdict filters, ranks or "
          "rejects a candidate. Ranking is on objective_EXACT alone.")

    def fleet_verdict(state_key, lines, plan_str):
        """Bracket + three-valued feasibility for one certified candidate."""
        sel = Exp4Selection(POOL_VERSION, frozenset(lines), frozenset())
        built = assemble(sel, _BY_RID, graph, H.baseline.network.stops,
                         pool_version=POOL_VERSION,
                         first_dep_sec_by_period=first_dep)
        plan = {}
        for key, hw in plan_str.items():
            r, _, per = str(key).partition("|")
            plan[(r, per)] = float(hw)
        tbl = materialize_timetable(built.network, plan, periods_cfg, first_dep,
                                    source=f"certified:{state_key}")
        rule = ConnectionRule(min_layover_sec=MIN_LAYOVER_SEC)
        hi = block_candidate_schedule(tbl, SameTerminalOracle(MIN_LAYOVER_SEC),
                                      periods_cfg, rule,
                                      max_edges=FLEET_MAX_EDGES)
        # The LOWER bound is taken from the analytic identity rather than a
        # second matching. Under the zero-deadhead relaxation the reachability
        # relation is transitively closed, so Dilworth forces minimum chain
        # cover = maximum antichain = peak interval concurrency; solver and
        # identity agreed at 180 on the real baseline. Using the identity is
        # therefore exact, not an approximation, and it avoids building a
        # near-complete graph on every certified candidate.
        _lb, lo_peak, _lm = period_lower_bounds(tbl, periods_cfg,
                                                MIN_LAYOVER_SEC)
        bound = CandidateFleetBound(
            lower=int(lo_peak), upper=hi.minimum_blocks,
            lower_oracle="zero_deadhead_relaxation (Dilworth identity)",
            upper_oracle=hi.deadhead_provenance["deadhead_source"],
            deadhead_provenance="OPEN", n_trips=len(tbl))
        vh = float(sum(t.runtime_min for t in tbl.trips)) / 60.0
        fb = production_feasible(
            hi, ENVELOPE_FLEET, tbl, periods_cfg,
            envelope_vehicle_hours=VEH_HOURS, candidate_vehicle_hours=vh,
            baseline_bound=baseline_bound, candidate_bound=bound,
            min_layover_sec=MIN_LAYOVER_SEC, envelope_digest=ENVELOPE_DIGEST)
        return {
            "state_key": state_key,
            "verdict": fb.status,
            "feasible": fb.feasible,
            "reasons": list(fb.reasons),
            "deadhead_oracle_upper": hi.deadhead_provenance,
            "deadhead_oracle_lower": {
                "deadhead_source": "zero_deadhead_relaxation",
                "method": "Dilworth identity, exact",
                "is_bound_only": True},
            "deadhead_provenance_status": (
                "COMPLETE" if fb.provenance_certification_grade else "OPEN"),
            "deadhead_provenance_note": fb.provenance_note,
            "fleet_bracket": bound.payload(),
            "terminal_identity": hi.terminal_identity,
            "terminal_identity_provenance": TERMINAL_IDENTITY_PROVENANCE,
            "terminal_identity_digest": TERMINAL_IDENTITY_DIGEST,
            "minimum_blocks_under_declared_oracle": (
                hi.minimum_blocks if fb.provenance_certification_grade
                else None),
            "minimum_blocks_NOT_CERTIFIED": hi.minimum_blocks,
            "revenue_vehicle_hours": vh,
            "vehicle_hours": fb.vehicle_hours,
            "envelope_digest": ENVELOPE_DIGEST,
            "operational_recourse": OPERATIONAL_RECOURSE,
            "operational_recourse_digest": OPERATIONAL_RECOURSE_DIGEST,
            "blocking_contract_digest": BLOCKING_CONTRACT_DIGEST,
            "per_period_DIAGNOSTIC_ONLY": fb.per_period,
            "undecidable_reason": (None if fb.status != "UNDECIDABLE"
                                   else fb.provenance_note),
        }

    # ----------------------------------------------------------- preflight --
    # Executes the whole fleet path -- assemble, materialise, both bracket
    # oracles, production_feasible -- on a small real candidate, without
    # starting a search. D23 checks the launcher's TEXT; this checks that the
    # text runs. OPERATIONS' recurring lesson is that a mechanism which looks
    # like it is working is not evidence that it ran.
    if a.stage == "preflight":
        lines = pool[:max(2, a.preflight_lines)]
        from cota_opt.frequency import snap_to_ladder            # noqa: F401
        sel = Exp4Selection(POOL_VERSION, frozenset(lines), frozenset())
        built = assemble(sel, _BY_RID, graph, H.baseline.network.stops,
                         pool_version=POOL_VERSION,
                         first_dep_sec_by_period=first_dep)
        routes = sorted({p.route_id for p in built.network.patterns.values()})
        plan_str = {f"{r}|{per}": 30.0 for r in routes for per in periods}
        print(f"\npreflight: {len(lines)} lines, {len(routes)} routes, "
              f"{len(plan_str)} route-periods at a flat 30 min headway")
        v = fleet_verdict("PREFLIGHT", lines, plan_str)
        print(f"  trips materialised : {v['fleet_bracket']['n_trips']}")
        _ti = v["terminal_identity"]
        print(f"  fleet bracket      : [{v['fleet_bracket']['lower']}, "
              f"{v['fleet_bracket']['upper']}] blocks")
        print(f"  terminal identity  : {_ti['n_shared_terminals']} shared "
              f"terminals; {_ti['trips_whose_destination_is_never_an_origin']}"
              f"/{_ti['n_trips']} trips stranded "
              f"({_ti['share_stranded']:.1%})"
              f"{'  <-- DEGENERATE' if _ti['degenerate'] else ''}")
        print(f"  revenue veh-hours  : {v['revenue_vehicle_hours']:.4f} "
              f"against {VEH_HOURS:.6f}")
        print(f"  deadhead provenance: {v['deadhead_provenance_status']} "
              f"-- {v['deadhead_provenance_note']}")
        print(f"  VERDICT            : {v['verdict']}")
        for r in v["reasons"]:
            print(f"    - {r}")
        (OUT / "preflight.json").write_text(json.dumps(v, indent=1,
                                                       default=str))
        print(f"\n  wrote {(OUT / 'preflight.json').relative_to(ROOT)}")
        print("  preflight only -- no search was started")
        return 0


    # ------------------------------------------------- master path set -----
    #
    # OPERATIONS 31, applied to the most expensive un-checkpointed step in the
    # run. Enumerating path sets on the 204-line supernetwork takes longer than
    # this container's idle-reclaim window, and it was being redone in memory
    # on every start -- so a recycle during the build meant the build had never
    # happened. It goes to disk the moment it exists, keyed by the pool it was
    # built from so a stale cache cannot be silently reused.
    master_pkl = OUT / "master_paths.pkl"
    master_meta = OUT / "master_paths.json"
    pool_digest = digest(sorted(pool))
    master = {}
    if master_pkl.exists() and master_meta.exists():
        try:
            _m = json.loads(master_meta.read_text())
            if _m.get("pool_digest") == pool_digest:
                import pickle
                master = pickle.loads(master_pkl.read_bytes())
                print(f"master path set: loaded from disk "
                      f"({ {k: int(v.n_paths) for k, v in sorted(master.items())} })")
            else:
                print("master path set: on-disk cache was built from a "
                      "different pool; rebuilding")
        except Exception as e:
            print(f"master path set: cache unreadable ({type(e).__name__}); "
                  f"rebuilding")

    if not master and a.stage in ("all", "master", "discover"):
        sup0 = Exp4Selection(POOL_VERSION, frozenset(pool), frozenset())
        print(f"master path set: building on {len(pool)} lines "
              f"(expensive; checkpointed on completion) ...")
        t_m = time.time()
        mc0 = {}
        if assembles(sup0):
            try:
                score_exp4_network(
                    sup0, harness=H, stops_gdf=sg, pool=_BY_RID, graph=graph,
                    pool_version=POOL_VERSION,
                    first_dep_sec_by_period=first_dep, limits=limits,
                    constraints=cons, lam=LAM, seed=SEED, iterations=1,
                    restarts=1, width=0, waiting_model="same_route",
                    starts="greedy", allow_off=True, pathset_cache=mc0)
            except Exception as e:
                print(f"  supernetwork master failed: {type(e).__name__}: {e}")
        master = dict(mc0)
        if master:
            import pickle
            master_pkl.write_bytes(pickle.dumps(master, protocol=4))
            master_meta.write_text(json.dumps({
                "pool_digest": pool_digest, "n_lines": len(pool),
                "pool_version": POOL_VERSION,
                "n_paths": {k: int(v.n_paths) for k, v in sorted(master.items())},
                "seconds": time.time() - t_m}, indent=1))
            print(f"  built and checkpointed in {time.time() - t_m:.0f}s: "
                  f"{ {k: int(v.n_paths) for k, v in sorted(master.items())} }")
    if a.stage == "master":
        print("master stage only -- no search was started")
        return 0

    # ---------------------------------------------------------- discovery --
    prop_path = OUT / "proposals.json"
    if prop_path.exists():
        rec = json.loads(prop_path.read_text())
        print(f"discovery: resumed, {len(rec['proposals'])} proposals on disk")
    elif a.stage not in ("all", "discover"):
        print(f"stage {a.stage!r} needs proposals, and "
              f"{prop_path.relative_to(ROOT)} does not exist. Run --stage "
              f"discover first.")
        return 2
    else:
        print(f"  master path set: "
              f"{ {k: int(v.n_paths) for k, v in sorted(master.items())} }")

        def rp_keys(built):
            ts = built.tstats.copy()
            ts["period"] = ts["first_dep_sec"].map(
                lambda x: period_of_seconds(x, periods_cfg))
            return sorted({(str(r), str(p))
                           for r, p in zip(ts["route_id"], ts["period"]) if p})

        n_scored = {"n": 0}

        def scorer(s):
            try:
                cache = None
                if master:
                    b = assemble(s, _BY_RID, graph, H.baseline.network.stops,
                                 pool_version=POOL_VERSION,
                                 first_dep_sec_by_period=first_dep)
                    cache = {}
                    ck = rp_keys(b)
                    for per, mps in master.items():
                        cache[per], _ = filter_for_network(mps, list(ck))
                sc, _ = score_exp4_network(
                    s, harness=H, stops_gdf=sg, pool=_BY_RID, graph=graph,
                    pool_version=POOL_VERSION,
                    first_dep_sec_by_period=first_dep, limits=limits,
                    constraints=cons, lam=LAM, seed=SEED,
                    iterations=20_000, restarts=1, width=0,
                    waiting_model="same_route", starts="greedy",
                    allow_off=True, pathset_cache=cache)
            except Exception as e:
                return float("inf"), {"error": str(e)[:120]}, False, {}
            n_scored["n"] += 1
            if n_scored["n"] % 20 == 0:
                print(f"    scored {n_scored['n']} "
                      f"({time.time() - t_start:.0f}s)")
            m = sc.metrics
            return (float(m.get("objective", float("inf"))),
                    {k: v for k, v in m.items()
                     if isinstance(v, (int, float))}, True, sc.plan)

        family = build_seed_family(pool, MIN_LINES, MAX_LINES)
        family += diversified_starts(pool, MIN_LINES, MAX_LINES, N_DIVERSIFIED)
        print(f"  {len(family)} preregistered starts, budget "
              f"{TOTAL_EVAL_BUDGET} unique evaluations")

        ms = run_multi_start(pool, scorer, periods, lo=MIN_LINES,
                             hi=MAX_LINES, pins=(),
                             pool_version=POOL_VERSION, seed_family=family,
                             budget=TOTAL_EVAL_BUDGET)
        rec = {"proposals": [{"state_key": k,
                              "state_digest": c.selection.state_digest,
                              "lines": sorted(c.selection.lines),
                              "objective_APPROXIMATE": float(c.objective),
                              "feasible": bool(c.feasible)}
                             for k, c in ms.candidates.items()],
               "proposal_meta": ms.payload()}
        prop_path.write_text(json.dumps(rec, indent=1))
        print(f"  discovery complete: {len(rec['proposals'])} proposals, "
              f"{ms.unique_evaluations} unique evals, "
              f"{ms.duplicate_visits} duplicates, {ms.seconds:.0f}s")

    # ---------------------------------------------------------- promotion --
    proposals = [ProposalRecord(state_key=p["state_key"],
                                state_digest=p["state_digest"],
                                score=ProposalScore(p["objective_APPROXIMATE"]))
                 for p in rec["proposals"]]
    feas = {p["state_key"]: p["feasible"] for p in rec["proposals"]}
    lines_of = {p["state_key"]: p["lines"] for p in rec["proposals"]}
    out = promote(proposals, feas)
    (OUT / "promotion.json").write_text(json.dumps(out.payload(), indent=1))
    print(f"promotion: {out.n_promoted} of {out.n_proposals} promoted"
          f"{'  [CAP BOUND]' if out.cap_binding else ''}")

    # ------------------------------------------------------- certification --
    cert_dir = OUT / "certified"
    cert_dir.mkdir(exist_ok=True)
    todo = [k for k in out.promoted_keys
            if not (cert_dir / f"{digest(k)}.json").exists()]
    print(f"certification: {len(out.promoted_keys) - len(todo)} done, "
          f"{len(todo)} remaining")

    if a.stage in ("all", "certify"):
        for i, k in enumerate(todo, 1):
            if time.time() > deadline:
                print(f"  shard bound reached ({a.max_hours}h); "
                      f"{len(todo) - i + 1} candidates remain. Re-run to resume.")
                break
            sel = Exp4Selection(POOL_VERSION, frozenset(lines_of[k]),
                                frozenset())
            built = assemble(sel, _BY_RID, graph, H.baseline.network.stops,
                             pool_version=POOL_VERSION,
                             first_dep_sec_by_period=first_dep)
            t0 = time.time()
            try:
                cr = certify(built.network, built.tstats, state_key=k,
                             state_digest=sel.state_digest, harness=H,
                             stops_gdf=sg, lam=LAM, seed=SEED,
                             constraints=cons, contract_digest=CERTIFICATION_DIGEST)
            except Exception as e:
                (cert_dir / f"{digest(k)}.json").write_text(json.dumps(
                    {"state_key": k, "error": f"{type(e).__name__}: {e}"[:200]},
                    indent=1))
                print(f"  [{i}/{len(todo)}] {k} FAILED {type(e).__name__}")
                continue
            # written the instant it exists -- OPERATIONS 31
            (cert_dir / f"{digest(k)}.json").write_text(
                json.dumps({**cr.payload(), "lines": lines_of[k]}, indent=1))
            print(f"  [{i}/{len(todo)}] {k[:44]} obj {cr.objective:,.4f} "
                  f"rounds {cr.rounds} converged {cr.converged} "
                  f"({time.time() - t0:.0f}s)")

    # ---------------------------------------------------- fleet feasibility --
    #
    # EXP4_BLOCKING §9 AS AMENDED. The question is EXISTENTIAL -- does a
    # feasible blocking of this candidate's timetable exist inside the
    # envelope -- and it is asked of the CERTIFIED plan, not of a plan solved
    # again here. Reblocking is permitted (OPERATIONAL_RECOURSE); extra buses
    # are not.
    #
    # The per-period arm that used to live here was removed by AMENDMENT 1:
    # it was a property of whichever maximum matching turned up, not of the
    # candidate. Nothing below reads `fleet_by_period` as a gate.
    fleet_dir = OUT / "fleet"
    fleet_dir.mkdir(exist_ok=True)

    if a.stage in ("all", "fleet"):
        done_c = sorted(cert_dir.glob("*.json"))
        n_f = 0
        for f in done_c:
            d = json.loads(f.read_text())
            if "error" in d:
                continue
            fp = fleet_dir / f.name
            if fp.exists():
                continue
            if time.time() > deadline:
                print("  shard bound reached during fleet evaluation")
                break
            try:
                v = fleet_verdict(d["state_key"], d["lines"],
                                  d.get("plan_EXACT") or {})
            except Exception as e:
                # A failure to MEASURE fleet is a missing diagnostic, not an
                # invalid comparison. It is recorded and the run continues;
                # READINESS_FROZEN names this explicitly.
                v = {"state_key": d["state_key"],
                     "verdict": "NOT_MEASURED",
                     "error": f"{type(e).__name__}: {e}"[:300],
                     "consequence": ("this candidate keeps its objective and "
                                     "its rank; only its fleet diagnostic is "
                                     "missing")}
            fp.write_text(json.dumps(v, indent=1, default=str))
            n_f += 1
        if n_f:
            print(f"fleet: {n_f} candidates evaluated")

    fleets = {}
    for f in sorted(fleet_dir.glob("*.json")):
        d = json.loads(f.read_text())
        fleets[d["state_key"]] = d
    if fleets:
        from collections import Counter
        tally = Counter(v["verdict"] for v in fleets.values())
        print(f"fleet feasibility: {dict(sorted(tally.items()))}")
        if tally.get("FEASIBLE"):
            print("  NOTE: a FEASIBLE verdict requires a deadhead oracle whose "
                  "provenance satisfies the certification contract")

    # ------------------------------------------------------------- report --
    certs = []
    for f in sorted(cert_dir.glob("*.json")):
        d = json.loads(f.read_text())
        if "error" not in d:
            certs.append(d)
    print(f"\n{'=' * 70}")
    print(f"  proposals    : {len(rec['proposals'])}")
    print(f"  promoted     : {out.n_promoted}")
    print(f"  certified    : {len(certs)} / {out.n_promoted}")
    if certs:
        certs.sort(key=lambda d: (d["objective_EXACT"], len(d["lines"]),
                                  tuple(sorted(d["lines"]))))
        w = certs[0]
        print(f"  EXACT leader : {w['state_key']}")
        print(f"                 {len(w['lines'])} lines, objective "
              f"{w['objective_EXACT']:,.4f}")
        if len(certs) > 1:
            sep = certs[1]["objective_EXACT"] - w["objective_EXACT"]
            print(f"  separation   : {sep:,.4f} "
                  f"({sep / abs(w['objective_EXACT']):.3e} relative) "
                  f"from the runner-up")
        on_bound = len(w["lines"]) in (MIN_LINES, MAX_LINES)
        print(f"  gate 4-6     : winner has {len(w['lines'])} lines; bounds "
              f"[{MIN_LINES}, {MAX_LINES}] "
              f"{'ACTIVE -- RESULT CENSORED' if on_bound else 'inactive'}")
        wf = fleets.get(w["state_key"], {})
        wv = wf.get("verdict", "NOT MEASURED")
        wb = wf.get("fleet_bracket") or {}
        print(f"  fleet        : {wv}"
              + (f", bracket [{wb.get('lower')}, {wb.get('upper')}] blocks"
                 if wb else "")
              + f" (deadhead {wf.get('deadhead_provenance_status', 'OPEN')})")
        print("  SCOPE OF THE CLAIM")
        print("    This leader is the best CERTIFIED OBJECTIVE under the "
              "canonical vehicle-hours")
        print(f"    envelope ({VEH_HOURS:.6f} vh, {ENVELOPE_DIGEST}). Its "
              f"FLEET REQUIREMENT IS {wv}:")
        print("    deadhead provenance is OPEN and, on synthesised candidates, "
              "terminal identity")
        print("    is degenerate. No operational deployability claim follows "
              "from this run.")
        print("    Fleet was reported and never gated; ranking used "
              "objective_EXACT alone.")
    complete = len(certs) == out.n_promoted and out.n_promoted > 0
    print(f"  status       : {'COMPLETE' if complete else 'IN PROGRESS'}")

    (OUT / "status.json").write_text(json.dumps({
        "experiment": "exp4", "architecture":
            "gen2 multi-start discovery -> permissive promotion -> "
            "solve_exact certification -> exact-only conclusions",
        "pool_version": POOL_VERSION, "pool_size": len(pool),
        "cardinality": [MIN_LINES, MAX_LINES],
        "envelope": {"veh_hours": VEH_HOURS,
                     "block_derived_fleet_by_period": ENVELOPE_FLEET,
                     "envelope_digest": ENVELOPE_DIGEST,
                     "source": "outputs/CANONICAL_ENVELOPE.json",
                     "fleet_gate": ("candidate blocking, EXP4_BLOCKING v2 "
                                    "as amended; NOT a scalar peak proxy"),
                     "blocking_contract_digest": BLOCKING_CONTRACT_DIGEST,
                     "operational_recourse_digest": OPERATIONAL_RECOURSE_DIGEST,
                     "deadhead_provenance": "OPEN",
                     "baseline_bracket": baseline_bound.payload()},
        "fleet_feasibility": {k: {"verdict": v["verdict"],
                                  "deadhead_provenance_status":
                                      v.get("deadhead_provenance_status"),
                                  "fleet_bracket": v.get("fleet_bracket")}
                              for k, v in sorted(fleets.items())},
        "proposal_digest": PROPOSAL_DIGEST,
        "promotion_digest": PROMOTION_DIGEST,
        "certification_digest": CERTIFICATION_DIGEST,
        "tie_break_digest": TIE_BREAK_DIGEST,
        "n_proposals": len(rec["proposals"]), "n_promoted": out.n_promoted,
        "n_certified": len(certs), "complete": complete,
        "exact_leader": certs[0]["state_key"] if certs else None,
        "exact_leader_objective": certs[0]["objective_EXACT"] if certs else None,
        "exact_leader_lines": certs[0]["lines"] if certs else None,
        "note": ("every number reported here is EXACT-stage. Discovery scores "
                 "decide nothing and are stored only as approximate provenance."),
        "scope_of_claim": (
            "best CERTIFIED OBJECTIVE under the canonical vehicle-hours "
            "envelope. FLEET REQUIREMENT IS NOT ESTABLISHED: deadhead "
            "provenance is OPEN and terminal identity is degenerate on "
            "synthesised candidates, so the fleet instrument returns "
            "UNDECIDABLE. No operational deployability claim follows."),
        "fleet_policy": (
            "REPORTED, NOT GATED. No fleet verdict filtered, ranked or "
            "rejected any candidate; ranking is on objective_EXACT alone. "
            "Authorised in outputs/exp4/READINESS_FROZEN.json."),
        "readiness_frozen": _json_or_none(READINESS_FROZEN),
        "d24_classification": "POST-RESULT operational validation, not a "
                              "launch gate",
        "seconds_this_shard": time.time() - t_start,
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
