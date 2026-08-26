"""What does serving one more stop actually cost, according to COTA's own schedule?

Experiment 3 will trade passenger walking against vehicle running time. The
exchange rate is the time a bus loses by serving an extra stop, and getting it
from a textbook dwell figure would make the whole experiment an artifact of that
figure -- the optimizer would consolidate exactly as aggressively as the assumed
penalty rewards.

COTA's schedule contains its own natural experiments. Where two patterns of the
same route traverse the same corridor and one serves stops the other skips, the
scheduled running-time difference over the shared segment is a measurement of
what those stops cost. No dwell assumption is required.

    Pattern A:  X - a - b - c - Y      scheduled 14 min
    Pattern B:  X - - - b - - - Y      scheduled 11 min
                                       => 2 extra stops cost 3 min

What this measures is a **scheduled stop-service penalty**, not passenger dwell.
It bundles deceleration, door time, boarding, acceleration, and whatever
recovery padding the scheduler wrote in. That is the right quantity for this
model, because the model's currency is scheduled running time -- but it is not
a behavioural dwell estimate and is not labelled as one.

Comparisons are only used when the two patterns share both endpoints of the
segment, run the same route and direction, and overlap in period, so corridor,
geometry, and traffic conditions are held as close to fixed as a schedule
allows. Everything else is reported with its uncertainty rather than averaged
into a single confident number.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


@dataclass
class StopPenalty:
    comparisons: pd.DataFrame
    summary: dict[str, Any]
    by_route: pd.DataFrame
    by_period: pd.DataFrame


def _pattern_index(net) -> dict[str, dict[str, int]]:
    return {pid: {s: i for i, s in enumerate(p.stops)}
            for pid, p in net.patterns.items()}


def _cum_seconds(p) -> np.ndarray:
    return np.concatenate([[0.0], np.cumsum([s.run_time_sec for s in p.segments])])


def find_comparisons(net, tstats: pd.DataFrame,
                     periods_of_pattern: dict[str, set[str]] | None = None,
                     min_shared_stops: int = 2,
                     min_segment_sec: float = 120.0,
                     max_skipped: int = 12,
                     require_shared_period: bool = True) -> pd.DataFrame:
    """Same route, same direction, shared endpoints, different stops between.

    For every pair of patterns on a route and direction, find the maximal
    stretch bounded by two stops they both serve, and record how many stops one
    serves that the other does not, together with the scheduled time each takes
    over that stretch.
    """
    idx = _pattern_index(net)
    cums = {pid: _cum_seconds(p) for pid, p in net.patterns.items()}
    trips = tstats.groupby("pattern_id").size().to_dict()

    by_rd: dict[tuple[str, int], list[str]] = {}
    for pid, p in net.patterns.items():
        by_rd.setdefault((p.route_id, p.direction_id), []).append(pid)

    rows = []
    for (route, direction), pids in by_rd.items():
        for i in range(len(pids)):
            for j in range(len(pids)):
                if i == j:
                    continue
                pa, pb = pids[i], pids[j]           # a serves more, we hope
                A, B = net.patterns[pa], net.patterns[pb]
                shared = [s for s in A.stops if s in idx[pb]]
                if len(shared) < min_shared_stops:
                    continue
                # keep shared stops that appear in the same order on both
                order_a = [idx[pa][s] for s in shared]
                order_b = [idx[pb][s] for s in shared]
                if not (np.all(np.diff(order_a) > 0) and np.all(np.diff(order_b) > 0)):
                    continue
                x, y = shared[0], shared[-1]
                ax, ay = idx[pa][x], idx[pa][y]
                bx, by = idx[pb][x], idx[pb][y]
                sec_a = float(cums[pa][ay] - cums[pa][ax])
                sec_b = float(cums[pb][by] - cums[pb][bx])
                if sec_a < min_segment_sec or sec_b < min_segment_sec:
                    continue
                stops_a = A.stops[ax:ay + 1]
                stops_b = B.stops[bx:by + 1]
                extra = [s for s in stops_a if s not in set(stops_b)]
                if not extra or len(extra) > max_skipped:
                    continue
                # B must not add stops of its own, or the difference is not
                # attributable to A's extra stops alone
                if any(s not in set(stops_a) for s in stops_b):
                    continue
                pers = ((periods_of_pattern or {}).get(pa, set())
                        & (periods_of_pattern or {}).get(pb, set()))
                # Without this, a peak pattern is compared against a midday one
                # and the traffic difference is booked as a stop penalty. It is
                # a partial control only: segment times in the network
                # abstraction are medians across all of a pattern's trips, so
                # two patterns can still sit at different points inside a
                # period. Fully removing the confound needs per-period segment
                # times, which the current network does not carry.
                if require_shared_period and periods_of_pattern is not None \
                        and not pers:
                    continue
                rows.append({
                    "route_id": route, "direction_id": direction,
                    "pattern_more": pa, "pattern_fewer": pb,
                    "from_stop": x, "to_stop": y,
                    "n_stops_more": len(stops_a), "n_stops_fewer": len(stops_b),
                    "n_extra_stops": len(extra),
                    "extra_stops": "+".join(extra),
                    "seconds_more": sec_a, "seconds_fewer": sec_b,
                    "seconds_difference": sec_a - sec_b,
                    "seconds_per_extra_stop": (sec_a - sec_b) / len(extra),
                    "trips_more": int(trips.get(pa, 0)),
                    "trips_fewer": int(trips.get(pb, 0)),
                    "shared_periods": "+".join(sorted(pers)),
                    "n_shared_periods": len(pers),
                })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # each unordered pair appears twice; keep the direction where one pattern
    # genuinely serves more stops
    return df[df["n_stops_more"] > df["n_stops_fewer"]].reset_index(drop=True)


def estimate(comparisons: pd.DataFrame,
             drop_negative: bool = False) -> StopPenalty:
    """Seconds per extra stop, with its spread and what it is not.

    Negative observations are **kept** by default. A pattern serving more stops
    can be scheduled faster -- different recovery padding, a different time of
    day, a genuinely faster alignment -- and dropping those would bias the
    estimate upward, which is the direction that makes stop consolidation look
    better than it is.
    """
    if comparisons.empty:
        return StopPenalty(comparisons,
                           {"n_comparisons": 0,
                            "note": "no usable natural experiment in this feed"},
                           pd.DataFrame(), pd.DataFrame())
    d = comparisons
    if drop_negative:
        d = d[d["seconds_difference"] > 0]
    v = d["seconds_per_extra_stop"].to_numpy(float)
    # weight by how many stops the comparison actually distinguishes: a
    # ten-stop difference measures the penalty better than a one-stop one
    w = d["n_extra_stops"].to_numpy(float)
    pooled = float((d["seconds_difference"].sum() / d["n_extra_stops"].sum()))
    summary = {
        "n_comparisons": int(len(d)),
        "n_routes": int(d["route_id"].nunique()),
        "total_extra_stops_observed": int(d["n_extra_stops"].sum()),
        "median_sec_per_stop": float(np.median(v)),
        "mean_sec_per_stop": float(np.average(v, weights=w)),
        "pooled_sec_per_stop": pooled,
        "p25_sec_per_stop": float(np.percentile(v, 25)),
        "p75_sec_per_stop": float(np.percentile(v, 75)),
        "share_negative": float((v < 0).mean()),
        "negatives_kept": not drop_negative,
        "interpretation": ("scheduled stop-service penalty: deceleration, door "
                           "time, boarding, acceleration and schedule padding "
                           "combined. NOT a passenger dwell estimate."),
    }
    def agg(by):
        g = (d.groupby(by)
             .agg(n=("seconds_per_extra_stop", "size"),
                  extra_stops=("n_extra_stops", "sum"),
                  median_sec=("seconds_per_extra_stop", "median"),
                  pooled_sec=("seconds_difference", "sum"))
             .reset_index())
        g["pooled_sec"] = g["pooled_sec"] / g["extra_stops"]
        return g.sort_values("n", ascending=False)
    return StopPenalty(d, summary, agg("route_id"),
                       agg("n_shared_periods") if "n_shared_periods" in d
                       else pd.DataFrame())


def validate(comparisons: pd.DataFrame, n_folds: int = 5,
             seed: int = 20260825) -> dict[str, Any]:
    """Held out by route: can the pooled penalty predict a route it never saw?

    Splitting by route rather than by row is the point. Two comparisons from
    the same route share its corridor, its traffic and its scheduler's padding
    habits, so a row-wise split would let the estimate memorise the route and
    report an accuracy it does not have on a new one.
    """
    if comparisons.empty or comparisons["route_id"].nunique() < n_folds:
        return {"n_folds": 0,
                "note": "too few routes with a natural experiment to hold out"}
    routes = comparisons["route_id"].drop_duplicates().to_numpy()
    rng = np.random.default_rng(seed)
    fold = {r: int(f) for r, f in zip(routes, rng.integers(0, n_folds, len(routes)))}
    d = comparisons.assign(fold=comparisons["route_id"].map(fold))

    preds = np.full(len(d), np.nan)
    for f in range(n_folds):
        train, test = d[d["fold"] != f], np.flatnonzero(d["fold"].to_numpy() == f)
        if train.empty or len(test) == 0:
            continue
        pooled = float(train["seconds_difference"].sum()
                       / train["n_extra_stops"].sum())
        preds[test] = pooled * d["n_extra_stops"].to_numpy()[test]

    ok = np.isfinite(preds)
    err = preds[ok] - d["seconds_difference"].to_numpy()[ok]
    obs = d["seconds_difference"].to_numpy()[ok]
    return {
        "n_folds": n_folds,
        "n_held_out": int(ok.sum()),
        "n_routes": int(len(routes)),
        "mae_sec": float(np.mean(np.abs(err))),
        "median_abs_error_sec": float(np.median(np.abs(err))),
        "bias_sec": float(np.mean(err)),
        "aggregate_bias_pct": float(100.0 * err.sum() / obs.sum())
        if obs.sum() else np.nan,
        "share_overpredicted": float((err > 0).mean()),
        # overprediction of the time an extra stop costs is the exploitable
        # direction: it makes removing stops look like it saves more than it does
        "exploitable_direction": "over-prediction of the saving from removing "
                                 "stops; positive aggregate bias means the "
                                 "estimate flatters consolidation",
    }


def verdict(summary: dict[str, Any], validation: dict[str, Any],
            tol_pct: float = 15.0) -> tuple[str, str]:
    """Is COTA's own schedule enough to price a stop, or is an assumption needed?"""
    n = summary.get("n_comparisons", 0)
    pooled = summary.get("pooled_sec_per_stop", float("nan"))
    # An inverted sign disqualifies the estimate whether or not validation
    # ran: there is no point holding out folds of a measurement that says
    # serving more stops makes a bus faster.
    if n and np.isfinite(pooled) and pooled <= 0:
        return ("insufficient",
                f"the pooled estimate is {pooled:+.0f} s per extra stop across "
                f"{n} comparisons -- patterns serving MORE stops are scheduled "
                "faster, which no dwell penalty can produce. These comparisons "
                "are measuring something other than stop cost, so this feed "
                "cannot price a stop and any Experiment 3 consolidation result "
                "would rest on an assumed penalty rather than a measured one")
    if n == 0:
        return ("insufficient",
                "the feed contains no usable same-route stop-skipping "
                "comparison; a stop penalty would have to be assumed, and any "
                "Experiment 3 result would inherit that assumption")
    if validation.get("n_folds", 0) == 0:
        return ("unvalidated",
                f"{n} comparisons exist but too few routes to hold one out; "
                "the estimate is descriptive only")
    b = validation.get("aggregate_bias_pct", np.nan)
    if np.isfinite(b) and abs(b) <= tol_pct:
        return ("usable",
                f"{n} comparisons across {summary['n_routes']} routes, pooled "
                f"{summary['pooled_sec_per_stop']:.1f} s per extra stop, "
                f"held-out aggregate bias {b:+.1f}% -- COTA's own schedule can "
                "price a stop without a dwell assumption")
    return ("biased",
            f"held-out aggregate bias {b:+.1f}% exceeds +/-{tol_pct:.0f}%: the "
            "pooled penalty does not transfer between routes, so a single "
            "system-wide figure would be misleading")
