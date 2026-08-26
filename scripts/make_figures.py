#!/usr/bin/env python3
"""Render every report figure from whatever results exist on disk.

Reads only CSVs and JSON from ``outputs/`` -- never the harness -- so it is
cheap enough to run repeatedly while the long jobs hold the machine, and safe
to run before they finish. A figure whose inputs are not there yet is skipped
with a line saying what it is waiting for, so the same command works now and
after the final runs land.
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

from cota_opt import figures as F

log = logging.getLogger("figures")
OUT = ROOT / "outputs"
FIG = OUT / "figures"


def _jsonl(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    return pd.DataFrame(rows)


def _skip(name: str, why: str) -> None:
    log.info("skip  %-28s waiting for %s", name, why)


def _done(name: str, paths) -> None:
    log.info("write %-28s %s", name, ", ".join(p.name for p in paths))


# ---------------------------------------------------------------------------

def exp1_frontier(final: pd.DataFrame, interim: pd.DataFrame) -> None:
    if final.empty:
        return _skip("exp1_frontier", "final|lam* cells in fixpoint.jsonl")
    series = [{"label": "converged path set",
               "gc": final["gc_change_pct"].tolist(),
               "unserved": final["unserved_change_pct"].tolist(),
               "annotate": final["lambda"].tolist()}]
    if not interim.empty:
        series.append({"label": "original path set",
                       "gc": interim["gc_change_pct"].tolist(),
                       "unserved": interim["unserved_change_pct"].tolist(),
                       "annotate": None})
    _done("exp1_frontier", F.render(
        F.frontier, "exp1_frontier", FIG, series=series,
        title="Experiment 1 — frequency redistribution inside today's budget",
        subtitle="2,517 weekday revenue vehicle-hours held fixed; route "
                 "geometry unchanged"))


def exp1_lambda(final: pd.DataFrame) -> None:
    if final.empty:
        return _skip("exp1_lambda_sweep", "final|lam* cells")
    d = final.sort_values("lambda")
    _done("exp1_lambda_sweep", F.render(
        F.lambda_sweep, "exp1_lambda_sweep", FIG,
        lam=d["lambda"].tolist(), gc=d["gc_change_pct"].tolist(),
        unserved=d["unserved_change_pct"].tolist(),
        title="What buying coverage costs",
        subtitle="λ is the weight the optimizer puts on unserved demand"))


def exp1_seeds() -> None:
    p = OUT / "final_checks.json"
    if not p.exists():
        return _skip("exp1_seed_stability", "final_checks.json")
    rows = json.loads(p.read_text()).get("seed_stability", [])
    if not rows:
        return _skip("exp1_seed_stability", "seed_stability rows")
    _done("exp1_seed_stability", F.render(
        F.seed_stability, "exp1_seed_stability", FIG, rows=rows,
        title="Which results survive a change of random seed",
        subtitle="a bar that straddles zero is noise, not a finding"))


def exp1_fidelity() -> None:
    p = OUT / "matrix.jsonl"
    if not p.exists():
        return _skip("exp1_route_vs_path", "matrix.jsonl")
    m = _jsonl(p)
    r = m[m["model"] == "R"].sort_values("lambda")
    if r.empty:
        return _skip("exp1_route_vs_path", "route-level rows in matrix.jsonl")
    _done("exp1_route_vs_path", F.render(
        F.claimed_vs_honest, "exp1_route_vs_path", FIG,
        labels=[f"λ = {v:g}" for v in r["lambda"]],
        claimed=r["own_unserved_change_pct"].tolist(),
        honest=r["scored_unserved_change_pct"].tolist(),
        title="A route-level model grading its own homework",
        xlabel="unserved demand, % change vs today",
        subtitle="same plans, two scorers: the route-level model cannot let "
                 "passengers re-route around a cut"))


# ---------------------------------------------------------------------------

def exp2_screen(audit: pd.DataFrame) -> None:
    if audit.empty or audit["screen_gc_change_pct"].isna().all():
        return _skip("exp2_screen_scatter", "screened rows in exp2_audit.csv")
    d = audit.dropna(subset=["screen_gc_change_pct"])
    _done("exp2_screen_scatter", F.render(
        F.screen_scatter, "exp2_screen_scatter", FIG,
        gc=d["screen_gc_change_pct"].tolist(),
        unserved=d["screen_unserved_change_pct"].tolist(),
        evidence=d["evidence_class"].tolist(),
        title="Experiment 2 screen — geometry at equal vehicle-hours",
        subtitle="frequency is NOT reallocated here; this ranks candidates, "
                 "it does not measure them"))

    _done("exp2_score_vs_modelled", F.render(
        F.score_vs_modelled, "exp2_score_vs_modelled", FIG,
        modelled_pct=d["modelled_share_pct"].tolist(),
        score=d["screen_gc_change_pct"].tolist(), threshold=2.0,
        title="Does a candidate look better the more of it was modelled?",
        ylabel="screening generalized cost, % change",
        subtitle="an upward slope would mean the running-time estimator is "
                 "buying the result"))

    groups = {k: {"x": g["screen_unserved_change_pct"].tolist(),
                  "y": g["screen_gc_change_pct"].tolist()}
              for k, g in d.groupby("kind")}
    _done("exp2_by_edit_type", F.render(
        F.by_edit_type, "exp2_by_edit_type", FIG, groups=groups,
        title="Which kind of edit does anything",
        xlabel="unserved, %", ylabel="generalized cost, %",
        subtitle="five edit types get five panels rather than five colours"))


def exp2_ladder() -> None:
    p = OUT / "exp2_ladder.csv"
    if not p.exists():
        return _skip("exp2_complexity_ladder", "exp2_ladder.csv")
    d = pd.read_csv(p).sort_values("n_edits")
    _done("exp2_complexity_ladder", F.render(
        F.complexity_ladder, "exp2_complexity_ladder", FIG,
        n_edits=d["n_edits"].tolist(),
        improvement=d["improvement_vs_exp1"].tolist(),
        title="How much structural change it takes",
        ylabel="improvement beyond the Experiment 1 frontier, %",
        subtitle="frequency re-optimized at every level, same 2,517-hour budget"))


def exp2_vs_exp1(final: pd.DataFrame) -> None:
    p = OUT / "exp2_frontier.csv"
    if not p.exists() or final.empty:
        return _skip("exp2_vs_exp1", "exp2_frontier.csv and the final Exp 1 frontier")
    g = pd.read_csv(p)
    _done("exp2_vs_exp1", F.render(
        F.frontier, "exp2_vs_exp1", FIG, series=[
            {"label": "geometry + re-optimized frequency",
             "gc": g["gc_change_pct"].tolist(),
             "unserved": g["unserved_change_pct"].tolist(),
             "annotate": None},
            {"label": "frequency only (Experiment 1)",
             "gc": final["gc_change_pct"].tolist(),
             "unserved": final["unserved_change_pct"].tolist(),
             "annotate": None}],
        title="Does limited geometry freedom move the frontier outward?",
        subtitle="both inside the same 2,517 vehicle-hours, both scored on the "
                 "converged path set"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", type=Path, default=FIG)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    globals()["FIG"] = args.outdir

    fx = _jsonl(OUT / "fixpoint.jsonl")
    final = (fx[fx.get("phase") == "final"].sort_values("lambda")
             if "phase" in fx.columns else pd.DataFrame())
    interim = (fx[(fx.get("iteration") == 0) & fx["lambda"].notna()]
               .sort_values("lambda")
               if "iteration" in fx.columns and "lambda" in fx.columns
               else pd.DataFrame())
    audit = (pd.read_csv(OUT / "exp2_audit.csv")
             if (OUT / "exp2_audit.csv").exists() else pd.DataFrame())

    exp1_frontier(final, interim)
    exp1_lambda(final)
    exp1_seeds()
    exp1_fidelity()
    exp2_screen(audit)
    exp2_ladder()
    exp2_vs_exp1(final)

    made = sorted(args.outdir.glob("*.svg")) if args.outdir.exists() else []
    log.info("\n%d figure files in %s", len(made), args.outdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
