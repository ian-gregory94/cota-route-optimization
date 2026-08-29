#!/usr/bin/env python3
"""Both ladder orderings, side by side, from Model B cells only.

D20's claim is that geometry edits do not compose. The strong form of it needs
two ladders — one composed in screen order, one in measured order — because a
reader shown only the screen-ordered run would reasonably conclude the ordering
was the problem. This puts them on one table.

Model B cells only. The first version of this table was assembled from cells
written by the mislabelled evaluator (ACCEPTANCE.md, *Defect: the Experiment 2
evaluator was Model A*), so it compared two Model A ladders while D20 described
them as Model B. Cells carry their pricing in the key since 2026-08-29; cells
without it are Model A by construction and are ignored here.

It also checks something the two runs make free: the measured-order run
re-derives every single-candidate cell under its own tag, at the same effort,
same seed, same network. Those must be bit-identical to the screen-order run's.
If they are not, the pipeline is not deterministic and every comparison in
Experiment 2 rests on sand.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

OUT = ROOT / "outputs"
EFFORT = "60000/2/32"
LAM = 2.0


def cells() -> dict[str, dict]:
    out = {}
    for line in (OUT / "exp2_eval.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        k = r.get("cell", "")
        if f"|same_route|{EFFORT}" in k:
            out[k] = r
    return out


def rungs(c: dict[str, dict], tag: str) -> dict[int, dict]:
    out = {}
    for k, v in c.items():
        if f"|{tag}|same_route|" not in k or " edits|" not in k:
            continue
        lab = k.split("eval|", 1)[1].split("|", 1)[0]
        if not lab.endswith("edits") or "seed" in lab:
            continue
        out[int(lab.split()[0])] = v
    return out


def determinism(c: dict[str, dict]) -> list[dict]:
    """Same candidate, same effort, same seed, two tags. Must agree exactly."""
    def singles(tag):
        out = {}
        for k, v in c.items():
            if "single:" in k and f"|{tag}|same_route|" in k:
                out[k.split("single:")[1].rsplit("|", 3)[0]] = v
        return out
    a, b = singles("s"), singles("m")
    rows = []
    for k in sorted(set(a) & set(b)):
        x, y = a[k][f"unserved_lam{LAM}"], b[k][f"unserved_lam{LAM}"]
        rows.append({"candidate": k, "screen_run": x, "measured_run": y,
                     "abs_diff": abs(x - y)})
    return rows


def main() -> int:
    c = cells()
    m, s = rungs(c, "m"), rungs(c, "s")
    # A partial ladder is worse than none: rungs 0 and 1 alone would show a
    # benefit and no sign of the reversal that arrives at 2 and 4, which is the
    # entire finding.
    want = {0, 1, 2, 4}
    if not (want <= set(m) and want <= set(s)):
        raise SystemExit(
            f"need rungs {sorted(want)} in both ladders under Model B at "
            f"{EFFORT}; have screen-order {sorted(s)} and measured-order "
            f"{sorted(m)}. Wait for exp2-ladder-B-fixed.")
    ks = sorted(want)
    rows = []
    for tag, tab in (("measured", m), ("screen", s)):
        base = tab.get(0)
        if base is None:
            raise SystemExit(f"{tag} ladder has no zero-edit rung")
        for k in ks:
            v = tab[k]
            rows.append({
                "order": tag, "n_edits": k,
                "unserved": v[f"unserved_lam{LAM}"], "gc": v[f"gc_lam{LAM}"],
                "unserved_vs_0edit_pct":
                    (v[f"unserved_lam{LAM}"] / base[f"unserved_lam{LAM}"] - 1) * 100,
                "gc_vs_0edit_pct":
                    (v[f"gc_lam{LAM}"] / base[f"gc_lam{LAM}"] - 1) * 100,
                "edits": v.get("edits", "")})
    df = pd.DataFrame(rows).sort_values(["order", "n_edits"])
    df.to_csv(OUT / "exp2_ladder_measured.csv", index=False)

    det = determinism(c)
    pd.set_option("display.width", 200)
    print("=" * 92)
    print(f"EXPERIMENT 2 — both ladder orderings, Model B, effort {EFFORT}")
    print("=" * 92)
    print(df[["order", "n_edits", "unserved_vs_0edit_pct",
              "gc_vs_0edit_pct"]].round(4).to_string(index=False))
    if det:
        d = pd.DataFrame(det)
        worst = d["abs_diff"].max()
        print(f"\ndeterminism check: {len(d)} candidates solved twice at the "
              f"same effort and seed, largest disagreement {worst:.6g}")
        if worst > 0:
            print("  NOT DETERMINISTIC — every comparison in Experiment 2 "
                  "assumes two identical solves give identical answers:")
            print(d[d.abs_diff > 0].round(6).to_string(index=False))
        else:
            print("  identical, as they must be")
    print(f"\nartifacts: {OUT / 'exp2_ladder_measured.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
