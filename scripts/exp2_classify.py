#!/usr/bin/env python3
"""Classify every candidate in the frozen Experiment 2 set against the
committed noise floor, and freeze the Experiment 2B eligibility rule.

This reads results that already exist. It runs no solver and decides nothing by
judgement: the threshold is the one committed in ACCEPTANCE.md before the
evaluations ran (3 x the unserved standard deviation of the zero-edit rung
across three seeds at the same effort), and the classification is a comparison
against it.

The eligibility rule it writes down is deliberately *not* "drop the harmful
ones". D20 established that a set's effect is not the sum of its members', so
using single-candidate performance to remove members from the joint search
would assume exactly the composability the experiment exists to test. A
candidate that hurts alone can substitute for one that helps; the only way to
know is to let the set search see it. Classification is evidence about singles.
It is not a filter on sets.

What eligibility *does* exclude is stated in the output: nothing on performance
grounds, and pairs that cannot physically coexist on structural grounds.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

OUT = ROOT / "outputs"
LAM = 2.0                      # the certified region; see gate 4
EFFORT = "60000/2/32"          # the ranking effort the singles are measured at
SIGMA = 3.0                    # committed in ACCEPTANCE.md before the runs


#: Runs before this scored under Model A while reporting Model B -- see the
#: defect note in ACCEPTANCE.md. Their logs are not evidence about Model B and
#: are not read here.
MODEL_B_LOGS = ("exp2_eval_modelB_fixed.log",)


def noise_floor(lam: float) -> tuple[float, str]:
    """Recover the floor from a Model B evaluation run's own log line.

    Read rather than recomputed, so the number classified against is the one
    the run committed to at the time. It must come from a run whose evaluator
    was Model B: classifying Model B effects against a Model A floor would mix
    the two models inside a single verdict, which is worse than either alone.
    """
    pat = re.compile(r"noise floor at this effort: (\{.*\})")
    for name in MODEL_B_LOGS:
        p = OUT / name
        if not p.exists():
            continue
        hits = pat.findall(p.read_text(errors="replace"))
        if hits:
            d = json.loads(hits[-1].replace("'", '"'))
            return SIGMA * float(d[str(lam)]["unserved_sd_pct"]), name
    raise SystemExit(
        "no Model B noise floor available yet. The only completed evaluation "
        "runs scored under Model A (ACCEPTANCE.md, 'Defect: the Experiment 2 "
        "evaluator was Model A'), and their floor may not be used to classify "
        "Model B effects. Wait for exp2-eval-B-fixed.")


def main() -> int:
    floor, floor_src = noise_floor(LAM)

    # Read the cells, not exp2_eval.csv. The CSV carries no record of which
    # evaluator wrote it, so mid-re-run it can hold Model A rows while the
    # floor above comes from the Model B log -- a verdict mixing two models
    # inside one comparison. Cell keys carry the pricing since 2026-08-29;
    # keys without it are Model A by construction and are ignored here.
    cells = {}
    for line in (OUT / "exp2_eval.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if f"|same_route|{EFFORT}" in r.get("cell", ""):
            cells[r["cell"]] = r
    base = [v for k, v in cells.items() if "|0 edits|" in k]
    singles = {k.split("single:")[1].rsplit("|", 3)[0]: v
               for k, v in cells.items() if "single:" in k}
    if not base or not singles:
        raise SystemExit(
            f"no Model B cells at effort {EFFORT} yet "
            f"({len(base)} zero-edit, {len(singles)} candidates). "
            "Wait for exp2-eval-B-fixed.")
    b_un = float(base[0][f"unserved_lam{LAM}"])
    b_gc = float(base[0][f"gc_lam{LAM}"])

    u = f"unserved_vs_noedit_pct_lam{LAM}"
    g = f"gc_vs_noedit_pct_lam{LAM}"
    s = pd.DataFrame([{
        "candidate": k,
        u: (float(v[f"unserved_lam{LAM}"]) / b_un - 1) * 100,
        g: (float(v[f"gc_lam{LAM}"]) / b_gc - 1) * 100,
        "modelled_share_pct": float(v.get("modelled_share_pct", float("nan"))),
    } for k, v in sorted(singles.items())])

    def klass(x: float) -> str:
        if x <= -floor:
            return "beneficial"
        if x >= floor:
            return "harmful"
        return "noise-floor"

    s["class"] = s[u].map(klass)
    s["margin_pts"] = s[u].abs() - floor
    s = s.sort_values(u).reset_index(drop=True)

    # Structural incompatibility, read off the implementation rather than
    # reasoned about: apply_edits maintains a set of live routes and a splice
    # does `alive -= {route_id, with_route}` before adding the merged route, so
    # a second splice naming either of them raises. Two splices sharing ANY
    # route therefore cannot coexist -- not because a terminal is used up, but
    # because neither original route survives the merge. Derived from the
    # candidate keys, never from measured performance.
    def routes(k: str) -> set[str]:
        p = k.split("|")
        return {p[1], p[2]}

    cands = list(s["candidate"])
    incompat = []
    for i, a in enumerate(cands):
        for b in cands[i + 1:]:
            shared = routes(a) & routes(b)
            if shared:
                incompat.append({"a": a, "b": b,
                                 "shared_routes": sorted(shared),
                                 "reason": "a splice consumes both its routes; "
                                           "neither survives the merge, so a "
                                           "second splice naming one raises"})

    rule = {
        "frozen": "2026-08-29",
        "lambda": LAM,
        "noise_floor_pts": floor,
        "sigma_margin": SIGMA,
        "threshold_source": "ACCEPTANCE.md, committed before the evaluations ran",
        "noise_floor_from": floor_src,
        "evaluator_pricing": "same_route (Model B)",
        "effort": "60000/2/32",
        "evaluator": "frozen Model B (same_route common lines)",
        "counts": s["class"].value_counts().to_dict(),
        "eligible_for_2B": cands,
        "excluded_on_performance": [],
        "eligibility_rule":
            "Every member of the frozen candidate set is eligible for the "
            "Experiment 2B joint search, including the two that are harmful "
            "alone. D20 shows a set's effect is not the sum of its members', "
            "so excluding a member on its single-candidate score would assume "
            "the composability 2B exists to test: a candidate that hurts alone "
            "can substitute for one that helps, and the search cannot discover "
            "that if the candidate is not in it. The classification below is "
            "evidence about singles and is not a filter on sets.",
        "incompatibility_rule":
            "Two splices sharing a route are structurally incompatible. "
            "apply_edits merges a splice's two routes into one synthetic route "
            "and removes both originals from the live set, so a later edit "
            "naming either raises rather than silently doing nothing. The rule "
            "is the implementation's, read off geometry.apply_edits, and is "
            "enforced on the candidate keys and never on measured "
            "performance. Sets violating it are never generated.",
        "n_incompatible_pairs": len(incompat),
        "recheck_required":
            "The two harmful candidates are classified at 60000/2/32, below "
            "L4. D19's falsification test -- re-run them at full effort and "
            "see whether they clear the floor in the other direction -- must "
            "run before either is described as harmful in a write-up. It does "
            "not gate 2B, because 2B does not exclude them either way.",
    }

    # the ordering file the measured-order ladder needs, in the shape
    # --ladder-from expects. It has to be built from Model B cells: ordering a
    # Model B ladder by Model A performance would reintroduce, as an ordering,
    # exactly the model mixing this script refuses everywhere else.
    order = s[["candidate", u]].copy()
    order.insert(0, "label", "single:" + order["candidate"])
    order.to_csv(OUT / "exp2_eval_order_modelB.csv", index=False)

    (OUT / "exp2_candidate_classes.json").write_text(
        json.dumps({"rule": rule,
                    "candidates": s[["candidate", "class", u, g,
                                     "margin_pts", "modelled_share_pct"]]
                    .to_dict("records"),
                    "incompatible_pairs": incompat}, indent=2))
    s[["candidate", "class", u, g, "margin_pts",
       "modelled_share_pct"]].to_csv(OUT / "exp2_candidate_classes.csv",
                                     index=False)

    pd.set_option("display.width", 200)
    print("=" * 92)
    print(f"EXPERIMENT 2 — candidate classification at lambda={LAM}, "
          f"noise floor {floor:.3f} pts ({SIGMA:g} sigma)")
    print("=" * 92)
    print(s[["candidate", "class", u, g, "margin_pts",
             "modelled_share_pct"]].round(4).to_string(index=False))
    print("\ncounts:", rule["counts"])
    print(f"structurally incompatible pairs: {len(incompat)}")
    for p in incompat:
        print(f"  {p['a']:24s} x {p['b']:24s} shares {p['shared_routes']}")
    print("\neligible for the 2B joint search: all "
          f"{len(cands)} — nothing excluded on performance.")
    print("artifacts:", OUT / "exp2_candidate_classes.json")
    print("           ", OUT / "exp2_eval_order_modelB.csv",
          "(measured order, for --ladder-from)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
