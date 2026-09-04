#!/usr/bin/env python3
"""Generate the Phase 5b manifest: every promoted state with no escalated cell.

Mechanical. The set is defined by a property of the MEASUREMENT -- absence of a
40-restart cell -- not by any property of the result, so it is fully determined
before a single Phase 5b number exists. See EXPERIMENT3_PHASE5B_DESIGN.md.

Does not read, modify or depend on any Phase 5b result, and does not touch the
frozen section 6 manifest.

    python scripts/exp3_phase5b_manifest.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "outputs" / "exp3"

from cota_opt.firewall import (EXP3_STAGE_B,               # noqa: E402
                               EXP3_STAGE_B_ESCALATED, ObservationStore)

NULL = "<none>"


def main() -> int:
    census = json.loads((OUT / "stageA_census.json").read_text())
    promoted = sorted(r["state"] for r in census["states"] if r["effect_pct"] < 0)

    # what already has an escalated measurement, read from the STORE not a report
    frozen = (OUT / "EVAL_PATH_FROZEN").read_text().strip()
    store = ObservationStore(OUT / "observations_stageB_esc")
    have: set[str] = set()
    for r in store.all():
        if (r.spec.contract_digest == EXP3_STAGE_B_ESCALATED.digest
                and r.code_version == frozen):
            have.add(r.spec.state_key or NULL)

    missing = [s for s in promoted if s not in have]
    if NULL not in have:
        raise SystemExit("the control has no escalated cells; stop -- a paired "
                         "statistic needs both arms at the same effort")

    sb = {r["state"]: r for r in
          json.loads((OUT / "stageB_report.json").read_text())["candidates"]}
    seeds = list(EXP3_STAGE_B_ESCALATED.solver.seeds)

    entries = []
    for s in sorted(missing, key=lambda x: sb[x]["mean_pct"]):
        r = sb[s]
        entries.append({
            "candidate": s,
            "reason": "promoted, and has no cell at the escalation effort",
            "stage_b_status": "certified" if r["certified"] else "not certified",
            "stage_b_effect_pct": r["mean_pct"],
            "stage_b_sd_pct": r["sd_pct"],
            "stage_b_ratio": r["ratio"],
            "stage_b_effects_by_seed_pct": r["effects_pct"],
            "escalation_restarts": EXP3_STAGE_B_ESCALATED.solver.restarts,
            "stage_b_restarts": EXP3_STAGE_B.solver.restarts,
            "escalation_seeds": seeds,
            "escalation_contract_digest": EXP3_STAGE_B_ESCALATED.digest,
        })

    man = {
        "phase": "5b",
        "rule": "escalate every promoted candidate with no measurement at the "
                "escalation effort, so the whole certified comparison set sits "
                "in one solver-effort regime",
        "rule_is_over": "a property of the measurement, not of the result",
        "generated_from": ["outputs/exp3/stageA_census.json",
                           "outputs/exp3/observations_stageB_esc (store)"],
        "does_not_modify": "outputs/exp3/escalation_manifest.json",
        "escalation_contract": EXP3_STAGE_B_ESCALATED.digest,
        "stage_b_contract": EXP3_STAGE_B.digest,
        "eval_path_frozen": frozen,
        "promoted_total": len(promoted),
        "already_escalated": len(have) - 1,          # minus the control
        "n_candidates": len(entries),
        "control_cells_added": 0,
        "control_note": "the control already has its escalated cells inside the "
                        "existing 170; none are added and none are re-run",
        "cells": len(entries) * len(seeds),
        "store_total_after": (len(promoted) + 1) * len(seeds),
        "candidates": entries,
    }
    p = OUT / "phase5b_manifest.json"
    p.write_text(json.dumps(man, indent=2))

    print(f"promoted {len(promoted)} | already escalated {len(have)-1} "
          f"(+ control) | missing {len(entries)}")
    for e in entries:
        print(f"  {e['candidate']:<44} stage B {e['stage_b_effect_pct']:+.5f}%")
    print(f"\n{len(entries)} x {len(seeds)} seeds = {man['cells']} cells at "
          f"{EXP3_STAGE_B_ESCALATED.solver.restarts} restarts")
    print(f"escalated store after completion: {man['store_total_after']} cells")
    print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
