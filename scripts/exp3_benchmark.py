#!/usr/bin/env python3
"""Run the Experiment 3 search on the space whose answer is already known.

Experiment 2B enumerated **every** structurally feasible subset of the frozen
twelve-candidate set — 240 states — and scored all of them. That table is the
only place in this project where the true optimum is not a matter of opinion, so
it is the only place a heuristic can be checked rather than trusted.

The contract requires this to pass before the search is pointed at the mutation
space. A search that cannot find the answer where the answer is known is not
evidence about a space where it is not.

**What this does not show.** The discovery-stage leader recovered here later
certified as NULL at full effort (D22, D24). This benchmark validates *search
recovery*, not the intervention. Those are different claims and conflating them
would be exactly the error gate 12 exists to prevent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cota_opt.statesearch import benchmark            # noqa: E402

OUT = ROOT / "outputs"

#: Declared before the benchmark was run. Seed 0 starts from the null; the
#: others start from single mutations spread across the sorted pool. The search
#: must recover the optimum from EVERY one of them independently — a heuristic
#: that finds the answer from one lucky start has not been shown to find it.
BENCHMARK_SEEDS = (0, 1, 2, 3, 4, 5, 6, 7)

#: The primary objective is not available in the 2B table (it predates the
#: Experiment 3 objective), so the benchmark uses the quantity 2B itself
#: ranked on, at the same effort, from the same rows. Comparing the search
#: against the exhaustive table means comparing on the table's own column.
OBJECTIVE_COLUMN = "unserved_vs_noedit_pct"


def main() -> int:
    src = OUT / "exp2b_stageA.csv"
    if not src.exists():
        print(f"missing {src}; the benchmark needs 2B's exhaustive table")
        return 1
    df = pd.read_csv(src)
    if "lambda" in df:
        df = df[df["lambda"] == 2.0]
    df = df.drop_duplicates(subset=["set_key"], keep="first")

    table = {str(r.set_key): float(getattr(r, OBJECTIVE_COLUMN))
             for r in df.itertuples()}
    if "<none>" not in table:
        table["<none>"] = 0.0

    classes = json.loads((OUT / "exp2_candidate_classes.json").read_text())
    pool = sorted(classes["rule"]["eligible_for_2B"])
    incompatible = {tuple(sorted((p["a"], p["b"])))
                    for p in classes["incompatible_pairs"]}

    expected = min((k for k in table if k != "<none>"),
                   key=lambda k: (table[k], k))

    print("=" * 84)
    print("EXPERIMENT 3 SEARCH BENCHMARK — the 2B space, whose answer is known")
    print("=" * 84)
    print(f"  pool                {len(pool)} mutations")
    print(f"  incompatible pairs  {len(incompatible)}")
    print(f"  states in the table {len(table)}")
    print(f"  objective column    {OBJECTIVE_COLUMN} (lower is better)")
    print(f"  expected optimum    {expected}  ({table[expected]:+.4f})")
    print(f"  seeds               {list(BENCHMARK_SEEDS)}")
    print()

    res = benchmark(pool, table, incompatible, BENCHMARK_SEEDS, expected,
                    max_cardinality=6, checkpoint_dir=OUT / "exp3")
    res["objective_column"] = OBJECTIVE_COLUMN
    res["seeds"] = list(BENCHMARK_SEEDS)
    res["pool_size"] = len(pool)
    res["incompatible_pairs"] = len(incompatible)

    for sd, v in res["per_seed"].items():
        mark = "ok" if v["recovered"] else "FAIL"
        print(f"  seed {sd:>2}  {v['found']:<62.62s} "
              f"{v['evaluated']:>4} evals  {mark}")
    print()
    c = res["combined"]
    print(f"  all seeds together  {c['found']}  ({c['score']:+.4f}), "
          f"{c['evaluated']} states evaluated of {len(table)}")
    r = res["resume"]
    if r.get("checked"):
        print(f"  resume              first pass {r['first_pass_evaluated']} "
              f"evals, second pass {r['second_pass_evaluated']} evals with "
              f"{r['second_pass_reused']} reused; same answer="
              f"{r['same_answer']}")
    print()
    print(f"  VERDICT: {'PASS' if res['pass'] else 'FAIL'}")
    if res["pass"]:
        print("  The heuristic recovers the exhaustive optimum from every "
              "declared seed,")
        print("  and a resumed run does no work and returns the same answer.")
        print("  Note: that optimum CERTIFIED AS NULL at full effort (D22). "
              "This validates")
        print("  search recovery, not the intervention.")
    else:
        print("  The search may not be pointed at the mutation space.")

    (OUT / "exp3").mkdir(parents=True, exist_ok=True)
    dest = OUT / "exp3" / "search_benchmark.json"
    dest.write_text(json.dumps(res, indent=2) + "\n")
    print(f"\nartifacts: {dest}")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
