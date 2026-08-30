#!/usr/bin/env python3
"""Replay the COMPLETE Phase A2 search policy on the space whose answer is known.

Not an approximation of the policy — the policy. Three lanes, first-improvement,
measured-singles ordering, seeded rotations, seeded random k=2/k=3 starts,
shared checkpoint and dedup, run against Experiment 2B's 240 exhaustively
enumerated states.

**This is a gate, not a report.** If the policy does not recover the known
optimum, Phase A2 does not run and Experiment 3 reports the Phase A1 singles
census instead. Improvising a different search after seeing A1's results is
exactly how a preregistration stops meaning anything.

The 2B optimum later certified as NULL (D22). This validates that the policy
finds what the exhaustive table says is best — nothing about whether that
intervention is worth making.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cota_opt.statesearch import (Checkpoint, NULL, Policy,  # noqa: E402
                                  State, run_policy, search)

OUT = ROOT / "outputs" / "exp3"
OBJECTIVE_COLUMN = "unserved_vs_noedit_pct"

#: The evaluation budget the replay gets. Deliberately close to Phase A2's own
#: ~330, so the policy is tested at the scale it will run at rather than given
#: enough budget to brute-force a 240-state space.
REPLAY_BUDGET = 120


def main() -> int:
    src = OUT.parent / "exp2b_stageA.csv"
    df = pd.read_csv(src)
    if "lambda" in df:
        df = df[df["lambda"] == 2.0]
    df = df.drop_duplicates(subset=["set_key"], keep="first")
    table = {str(r.set_key): float(getattr(r, OBJECTIVE_COLUMN))
             for r in df.itertuples()}
    table.setdefault(NULL, 0.0)

    classes = json.loads((OUT.parent / "exp2_candidate_classes.json").read_text())
    pool = sorted(classes["rule"]["eligible_for_2B"])
    incompatible = {tuple(sorted((p["a"], p["b"])))
                    for p in classes["incompatible_pairs"]}

    # The stand-in for Phase A1: the table's own measured k=1 rows. Same role
    # exactly — a measured single-mutation objective with frequency
    # re-optimized, used to order visits and nothing else.
    singles = {m: table.get(m, float("inf")) for m in pool}
    expected = min((k for k in table if k != NULL),
                   key=lambda k: (table[k], k))

    def lookup(st: State) -> float:
        try:
            return table[st.key]
        except KeyError:
            raise KeyError(
                f"{st.key} is feasible but absent from the table; the "
                f"benchmark space must be exhaustive") from None

    print("=" * 84)
    print("PHASE A2 POLICY REPLAY — the 2B space, whose answer is known")
    print("=" * 84)
    pol = Policy()
    print(f"  states in the table  {len(table)}")
    print(f"  pool                 {len(pool)}")
    print(f"  replay budget        {REPLAY_BUDGET} evaluations")
    print(f"  expected optimum     {expected}  ({table[expected]:+.4f})")
    print()

    cp_path = OUT / "policy_replay.jsonl"
    if cp_path.exists():
        cp_path.unlink()
    res = run_policy(pool, lookup, incompatible, singles, REPLAY_BUDGET,
                     policy=pol, checkpoint=Checkpoint(cp_path))

    for ln in res["lanes"]:
        print(f"  lane {ln['lane']}  starts={ln['starts']}")
        print(f"          quota {ln['quota']:>3}  used {ln['used']:>3}  "
              f"best {ln['best']}  ({ln['best_score']:+.4f})")
    print()
    print(f"  policy best          {res['best']}  ({res['best_score']:+.4f})")
    print(f"  unique states scored {res['unique_states_scored']} of {len(table)}")
    print(f"  carried to lane 3    {res['carried_to_lane3']}")

    # Resume, on the full policy: a second run must do no work and agree.
    cp2 = Checkpoint(cp_path)
    before = len(cp2.scores)
    res2 = run_policy(pool, lookup, incompatible, singles, REPLAY_BUDGET,
                      policy=pol, checkpoint=cp2)
    resume_ok = (res2["best"] == res["best"] and res2["spent"] == 0
                 and len(cp2.scores) == before)

    ok = res["best"] == expected and resume_ok
    res.update({"pass": ok, "expected": expected,
                "exhaustive_optimum": expected,
                "space_size": len(table),
                "objective_column": OBJECTIVE_COLUMN,
                "resume": {"same_answer": res2["best"] == res["best"],
                           "second_pass_spent": res2["spent"],
                           "no_new_states": len(cp2.scores) == before},
                "note": "The COMPLETE Phase A2 policy, replayed. The optimum "
                        "recovered here certified as NULL at full effort "
                        "(D22): this validates search recovery, not the "
                        "intervention."})

    print(f"  resume               same answer={res2['best'] == res['best']}, "
          f"second pass spent {res2['spent']}")
    print()
    print(f"  VERDICT: {'PASS' if ok else 'FAIL'}")
    if not ok:
        print("  Phase A2 MUST NOT RUN. Report the Phase A1 singles census "
              "instead;")
        print("  improvising another search after seeing A1's results is how a")
        print("  preregistration stops meaning anything.")

    dest = OUT / "policy_benchmark.json"
    dest.write_text(json.dumps(res, indent=2) + "\n")
    print(f"\nartifacts: {dest}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
