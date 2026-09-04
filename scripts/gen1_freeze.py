#!/usr/bin/env python3
"""Freeze Generation 1, and verify the freeze afterwards.

Gen1 is the methodology of Experiments 1, 2, 2B and 3 (METHODOLOGY.md), frozen
once those close. All four are closed, so this writes the terminal record.

What this freezes, and what it deliberately does not
----------------------------------------------------
`scripts/exp3_freeze.py --verify` asserts that the whole tree still matches the
moment of freezing, including the live `code_version()`. That check began
failing the same day it was written: `c2b2b947` added the Stage B machinery and
moved the source digest from `src-74b02d24b77f` to `src-bd82ac5a6dae`, which is
exactly what a project does after freezing a stage — it keeps working. Stage A's
*evidence* never stopped verifying; its 87 receipts and its contract digest
still check out today.

So this freeze separates the two:

* **ASSERTED** — things that must remain true forever, or the record is broken:
  contract digests, receipt counts, the digests recorded *inside* receipts, the
  content hashes of result artifacts, and the experiment tags.
* **RECORDED** — things that legitimately move as work continues: the live
  source digest, and the content of documents the project appends to
  (DISCOVERIES.md, OPERATIONS.md). A change in these is reported as
  information, never as a failure.

A freeze that fails every time someone writes a new line in OPERATIONS.md is a
freeze nobody runs, and a check nobody runs is not a check (OPERATIONS 27).

    python scripts/gen1_freeze.py --write     # check, then write the manifest
    python scripts/gen1_freeze.py --verify    # re-check a written manifest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "outputs"
MANIFEST = OUT / "GEN1_FREEZE_MANIFEST.json"

from cota_opt.exp3_cell import code_version                      # noqa: E402
from cota_opt.firewall import (EXP3_STAGE_A, EXP3_STAGE_B,       # noqa: E402
                               EXP3_STAGE_B_ESCALATED,
                               ObservationStore)

#: Result artifacts whose content must not change. Documents the project
#: appends to are deliberately absent -- see the module docstring.
ASSERTED_ARTIFACTS = [
    "outputs/CANONICAL_RESULTS.json",
    "outputs/exp3/stageA_census.json",
    "outputs/exp3/stageB_report.json",
    "outputs/exp3/escalation_manifest.json",
    "outputs/exp3/escalation_report.json",
    "outputs/exp3/d33_stageb/d33_stageb_report.json",
    "outputs/exp3/phase5b_manifest.json",
    "EXPERIMENT3_CLOSURE.md",
    "EXPERIMENT3_ROBUSTNESS.md",
    "EXPERIMENT3_PHASE5_DESIGN.md",
    "EXPERIMENT3_PHASE5B_DESIGN.md",
    "EXPERIMENT3_D33_STAGEB_DESIGN.md",
    "EXPERIMENT3_STAGE_B_PREREGISTRATION.md",
    "METHODOLOGY.md",
]

#: Recorded, not asserted: these move as work continues.
RECORDED_ARTIFACTS = ["DISCOVERIES.md", "OPERATIONS.md", "ACCEPTANCE.md"]

STORES = [("exp3_stage_a", "outputs/exp3/observations", EXP3_STAGE_A),
          ("exp3_stage_b", "outputs/exp3/observations_stageB", EXP3_STAGE_B),
          ("exp3_escalated", "outputs/exp3/observations_stageB_esc",
           EXP3_STAGE_B_ESCALATED)]


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git(*a: str) -> str:
    return subprocess.run(("git",) + a, cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()


def collect() -> dict:
    stores = {}
    for name, rel, contract in STORES:
        recs = list(ObservationStore(ROOT / rel).all())
        mine = [r for r in recs if r.spec.contract_digest == contract.digest]
        stores[name] = {
            "path": rel,
            "contract_digest": contract.digest,
            "restarts": contract.solver.restarts,
            "n_receipts": len(mine),
            "receipt_digests_sha256": hashlib.sha256(
                "".join(sorted(r.digest for r in mine)).encode()).hexdigest(),
            "code_versions": sorted({r.code_version for r in mine}),
        }
    return {
        "generation": "gen1",
        "frozen_at": subprocess.run(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"],
                                    capture_output=True, text=True).stdout.strip(),
        "definition": "METHODOLOGY.md, section 'Generation 1'",
        "experiments_closed": ["exp1", "exp2", "exp2b", "exp3"],
        "tags": {t: git("rev-parse", f"{t}^{{commit}}")
                 for t in ("exp3-frozen-v1", "exp3-final-v1") if git("tag", "-l", t)},
        "repo_revision": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "asserted": {
            "contract_digests": {
                "exp3_stage_a": EXP3_STAGE_A.digest,
                "exp3_stage_b": EXP3_STAGE_B.digest,
                "exp3_escalated": EXP3_STAGE_B_ESCALATED.digest,
            },
            "stores": stores,
            "artifact_sha256": {
                f: sha256(ROOT / f) for f in ASSERTED_ARTIFACTS
                if (ROOT / f).exists()},
        },
        "recorded": {
            "source_digest_at_freeze": code_version(),
            "source_digest_note":
                "RECORDED, NOT ASSERTED. Gen2 development moves this by "
                "definition. Gen1 results stay verifiable because every "
                "receipt carries the code_version it was produced under.",
            "artifact_sha256": {
                f: sha256(ROOT / f) for f in RECORDED_ARTIFACTS
                if (ROOT / f).exists()},
        },
    }


def do_write() -> int:
    m = collect()
    missing = [f for f in ASSERTED_ARTIFACTS if not (ROOT / f).exists()]
    if missing:
        print("REFUSING: asserted artifacts missing:", file=sys.stderr)
        for f in missing:
            print(f"    {f}", file=sys.stderr)
        return 2
    dirty = git("status", "--porcelain")
    if dirty:
        print("REFUSING: working tree is dirty. A freeze of a tree that is "
              "still moving is not a freeze.", file=sys.stderr)
        return 2
    MANIFEST.write_text(json.dumps(m, indent=2))
    print(f"GEN1 FROZEN at {m['frozen_at']}")
    print(f"  source digest (recorded) : {m['recorded']['source_digest_at_freeze']}")
    for n, s in m["asserted"]["stores"].items():
        print(f"  {n:<16} {s['n_receipts']:>4} receipts @ {s['restarts']} restarts"
              f"  {s['contract_digest']}")
    print(f"  asserted artifacts       : {len(m['asserted']['artifact_sha256'])}")
    print(f"  recorded artifacts       : {len(m['recorded']['artifact_sha256'])}")
    print(f"\nwrote {MANIFEST}")
    return 0


def do_verify() -> int:
    if not MANIFEST.exists():
        print(f"no manifest at {MANIFEST}", file=sys.stderr)
        return 2
    m = json.loads(MANIFEST.read_text())
    now = collect()
    ok = True

    def say(name, good, detail=""):
        nonlocal ok
        ok &= good
        print(f"  {name:<52} {'ok' if good else 'FAIL'}  {detail}")

    print("=" * 78)
    print(f"VERIFY GEN1  (frozen {m['frozen_at']})")
    print("=" * 78)
    print("\nASSERTED — must still be true:")
    for k, want in m["asserted"]["contract_digests"].items():
        say(f"contract digest {k}", now["asserted"]["contract_digests"][k] == want)
    for k, want in m["asserted"]["stores"].items():
        have = now["asserted"]["stores"][k]
        say(f"{k}: receipt count",
            have["n_receipts"] == want["n_receipts"],
            f"{have['n_receipts']} vs {want['n_receipts']}")
        say(f"{k}: receipt digests unchanged",
            have["receipt_digests_sha256"] == want["receipt_digests_sha256"])
        say(f"{k}: code versions in receipts",
            have["code_versions"] == want["code_versions"],
            ",".join(have["code_versions"]))
    bad = [f for f, want in m["asserted"]["artifact_sha256"].items()
           if not (ROOT / f).exists() or sha256(ROOT / f) != want]
    say(f"all {len(m['asserted']['artifact_sha256'])} asserted artifacts hash the same",
        not bad, "; ".join(bad[:4]))
    for t, want in m.get("tags", {}).items():
        say(f"tag {t} still points at the same commit",
            git("rev-parse", f"{t}^{{commit}}") == want)

    print("\nRECORDED — reported, never a failure:")
    was = m["recorded"]["source_digest_at_freeze"]
    isnow = now["recorded"]["source_digest_at_freeze"]
    print(f"  {'source digest':<52} "
          f"{'unchanged' if was == isnow else f'MOVED {was} -> {isnow}'}")
    if was != isnow:
        print("       (expected once Gen2 work begins; Gen1 receipts carry "
              "their own code_version and stay verifiable)")
    for f, want in m["recorded"]["artifact_sha256"].items():
        p = ROOT / f
        state = ("missing" if not p.exists()
                 else "unchanged" if sha256(p) == want else "appended/edited")
        print(f"  {f:<52} {state}")

    print("=" * 78)
    print("GEN1 VERIFIED" if ok else "FAILED — an asserted fact no longer holds")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    return do_write() if a.write else do_verify()


if __name__ == "__main__":
    raise SystemExit(main())
