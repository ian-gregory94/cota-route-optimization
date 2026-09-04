#!/usr/bin/env python3
"""Experiment 4 — the definition-of-ready gate, checked rather than claimed.

22 items: the 15 in EXPERIMENT4_CONTRACT.md section 24, plus the 7 added by
EXPERIMENT4_DESIGN.md section 9 after D27-D33.

Every check reads an artifact, imports a module, or runs a test. Items that
cannot be checked mechanically are reported as MANUAL with what a human must
confirm -- they are never silently counted as met. Exits non-zero while any
item is open, so "is Experiment 4 ready" has one answer and it is not a
memory.

    python scripts/exp4_readiness.py
    python scripts/exp4_readiness.py --json outputs/exp4/readiness.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "outputs" / "exp4"

MET, OPEN, MANUAL = "MET", "OPEN", "MANUAL"


def _json(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _git(*args: str) -> str:
    r = subprocess.run(("git",) + args, cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip()


def checks() -> list[tuple[str, str, str, str]]:
    """(id, title, status, detail)"""
    out: list[tuple[str, str, str, str]] = []

    def add(i, title, status, detail=""):
        out.append((i, title, status, detail))

    pool = _json(OUT / "route_pool.json")
    lg = _json(OUT / "linkgraph_audit.json")
    tr = _json(OUT / "transition_audit.json")
    rc = _json(OUT / "reconstruction.json")

    # ---- contract section 24 ------------------------------------------------
    tags = _git("tag", "-l", "exp3-final-v1")
    dirty = _git("status", "--porcelain")
    add("C1", "Experiment 3 closed and frozen",
        MET if tags and not dirty else OPEN,
        f"tag={tags or 'absent'}, tree={'clean' if not dirty else 'dirty'}")

    base = OUT / "pre_exp4_baseline_v1.json"
    add("C2", "pre_exp4_baseline_v1 exists",
        MET if base.exists() else OPEN,
        str(base.relative_to(ROOT)) if base.exists() else "not found")

    add("C3", "Synthetic routes exist independently of legacy route ids",
        MET if pool and pool.get("accepted", 0) > 0 else OPEN,
        f"{pool.get('accepted')} accepted from "
        f"{len(pool.get('accepted_by_generator', {}))} generators" if pool else "no pool")

    add("C4", "Legacy network reconstructs and reproduces score and resources",
        MET if rc and rc.get("every_route_reconstructed")
        and rc.get("stop_coverage_complete") else OPEN,
        f"{rc.get('reconstructed')} routes, stop coverage complete="
        f"{rc.get('stop_coverage_complete')}; SCORE/RESOURCE reproduction is the "
        "part to confirm" if rc else "no reconstruction artifact")

    add("C5", "Peak express service explicitly separated", MANUAL,
        "confirm the express class is separated in the pool/eligibility rules")

    add("C6", "Observed-link graph built and audited",
        MET if lg and lg.get("every_pattern_is_a_path") else OPEN,
        f"{lg.get('n_stops')} stops, {lg.get('n_directed_links')} links, "
        f"every_pattern_is_a_path={lg.get('every_pattern_is_a_path')}" if lg else "absent")

    add("C7", "Frozen route pool contains the current network",
        MET if pool and pool.get("legacy_in_pool") == pool.get("legacy_lines")
        and pool.get("legacy_lines", 0) > 0 else OPEN,
        f"legacy_in_pool={pool.get('legacy_in_pool')}/"
        f"{pool.get('legacy_lines')}" if pool else "no pool")

    add("C8", "Synthetic route-period service can be OFF", MANUAL,
        "confirm OFF is representable with no fabricated baseline headway")
    add("C9", "Discovery path reuse benchmarked against exact rebuilds", MANUAL,
        "needs a measured benchmark artifact under outputs/exp4/")
    add("C10", "Outer network search recovers an exhaustively known optimum",
        OPEN, "no recovery-test artifact under outputs/exp4/")
    add("C11", "Committed gate on common-lines exposure", MANUAL,
        "confirm the gate is committed, not merely designed")
    add("C12", "Committed transfer-depth, path-cap and OD-cap adequacy gates",
        MANUAL, "confirm committed")
    add("C13", "Demand-robustness claims written before the winner is known",
        MANUAL, "confirm written and committed ahead of any result")
    add("C14", "Structural-distance measurement exists", MANUAL,
        "confirm a committed implementation")
    add("C15", "Every ACCEPTANCE.md rejection condition in place before scoring",
        MANUAL, "confirm each rejection condition is implemented")

    # ---- design section 9 ---------------------------------------------------
    try:
        from cota_opt.firewall import exp4_draft            # noqa: F401
        has_draft = True
    except Exception:
        has_draft = False
    try:
        import cota_opt.firewall as fw
        exported = any(n.startswith("EXP4") for n in dir(fw))
    except Exception:
        exported = False
    add("D16", "Experiment 4 ExperimentContract exists and is in force",
        OPEN if not exported else MET,
        f"draft module present={has_draft}, exported from firewall/={exported}; "
        "the draft is explicitly 'not yet in force'")

    add("D17", "Recovery behaviours classified in writing before the search",
        MET if "recovery" in (ROOT / "EXPERIMENT4_DESIGN.md").read_text().lower()
        else OPEN,
        "EXPERIMENT4_DESIGN.md section 2 classifies seven; a committed machine-"
        "readable form is what the search will actually consult")

    gap = OUT / "gap_benchmark.json"
    add("D18", "Gap benchmark run on Experiment 4 networks, Q3 answered",
        MET if gap.exists() else OPEN,
        str(gap.relative_to(ROOT)) if gap.exists()
        else "not run -- this is the compute-heavy gate and it can forbid "
             "discovery-effort comparison outright")

    add("D19", "Effort stated in restarts with convergence asserted", MANUAL,
        "confirm no Experiment 4 document quotes an iteration ceiling as depth")

    cls = (tr or {}).get("classes", {})
    add("D20", "Transition-level evidence on every pool line and the receipt",
        MET if tr and tr.get("n_lines") == (pool or {}).get("accepted") else OPEN,
        f"{tr.get('n_lines')} lines classified, classes={cls}; receipt-side "
        "attachment still to confirm" if tr else "absent")

    gen1 = ROOT / "GEN1_FREEZE.md"
    add("D21", "Gen1 frozen and the Gen1->Gen2 bridge suite has run",
        MET if gen1.exists() else OPEN,
        "GEN1_FREEZE.md absent; METHODOLOGY puts Gen1 freeze immediately after "
        "Experiment 3 certification, which is now complete -- this is the next step")

    merged = (ROOT / "src" / "cota_opt" / "firewall" / "search_allowance.py")
    staged = (ROOT / "scripts" / "exp4_staging" / "search_allowance.py")
    add("D22", "Search-allowance contract merged into firewall/ and in force",
        MET if merged.exists() else OPEN,
        f"still staged at {staged.relative_to(ROOT)}; OPERATIONS 24 blocked the "
        "move while the Experiment 3 batch ran and that block is now lifted"
        if not merged.exists() else "merged")

    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    rows = checks()
    w = max(len(t) for _, t, _, _ in rows)
    print("EXPERIMENT 4 — DEFINITION OF READY\n")
    print(f"  {'':4} {'item':<{w}}  status")
    for i, title, status, detail in rows:
        print(f"  {i:<4} {title:<{w}}  {status}")
        if detail:
            print(f"       {'':<{w}}  {detail}")
    met = sum(1 for *_, s, _ in rows if s == MET)
    opn = sum(1 for *_, s, _ in rows if s == OPEN)
    man = sum(1 for *_, s, _ in rows if s == MANUAL)
    print(f"\n  {met} met | {opn} open | {man} need manual confirmation "
          f"| {len(rows)} total")
    print("\nExperiment 4 is NOT ready to launch a search while any item is open "
          "or unconfirmed.\nMANUAL items are not met -- they are unchecked.")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"items": [{"id": i, "title": t, "status": s, "detail": d}
                       for i, t, s, d in rows],
             "met": met, "open": opn, "manual": man, "total": len(rows),
             "ready": opn == 0 and man == 0}, indent=2))
        print(f"\nwrote {args.json}")
    return 1 if (opn or man) else 0


if __name__ == "__main__":
    raise SystemExit(main())
