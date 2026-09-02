#!/usr/bin/env python3
"""Generate the literal §6 escalation manifest from the frozen Stage B results.

Mechanical. Every entry is derived from `stageB_report.json` and the §6 rules
in `EXPERIMENT3_STAGE_B_PREREGISTRATION.md`; nothing here is a judgement call
and the set is not narrowed retrospectively.

§6 escalates a candidate when either:
  * it FAILS the paired criterion at 20 restarts -- |mean delta| <= 3*SD(delta);
  * its paired spread is UNSTABLE -- SD(delta) > 3x the median SD across the 39.
and additionally escalates BOTH members of any unresolved pairwise relationship
between two certified candidates.

This implementation adds one trigger the preregistration did not name because
it could not have: a candidate whose verdict depends on the sample-vs-population
SD convention, which the preregistration is silent on. Rather than settle that
convention after seeing the data, such a candidate escalates. That is strictly
more conservative -- it can only enlarge the escalation set.

Dedup is exact: a candidate appearing under several triggers appears once, with
every reason recorded.

    python scripts/exp3_escalation_manifest.py
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "outputs" / "exp3"

from cota_opt.firewall import (EXP3_STAGE_B,           # noqa: E402
                               EXP3_STAGE_B_ESCALATED)


def main() -> int:
    rep = json.loads((OUT / "stageB_report.json").read_text())
    rows = {r["state"]: r for r in rep["candidates"]}
    pw = rep["pairwise"]
    median_sd = rep["median_sd_pct"]
    certified = set(rep["certified"])

    reasons: dict[str, list[str]] = {}
    detail: dict[str, dict] = {}

    def add(state: str, why: str, **extra):
        reasons.setdefault(state, [])
        if why not in reasons[state]:
            reasons[state].append(why)
        detail.setdefault(state, {}).update(extra)

    # --- §6 trigger 1: failed the paired criterion at 20 restarts ----------
    for s, r in rows.items():
        if not r["certified"]:
            add(s, "failed the paired criterion at 20 restarts "
                   f"(|mean| {abs(r['mean_pct']):.5f}% <= 3*SD {3*r['sd_pct']:.5f}%)")

    # --- §6 trigger 2: unstable paired spread ------------------------------
    for s, r in rows.items():
        if r["sd_pct"] > 3.0 * median_sd:
            add(s, f"paired spread unstable: SD {r['sd_pct']:.6f}% > 3x median "
                   f"{median_sd:.6f}%")

    # --- §6 trigger 3: unresolved pairwise relation between certified ------
    for p in pw:
        if p.get("resolved"):
            continue
        for s in (p["a"], p["b"]):
            if s in certified:
                add(s, "unresolved pairwise relation with another certified "
                       "candidate")
                detail.setdefault(s, {}).setdefault("unresolved_with", [])
                other = p["b"] if s == p["a"] else p["a"]
                if other not in detail[s]["unresolved_with"]:
                    detail[s]["unresolved_with"].append(other)

    # --- extra, conservative: verdict depends on the SD convention ---------
    for s, r in rows.items():
        if r.get("ddof_sensitive"):
            add(s, "verdict depends on the sample-vs-population SD convention, "
                   "which the preregistration does not fix")

    entries = []
    for s in sorted(reasons, key=lambda x: rows[x]["mean_pct"]):
        r = rows[s]
        e = {
            "candidate": s,
            "trigger_reasons": reasons[s],
            "stage_b_status": "certified" if r["certified"] else "not certified",
            "stage_b_effect_pct": r["mean_pct"],
            "stage_b_sd_pct": r["sd_pct"],
            "stage_b_ratio": r["ratio"],
            "stage_b_effects_by_seed_pct": r["effects_pct"],
            "stage_b_sd_pct_ddof0": r.get("sd_pct_ddof0"),
            "ddof_sensitive": bool(r.get("ddof_sensitive")),
            "escalation_restarts": EXP3_STAGE_B_ESCALATED.solver.restarts,
            "stage_b_restarts": EXP3_STAGE_B.solver.restarts,
            "escalation_seeds": list(EXP3_STAGE_B_ESCALATED.solver.seeds),
            "escalation_contract_digest": EXP3_STAGE_B_ESCALATED.digest,
            "source_contract_digest": EXP3_STAGE_B.digest,
        }
        if "unresolved_with" in detail.get(s, {}):
            e["unresolved_comparisons"] = sorted(detail[s]["unresolved_with"])
        entries.append(e)

    counts = {
        "failed_criterion": sum(1 for s in reasons
                                if any("failed the paired" in w for w in reasons[s])),
        "unresolved_pairwise": sum(1 for s in reasons
                                   if any("unresolved pairwise" in w for w in reasons[s])),
        "unstable_spread": sum(1 for s in reasons
                               if any("unstable" in w for w in reasons[s])),
        "ddof_sensitive": sum(1 for s in reasons
                              if any("SD convention" in w for w in reasons[s])),
    }
    man = {
        "generated_from": "outputs/exp3/stageB_report.json",
        "rule": "literal section 6; not narrowed retrospectively",
        "stage_b_contract": EXP3_STAGE_B.digest,
        "escalation_contract": EXP3_STAGE_B_ESCALATED.digest,
        "escalation_effort": {
            "restarts": EXP3_STAGE_B_ESCALATED.solver.restarts,
            "stage_b_restarts": EXP3_STAGE_B.solver.restarts,
            "evaluation_ceiling": EXP3_STAGE_B_ESCALATED.solver.evaluation_ceiling,
            "candidate_width": EXP3_STAGE_B_ESCALATED.solver.candidate_width,
            "start_policy": str(EXP3_STAGE_B_ESCALATED.solver.start_policy),
            "seeds": list(EXP3_STAGE_B_ESCALATED.solver.seeds),
            "everything_else": "held fixed; the two contracts differ only in "
                               "restarts and the version label",
        },
        "median_sd_pct": median_sd,
        "n_candidates": len(entries),
        "trigger_counts_before_dedup": counts,
        "cells": (len(entries) + 1) * len(EXP3_STAGE_B_ESCALATED.solver.seeds),
        "note": "the control is escalated too: a paired statistic needs both "
                "arms at the same effort, so control cells are added and are "
                "not counted in n_candidates",
        "candidates": entries,
    }
    p = OUT / "escalation_manifest.json"
    p.write_text(json.dumps(man, indent=2))

    print(f"escalation set: {len(entries)} candidates "
          f"(+ control) x {len(EXP3_STAGE_B_ESCALATED.solver.seeds)} seeds "
          f"= {man['cells']} cells at "
          f"{EXP3_STAGE_B_ESCALATED.solver.restarts} restarts")
    print("triggers before dedup:", counts)
    print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
