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

#: The envelope, pinned from the unedited baseline exactly as every previous
#: experiment pinned it. Not a free parameter.
VEH_HOURS = 2507.0
PEAK_VEHICLES = 200.0

LAM = 2.0
SEED = 20260825


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-hours", type=float, default=6.0)
    ap.add_argument("--stage", default="all",
                    choices=("all", "discover", "certify", "report"))
    a = ap.parse_args()

    from cota_opt.configs import period_of_seconds, service_periods
    from cota_opt.contract import ContractLimits
    from cota_opt.exp4_assemble import assemble
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

    cons = pinned(VEH_HOURS, {p: PEAK_VEHICLES for p in periods})
    limits = ContractLimits(veh_hour_budget=VEH_HOURS,
                            peak_vehicle_budget=PEAK_VEHICLES,
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
          f"cardinality {MIN_LINES}-{MAX_LINES}, envelope {VEH_HOURS} vh / "
          f"{PEAK_VEHICLES} peak")

    # ---------------------------------------------------------- discovery --
    prop_path = OUT / "proposals.json"
    if prop_path.exists():
        rec = json.loads(prop_path.read_text())
        print(f"discovery: resumed, {len(rec['proposals'])} proposals on disk")
    elif a.stage in ("all", "discover"):
        sup = Exp4Selection(POOL_VERSION, frozenset(pool), frozenset())
        master = {}
        if assembles(sup):
            mc = {}
            try:
                score_exp4_network(
                    sup, harness=H, stops_gdf=sg, pool=_BY_RID, graph=graph,
                    pool_version=POOL_VERSION,
                    first_dep_sec_by_period=first_dep, limits=limits,
                    constraints=cons, lam=LAM, seed=SEED, iterations=1,
                    restarts=1, width=0, waiting_model="same_route",
                    starts="greedy", allow_off=True, pathset_cache=mc)
            except Exception as e:
                print(f"  supernetwork master failed: {type(e).__name__}: {e}")
            master = dict(mc)
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
    complete = len(certs) == out.n_promoted and out.n_promoted > 0
    print(f"  status       : {'COMPLETE' if complete else 'IN PROGRESS'}")

    (OUT / "status.json").write_text(json.dumps({
        "experiment": "exp4", "architecture":
            "gen2 multi-start discovery -> permissive promotion -> "
            "solve_exact certification -> exact-only conclusions",
        "pool_version": POOL_VERSION, "pool_size": len(pool),
        "cardinality": [MIN_LINES, MAX_LINES],
        "envelope": {"veh_hours": VEH_HOURS, "peak": PEAK_VEHICLES},
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
        "seconds_this_shard": time.time() - t_start,
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
