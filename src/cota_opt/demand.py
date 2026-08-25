"""Demand data architecture: Census LEHD LODES → geographic OD → stop access.

Documented path
---------------
1. **Census block home/work flow.** LODES ``od`` gives block→block job flows;
   ``rac`` gives workers by residence block; ``wac`` gives jobs by workplace
   block. This module supports rac/wac (compact, sufficient for stop-catchment
   weights) and defines the OD structure for the full ``od`` table.
2. **Geographic OD demand.** Blocks are aggregated to block groups (GEOID[:12])
   and joined to Census population-weighted block-group centroids, producing
   point-located origin (workers) and destination (jobs) mass.
3. **Future stop-access demand.** Each block-group centroid's mass is allocated
   to transit stops within a catchment radius (config), distance-decayed. The
   result is a per-stop origin/destination weight used as a *demand proxy*.

This is a proxy, not observed ridership. It is labeled as such everywhere it is
consumed. No normative demographic weighting is embedded in the optimization.
"""
from __future__ import annotations

import gzip
import logging
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

log = logging.getLogger(__name__)

GEOGRAPHIC = "EPSG:4326"


@dataclass(frozen=True)
class ODFlow:
    """One origin→destination demand record."""

    origin_geoid: str
    dest_geoid: str
    flow: float
    time_category: str = "ALL"      # e.g. am_peak, once temporally disaggregated


@dataclass
class ODMatrix:
    """Geographic OD demand. Long form to stay sparse."""

    flows: pd.DataFrame              # origin_geoid, dest_geoid, flow, time_category
    geography: str = "block_group"
    source: str = "UNKNOWN"

    def total(self) -> float:
        return float(self.flows["flow"].sum())


def read_lodes(path: Path, geo_col: str) -> pd.DataFrame:
    """Read a LODES rac/wac CSV(.gz). Returns [geoid_block, total_jobs]."""
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as f:
        df = pd.read_csv(f, dtype={geo_col: str})
    if geo_col not in df.columns or "C000" not in df.columns:
        raise ValueError(f"unexpected LODES schema in {path}: {list(df.columns)[:8]}")
    return df[[geo_col, "C000"]].rename(columns={geo_col: "geoid_block",
                                                 "C000": "total"})


def to_block_groups(df: pd.DataFrame, county_fips: set[str] | None = None
                    ) -> pd.DataFrame:
    """Aggregate block-level totals to block groups (GEOID[:12])."""
    d = df.copy()
    d["geoid_block"] = d["geoid_block"].astype(str).str.zfill(15)
    if county_fips:
        d = d[d["geoid_block"].str[:5].isin(county_fips)]
    d["geoid_bg"] = d["geoid_block"].str[:12]
    return d.groupby("geoid_bg", as_index=False)["total"].sum()


def read_bg_centroids(path: Path) -> pd.DataFrame:
    """Census ``CenPop2020_Mean_BG*.txt`` → [geoid_bg, population, lat, lon]."""
    df = pd.read_csv(path, dtype=str)
    cols = {c.upper(): c for c in df.columns}
    need = ["STATEFP", "COUNTYFP", "TRACTCE", "BLKGRPCE", "POPULATION",
            "LATITUDE", "LONGITUDE"]
    missing = [c for c in need if c not in cols]
    if missing:
        raise ValueError(f"centroid file missing columns {missing}")
    out = pd.DataFrame({
        "geoid_bg": (df[cols["STATEFP"]].str.zfill(2) + df[cols["COUNTYFP"]].str.zfill(3)
                     + df[cols["TRACTCE"]].str.zfill(6) + df[cols["BLKGRPCE"]].str.zfill(1)),
        "population": pd.to_numeric(df[cols["POPULATION"]], errors="coerce"),
        "lat": pd.to_numeric(df[cols["LATITUDE"]], errors="coerce"),
        "lon": pd.to_numeric(df[cols["LONGITUDE"]], errors="coerce"),
    })
    return out.dropna(subset=["lat", "lon"])


def build_bg_frame(centroids: pd.DataFrame, workers_bg: pd.DataFrame,
                   jobs_bg: pd.DataFrame, projected: str) -> gpd.GeoDataFrame:
    """Join workers (RAC) and jobs (WAC) onto block-group centroids."""
    df = centroids.merge(workers_bg.rename(columns={"total": "workers"}),
                         on="geoid_bg", how="left")
    df = df.merge(jobs_bg.rename(columns={"total": "jobs"}),
                  on="geoid_bg", how="left")
    df[["workers", "jobs"]] = df[["workers", "jobs"]].fillna(0.0)
    g = gpd.GeoDataFrame(df, geometry=[Point(xy) for xy in zip(df["lon"], df["lat"])],
                         crs=GEOGRAPHIC)
    return g.to_crs(projected)


