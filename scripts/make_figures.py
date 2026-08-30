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


def exp2_candidate_classes() -> None:
    p = OUT / "exp2_candidate_classes.json"
    if not p.exists():
        return _skip("exp2_candidate_classes", "exp2_candidate_classes.json")
    d = json.loads(p.read_text())
    rows = sorted(d["candidates"], key=lambda r: r["unserved_vs_noedit_pct_lam2.0"])
    n = d["rule"]["counts"]
    _done("exp2_candidate_classes", F.render(
        F.candidate_classes, "exp2_candidate_classes", FIG,
        labels=[r["candidate"].replace("splice|", "") for r in rows],
        effect=[r["unserved_vs_noedit_pct_lam2.0"] for r in rows],
        floor=float(d["rule"]["noise_floor_pts"]),
        title="Twelve geometry candidates, each evaluated on its own",
        xlabel="change in unserved demand vs no edit, % (negative is better)",
        subtitle=f"{n.get('beneficial', 0)} beneficial, "
                 f"{n.get('noise-floor', 0)} inside the noise floor, "
                 f"{n.get('harmful', 0)} harmful — frequency re-optimized on "
                 f"every network, one frozen Model B evaluator"))


def exp2_ladder_orders() -> None:
    p = OUT / "exp2_ladder_measured.csv"
    if not p.exists():
        return _skip("exp2_ladder_orders", "exp2_ladder_measured.csv")
    d = pd.read_csv(p)
    m = d[d["order"] == "measured"].sort_values("n_edits")
    sc = d[d["order"] == "screen"].sort_values("n_edits")
    if m.empty or sc.empty or list(m["n_edits"]) != list(sc["n_edits"]):
        return _skip("exp2_ladder_orders", "matching measured and screen rungs")
    floor = 0.288
    q = OUT / "exp2_candidate_classes.json"
    if q.exists():
        floor = float(json.loads(q.read_text())["rule"]["noise_floor_pts"])
    _done("exp2_ladder_orders", F.render(
        F.ladder_orders, "exp2_ladder_orders", FIG,
        n_edits=m["n_edits"].tolist(),
        measured=m["unserved_vs_0edit_pct"].tolist(),
        screened=sc["unserved_vs_0edit_pct"].tolist(),
        floor=floor,
        title="Geometry edits do not compose, in either ordering",
        ylabel="change in unserved demand vs no edit, %",
        subtitle="best-first ordering helps every rung and still cannot make "
                 "composition pay: one edit helps, two land inside the noise "
                 "floor, four are worse than making no change at all"))


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


def ab_frontier(final_a: pd.DataFrame, final_b: pd.DataFrame) -> None:
    if final_a.empty or final_b.empty:
        return _skip("ab_frontier", "final frontiers under both models")
    _done("ab_frontier", F.render(
        F.frontier, "ab_frontier", FIG, series=[
            {"label": "Model B — same-route common lines",
             "gc": final_b["gc_change_pct"].tolist(),
             "unserved": final_b["unserved_change_pct"].tolist(),
             "annotate": final_b["lambda"].tolist()},
            {"label": "Model A — pattern waiting",
             "gc": final_a["gc_change_pct"].tolist(),
             "unserved": final_a["unserved_change_pct"].tolist(),
             "annotate": None}],
        title="What correcting same-route waiting did to the frontier",
        subtitle="same budget, same solver effort, same demand — only the "
                 "valuation of waiting changed"))


def ab_residual() -> None:
    rows = []
    for label, path in (("Model A — pattern waiting", "model_diagnostics.json"),
                        ("Model B — corrected", "model_diagnostics_modelB.json")):
        p = OUT / path
        if not p.exists():
            continue
        h = json.loads(p.read_text()).get("hyperpath", {})
        if not h:
            continue
        rows.append({
            "model": label,
            "same_route_pct": float(h.get(
                "same_route_share_of_generalized_cost_pct",
                h.get("bound_share_of_generalized_cost_pct", 0.0)
                - h.get("cross_route_share_of_generalized_cost_pct", 0.0))),
            "cross_route_pct": float(
                h.get("cross_route_share_of_generalized_cost_pct", 0.0))})
    if len(rows) < 2:
        return _skip("ab_common_lines_residual",
                     "model_diagnostics_modelB.json")
    _done("ab_common_lines_residual", F.render(
        F.residual_split, "ab_common_lines_residual", FIG, rows=rows,
        title="The common-lines bound, before and after the correction",
        subtitle="the same-route half is a defect and should collapse; the "
                 "cross-route half is a deferred limitation and should not"))


def ab_trunk_frequency(final_a: pd.DataFrame, final_b: pd.DataFrame) -> None:
    """Do the trunk routes stop losing so much frequency once waiting is right?"""
    trunk = ["010", "005", "007", "001", "002"]
    pa = OUT / "fixpoint_plans" / "final_lam2.0.csv"
    pb = OUT / "fixpoint_plans_modelB" / "final_lam2.0.csv"
    base = (OUT / "experiments" /
            "exp1_frequency_redistribution_20260826T003902Z" /
            "frequency_plan_baseline.csv")
    if not (pa.exists() and pb.exists() and base.exists()):
        return _skip("ab_trunk_frequency", "final lambda=2 plans under both models")
    b = pd.read_csv(base, dtype={"route_id": str}).rename(
        columns={"headway_min": "base"})
    out_a, out_b = [], []
    for r in trunk:
        for df, sink in ((pd.read_csv(pa, dtype={"route_id": str}), out_a),
                         (pd.read_csv(pb, dtype={"route_id": str}), out_b)):
            m = b.merge(df, on=["route_id", "period"])
            m = m[m["route_id"] == r]
            sink.append(float((m["headway_min"] - m["base"]).mean())
                        if len(m) else np.nan)
    _done("ab_trunk_frequency", F.render(
        F.ab_bars, "ab_trunk_frequency", FIG,
        labels=[f"route {r}" for r in trunk], model_a=out_a, model_b=out_b,
        title="Trunk-route headway change at the balanced point",
        xlabel="mean headway change, minutes (positive = less service)",
        subtitle="the routes carrying most of the same-route waiting bias"))


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
    exp2_candidate_classes()
    exp2_ladder_orders()
    exp2_vs_exp1(final)

    fxb = _jsonl(OUT / "fixpoint_modelB.jsonl")
    final_b = (fxb[fxb.get("phase") == "final"].sort_values("lambda")
               if "phase" in fxb.columns else pd.DataFrame())
    ab_frontier(final, final_b)
    ab_residual()
    ab_trunk_frequency(final, final_b)

    made = sorted(args.outdir.glob("*.svg")) if args.outdir.exists() else []
    log.info("\n%d figure files in %s", len(made), args.outdir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
