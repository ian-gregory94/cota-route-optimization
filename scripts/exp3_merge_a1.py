#!/usr/bin/env python3
"""Merge Phase A1's shards into the canonical checkpoint and table.

Separate files per shard, merged deliberately, because Experiment 2B lost 57 of
240 subsets to two workers computing `index % n` over a list that was re-sorted
between their start times. Shards here partition a **canonically sorted** pool
and never write to each other's files, and this step checks the union is
complete before Phase A2 is allowed to use it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "outputs" / "exp3"


def main() -> int:
    pool = sorted(m["id"] for m in
                  json.loads((OUT / "mutation_pool.json").read_text())["mutations"])
    scores, rows = {}, []
    for p in sorted(OUT.glob("stageA_states.shard*.jsonl")):
        for line in p.read_text().splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                    scores[r["state"]] = r
                except (json.JSONDecodeError, KeyError):
                    continue
    for p in sorted(OUT.glob("stageA_rows.shard*.jsonl")):
        for line in p.read_text().splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    dest = OUT / "stageA_states.jsonl"
    with dest.open("w") as f:
        for r in scores.values():
            f.write(json.dumps(r) + "\n")
    seen, uniq = set(), []
    for r in rows:
        k = (r.get("state_key"), r.get("seed"), r.get("role"))
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    if uniq:
        pd.DataFrame(uniq).to_csv(OUT / "stageA_states.csv", index=False)
    with (OUT / "stageA_rows.jsonl").open("w") as f:
        for r in uniq:
            f.write(json.dumps(r) + "\n")

    have = {k for k in scores if k in set(pool)}
    missing = sorted(set(pool) - have)
    reps = [k for k in scores if k.startswith("<none>|rep")]
    print("=" * 78)
    print("PHASE A1 MERGE")
    print("=" * 78)
    print(f"  singles scored     {len(have)} of {len(pool)}")
    print(f"  zero-edit reps     {len(reps)}")
    print(f"  unique states      {len(scores)}")
    print(f"  rows               {len(uniq)}")
    if missing:
        print(f"  MISSING            {len(missing)}: {missing[:5]}"
              f"{'...' if len(missing) > 5 else ''}")
    (OUT / "stageA_A1_merge.json").write_text(json.dumps(
        {"singles_scored": len(have), "pool_size": len(pool),
         "replicates": len(reps), "unique_states": len(scores),
         "missing": missing, "complete": not missing}, indent=2) + "\n")
    print(f"\nartifacts: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
