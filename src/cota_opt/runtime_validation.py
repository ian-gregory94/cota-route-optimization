"""Out-of-sample validation of the novel-link running-time estimator.

A geometry edit that routes a bus down a street no COTA line runs needs a
running time nobody observed. That time is money: the vehicle-hour budget is
fixed, so any second the estimator shaves off a new link is a second the
optimizer gets to spend on frequency somewhere else. Random error in that
estimate widens the uncertainty band. **Systematic underestimation is
exploitable** — the search would learn to prefer exactly the alignments the
model is most optimistic about, and the resulting frontier would be an artifact
of the estimator rather than a fact about the network.

So the estimator is validated the way it is actually used: hold a link out,
refit without it, predict it, compare. Reported with the bias, not just the
spread, and broken out by the link characteristics that could hide a
directional error inside a decent-looking average.

Nothing here touches the optimizer. It runs independently and its verdict is a
gate on which candidates may define the headline, per ACCEPTANCE.md.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .geometry import SegmentTimeModel, _lsq
from .network import TransitNetwork

log = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    table: pd.DataFrame
    summary: dict[str, Any]
    by_distance: pd.DataFrame
    by_route: pd.DataFrame
    calibration: dict[str, float]


def _observations(net: TransitNetwork,
                  coords: dict[str, tuple[float, float]]) -> pd.DataFrame:
    rows = []
    for p in net.patterns.values():
        for seg in p.segments:
            if seg.from_stop not in coords or seg.to_stop not in coords:
                continue
            ax, ay = coords[seg.from_stop]
            bx, by = coords[seg.to_stop]
            d = float(np.hypot(ax - bx, ay - by))
            if d <= 0 or not np.isfinite(seg.run_time_sec) or seg.run_time_sec <= 0:
                continue
            rows.append({"route_id": p.route_id, "pattern_id": p.pattern_id,
                         "from_stop": seg.from_stop, "to_stop": seg.to_stop,
                         "metres": d, "observed_sec": float(seg.run_time_sec)})
    return pd.DataFrame(rows)


def validate(net: TransitNetwork, stops_projected, n_folds: int = 5,
             seed: int = 20260825) -> ValidationResult:
    """K-fold: refit the estimator without a fold, predict that fold.

    Folds are split by **link**, not by row, so a link that appears on several
    patterns cannot sit in both the training and the held-out set and flatter
    the result.
    """
    model = SegmentTimeModel.fit(net, stops_projected)
    obs = _observations(net, model.coords)
    if obs.empty:
        raise ValueError("no observations to validate against")

    links = obs[["from_stop", "to_stop"]].drop_duplicates().reset_index(drop=True)
    rng = np.random.default_rng(seed)
    links["fold"] = rng.integers(0, n_folds, len(links))
    obs = obs.merge(links, on=["from_stop", "to_stop"], how="left")

    preds = np.full(len(obs), np.nan)
    for f in range(n_folds):
        train = obs[obs["fold"] != f]
        test_idx = np.where(obs["fold"].to_numpy() == f)[0]
        if len(train) == 0 or len(test_idx) == 0:
            continue
        sys_fit = _lsq(train["metres"].to_numpy(), train["observed_sec"].to_numpy())
        per_route = {}
        for rid, grp in train.groupby("route_id"):
            per_route[rid] = (_lsq(grp["metres"].to_numpy(),
                                   grp["observed_sec"].to_numpy())
                              if len(grp) >= SegmentTimeModel.MIN_SEGMENTS
                              else sys_fit)
        sub = obs.iloc[test_idx]
        c = np.array([per_route.get(r, sys_fit)[0] for r in sub["route_id"]])
        m = np.array([per_route.get(r, sys_fit)[1] for r in sub["route_id"]])
        preds[test_idx] = np.maximum(1.0, c + m * sub["metres"].to_numpy())

    obs["predicted_sec"] = preds
    obs = obs[np.isfinite(obs["predicted_sec"])].copy()
    obs["error_sec"] = obs["predicted_sec"] - obs["observed_sec"]
    obs["abs_error_sec"] = obs["error_sec"].abs()
    obs["ape_pct"] = (obs["abs_error_sec"] / obs["observed_sec"]) * 100
    obs["signed_pct"] = (obs["error_sec"] / obs["observed_sec"]) * 100

    long = obs["observed_sec"] >= 30.0
    total_bias = float(obs["error_sec"].sum())
    total_obs = float(obs["observed_sec"].sum())
    summary = {
        "n_links": int(len(obs)),
        "n_folds": n_folds,
        "mae_sec": float(obs["abs_error_sec"].mean()),
        "median_ape_pct": float(obs.loc[long, "ape_pct"].median()),
        "bias_sec_per_link": float(obs["error_sec"].mean()),
        "median_signed_pct": float(obs.loc[long, "signed_pct"].median()),
        # the number that actually matters: does the estimator, applied to a
        # whole alignment, systematically under- or over-state its running time?
        "aggregate_bias_pct": 100.0 * total_bias / total_obs,
        "share_underestimated": float((obs["error_sec"] < 0).mean()),
        "p05_error_sec": float(obs["error_sec"].quantile(0.05)),
        "p95_error_sec": float(obs["error_sec"].quantile(0.95)),
    }

    bins = [0, 100, 200, 400, 800, 1600, np.inf]
    obs["distance_band_m"] = pd.cut(
        obs["metres"], bins,
        labels=["<100", "100-200", "200-400", "400-800", "800-1600", ">1600"])
    by_distance = (obs.groupby("distance_band_m", observed=True)
                   .agg(n=("metres", "size"),
                        mean_observed_sec=("observed_sec", "mean"),
                        mae_sec=("abs_error_sec", "mean"),
                        bias_sec=("error_sec", "mean"),
                        aggregate_bias_pct=("error_sec",
                                            lambda s: 100 * s.sum()
                                            / obs.loc[s.index, "observed_sec"].sum()))
                   .reset_index())
    by_route = (obs.groupby("route_id")
                .agg(n=("metres", "size"),
                     mae_sec=("abs_error_sec", "mean"),
                     bias_sec=("error_sec", "mean"),
                     aggregate_bias_pct=("error_sec",
                                         lambda s: 100 * s.sum()
                                         / obs.loc[s.index, "observed_sec"].sum()))
                .reset_index().sort_values("aggregate_bias_pct"))

    # A single multiplicative correction that would zero the aggregate bias.
    # Estimated here only; adopting it is a separate decision, and it is only
    # legitimate if it is derived out of sample, as this one is.
    calib = {"multiplier_to_zero_aggregate_bias": float(total_obs / (total_obs + total_bias))
             if (total_obs + total_bias) > 0 else 1.0}
    return ValidationResult(obs, summary, by_distance, by_route, calib)


def verdict(summary: dict[str, Any], tol_pct: float = 2.0) -> tuple[str, str]:
    """Classify the estimator's directional bias, which is the exploitable one."""
    b = summary["aggregate_bias_pct"]
    if abs(b) <= tol_pct:
        return ("unbiased", f"aggregate bias {b:+.2f}% is within +/-{tol_pct}%; "
                            "novel-link candidates are not systematically flattered")
    if b < 0:
        return ("underestimates",
                f"aggregate bias {b:+.2f}%: the estimator makes new alignments "
                "look FASTER than they run, which the optimizer can exploit by "
                "buying frequency with running time that does not exist")
    return ("overestimates",
            f"aggregate bias {b:+.2f}%: new alignments are priced slower than "
            "they run, so novel-link candidates are penalised, not flattered")
