"""Figures for the Experiment 1 and 2 write-ups.

Every figure is rendered twice, light and dark, from one validated categorical
palette, so the published page can serve whichever the reader's theme asks for
instead of pasting a light-mode PNG onto a dark surface.

Rules the figures follow, and why:

* **At most three categorical hues.** The palette's first three slots are the
  ones that clear colour-vision separation on *all* pairs, which is the case a
  scatter puts you in. A fourth series would fail that, so anything with more
  categories is drawn as small multiples instead of more colours.
* **One axis, always.** Two measures of different scale get two panels. A
  second y-axis lets the author choose the story by choosing the scaling.
* **Series are direct-labelled.** Identity is never carried by colour alone,
  which also discharges the light-mode contrast warning on the third hue.
* **The grid recedes.** Data marks are the only thing at full contrast.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


@dataclass(frozen=True)
class Theme:
    name: str
    surface: str
    text_primary: str
    text_secondary: str
    text_muted: str
    grid: str
    series: tuple[str, str, str]
    accent_neutral: str


LIGHT = Theme("light", "#fcfcfb", "#0b0b0b", "#52514e", "#7a7973", "#e3e2dd",
              ("#2a78d6", "#eb6834", "#1baf7a"), "#9a9993")
DARK = Theme("dark", "#1a1a19", "#ffffff", "#c3c2b7", "#8f8e86", "#333331",
             ("#3987e5", "#d95926", "#199e70"), "#6b6a64")
THEMES = (LIGHT, DARK)


def _style(t: Theme) -> dict[str, Any]:
    return {
        "figure.facecolor": t.surface,
        "axes.facecolor": t.surface,
        "savefig.facecolor": t.surface,
        "axes.edgecolor": t.grid,
        "axes.labelcolor": t.text_secondary,
        "axes.titlecolor": t.text_primary,
        "text.color": t.text_primary,
        "xtick.color": t.text_muted,
        "ytick.color": t.text_muted,
        "xtick.labelcolor": t.text_secondary,
        "ytick.labelcolor": t.text_secondary,
        "grid.color": t.grid,
        "grid.linewidth": 0.8,
        "axes.grid": True,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.titleweight": "600",
        "lines.linewidth": 2.0,
        "lines.markersize": 7,
        "figure.dpi": 130,
    }


def render(builder, stem: str, outdir: Path, **kwargs) -> list[Path]:
    """Run ``builder(ax_or_fig, theme, **kwargs)`` once per theme."""
    outdir.mkdir(parents=True, exist_ok=True)
    written = []
    for t in THEMES:
        with plt.rc_context(_style(t)):
            fig = builder(t, **kwargs)
            p = outdir / f"{stem}.{t.name}.svg"
            fig.savefig(p, bbox_inches="tight", transparent=False)
            plt.close(fig)
            written.append(p)
    return written


def _finish(ax, t: Theme, title: str, xlabel: str, ylabel: str,
            subtitle: str | None = None) -> None:
    lines = subtitle.count("\n") + 1 if subtitle else 0
    ax.set_title(title, loc="left", pad=10 + 12 * lines)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9,
                color=t.text_secondary, va="bottom", linespacing=1.5)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(axis="both", alpha=0.7)


def _label_last(ax, x, y, text: str, color: str, dx: float = 4.0) -> None:
    ax.annotate(text, (x, y), textcoords="offset points", xytext=(dx, 0),
                color=color, fontsize=9, va="center", fontweight="600")


# ---------------------------------------------------------------------------
# Experiment 1
# ---------------------------------------------------------------------------

def frontier(t: Theme, series: Sequence[dict], title: str,
             subtitle: str | None = None):
    """Pareto frontiers: generalized cost against unserved demand.

    Each series is ``{"label", "gc", "unserved", "annotate"}`` where annotate
    optionally carries a per-point string (the lambda value).
    """
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    for i, s in enumerate(series[:3]):
        c = t.series[i]
        x = np.asarray(s["unserved"], float)
        y = np.asarray(s["gc"], float)
        order = np.argsort(x)
        x, y = x[order], y[order]
        ax.plot(x, y, "-o", color=c, label=s["label"], zorder=3 - i,
                markeredgecolor=t.surface, markeredgewidth=1.5)
        _label_last(ax, x[-1], y[-1], s["label"], c)
        for lab, xi, yi in zip(np.asarray(s.get("annotate", []))[order]
                               if s.get("annotate") is not None
                               and len(s.get("annotate", [])) == len(order)
                               else [], x, y):
            ax.annotate(f"λ={lab:g}", (xi, yi), textcoords="offset points",
                        xytext=(0, -13), ha="center", fontsize=8,
                        color=t.text_muted)
    ax.axhline(0, color=t.accent_neutral, lw=1, ls=":", zorder=1)
    ax.axvline(0, color=t.accent_neutral, lw=1, ls=":", zorder=1)
    ax.annotate("today's schedule", (0, 0), textcoords="offset points",
                xytext=(6, 6), fontsize=8, color=t.text_muted)
    _finish(ax, t, title, "unserved demand, % change vs today",
            "generalized cost, % change vs today", subtitle)
    if len(series) > 1:
        ax.legend(loc="best", labelcolor=t.text_secondary)
    return fig


def lambda_sweep(t: Theme, lam: Sequence[float], gc: Sequence[float],
                 unserved: Sequence[float], title: str,
                 subtitle: str | None = None):
    """Two panels rather than two y-axes on one."""
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 4.0))
    lam = np.asarray(lam, float)
    for ax, vals, lab, c in ((axes[0], np.asarray(gc, float),
                              "generalized cost", t.series[0]),
                             (axes[1], np.asarray(unserved, float),
                              "unserved demand", t.series[1])):
        ax.plot(lam, vals, "-o", color=c, markeredgecolor=t.surface,
                markeredgewidth=1.5)
        ax.set_xscale("log", base=2)
        ax.axhline(0, color=t.accent_neutral, lw=1, ls=":")
        ax.set_xticks(lam)
        ax.set_xticklabels([f"{v:g}" for v in lam])
        _finish(ax, t, lab, "λ (weight on unserved demand)", "% change vs today")
    if subtitle:
        fig.suptitle(title, x=0.005, ha="left", fontsize=12, fontweight="600",
                     color=t.text_primary)
        fig.text(0.005, 0.95, subtitle, ha="left", fontsize=9,
                 color=t.text_secondary)
        fig.subplots_adjust(top=0.80)
    fig.tight_layout()
    return fig


def seed_stability(t: Theme, rows: Sequence[dict], title: str,
                   subtitle: str | None = None):
    """Mean +/- sd per lambda for each measure, as a dot plot with whiskers.

    ``rows``: ``{"lambda", "gc_mean", "gc_sd", "uns_mean", "uns_sd"}``.
    """
    fig, ax = plt.subplots(figsize=(7.2, 0.9 + 0.9 * len(rows)))
    ypos = np.arange(len(rows))[::-1]
    for i, (key_m, key_s, lab) in enumerate(
            (("gc_mean", "gc_sd", "generalized cost"),
             ("uns_mean", "uns_sd", "unserved demand"))):
        c = t.series[i]
        m = np.array([r[key_m] for r in rows], float)
        s = np.array([r[key_s] for r in rows], float)
        off = 0.14 * (1 if i else -1)
        ax.errorbar(m, ypos + off, xerr=s, fmt="o", color=c, ecolor=c,
                    elinewidth=2, capsize=4, label=lab,
                    markeredgecolor=t.surface, markeredgewidth=1.5)
        for mi, si, yi in zip(m, s, ypos + off):
            ax.annotate(f"{mi:+.2f} ± {si:.2f}", (mi, yi),
                        textcoords="offset points", xytext=(0, 9),
                        ha="center", fontsize=8, color=t.text_secondary)
    ax.axvline(0, color=t.accent_neutral, lw=1.2, ls=":")
    ax.set_yticks(ypos)
    ax.set_yticklabels([f"λ = {r['lambda']:g}" for r in rows])
    ax.grid(axis="y", visible=False)
    _finish(ax, t, title, "% change vs today (mean ± sd across seeds)", "",
            subtitle)
    ax.legend(loc="lower right", labelcolor=t.text_secondary)
    return fig


def claimed_vs_honest(t: Theme, labels: Sequence[str],
                      claimed: Sequence[float], honest: Sequence[float],
                      title: str, xlabel: str, subtitle: str | None = None):
    """Dumbbell: what a model believed, against what its plan delivers.

    The gap is the finding, so the gap is the mark that carries the ink.
    """
    fig, ax = plt.subplots(figsize=(7.6, 0.55 + 0.46 * len(labels)))
    y = np.arange(len(labels))[::-1]
    c_claim, c_true = t.series[0], t.series[1]
    for yi, a, b in zip(y, claimed, honest):
        ax.plot([a, b], [yi, yi], color=t.accent_neutral, lw=2, zorder=1,
                solid_capstyle="round")
    ax.scatter(claimed, y, s=64, color=c_claim, zorder=3, label="believed",
               edgecolor=t.surface, linewidth=1.5)
    ax.scatter(honest, y, s=64, color=c_true, zorder=3,
               label="delivered, scored by path assignment",
               edgecolor=t.surface, linewidth=1.5)
    ax.axvline(0, color=t.accent_neutral, lw=1.2, ls=":")
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.grid(axis="y", visible=False)
    _finish(ax, t, title, xlabel, "", subtitle)
    ax.legend(loc="best", labelcolor=t.text_secondary)
    return fig


# ---------------------------------------------------------------------------
# Experiment 2
# ---------------------------------------------------------------------------

def screen_scatter(t: Theme, gc: Sequence[float], unserved: Sequence[float],
                   evidence: Sequence[str], title: str,
                   subtitle: str | None = None):
    """Screened candidates, split by evidence class rather than by edit type.

    Evidence class is the decision variable: a novel-link candidate is priced
    partly by a model, so it is drawn as an open mark to keep that visible
    without relying on hue alone.
    """
    fig, ax = plt.subplots(figsize=(7.2, 5.0))
    gc = np.asarray(gc, float)
    un = np.asarray(unserved, float)
    ev = np.asarray(evidence)
    for i, (cls, lab) in enumerate((("primary", "primary (observed links)"),
                                    ("novel_link", "novel-link (modelled)"))):
        m = ev == cls
        if not m.any():
            continue
        c = t.series[i]
        ax.scatter(un[m], gc[m], s=58, label=lab,
                   facecolor=c if cls == "primary" else "none",
                   edgecolor=c if cls == "novel_link" else t.surface,
                   linewidth=1.8, zorder=3 - i)
    ax.axhline(0, color=t.accent_neutral, lw=1, ls=":")
    ax.axvline(0, color=t.accent_neutral, lw=1, ls=":")
    ax.annotate("better on both\n↙", (ax.get_xlim()[0], ax.get_ylim()[0]),
                textcoords="offset points", xytext=(12, 12), fontsize=8,
                color=t.text_muted)
    _finish(ax, t, title, "unserved demand, % change", "generalized cost, % change",
            subtitle)
    ax.legend(loc="best", labelcolor=t.text_secondary)
    return fig


def score_vs_modelled(t: Theme, modelled_pct: Sequence[float],
                      score: Sequence[float], threshold: float, title: str,
                      ylabel: str, subtitle: str | None = None):
    """Does a candidate look better the more of it was made up?"""
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    x = np.asarray(modelled_pct, float)
    y = np.asarray(score, float)
    ax.scatter(x, y, s=54, color=t.series[0], edgecolor=t.surface,
               linewidth=1.5, zorder=3)
    if len(x) > 2 and np.ptp(x) > 0:
        b, a = np.polyfit(x, y, 1)
        xs = np.linspace(x.min(), x.max(), 50)
        ax.plot(xs, a + b * xs, color=t.series[1], lw=2, ls="--", zorder=2)
        ax.annotate(f"slope {b:+.3f} per point of modelled share",
                    (xs[-1], a + b * xs[-1]), textcoords="offset points",
                    xytext=(-6, 10), ha="right", fontsize=9,
                    color=t.series[1], fontweight="600")
    ax.axvline(threshold, color=t.accent_neutral, lw=1.2, ls=":")
    ax.annotate(f"primary ≤ {threshold:g}%", (threshold, ax.get_ylim()[1]),
                textcoords="offset points", xytext=(-6, -12), ha="right",
                fontsize=8, color=t.text_muted)
    _finish(ax, t, title, "share of segments priced by the running-time model, %",
            ylabel, subtitle)
    return fig


def by_edit_type(t: Theme, groups: dict[str, dict[str, Sequence[float]]],
                 title: str, xlabel: str, ylabel: str,
                 subtitle: str | None = None):
    """Small multiples: five edit types need five panels, not five hues."""
    kinds = list(groups)
    n = len(kinds)
    fig, axes = plt.subplots(1, n, figsize=(2.5 * n, 3.4), sharex=True,
                             sharey=True)
    axes = np.atleast_1d(axes)
    for ax, k in zip(axes, kinds):
        g = groups[k]
        ax.scatter(g["x"], g["y"], s=44, color=t.series[0],
                   edgecolor=t.surface, linewidth=1.2, zorder=3)
        ax.axhline(0, color=t.accent_neutral, lw=1, ls=":")
        ax.axvline(0, color=t.accent_neutral, lw=1, ls=":")
        ax.set_title(f"{k}  (n={len(g['x'])})", loc="left", fontsize=10)
        ax.set_xlabel(xlabel)
        ax.grid(alpha=0.7)
    axes[0].set_ylabel(ylabel)
    fig.suptitle(title, x=0.005, ha="left", fontsize=12, fontweight="600",
                 color=t.text_primary)
    if subtitle:
        fig.text(0.005, 0.93, subtitle, ha="left", fontsize=9,
                 color=t.text_secondary)
    fig.tight_layout(rect=(0, 0, 1, 0.88 if subtitle else 0.93))
    return fig


def complexity_ladder(t: Theme, n_edits: Sequence[int],
                      improvement: Sequence[float], title: str, ylabel: str,
                      subtitle: str | None = None):
    """How much of the geometry benefit the first one or two edits capture."""
    fig, ax = plt.subplots(figsize=(6.6, 4.2))
    x = np.asarray(n_edits, float)
    y = np.asarray(improvement, float)
    ax.plot(x, y, "-o", color=t.series[0], markeredgecolor=t.surface,
            markeredgewidth=1.5, zorder=3)
    if len(y) and y[-1] != 0:
        for xi, yi in zip(x, y):
            ax.annotate(f"{100 * yi / y[-1]:.0f}% of the total",
                        (xi, yi), textcoords="offset points", xytext=(0, 10),
                        ha="center", fontsize=8, color=t.text_secondary)
    ax.axhline(0, color=t.accent_neutral, lw=1, ls=":")
    ax.set_xticks(x)
    _finish(ax, t, title, "geometry edits allowed", ylabel, subtitle)
    return fig


def candidate_classes(t: Theme, labels: Sequence[str],
                      effect: Sequence[float], floor: float,
                      title: str, xlabel: str,
                      subtitle: str | None = None):
    """Every candidate against the floor its classification was decided by.

    The floor is drawn rather than described, because the whole point of the
    classification is that three of these candidates are inside it. A bar chart
    without the band invites the reader to rank all twelve, which is exactly
    what the evidence does not support.
    """
    fig, ax = plt.subplots(figsize=(7.4, 5.0))
    y = np.arange(len(labels))
    v = np.asarray(effect, float)
    colors = [t.series[2] if x <= -floor else
              (t.series[1] if x >= floor else t.accent_neutral) for x in v]
    ax.barh(y, v, color=colors, height=0.66, zorder=3)
    ax.axvspan(-floor, floor, color=t.accent_neutral, alpha=0.18, zorder=1)
    ax.axvline(0, color=t.text_muted, lw=1)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    band = (f"shaded band = ±{floor:.3f} pts, the measured noise floor — "
            f"nothing inside it is distinguishable from search noise")
    _finish(ax, t, title, xlabel, "",
            f"{subtitle}\n{band}" if subtitle else band)
    ax.grid(axis="y", alpha=0)
    return fig


def ladder_orders(t: Theme, n_edits: Sequence[int],
                  measured: Sequence[float], screened: Sequence[float],
                  floor: float, title: str, ylabel: str,
                  subtitle: str | None = None):
    """Two orderings of the same ladder, so the reader can see that the
    ordering is not what broke it."""
    fig, ax = plt.subplots(figsize=(6.8, 4.4))
    x = np.asarray(n_edits, float)
    ax.axhspan(-floor, floor, color=t.accent_neutral, alpha=0.18, zorder=1)
    ax.plot(x, np.asarray(measured, float), "-o", color=t.series[0],
            markeredgecolor=t.surface, markeredgewidth=1.5, zorder=3,
            label="composed in measured order (best first)")
    ax.plot(x, np.asarray(screened, float), "--s", color=t.series[1],
            markeredgecolor=t.surface, markeredgewidth=1.5, zorder=3,
            label="composed in screen order")
    ax.axhline(0, color=t.text_muted, lw=1, ls=":")
    ax.set_xticks(x)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    _finish(ax, t, title, "geometry edits applied", ylabel, subtitle)
    return fig


# ---------------------------------------------------------------------------
# Model A vs Model B
# ---------------------------------------------------------------------------

def ab_bars(t: Theme, labels: Sequence[str], model_a: Sequence[float],
            model_b: Sequence[float], title: str, xlabel: str,
            subtitle: str | None = None):
    """Paired horizontal bars: the same quantity under both waiting models."""
    fig, ax = plt.subplots(figsize=(7.6, 0.6 + 0.55 * len(labels)))
    y = np.arange(len(labels))[::-1]
    h = 0.34
    for off, vals, lab, c in ((h / 2, np.asarray(model_a, float),
                               "Model A — pattern waiting", t.series[0]),
                              (-h / 2, np.asarray(model_b, float),
                               "Model B — same-route common lines", t.series[1])):
        ax.barh(y + off, vals, height=h, color=c, label=lab, zorder=3)
        for v, yi in zip(vals, y + off):
            ax.annotate(f"{v:+.2f}", (v, yi), textcoords="offset points",
                        xytext=(6 if v >= 0 else -6, 0),
                        ha="left" if v >= 0 else "right", va="center",
                        fontsize=8, color=t.text_secondary)
    ax.axvline(0, color=t.accent_neutral, lw=1.2, ls=":")
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.grid(axis="y", visible=False)
    _finish(ax, t, title, xlabel, "", subtitle)
    ax.legend(loc="best", labelcolor=t.text_secondary)
    return fig


def residual_split(t: Theme, rows: Sequence[dict], title: str,
                   subtitle: str | None = None):
    """Where the common-lines bound sits, before and after the correction.

    ``rows``: ``{"model", "same_route_pct", "cross_route_pct"}``. Two stacked
    segments with a surface gap between them, because the whole point is the
    same-route part collapsing while the cross-route part does not.
    """
    fig, ax = plt.subplots(figsize=(7.2, 1.2 + 0.9 * len(rows)))
    y = np.arange(len(rows))[::-1]
    same = np.array([r["same_route_pct"] for r in rows], float)
    cross = np.array([r["cross_route_pct"] for r in rows], float)
    ax.barh(y, same, height=0.42, color=t.series[0], zorder=3,
            label="same-route patterns")
    ax.barh(y, cross, height=0.42, left=same + 0.012 * max(1e-9, (same + cross).max()),
            color=t.series[1], zorder=3, label="cross-route lines")
    for yi, a_, b_ in zip(y, same, cross):
        ax.annotate(f"{a_:.2f}%", (a_ / 2, yi), ha="center", va="center",
                    fontsize=8, color=t.surface, fontweight="600")
        ax.annotate(f"{b_:.2f}%", (a_ + b_ + 0.02 * (same + cross).max(), yi),
                    ha="left", va="center", fontsize=8, color=t.text_secondary)
    ax.set_yticks(y)
    ax.set_yticklabels([r["model"] for r in rows])
    ax.grid(axis="y", visible=False)
    _finish(ax, t, title, "upper bound, % of generalized cost", "", subtitle)
    ax.legend(loc="lower right", labelcolor=t.text_secondary)
    return fig
