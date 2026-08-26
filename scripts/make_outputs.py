#!/usr/bin/env python3
"""Generate the baseline report and the Experiment 1 Pareto chart."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from cota_opt.baseline import build_baseline
from cota_opt.paths import outputs_dir
from cota_opt.report import build_report

UPLOADS = Path("/mnt/user-data/uploads/Downloads")
DEMAND_FILES = {"rac": UPLOADS / "oh_rac_S000_JT00_2022.csv.gz",
                "wac": UPLOADS / "oh_wac_S000_JT00_2022.csv.gz",
                "centroids": UPLOADS / "CenPop2020_Mean_BG39.txt"}

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
GRID = "#e5e4e0"


def latest_experiment() -> Path:
    exps = sorted((outputs_dir() / "experiments").glob("exp1_*"))
    if not exps:
        raise SystemExit("no experiment found — run scripts/run_exp1.py first")
    return exps[-1]


def pareto_chart(exp_dir: Path, out: Path) -> None:
    df = pd.read_csv(exp_dir / "pareto_frontier.csv")
    base = df[df["solution"].str.startswith("baseline")].iloc[0]
    sol = df[~df["solution"].str.startswith("baseline")].copy()
    front = sol[sol["on_pareto_front"]].sort_values("generalized_cost")
    dom = sol[~sol["on_pareto_front"]]

    fig, ax = plt.subplots(figsize=(8.2, 5.4), dpi=170)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    ax.plot(front["gc_change_pct"], front["unserved_change_pct"],
            color=BLUE, lw=2, zorder=2, solid_capstyle="round")
    ax.scatter(front["gc_change_pct"], front["unserved_change_pct"],
               s=64, color=BLUE, zorder=3, edgecolor=SURFACE, linewidth=2,
               label="Pareto-optimal plans")
    if len(dom):
        ax.scatter(dom["gc_change_pct"], dom["unserved_change_pct"], s=42,
                   facecolor="none", edgecolor=INK2, linewidth=1.2, zorder=2,
                   label="dominated plans")
    ax.scatter([0], [0], s=150, marker="*", color=ORANGE, zorder=4,
               edgecolor=SURFACE, linewidth=1.5,
               label="COTA current schedule (baseline)")

    # label only the endpoints and the strict-improvement point; the tail
    # bunches too tightly to label every solution
    label_lams = {front["unserved_multiplier"].min(),
                  front["unserved_multiplier"].max(), 0.5, 1.0}
    for _, r in front.iterrows():
        if r["unserved_multiplier"] not in label_lams:
            continue
        dx, dy = (7, 6) if r["unserved_multiplier"] <= 1.0 else (7, -14)
        ax.annotate(f"λ={r['unserved_multiplier']:g}",
                    (r["gc_change_pct"], r["unserved_change_pct"]),
                    textcoords="offset points", xytext=(dx, dy),
                    fontsize=8.5, color=INK2)

    # the quadrant where a plan beats today's schedule on BOTH objectives
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    ax.add_patch(plt.Rectangle((x0, y0), -x0, -y0, facecolor="#1baf7a",
                               alpha=0.06, zorder=0, linewidth=0))
    ax.text(x0 * 0.97, y0 * 0.94, "better on both objectives",
            fontsize=8.5, color="#0e7a55", va="bottom", zorder=1)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)

    ax.axhline(0, color=GRID, lw=1, zorder=1)
    ax.axvline(0, color=GRID, lw=1, zorder=1)
    ax.grid(True, color=GRID, lw=0.7, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)

    ax.set_xlabel("Passenger generalized cost  (% change vs current schedule)",
                  color=INK2, fontsize=10)
    ax.set_ylabel("Unserved demand  (% change vs current schedule)",
                  color=INK2, fontsize=10)
    ax.set_title("Experiment 1 — frequency redistribution at constant resources",
                 color=INK, fontsize=13, pad=14, loc="left", fontweight="bold")
    ax.text(0, 1.015, "Down and to the left is better. Proxy demand — not observed ridership.",
            transform=ax.transAxes, color=INK2, fontsize=9)
    ax.tick_params(colors=INK2, labelsize=9)
    leg = ax.legend(frameon=False, fontsize=9, loc="upper right")
    for t in leg.get_texts():
        t.set_color(INK2)
    fig.tight_layout()
    fig.savefig(out, facecolor=SURFACE)
    print(f"wrote {out}")


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    exp = latest_experiment()
    b = build_baseline(demand_files=DEMAND_FILES, write=False)
    metrics = json.loads((exp / "experiment.json").read_text())["metrics"]
    paths = build_report(b, exp_metrics=metrics)
    print("report:", paths["markdown"])
    pareto_chart(exp, outputs_dir() / "exp1_pareto.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
