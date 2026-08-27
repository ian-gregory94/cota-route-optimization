#!/usr/bin/env python3
"""Does the Experiment 2 candidate ranking depend on the waiting model?

The screen was run under Model A. Model B cannot be run here -- its multiplier
depends on the boarding stop, the alighting stop and their order, so it is a
property of a leg, and the screen prices straight out of RAPTOR's labels where
waiting is fixed per pattern before the alighting stop is known.

So the screen is bracketed. Pricing every pattern at its route's whole
frequency is a strict lower bound on any Model B path cost; Model A is the
upper end. Any real Model B ranking lies between them, and this compares the
two ends.

Thresholds were committed to ACCEPTANCE.md before the second screen ran:
Spearman >= 0.80 AND top-10 overlap >= 7/10 keeps the Model A shortlist as
triage; 0.50-0.80 or 4-6/10 means re-derive from the intersection; below that
the screen is not measuring a model-independent property. The worse bound
decides.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

log = logging.getLogger("exp2compare")
OUT = ROOT / "outputs"

RHO_KEEP, RHO_FLOOR = 0.80, 0.50
OVERLAP_KEEP, OVERLAP_FLOOR = 7, 3
TOP_N = 10


def _rank(df: pd.DataFrame, metric: str) -> pd.Series:
    """Rank candidates best-first on the screening metric.

    Lower ``unserved_change_pct`` is better; ties break on generalized cost, so
    the ordering is total and the two screens are compared like for like.
    """
    d = df.sort_values([metric, "gc_change_pct"], kind="mergesort")
    return pd.Series(np.arange(1, len(d) + 1), index=d["key"].to_numpy())


def spearman(a: pd.Series, b: pd.Series) -> float:
    keys = sorted(set(a.index) & set(b.index))
    if len(keys) < 3:
        return float("nan")
    x = np.array([a[k] for k in keys], float)
    y = np.array([b[k] for k in keys], float)
    x = (x - x.mean()) / (x.std() or 1.0)
    y = (y - y.mean()) / (y.std() or 1.0)
    return float((x * y).mean())


def verdict(rho: float, overlap: int) -> tuple[str, str]:
    if not np.isfinite(rho):
        return "insufficient", "too few candidates scored under both models"
    if rho >= RHO_KEEP and overlap >= OVERLAP_KEEP:
        return ("stable",
                f"Spearman {rho:.3f} and {overlap}/{TOP_N} of the top ten "
                "survive both ends of the bracket, so the ranking does not "
                "depend on the waiting model and the Model A shortlist stands "
                "as triage")
    if rho < RHO_FLOOR or overlap <= OVERLAP_FLOOR:
        return ("unusable",
                f"Spearman {rho:.3f} with {overlap}/{TOP_N} top-ten overlap: "
                "the screen is not measuring a model-independent property, so "
                "no candidate may be promoted on screening evidence alone")
    return ("model_sensitive",
            f"Spearman {rho:.3f} with {overlap}/{TOP_N} top-ten overlap: the "
            "ranking moves with the waiting model, so the shortlist must be "
            "re-derived from the intersection of both ends and named as such")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", type=str, default="exp2_screen.csv",
                    help="Model A screen (pattern pricing)")
    ap.add_argument("--b", type=str, default="exp2_screen_bound.csv",
                    help="lower-bound screen (route-level pricing)")
    ap.add_argument("--metric", type=str, default="unserved_change_pct")
    ap.add_argument("--out", type=str, default="exp2_bracket")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    pa, pb = OUT / args.a, OUT / args.b
    for p in (pa, pb):
        if not p.exists():
            log.error("missing %s", p)
            return 2
    A = pd.read_csv(pa).dropna(subset=[args.metric])
    B = pd.read_csv(pb).dropna(subset=[args.metric])
    log.info("%d candidates under pattern pricing, %d under route-level",
             len(A), len(B))

    ra, rb = _rank(A, args.metric), _rank(B, args.metric)
    rho = spearman(ra, rb)
    top_a = set(ra.sort_values().index[:TOP_N])
    top_b = set(rb.sort_values().index[:TOP_N])
    overlap = len(top_a & top_b)
    label, why = verdict(rho, overlap)

    keys = sorted(set(ra.index) & set(rb.index))
    m = pd.DataFrame({
        "key": keys,
        "rank_pattern": [int(ra[k]) for k in keys],
        "rank_route": [int(rb[k]) for k in keys],
    })
    m["rank_move"] = m["rank_route"] - m["rank_pattern"]
    m = m.merge(A[["key", args.metric, "gc_change_pct", "kind"]], on="key",
                how="left").rename(columns={args.metric: f"{args.metric}_pattern",
                                            "gc_change_pct": "gc_pattern"})
    m = m.merge(B[["key", args.metric, "gc_change_pct"]], on="key", how="left",
                suffixes=("", "_route")).rename(
        columns={args.metric: f"{args.metric}_route",
                 "gc_change_pct": "gc_route"})
    m["in_top10_pattern"] = m["key"].isin(top_a)
    m["in_top10_route"] = m["key"].isin(top_b)
    m = m.sort_values("rank_pattern", ignore_index=True)
    m.to_csv(OUT / f"{args.out}.csv", index=False)

    # per-kind: a ranking stable overall can still be stable WITHIN splices and
    # unstable across kinds, and that would change which candidates are safe to
    # promote. Aggregate agreement is not per-kind agreement.
    by_kind = []
    for kind, g in m.groupby("kind", dropna=False):
        sub_a = ra[ra.index.isin(g["key"])]
        sub_b = rb[rb.index.isin(g["key"])]
        r = spearman(sub_a, sub_b)
        by_kind.append({
            "kind": kind, "n": int(len(g)),
            "spearman_within_kind": r,
            "mean_rank_pattern": float(g["rank_pattern"].mean()),
            "mean_rank_route": float(g["rank_route"].mean()),
            "mean_rank_move": float(g["rank_move"].mean()),
            "worst_rank_move": int(g["rank_move"].abs().max()),
            "in_top10_pattern": int(g["in_top10_pattern"].sum()),
            "in_top10_route": int(g["in_top10_route"].sum()),
        })
    bk = pd.DataFrame(by_kind).sort_values("n", ascending=False, ignore_index=True)
    bk.to_csv(OUT / f"{args.out}_by_kind.csv", index=False)

    out = {"n_compared": len(keys), "metric": args.metric,
           "by_kind": by_kind,
           "spearman": rho, "top_n": TOP_N, "top_n_overlap": overlap,
           "thresholds": {"rho_keep": RHO_KEEP, "rho_floor": RHO_FLOOR,
                          "overlap_keep": OVERLAP_KEEP,
                          "overlap_floor": OVERLAP_FLOOR,
                          "committed": "ACCEPTANCE.md, before the second screen ran"},
           "verdict": label, "explanation": why,
           "kept_in_both_top10": sorted(top_a & top_b),
           "top10_pattern_only": sorted(top_a - top_b),
           "top10_route_only": sorted(top_b - top_a),
           "largest_rank_moves": m.reindex(
               m["rank_move"].abs().sort_values(ascending=False).index
           ).head(8)[["key", "rank_pattern", "rank_route", "rank_move"]]
           .to_dict("records"),
           "note": ("a screen ranks candidates and cannot size them: frequency "
                    "is held fixed, so no screen number is an Experiment 2 "
                    "result")}
    (OUT / f"{args.out}.json").write_text(json.dumps(out, indent=2, default=str))

    print("\n" + "=" * 92)
    print("EXPERIMENT 2 SCREEN — bracketed between Model A and the Model B lower bound")
    print("=" * 92)
    print(f"  candidates compared        {len(keys)}")
    print(f"  Spearman rank correlation  {rho:.4f}   (keep >= {RHO_KEEP})")
    print(f"  top-{TOP_N} overlap             {overlap}/{TOP_N}      (keep >= {OVERLAP_KEEP})")
    print(f"\n  VERDICT: {label.upper()}\n  {why}")
    print(f"\n  in the top ten under both ({len(top_a & top_b)}):")
    for k in sorted(top_a & top_b):
        print(f"    {k}")
    if top_a - top_b:
        print(f"  top ten under Model A only:")
        for k in sorted(top_a - top_b):
            print(f"    {k}")
    if top_b - top_a:
        print(f"  top ten under the bound only:")
        for k in sorted(top_b - top_a):
            print(f"    {k}")
    print("\n  by edit kind (a stable total can hide an unstable kind):")
    print(bk.round(3).to_string(index=False))
    print("\n  largest rank moves:")
    print(m.reindex(m["rank_move"].abs().sort_values(ascending=False).index)
          .head(8)[["key", "rank_pattern", "rank_route", "rank_move"]]
          .to_string(index=False))
    print("\n  a screen ranks candidates and cannot size them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
