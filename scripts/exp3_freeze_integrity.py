#!/usr/bin/env python3
"""Phase 9 — the integrity suite the Experiment 3 freeze rests on.

Re-runnable. Every check reads the observation stores rather than any report,
because a report is something the pipeline said about the work and a receipt is
the work. Exits non-zero if any check fails.

    python scripts/exp3_freeze_integrity.py
"""
from __future__ import annotations

import collections
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "outputs" / "exp3"

from cota_opt.firewall import (EXP3_STAGE_B as B,               # noqa: E402
                               EXP3_STAGE_B_ESCALATED as E,
                               ObservationStore)

NULL = "<none>"


def main() -> int:
    frozen = (OUT / "EVAL_PATH_FROZEN").read_text().strip()
    fails: list[str] = []

    def chk(name: str, ok: bool, detail: str = "") -> None:
        if not ok:
            fails.append(name)
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<52} {detail}")

    for label, d, contract, n in (("Stage B", "observations_stageB", B, 200),
                                  ("escalated", "observations_stageB_esc", E, 170)):
        recs = list(ObservationStore(OUT / d).all())
        ok = [r for r in recs
              if r.spec.contract_digest == contract.digest and r.code_version == frozen]
        print(f"\n--- {label} store ({contract.digest}) ---")
        chk(f"{label}: cell count", len(ok) == n, f"{len(ok)}/{n}")
        chk(f"{label}: single contract digest",
            len({r.spec.contract_digest for r in recs}) == 1,
            str({r.spec.contract_digest for r in recs}))
        chk(f"{label}: single code version",
            len({r.code_version for r in recs}) == 1,
            str({r.code_version for r in recs}))
        chk(f"{label}: all on EVAL_PATH_FROZEN",
            all(r.code_version == frozen for r in recs), frozen)
        chk(f"{label}: no foreign-contract receipts",
            not [r for r in recs if r.spec.contract_digest != contract.digest], "0 found")
        rs = collections.Counter(getattr(r, "restarts_completed", None) for r in ok)
        chk(f"{label}: restarts_completed uniform",
            set(rs) == {contract.solver.restarts}, str(dict(rs)))
        keys = [(r.spec.state_key or NULL, r.spec.seed) for r in ok]
        chk(f"{label}: no duplicate (state,seed)",
            len(keys) == len(set(keys)), f"{len(keys) - len(set(keys))} dupes")

    a = {r.digest for r in ObservationStore(OUT / "observations_stageB").all()}
    b = {r.digest for r in ObservationStore(OUT / "observations_stageB_esc").all()}
    print("\n--- cross-store: the two regimes must not mix ---")
    chk("no receipt appears in both stores", not (a & b), f"{len(a & b)} shared")
    chk("Stage B and escalated contracts differ", B.digest != E.digest,
        f"{B.digest} vs {E.digest}")
    chk("same five seeds in both regimes",
        list(B.solver.seeds) == list(E.solver.seeds), str(list(E.solver.seeds)))

    man = json.loads((OUT / "escalation_manifest.json").read_text())
    exp = {(s, sd) for s in [NULL] + [c["candidate"] for c in man["candidates"]]
           for sd in E.solver.seeds}
    got = {(r.spec.state_key or NULL, r.spec.seed)
           for r in ObservationStore(OUT / "observations_stageB_esc").all()}
    print("\n--- frozen manifest coverage ---")
    chk("escalated keys == frozen manifest exactly", got == exp,
        f"{len(got - exp)} unexpected, {len(exp - got)} missing")
    p5b = {c["candidate"] for c in
           json.loads((OUT / "phase5b_manifest.json").read_text())["candidates"]}
    chk("zero Phase 5b states in the store",
        not ({s for s, _ in got} & p5b),
        f"{len({s for s, _ in got} & p5b)} present")

    print("\n--- firewall ---")
    r = subprocess.run(
        "grep -c REFUSED outputs/exp3/*.run.log 2>/dev/null | "
        "awk -F: '{s+=$2} END{print s+0}'",
        shell=True, capture_output=True, text=True, cwd=ROOT)
    chk("zero firewall refusals across all batches", r.stdout.strip() == "0",
        r.stdout.strip())

    print("\n" + "=" * 62)
    print("ALL INTEGRITY CHECKS PASS" if not fails
          else f"{len(fails)} FAILED: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
