#!/usr/bin/env python3
"""C10 / gate 4-14 — the deceptive benchmark, on the PRODUCTION evaluator.

The surrogate cannot do this job and that was measured, not guessed: weighted
set coverage is submodular (535,599 diminishing-returns checks, zero
violations), greedy carries a (1 - 1/e) guarantee on it, and greedy found the
exact optimum in all four surrogate spaces. A benchmark that a heuristic always
solves proves nothing about a heuristic.

The production objective is different in kind. It prices a JOURNEY, so two lines
that meet at a common stop create transfer opportunities worth more than either
line carries alone -- a complementarity, which is the opposite of diminishing
returns. That is the structure gate 4-14 demands, and it is a property of the
real evaluator rather than something a fixture can fake.

Every case here is scored by `solve_on_network` through
`exp4_score.score_exp4_network`: the same RAPTOR semantics, waiting model,
vehicle-hour and peak-vehicle accounting and envelope that scored Experiments
1-3. Gen2 is then required to recover the exact optimum found by exhaustive
enumeration over the same space.

    python scripts/exp4_c10_benchmark.py --json outputs/exp4/c10_benchmark.json
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

from cota_opt.exp4_network import Exp4Selection                    # noqa: E402
from cota_opt.gen2_search import enumerate_exact, search           # noqa: E402


def build_cases():
    """Structurally different deceptive spaces, all on the real evaluator.

    Each names the complementarity it relies on. The claim that a case IS
    deceptive is not asserted -- it is tested, by running greedy (add-only, no
    swaps) and requiring it to miss the enumerated optimum.
    """
    from exp4_c10_fixtures import CASES
    return CASES


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--case", default="", help="run one case by name")
    a = ap.parse_args()

    from exp4_c10_fixtures import make_scorer, CASES

    results = []
    t0 = time.time()
    for case in CASES:
        if a.case and case["name"] != a.case:
            continue
        print(f"\n=== {case['name']} ===")
        print(f"    {case['complementarity']}")
        scorer, lines, periods = make_scorer(case)

        from exp4_c10_fixtures import POOL_VERSION
        oracle = enumerate_exact(lines, scorer, periods,
                                 max_lines=case.get("max_lines"),
                                 min_lines=case.get("min_lines", 1),
                                 pool_version=POOL_VERSION,
                                 max_networks=case.get("max_networks", 4096))
        if oracle.best is None:
            # Surface WHY, rather than reporting an empty space. A scorer that
            # refuses every selection looks identical to a space with no
            # feasible network, and the first is a bug while the second is a
            # finding.
            why = sorted({str(c.fitness.get("error", "no error recorded"))
                          for c in oracle.evaluated})[:3]
            print(f"    no feasible network — reasons: {why}")
            results.append({"case": case["name"],
                            "error": "no feasible network",
                            "scorer_errors": why})
            continue

        greedy = search(lines, scorer, periods,
                        seed_lines=case.get("seed"),
                        max_lines=case.get("max_lines"),
                        min_lines=case.get("min_lines", 1),
                        pool_version=POOL_VERSION,
                        allow_swaps=False, max_evaluations=400)
        gen2 = search(lines, scorer, periods,
                      seed_lines=case.get("seed"),
                      max_lines=case.get("max_lines"),
                      min_lines=case.get("min_lines", 1),
                      pool_version=POOL_VERSION,
                      allow_swaps=True, max_evaluations=400)

        opt = sorted(oracle.best.selection.lines)
        g = sorted(greedy.best.selection.lines) if greedy.best else None
        n = sorted(gen2.best.selection.lines) if gen2.best else None
        greedy_missed = (g != opt)
        gen2_found = (n == opt)

        print(f"    optimum  {opt}   obj {oracle.best.objective:.4f}"
              f"   ({oracle.n_evaluations} networks enumerated)")
        print(f"    greedy   {g}   obj "
              f"{greedy.best.objective if greedy.best else float('nan'):.4f}"
              f"   -> {'MISSES (deceptive)' if greedy_missed else 'finds it'}")
        print(f"    gen2     {n}   obj "
              f"{gen2.best.objective if gen2.best else float('nan'):.4f}"
              f"   -> {'RECOVERS' if gen2_found else 'FAILS'}")

        results.append({
            "case": case["name"],
            "complementarity": case["complementarity"],
            "n_networks_enumerated": oracle.n_evaluations,
            "optimum": opt,
            "optimum_objective": oracle.best.objective,
            "optimum_fitness": oracle.best.fitness,
            "optimum_route_fates": [f.as_dict() for f in oracle.best.fates],
            "greedy": g, "greedy_objective":
                greedy.best.objective if greedy.best else None,
            "greedy_evaluations": greedy.n_evaluations,
            "greedy_missed_optimum": greedy_missed,
            "gen2": n, "gen2_objective":
                gen2.best.objective if gen2.best else None,
            "gen2_evaluations": gen2.n_evaluations,
            "gen2_recovered_optimum": gen2_found,
            "gen2_seconds": gen2.seconds,
            "oracle_seconds": oracle.seconds,
            "case_is_deceptive": greedy_missed,
            "gen2_path": [{"state": c.selection.state_key, "parent": c.parent,
                           "move": c.move, "objective": c.objective}
                          for c in gen2.evaluated],
        })

    deceptive = [r for r in results if r.get("case_is_deceptive")]
    recovered = [r for r in results if r.get("gen2_recovered_optimum")]
    gate_closes = bool(deceptive) and len(recovered) == len(results)

    print(f"\n{'=' * 64}")
    print(f"  cases                     : {len(results)}")
    print(f"  genuinely deceptive       : {len(deceptive)} "
          f"(greedy misses the enumerated optimum)")
    print(f"  gen2 recovered the optimum: {len(recovered)}/{len(results)}")
    print(f"  GATE 4-14 CLOSES          : {gate_closes}")
    if not gate_closes:
        print("    A gate closes only when at least one case genuinely defeats "
              "greedy\n    AND Gen2 recovers every optimum. Neither half is "
              "assumed.")

    out = {"evaluator": "production (solve_on_network via score_exp4_network)",
           "seconds": time.time() - t0, "cases": results,
           "n_deceptive": len(deceptive), "n_recovered": len(recovered),
           "gate_4_14_closes": gate_closes}
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2))
        print(f"\nwrote {a.json}")
    return 0 if gate_closes else 1


if __name__ == "__main__":
    raise SystemExit(main())
