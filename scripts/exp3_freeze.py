#!/usr/bin/env python3
"""Freeze Experiment 3, or refuse and say why.

Every precondition is checked here rather than remembered. A freeze that can be
declared while an input is still moving is not a freeze.

It also records the final source and artifact digests **independently of git**,
into `outputs/exp3/FREEZE_MANIFEST.json`, because the history is going to be
collapsed afterwards and a manifest that lives only inside the thing being
rewritten cannot verify the rewrite. The manifest lists content hashes, not
commit ids: a squash changes every commit id and must change no content.

    python scripts/exp3_freeze.py            # check only
    python scripts/exp3_freeze.py --write    # check, then write the manifest
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

from cota_opt.exp3_cell import code_version, repo_revision   # noqa: E402
from cota_opt.firewall import (EXP3_STAGE_A, Inadmissible,   # noqa: E402
                               ObservationStore, admit, compare)

OUT = ROOT / "outputs" / "exp3"

#: Artifacts whose content defines the frozen record. Hashed, not committed --
#: the point is to be able to verify them after a history rewrite.
ARTIFACTS = [
    "outputs/exp3/stageA_census.json",
    "outputs/exp3/stageA_rescored.jsonl",
    "outputs/exp3/gap_benchmark.jsonl",
    "outputs/exp3/gap_report.json",
    "outputs/exp3/a2_recomputed.json",
    "outputs/exp3/validation_result.json",
    "outputs/exp3/validation_fallback.jsonl",
    "outputs/exp3/rescore_set.LOCKED.json",
    "outputs/exp3/mutation_pool.json",
    "outputs/exp3/pinned_envelope.json",
    "outputs/exp2b_confirmation.json",
    "outputs/exp2b_certification.json",
    "outputs/exp2b_certification.superseded.json",
    "decisions/2026-08-31-replicate-spread-is-not-a-materiality-floor.md",
    "DISCOVERIES.md", "ACCEPTANCE.md", "OPERATIONS.md", "METHODOLOGY.md",
    "ARCHITECTURE_FIREWALL.md", "EXPERIMENT4_DESIGN.md",
]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def say(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  {label:52s} {'ok' if ok else 'FAIL'}{'  ' + detail if detail else ''}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--tag", default="exp3-frozen-v1")
    args = ap.parse_args()
    ok = True
    print("=" * 78)
    print("FREEZE EXPERIMENT 3")
    print("=" * 78)

    # --- 1. the re-score is complete, under one source revision -----------
    frozen_f = OUT / "EVAL_PATH_FROZEN"
    frozen = frozen_f.read_text().strip() if frozen_f.exists() else None
    now = code_version()
    ok &= say("evaluation path matches the frozen digest",
              frozen is None or frozen == now, f"{now}")

    wanted = [l.strip() for l in (OUT / "rescore_needed.txt").read_text()
              .splitlines() if l.strip()]
    store = ObservationStore(OUT / "observations")
    receipts = [r for r in store.all()
                if r.spec.contract_digest == EXP3_STAGE_A.digest
                and (frozen is None or r.code_version == frozen)]
    base = EXP3_STAGE_A.solver.seeds[0]
    keys = {r.spec.state_key for r in receipts}
    singles = {w for w in wanted if not w.startswith("<none>")}
    missing = sorted(singles - keys)
    ok &= say(f"all {len(singles)} single states have a receipt",
              not missing, f"{len(missing)} missing" if missing else "")
    if missing:
        for m in missing[:5]:
            print(f"      missing: {m}")

    # `<none>` and `<none>|rep0` are the SAME cell -- same state, same base
    # seed, therefore one receipt. Three distinct zero-edit receipts is the
    # complete set: base, base+1, base+2.
    reps = sorted({r.spec.seed for r in receipts if r.spec.state_key == "<none>"})
    ok &= say("control at all three replicate seeds",
              reps == [base, base + 1, base + 2],
              f"seeds {reps}")

    # --- 2. every receipt is admissible -----------------------------------
    bad = [(r.spec.state_key, admit(r, EXP3_STAGE_A))
           for r in receipts]
    bad = [(k, v) for k, v in bad if isinstance(v, Inadmissible)]
    ok &= say("every receipt is admissible", not bad,
              f"{len(bad)} inadmissible" if bad else "")
    for k, v in bad[:3]:
        print(f"      {k}: {'; '.join(v.reasons)[:90]}")

    # --- 3. the census compares cleanly -----------------------------------
    control = next((r for r in receipts if r.spec.state_key == "<none>"
                    and r.spec.seed == base), None)
    ok &= say("a control receipt exists at the base seed", control is not None)
    refused = []
    if control is not None:
        at_base = {r.spec.state_key: r for r in receipts
                   if r.spec.seed == base and r.spec.state_key != "<none>"}
        for k, r in at_base.items():
            if not compare(control, r, EXP3_STAGE_A):
                refused.append(k)
        ok &= say(f"all {len(at_base)} comparisons admitted", not refused,
                  f"{len(refused)} refused" if refused else "")
        for k in refused[:3]:
            print(f"      refused: {k}")

    # --- 4. the supporting measurements are complete ----------------------
    gap = OUT / "gap_benchmark.jsonl"
    n_gap = len([l for l in gap.read_text().splitlines() if l.strip()]) if gap.exists() else 0
    ok &= say("optimization-gap benchmark complete (75 cells)", n_gap >= 75,
              f"{n_gap} cells")
    conf = ROOT / "outputs" / "exp2b_confirmation.json"
    passed = False
    if conf.exists():
        d = json.loads(conf.read_text())
        passed = d.get("measurable") is False
    ok &= say("Experiment 2B confirmed NULL under matched starts", passed)

    # --- 5. the tree and the suite ----------------------------------------
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip()
    ok &= say("working tree clean", not dirty,
              f"{len(dirty.splitlines())} entries" if dirty else "")
    running = subprocess.run(["bash", "-c",
                              "ps -o args= -e | grep -c '[e]xp3_.*_loop.sh' || true"],
                             capture_output=True, text=True).stdout.strip()
    ok &= say("no batch loop still running", running in ("", "0"), running)

    print()
    if not ok:
        print("REFUSED — Experiment 3 is not frozen.")
        return 1
    print("All preconditions hold.")

    manifest = {
        "frozen_at": subprocess.run(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"],
                                    capture_output=True, text=True).stdout.strip(),
        "methodology_generation": EXP3_STAGE_A.methodology_generation,
        "source_digest": now,
        "contract_digest": EXP3_STAGE_A.digest,
        "repo_revision_at_freeze": repo_revision(),
        "n_receipts": len(receipts),
        "receipt_digests": sorted(r.digest for r in receipts),
        "spec_digests": sorted(r.spec.digest for r in receipts),
        "artifact_sha256": {a: sha256(ROOT / a) for a in ARTIFACTS
                            if (ROOT / a).exists()},
        "note": "Content hashes, not commit ids. The history is collapsed after "
                "this freeze, which changes every commit id and must change no "
                "content. Verify a rewrite against this file.",
    }
    if args.write:
        (OUT / "FREEZE_MANIFEST.json").write_text(
            json.dumps(manifest, indent=2) + "\n")
        print(f"wrote {OUT / 'FREEZE_MANIFEST.json'}")
        print(f"  source digest   {now}")
        print(f"  contract digest {EXP3_STAGE_A.digest}")
        print(f"  {len(receipts)} receipts, "
              f"{len(manifest['artifact_sha256'])} artifacts hashed")
        print(f"\nNow: commit the manifest, then tag {args.tag}.")
    else:
        print("(re-run with --write to record the manifest)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