def allocate_to_stops(bg: gpd.GeoDataFrame, stops: gpd.GeoDataFrame,
                      radius_m: float) -> pd.DataFrame:
    """Distance-decayed allocation of block-group mass to stops in catchment.

    Each block group's workers/jobs are split among stops within ``radius_m``
    with weights ``(1 - d/radius)``; mass with no stop in range is retained as
    ``unreachable`` (it is demand the network does not touch at all).
    Returns [stop_id, workers_access, jobs_access] plus an attrs dict of totals.
    """
    if stops.crs != bg.crs:
        raise ValueError(f"CRS mismatch: stops {stops.crs} vs bg {bg.crs}")
    if not stops.crs.is_projected:
        raise ValueError("stop allocation requires a projected CRS (meters)")
    sidx = stops.sindex
    acc_w: dict[str, float] = {}
    acc_j: dict[str, float] = {}
    unreachable_w = unreachable_j = 0.0
    stop_ids = stops["stop_id"].to_numpy()
    stop_geom = stops.geometry.to_numpy()
    for geom, w, j in zip(bg.geometry, bg["workers"], bg["jobs"]):
        if w <= 0 and j <= 0:
            continue
        cand = list(sidx.query(geom.buffer(radius_m)))
        if not cand:
            unreachable_w += w
            unreachable_j += j
            continue
        d = np.array([geom.distance(stop_geom[i]) for i in cand])
        keep = d <= radius_m
        if not keep.any():
            unreachable_w += w
            unreachable_j += j
            continue
        cand = np.asarray(cand)[keep]
        wts = 1.0 - d[keep] / radius_m
        s = wts.sum()
        if s <= 0:
            unreachable_w += w
            unreachable_j += j
            continue
        wts = wts / s
        for i, frac in zip(cand, wts):
            sid = stop_ids[i]
            acc_w[sid] = acc_w.get(sid, 0.0) + w * frac
            acc_j[sid] = acc_j.get(sid, 0.0) + j * frac
    out = pd.DataFrame({
        "stop_id": sorted(set(acc_w) | set(acc_j)),
    })
    out["workers_access"] = out["stop_id"].map(acc_w).fillna(0.0)
    out["jobs_access"] = out["stop_id"].map(acc_j).fillna(0.0)
    out.attrs["unreachable_workers"] = unreachable_w
    out.attrs["unreachable_jobs"] = unreachable_j
    out.attrs["total_workers"] = float(bg["workers"].sum())
    out.attrs["total_jobs"] = float(bg["jobs"].sum())
    out.attrs["catchment_radius_m"] = radius_m
    return out


def route_demand_proxy(stop_access: pd.DataFrame, stop_routes: dict[str, set[str]],
                       resident_weight: float = 1.0, job_weight: float = 1.0,
                       ) -> pd.DataFrame:
    """Per-route daily demand potential from stop access weights.

    A stop's demand mass is split evenly among the routes serving it, so a stop
    served by three routes does not count three times. The result is a
    *relative* daily boarding potential, not an absolute ridership forecast.
    """
    rows: dict[str, float] = {}
    for sid, w, j in zip(stop_access["stop_id"], stop_access["workers_access"],
                         stop_access["jobs_access"]):
        routes = stop_routes.get(sid)
        if not routes:
            continue
        mass = resident_weight * w + job_weight * j
        share = mass / len(routes)
        for r in routes:
            rows[r] = rows.get(r, 0.0) + share
    df = pd.DataFrame({"route_id": list(rows), "demand_potential": list(rows.values())})
    return df.sort_values("demand_potential", ascending=False).reset_index(drop=True)


def split_by_period(route_demand: pd.DataFrame,
                    period_shares: dict[str, float]) -> pd.DataFrame:
    """Expand route demand across service periods using configured shares."""
    tot = sum(period_shares.values())
    if abs(tot - 1.0) > 1e-6:
        raise ValueError(f"period_shares must sum to 1.0, got {tot}")
    rows = []
    for _, r in route_demand.iterrows():
        for p, share in period_shares.items():
            rows.append({"route_id": r["route_id"], "period": p,
                         "demand_potential": float(r["demand_potential"]) * share})
    return pd.DataFrame(rows)
