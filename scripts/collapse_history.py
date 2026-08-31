#!/usr/bin/env python3
"""Collapse background-loop commits into per-batch checkpoints.

The batch loops committed once per slice, and for a while committed their own
growing log files, so 45 substantive commits sit inside roughly 2,700. This
rebuilds the branch keeping every substantive commit individually addressable
and collapsing each *run* of consecutive chore commits into one checkpoint.

Safety, in order of how much it matters:

* It builds a NEW branch and never touches the old one. Nothing is destroyed by
  running it.
* Each new commit reuses the ORIGINAL TREE of a real commit, via
  ``git commit-tree``. The final tree is therefore identical to the original by
  construction, not by inspection — and the script verifies that anyway, and
  refuses to report success if it does not hold.
* It refuses to run while a batch loop is committing, because a branch that
  moves underneath a rewrite is how work is lost.
* Tags are reported, not moved. A tag pointing into the old history keeps
  pointing there; re-tagging is a separate, deliberate act.

    python scripts/collapse_history.py --base b014c26c --into exp3-clean
    python scripts/collapse_history.py --base b014c26c --into exp3-clean --write
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*a: str, check: bool = True) -> str:
    r = subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(a)} failed:\n{r.stderr}")
    return r.stdout.strip()


def is_chore(subject: str) -> bool:
    return subject.startswith("chore:")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--branch", default="exp3")
    ap.add_argument("--into", default="exp3-clean")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    # The refusal applies to --write. A dry run reads and prints; it cannot
    # lose anything, and being able to inspect the plan while a batch is still
    # going is worth more than the symmetry.
    if args.write:
        running = subprocess.run(
            ["bash", "-c", "ps -o args= -e | grep -c '[e]xp3_.*loop.sh' || true"],
            capture_output=True, text=True).stdout.strip()
        if running not in ("", "0"):
            raise SystemExit(
                f"{running} batch loop(s) still committing. A branch that "
                f"moves underneath a rewrite is how work is lost. Stop them "
                f"first.")
        if git("status", "--porcelain"):
            raise SystemExit("working tree is dirty; commit or stash first")

    log = git("log", "--reverse", "--format=%H%x00%s", f"{args.base}..{args.branch}")
    commits = [tuple(l.split("\0", 1)) for l in log.splitlines() if l]
    if not commits:
        raise SystemExit("nothing to collapse")

    # Group: each substantive commit is its own group; consecutive chores merge.
    groups: list[tuple[str, list[tuple[str, str]]]] = []
    for sha, subj in commits:
        if is_chore(subj) and groups and groups[-1][0] == "chore":
            groups[-1][1].append((sha, subj))
        else:
            groups.append(("chore" if is_chore(subj) else "keep", [(sha, subj)]))

    n_chore = sum(len(g) for k, g in groups if k == "chore")
    n_keep = sum(len(g) for k, g in groups if k == "keep")
    print(f"{len(commits)} commits: {n_keep} substantive, {n_chore} chore")
    print(f"collapsing into {len(groups)} commits "
          f"({sum(1 for k, _ in groups if k == 'chore')} checkpoints)\n")

    for kind, g in groups:
        if kind == "keep":
            print(f"  keep       {g[0][0][:9]}  {g[0][1][:64]}")
        else:
            print(f"  checkpoint {g[-1][0][:9]}  {len(g):4d} commits -> "
                  f"{g[-1][1][:52]}")

    if not args.write:
        print("\n(re-run with --write to build the branch)")
        return 0

    prev = git("rev-parse", args.base)
    for kind, g in groups:
        sha = g[-1][0]
        tree = git("rev-parse", f"{sha}^{{tree}}")
        if kind == "keep":
            msg = git("log", "-1", "--format=%B", sha)
        else:
            first, last = g[0][1], g[-1][1]
            msg = (f"chore: batch checkpoint ({len(g)} slices)\n\n"
                   f"Collapsed from {len(g)} consecutive loop commits, from\n"
                   f"  {first}\n"
                   f"to\n"
                   f"  {last}\n\n"
                   f"The tree is the last of the run, unchanged. Original "
                   f"commits {g[0][0][:9]}..{g[-1][0][:9]} in the pre-collapse "
                   f"history.\n\n"
                   f"Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>\n")
        prev = git("commit-tree", tree, "-p", prev, "-m", msg)

    git("branch", "-f", args.into, prev)
    diff = git("diff", "--stat", args.branch, args.into, check=False)
    print(f"\nbuilt {args.into} at {prev[:9]}")
    if diff:
        print("REFUSED TO CLAIM SUCCESS — the trees differ:")
        print(diff[:2000])
        return 2
    print(f"tree identical to {args.branch}: verified")
    tags = git("tag", "--points-at", args.base, check=False)
    print(f"\ntags at base: {tags or '(none)'}")
    print("Tags elsewhere in the old history still point there; re-tagging is "
          "a separate deliberate act.")
    print(f"\nOld branch {args.branch} is untouched. Compare, then move it "
          f"only when you are satisfied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
