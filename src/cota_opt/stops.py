"""Experiment 3 infrastructure: what COTA's stop network actually looks like.

Experiment 3 will eventually ask whether stop placement and transfer design
have anything left to give after frequency (Experiment 1) and limited route
geometry (Experiment 2) have been optimized. Nothing here answers that. This
module builds the descriptive base a later optimization would need, and it is
deliberately conservative about what counts as evidence that a stop could go.

The trap this module exists to avoid is treating proximity as redundancy. Two
stops 120 m apart on opposite sides of a freeway are not interchangeable, and
a stop that is the only access a block group has is not a duplicate of anything
however close its neighbour is. So every stop carries what would actually be
lost, not just how close the next one is.

Distance basis, stated because it bounds every conclusion drawn from this:

* **along-route spacing** uses ``shape_dist_traveled`` where the feed provides
  it, which is exact; otherwise straight-line between consecutive stops, which
  understates it. The column says which.
* **walking distance between stops** comes from the router's footpath set,
  which is straight-line within a radius plus whatever ``transfers.txt``
  declares. It has **no pedestrian network and no barriers** -- no rivers, rail,
  freeways, or missing crossings. Every walking figure here is therefore a
  lower bound on real walking effort, and a stop pair this module calls
  "close" may be operationally distant. Fixing that needs an outside
  pedestrian network and is recorded as a limitation, not papered over.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

#: descriptive spacing bands, for counting only. Nothing is a deletion rule.
SPACING_BANDS_M = (150.0, 200.0, 300.0, 400.0)


# ---------------------------------------------------------------------------
# along-route spacing
# ---------------------------------------------------------------------------

def along_route_distances(feed, tstats: pd.DataFrame, net,
                          coords: dict[str, tuple[float, float]],
                          sdt_to_metres: float | None = None) -> pd.DataFrame:
    """Distance between consecutive stops, per pattern.

    ``shape_dist_traveled`` is used when the feed carries it -- COTA's is in
    kilometres, a unit error caught earlier by comparing against projected
    geometry -- and straight-line otherwise. ``distance_basis`` records which,
    because a straight-line figure understates a curving street and any
    conclusion about "closely spaced stops" inherits that.
    """
    st = feed.stop_times
    have_sdt = "shape_dist_traveled" in st.columns and sdt_to_metres
    rep: dict[str, pd.DataFrame] = {}
    if have_sdt:
        first = (tstats.sort_values("first_dep_sec")
                 .drop_duplicates("pattern_id")[["trip_id", "pattern_id"]])
        sub = st[st["trip_id"].isin(first["trip_id"])].merge(
            first, on="trip_id").sort_values(["pattern_id", "stop_sequence"])
        for pid, g in sub.groupby("pattern_id"):
            rep[pid] = g

    rows = []
    for pid, p in net.patterns.items():
        basis, dists = "straight_line", None
        g = rep.get(pid)
        if g is not None and len(g) == len(p.stops):
            v = g["shape_dist_traveled"].to_numpy(float)
            # the first stop is the origin: some feeds leave it blank rather
            # than writing 0, and rejecting the whole pattern for that one
            # missing zero threw away every exact distance in this feed
            if len(v) and not np.isfinite(v[0]) and np.all(np.isfinite(v[1:])):
                v = v.copy()
                v[0] = 0.0
            if np.all(np.isfinite(v)):
                d = np.diff(v) * sdt_to_metres
                if np.all(d >= 0):
                    dists, basis = d, "shape_dist_traveled"
        if dists is None:
            dists = np.array([
                float(np.hypot(coords[a][0] - coords[b][0],
                               coords[a][1] - coords[b][1]))
                if a in coords and b in coords else np.nan
                for a, b in zip(p.stops, p.stops[1:])])
        for i, (a, b) in enumerate(zip(p.stops, p.stops[1:])):
            rows.append({"pattern_id": pid, "route_id": p.route_id,
                         "direction_id": p.direction_id, "seq": i,
                         "from_stop": a, "to_stop": b,
                         "metres": float(dists[i]),
                         "run_time_sec": float(p.segments[i].run_time_sec)
                         if i < len(p.segments) else np.nan,
                         "distance_basis": basis,
                         "n_trips": p.n_trips})
    return pd.DataFrame(rows)


def spacing_summary(spacing: pd.DataFrame,
                    bands: tuple[float, ...] = SPACING_BANDS_M) -> pd.DataFrame:
    """Descriptive distribution per route. Counts, not candidates."""
    d = spacing.dropna(subset=["metres"])
    out = (d.groupby("route_id")
           .agg(n_pairs=("metres", "size"),
                median_m=("metres", "median"),
                q25_m=("metres", lambda s: s.quantile(0.25)),
                q75_m=("metres", lambda s: s.quantile(0.75)),
                basis=("distance_basis", lambda s: s.mode().iat[0]))
           .reset_index())
    for b in bands:
        out[f"pairs_under_{int(b)}m"] = (
            d[d["metres"] < b].groupby("route_id").size()
            .reindex(out["route_id"]).fillna(0).astype(int).to_numpy())
    return out.sort_values("median_m")


# ---------------------------------------------------------------------------
# catchments and what a stop uniquely provides
# ---------------------------------------------------------------------------

@dataclass
class Catchments:
    """Which zones reach which stops, and how much flow rides on that."""

    stops_of_zone: dict[int, np.ndarray]
    zones_of_stop: dict[int, list[int]]
    zone_flow: np.ndarray
    #: flow attributed to a stop, split evenly among a zone's access stops
    stop_flow: np.ndarray
    #: flow whose ONLY access is this stop -- what disappears if it goes
    stop_unique_flow: np.ndarray


def build_catchments(zs, n_stops: int, zone_flow: np.ndarray) -> Catchments:
    stops_of_zone: dict[int, np.ndarray] = {}
    zones_of_stop: dict[int, list[int]] = {}
    stop_flow = np.zeros(n_stops)
    unique = np.zeros(n_stops)
    for z in range(zs.n):
        s, _ = zs.access_of(z)
        if len(s) == 0:
            continue
        stops_of_zone[z] = s
        share = float(zone_flow[z]) / len(s)
        for si in s:
            si = int(si)
            zones_of_stop.setdefault(si, []).append(z)
            stop_flow[si] += share
        if len(s) == 1:
            unique[int(s[0])] += float(zone_flow[z])
    return Catchments(stops_of_zone, zones_of_stop, zone_flow, stop_flow, unique)


def overlap(cat: Catchments, a: int, b: int) -> dict[str, float]:
    """Catchment overlap between two stops, spatial and demand-weighted."""
    za = set(cat.zones_of_stop.get(a, []))
    zb = set(cat.zones_of_stop.get(b, []))
    if not za or not zb:
        return {"zone_overlap": 0.0, "flow_overlap": 0.0,
                "flow_only_a": 0.0, "flow_only_b": 0.0}
    both = za & zb
    fa = sum(cat.zone_flow[z] for z in za)
    fb = sum(cat.zone_flow[z] for z in zb)
    fboth = sum(cat.zone_flow[z] for z in both)
    return {
        "zone_overlap": len(both) / len(za | zb),
        "flow_overlap": fboth / max(1e-9, fa + fb - fboth),
        "flow_only_a": fa - fboth,
        "flow_only_b": fb - fboth,
    }


# ---------------------------------------------------------------------------
# the audit
# ---------------------------------------------------------------------------

def neighbours(rn, si: int) -> list[tuple[int, float]]:
    """Stops reachable on foot from ``si``, with walking minutes.

    From the router's footpath set: straight-line within the walk radius plus
    ``transfers.txt``. No pedestrian network, no barriers -- see the module
    docstring. These are lower bounds on real walking effort.
    """
    a, b = rn.fp_offsets[si], rn.fp_offsets[si + 1]
    return [(int(rn.fp_to[k]), float(rn.fp_min[k])) for k in range(a, b)]


def audit(rn, net, tstats: pd.DataFrame, zs, zone_flow: np.ndarray,
          spacing: pd.DataFrame, periods: dict[str, tuple[float, float]],
          stop_names: dict[str, str], stop_lonlat: dict[str, tuple[float, float]],
          ) -> tuple[pd.DataFrame, Catchments]:
    """One row per served stop: service, catchment, and what it uniquely provides."""
    cat = build_catchments(zs, rn.n_stops, zone_flow)

    ts = tstats.copy()
    if "period" not in ts.columns:
        from .configs import period_of_seconds
        ts["period"] = ts["first_dep_sec"].map(
            lambda s: period_of_seconds(s, periods))
    trips_of_pattern = ts.groupby("pattern_id").size().to_dict()
    periods_of_pattern = (ts.dropna(subset=["period"]).groupby("pattern_id")
                          ["period"].apply(lambda s: sorted(set(s))).to_dict())

    by_stop: dict[str, dict[str, Any]] = {}
    for pid, p in net.patterns.items():
        n_tr = int(trips_of_pattern.get(pid, 0))
        pers = periods_of_pattern.get(pid, [])
        for pos, s in enumerate(p.stops):
            rec = by_stop.setdefault(s, {
                "routes": set(), "patterns": set(), "directions": set(),
                "trips": 0, "periods": set(), "terminal_of": set()})
            rec["routes"].add(p.route_id)
            rec["patterns"].add(pid)
            rec["directions"].add(p.direction_id)
            rec["trips"] += n_tr
            rec["periods"].update(pers)
            if pos in (0, len(p.stops) - 1):
                rec["terminal_of"].add(p.route_id)

    sp = spacing.dropna(subset=["metres"])
    prev_m = sp.groupby("to_stop")["metres"].min().to_dict()
    next_m = sp.groupby("from_stop")["metres"].min().to_dict()

    rows = []
    for s, rec in by_stop.items():
        si = rn.stop_index.get(s)
        if si is None:
            continue
        nb = [(j, w) for j, w in neighbours(rn, si) if j != si]
        nb.sort(key=lambda t: t[1])
        nearest = nb[0] if nb else None
        zones = cat.zones_of_stop.get(si, [])
        ov = overlap(cat, si, nearest[0]) if nearest else {
            "zone_overlap": 0.0, "flow_overlap": 0.0}
        lon, lat = stop_lonlat.get(s, (np.nan, np.nan))
        rows.append({
            "stop_id": s,
            "stop_name": stop_names.get(s, s),
            "lon": lon, "lat": lat,
            "n_routes": len(rec["routes"]),
            "routes": "+".join(sorted(rec["routes"])),
            "n_patterns": len(rec["patterns"]),
            "n_directions": len(rec["directions"]),
            "daily_trips": rec["trips"],
            "n_periods": len(rec["periods"]),
            "periods": "+".join(sorted(rec["periods"])),
            "is_terminal": bool(rec["terminal_of"]),
            "terminal_of": "+".join(sorted(rec["terminal_of"])),
            "is_transfer_point": len(rec["routes"]) > 1,
            # spacing along the routes that serve it
            "prev_spacing_m": prev_m.get(s, np.nan),
            "next_spacing_m": next_m.get(s, np.nan),
            # walking alternatives (lower bound: no barriers modelled)
            "n_walk_neighbours": len(nb),
            "nearest_stop_id": rn.stop_ids[nearest[0]] if nearest else None,
            "nearest_walk_min": nearest[1] if nearest else np.nan,
            # demand
            "n_zones_in_catchment": len(zones),
            "catchment_flow": float(cat.stop_flow[si]),
            "unique_flow": float(cat.stop_unique_flow[si]),
            "zone_overlap_with_nearest": ov["zone_overlap"],
            "flow_overlap_with_nearest": ov["flow_overlap"],
            "distance_basis": (sp[(sp["from_stop"] == s) | (sp["to_stop"] == s)]
                               ["distance_basis"].mode().iat[0]
                               if ((sp["from_stop"] == s) | (sp["to_stop"] == s)).any()
                               else "none"),
        })
    df = pd.DataFrame(rows)
    df["protected"] = protection_flags(df)
    return df.sort_values("daily_trips", ascending=False).reset_index(drop=True), cat


def protection_flags(df: pd.DataFrame, walk_alt_min: float = 5.0,
                     unique_flow_floor: float = 1.0) -> pd.Series:
    """Reasons a stop should not enter the primary consolidation pool.

    Conservative on purpose: a stop is kept out of the candidate pool for any
    of these, and the reason is recorded so a planner can disagree with a
    specific rule rather than with an opaque filter. Protection is not a claim
    that the stop is valuable -- only that this analysis cannot show it is
    disposable.
    """
    reasons = []
    for r in df.itertuples():
        why = []
        if r.is_terminal:
            why.append("terminal")
        if r.unique_flow >= unique_flow_floor:
            why.append(f"only access for {r.unique_flow:,.0f} daily trips")
        if not np.isfinite(r.nearest_walk_min) or r.nearest_walk_min > walk_alt_min:
            why.append("no walking alternative within "
                       f"{walk_alt_min:.0f} min")
        if r.n_routes > 1:
            why.append(f"transfer point ({r.n_routes} routes)")
        if r.n_zones_in_catchment == 0:
            why.append("catchment not reconstructable")
        reasons.append("; ".join(why))
    return pd.Series(reasons, index=df.index)


def summary(df: pd.DataFrame, spacing: pd.DataFrame) -> dict[str, Any]:
    d = spacing.dropna(subset=["metres"])
    out: dict[str, Any] = {
        "n_stops_served": int(len(df)),
        "n_transfer_points": int(df["is_transfer_point"].sum()),
        "n_terminals": int(df["is_terminal"].sum()),
        "n_protected": int((df["protected"] != "").sum()),
        "n_unprotected": int((df["protected"] == "").sum()),
        "median_spacing_m": float(d["metres"].median()),
        "distance_basis": d["distance_basis"].mode().iat[0] if len(d) else "none",
        "median_nearest_walk_min": float(df["nearest_walk_min"].median()),
        "stops_with_no_walk_alternative": int(
            (~np.isfinite(df["nearest_walk_min"])).sum()),
        "stops_that_are_sole_access": int((df["unique_flow"] > 0).sum()),
        "flow_with_sole_access": float(df["unique_flow"].sum()),
    }
    for b in SPACING_BANDS_M:
        out[f"pairs_under_{int(b)}m"] = int((d["metres"] < b).sum())
        out[f"share_under_{int(b)}m"] = float((d["metres"] < b).mean())
    return out
