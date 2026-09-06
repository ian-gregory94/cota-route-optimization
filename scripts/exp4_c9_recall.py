#!/usr/bin/env python3
"""C9 — proposal recall. Can discovery discard what certification would pick?

C9 no longer asks whether master-path reuse identifies the exact leader inside
the D18 promotion band. D18 emitted no band and must not be made to. Under the
architecture the band's absence forced --

    Discovery proposes. Exact optimization decides.

-- discovery bias is contained rather than disproved, and exactly one question
about discovery still matters:

    **Can proposal-only discovery discard a candidate that exact certification
    would have selected?**

That is a RECALL question, not an agreement question. Whether discovery scores
resemble certified scores is explicitly NOT the criterion: D18 already
established they do not, structurally, and the architecture is built on the
assumption that they never will.

THE TEST
--------
On reduced instances where the complete candidate space can be enumerated:

  1. enumerate every candidate network in the space;
  2. exact-certify all of them -- this is ground truth, and it uses the SAME
     instrument production certification uses, so the comparison is honest;
  3. identify the true certified winner and the certified near-optimal
     frontier;
  4. run production discovery + the preregistered promotion policy
     INDEPENDENTLY, with no knowledge of step 2;
  5. check the certified winner is in the promoted set;
  6. measure recall of the wider certified frontier.

Ground truth in step 2 and the pipeline in step 4 never touch. The pipeline
cannot see the answer it is being scored against.

PREREGISTERED CRITERIA -- fixed here before any recall number existed
---------------------------------------------------------------------
  PRIMARY  (required)  the certified winner is promoted in 100% of cells.
                       Anything less means the architecture's core claim --
                       that certification decides -- is false, because
                       certification never got to see the winner.

  FRONTIER (required)  recall of the certified top-FRONTIER_K is at least
                       FRONTIER_MIN_RECALL across all cells, so a pass cannot
                       rest on one lucky winner.

FRONTIER_K = 5 is a rank, not a threshold: it needs no assumption about what
margin is meaningful, which matters because D18 forbade the measurement that
would have told us.

If a cell fails, the promotion rule is NOT tuned against it. Section 6 of the
execution contract: a change would be a new preregistered revision followed by
a completely fresh validation suite.

    python scripts/exp4_c9_recall.py --json outputs/exp4/c9_recall.json
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

FRONTIER_K = 5
FRONTIER_MIN_RECALL = 0.90

C9_CRITERION = {
    "question": ("can proposal-only discovery discard a candidate that exact "
                 "certification would have selected?"),
    "primary": "the certified winner is promoted in 100% of cells",
    "frontier": (f"recall of the certified top-{FRONTIER_K} is at least "
                 f"{FRONTIER_MIN_RECALL:.0%} across all cells"),
    "frontier_k": FRONTIER_K,
    "frontier_min_recall": FRONTIER_MIN_RECALL,
    "not_the_criterion": ("agreement between discovery scores and certified "
                          "scores. D18 established they diverge structurally "
                          "and the architecture assumes they always will."),
    "version": 1,
}


class _Cached:
    """A cached certified result, shaped like the real one for the fields used.

    Deliberately minimal: if a field is needed that the cache does not carry,
    this raises rather than silently returning a default, so a cache can never
    quietly stand in for something it does not contain.
    """

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __getattr__(self, name):
        raise AttributeError(
            f"the certification cache does not carry {name!r}; recompute with "
            f"--fresh rather than defaulting it")


def _subsets(lines, lo, hi):
    for n in range(lo, hi + 1):
        for c in itertools.combinations(sorted(lines), n):
            yield frozenset(c)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--cells", default="")
    ap.add_argument("--max-candidates", type=int, default=0)
    ap.add_argument("--fresh", action="store_true",
                    help="ignore the certification cache and recompute ground "
                         "truth from scratch; used for the cold determinism run")
    a = ap.parse_args()

    from cota_opt.configs import service_periods
    from cota_opt.contract import ContractLimits
    from cota_opt.exp4_assemble import assemble
    from cota_opt.exp4_certify import (CERTIFICATION_CONTRACT,
                                       CERTIFICATION_DIGEST, certify, n_off_in)
    from cota_opt.exp4_inference import (Exp4Candidate, ProposalRecord,
                                         ProposalScore, rank_certified)
    from cota_opt.exp4_network import Exp4Selection
    from cota_opt.exp4_promotion import (PROMOTION_DIGEST, PROMOTION_RULE,
                                         promote)
    from cota_opt.exp4_score import score_exp4_network
    from cota_opt.gen2_search import search
    from cota_opt.firewall.core import digest
    from exp2_treatments import pinned
    from exp4_c10_fixtures import (CASES, POOL_VERSION, _BY_RID, _boot,
                                   _first_dep_by_period)

    st = _boot()
    H, sg, graph = st["H"], st["sg"], st["graph"]
    periods = sorted(service_periods(H.assumptions))
    first_dep = _first_dep_by_period()
    t_all = time.time()

    # ---- the benchmark cells -------------------------------------------
    #
    # Chosen to stress the D18 failure mode specifically: the gap tracks
    # structure, so the cells must span sparse and dense and must not all come
    # from one pool. Pools are drawn from the frozen C10 geometry, which is real
    # Experiment 4 network material rather than a fixture invented for this.
    #
    # Cardinality bounds are set so the complete space is enumerable AND large
    # enough that the promotion policy has to discriminate: with a floor of 25,
    # a 25-candidate space would be promoted entire and the test would measure
    # nothing.
    poolA = sorted(CASES[1]["lines"])            # large_gap
    poolB = sorted(CASES[3]["lines"])            # greedy_overbuilds
    poolC = sorted(set(CASES[0]["lines"]) | set(CASES[2]["lines"]))

    def assembles(sel):
        try:
            assemble(sel, _BY_RID, graph, H.baseline.network.stops,
                     pool_version=POOL_VERSION,
                     first_dep_sec_by_period=first_dep)
            return True
        except Exception:
            return False

    def solo(pool):
        return [l for l in pool
                if assembles(Exp4Selection(POOL_VERSION, frozenset([l]),
                                           frozenset()))]

    poolA, poolB, poolC = solo(poolA), solo(poolB), solo(poolC)

    CELLS = [
        {"name": "sparse_wide_pool", "pool": poolC, "lo": 1, "hi": 2,
         "vh": 160.0, "peak": 40.0, "pins": (),
         "stresses": "sparse networks over the widest pool"},
        {"name": "sparse_to_mid", "pool": poolA, "lo": 1, "hi": 3,
         "vh": 160.0, "peak": 40.0, "pins": (),
         "stresses": "the sparse-to-mid range where D18's gap grows fastest"},
        {"name": "dense", "pool": poolA, "lo": 3, "hi": 5,
         "vh": 160.0, "peak": 40.0, "pins": (),
         "stresses": "dense networks, D18's low-gap end"},
        {"name": "many_off", "pool": poolA, "lo": 2, "hi": 4,
         "vh": 160.0, "peak": 40.0, "pins": "first_line_all_periods",
         "stresses": "a pinned-off line, the fate no subset can express"},
        {"name": "other_pool", "pool": poolB, "lo": 1, "hi": 3,
         "vh": 200.0, "peak": 40.0, "pins": (),
         "stresses": "a different pool, so structure is not one pool's quirk"},
    ]
    if a.cells:
        want = set(a.cells.split(","))
        CELLS = [c for c in CELLS if c["name"] in want]

    reports = []
    for cell in CELLS:
        pool = cell["pool"]
        pins = (frozenset((pool[0], p) for p in periods)
                if cell["pins"] == "first_line_all_periods" else frozenset())
        cons = pinned(cell["vh"], {p: cell["peak"] for p in periods})
        limits = ContractLimits(veh_hour_budget=cell["vh"],
                                peak_vehicle_budget=cell["peak"],
                                required_waiting_model="same_route")

        universe = []
        for s in _subsets(pool, cell["lo"], min(cell["hi"], len(pool))):
            sel = Exp4Selection(POOL_VERSION, s, pins if s >= set(
                k[0] for k in pins) or not pins else frozenset())
            if assembles(sel):
                universe.append(sel)
        if a.max_candidates:
            universe = universe[:a.max_candidates]
        if len(universe) < 3:
            print(f"\n=== {cell['name']}: only {len(universe)} candidates, "
                  f"skipping ===")
            continue

        udig = digest({"cell": cell["name"], "pool": sorted(pool),
                       "lo": cell["lo"], "hi": cell["hi"],
                       "pins": sorted(map(list, pins)),
                       "candidates": [s.state_key for s in universe]})
        print(f"\n=== {cell['name']}: {len(universe)} candidates, "
              f"pool {len(pool)}, cardinality {cell['lo']}-{cell['hi']}, "
              f"digest {udig} ===")
        print(f"    stresses: {cell['stresses']}")

        # ---- STEP 1-3: ground truth, by exact certification -------------
        #
        # Checkpointed per candidate. The first run of this benchmark computed
        # 1,369 seconds of certification for the dense cell and lost every
        # second of it to a crash in the NEXT stage -- OPERATIONS 31 exactly.
        # Certification is deterministic, so a cached result is the same result;
        # the cache is keyed by the universe digest so it can never be read
        # across a changed space. --fresh ignores it.
        cache_path = (ROOT / "outputs" / "exp4" / "c9_cache" /
                      f"{cell['name']}-{udig}.json")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cached = {}
        if cache_path.exists() and not a.fresh:
            cached = json.loads(cache_path.read_text())
            print(f"    cache: {len(cached)} certified results on disk")

        truth = {}
        t0 = time.time()
        for i, sel in enumerate(universe, 1):
            if sel.state_key in cached:
                c = cached[sel.state_key]
                truth[sel.state_key] = {
                    "sel": sel, "cert": _Cached(**c),
                    "lines": sorted(sel.lines)}
                continue
            built = assemble(sel, _BY_RID, graph, H.baseline.network.stops,
                             pool_version=POOL_VERSION,
                             first_dep_sec_by_period=first_dep)
            try:
                cr = certify(built.network, built.tstats,
                             state_key=sel.state_key,
                             state_digest=sel.state_digest,
                             harness=H, stops_gdf=sg, lam=2.0, seed=20260825,
                             constraints=cons,
                             pinned_off=frozenset(sel.pinned_off),
                             contract_digest=CERTIFICATION_DIGEST)
            except Exception as e:
                print(f"    [{i}/{len(universe)}] {sel.state_key} "
                      f"UNCERTIFIABLE: {type(e).__name__}")
                continue
            truth[sel.state_key] = {"sel": sel, "cert": cr,
                                    "lines": sorted(sel.lines)}
            # write the instant it exists, before anything else can fail
            cached[sel.state_key] = {
                "objective": cr.objective, "converged": cr.converged,
                "rounds": cr.rounds, "plan_digest": cr.plan_digest,
                "guarantee": cr.guarantee, "seconds": cr.seconds}
            cache_path.write_text(json.dumps(cached, indent=1))
            if i % 10 == 0 or i == len(universe):
                print(f"    certified {i}/{len(universe)} "
                      f"({time.time() - t0:.0f}s)")
        t_truth = time.time() - t0
        if len(truth) < 3:
            print(f"    only {len(truth)} certifiable; skipping cell")
            continue

        order = sorted(truth.values(), key=lambda r: (
            r["cert"].objective, len(r["lines"]), tuple(r["lines"])))
        winner = order[0]["sel"].state_key
        frontier = [r["sel"].state_key for r in order[:FRONTIER_K]]
        n_conv = sum(1 for r in truth.values() if r["cert"].converged)
        print(f"    ground truth: winner {winner} "
              f"obj {order[0]['cert'].objective:,.4f}; "
              f"{n_conv}/{len(truth)} converged; {t_truth:.0f}s")

        # ---- STEP 4: the production pipeline, independently -------------
        def scorer(s):
            try:
                sc, _ = score_exp4_network(
                    s, harness=H, stops_gdf=sg, pool=_BY_RID, graph=graph,
                    pool_version=POOL_VERSION,
                    first_dep_sec_by_period=first_dep, limits=limits,
                    constraints=cons, lam=2.0, seed=20260825,
                    iterations=20_000, restarts=1, width=0,
                    waiting_model="same_route", starts="greedy",
                    allow_off=True)
            except Exception as e:
                return float("inf"), {"error": str(e)[:120]}, False, {}
            m = sc.metrics
            return (float(m.get("objective", float("inf"))),
                    {k: v for k, v in m.items()
                     if isinstance(v, (int, float))}, True, sc.plan)

        t0 = time.time()
        # gen2_search seeds with a single line by default, which it then
        # refuses when a cell's min_lines is above 1. The seed is the smallest
        # admissible network in deterministic pool order -- a starting point,
        # not a hint: it is chosen without reference to any certified result.
        seed = tuple(sorted(pool)[:cell["lo"]])
        res = search(pool, scorer, periods, max_lines=cell["hi"],
                     min_lines=cell["lo"], seed_lines=seed,
                     pinned_off=tuple(pins),
                     pool_version=POOL_VERSION, allow_swaps=True,
                     pair_adds=True, max_evaluations=400)
        t_disc = time.time() - t0

        proposals, feas = [], {}
        for c in res.evaluated:
            k = c.selection.state_key
            if k in feas:
                continue
            feas[k] = bool(c.feasible)
            proposals.append(ProposalRecord(
                state_key=k, state_digest=c.selection.state_digest,
                score=ProposalScore(float(c.objective))))
        out = promote(proposals, feas)
        promoted = set(out.promoted_keys)
        print(f"    discovery: {len(proposals)} proposals "
              f"({sum(feas.values())} feasible) in {t_disc:.0f}s "
              f"-> promoted {out.n_promoted}"
              f"{' [CAP BOUND]' if out.cap_binding else ''}")

        # ---- STEP 5-6: recall -------------------------------------------
        winner_retained = winner in promoted
        # A candidate discovery never proposed is a recall miss too -- the
        # promoted set is a subset of the proposals, so "not proposed" and
        # "proposed and dropped" are the same failure from certification's view.
        fr_hits = [k for k in frontier if k in promoted]
        fr_recall = len(fr_hits) / len(frontier) if frontier else 0.0
        never_proposed = [k for k in frontier if k not in feas]
        print(f"    RECALL: winner {'RETAINED' if winner_retained else 'LOST'}"
              f" | top-{FRONTIER_K} recall {fr_recall:.0%} "
              f"({len(fr_hits)}/{len(frontier)})"
              + (f" | {len(never_proposed)} never proposed"
                 if never_proposed else ""))
        if not winner_retained:
            w = truth[winner]
            print(f"      LOST WINNER {winner}: {len(w['lines'])} lines, "
                  f"certified {w['cert'].objective:,.4f}, "
                  f"proposed={winner in feas}, "
                  f"feasible_at_discovery={feas.get(winner)}")

        reports.append({
            "cell": cell["name"], "stresses": cell["stresses"],
            "universe_digest": udig,
            "pool_size": len(pool), "cardinality": [cell["lo"], cell["hi"]],
            "n_candidates": len(universe), "n_certified": len(truth),
            "n_converged": n_conv,
            "certified_winner": winner,
            "certified_winner_objective": order[0]["cert"].objective,
            "certified_frontier": frontier,
            "n_proposals": out.n_proposals, "n_feasible": out.n_feasible,
            "n_promoted": out.n_promoted,
            "promotion": out.payload(),
            "winner_retained": winner_retained,
            "frontier_hits": fr_hits, "frontier_recall": fr_recall,
            "frontier_never_proposed": never_proposed,
            "seconds_ground_truth": t_truth, "seconds_discovery": t_disc,
            "certified_objectives": {k: v["cert"].objective
                                     for k, v in sorted(truth.items())},
        })

    if not reports:
        print("\nno cells ran")
        return 1

    winners_ok = all(r["winner_retained"] for r in reports)
    worst_fr = min(r["frontier_recall"] for r in reports)
    frontier_ok = worst_fr >= FRONTIER_MIN_RECALL
    passes = winners_ok and frontier_ok

    print(f"\n{'=' * 74}")
    print(f"  cells                         : {len(reports)}")
    print(f"  certified winner retained     : "
          f"{sum(r['winner_retained'] for r in reports)}/{len(reports)}"
          f"  (required: all)")
    print(f"  worst top-{FRONTIER_K} recall           : {worst_fr:.0%}"
          f"  (required: >= {FRONTIER_MIN_RECALL:.0%})")
    print(f"  promotion breadth             : "
          f"{sum(r['n_promoted'] for r in reports)} promoted of "
          f"{sum(r['n_proposals'] for r in reports)} proposals across cells")
    print(f"  ground-truth certification    : "
          f"{sum(r['n_certified'] for r in reports)} candidates, "
          f"{sum(r['seconds_ground_truth'] for r in reports):.0f}s")
    print(f"\n  C9: {'MET' if passes else 'OPEN'}")

    out_doc = {
        "item": "C9",
        "criterion": C9_CRITERION,
        "certification_contract": CERTIFICATION_CONTRACT,
        "certification_digest": CERTIFICATION_DIGEST,
        "promotion_rule": PROMOTION_RULE,
        "promotion_digest": PROMOTION_DIGEST,
        "n_cells": len(reports),
        "winner_retained_all_cells": winners_ok,
        "worst_frontier_recall": worst_fr,
        "frontier_criterion_met": frontier_ok,
        "verdict": "MET" if passes else "OPEN",
        "seconds": time.time() - t_all,
        "cells": reports,
    }
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(out_doc, indent=2))
        print(f"\nwrote {a.json}")
    return 0 if passes else 2


if __name__ == "__main__":
    raise SystemExit(main())
