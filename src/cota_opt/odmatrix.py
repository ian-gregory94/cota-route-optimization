"""Origin-destination demand at zone level, and the mapping from zones to stops.

Two sources, same output type:

``from_lodes_od``
    Real LEHD LODES origin-destination flows (block to block), aggregated to
    block groups. Preferred — no distance-decay assumption is needed.

``from_gravity``
    Doubly-constrained gravity model built from LODES RAC (workers by residence)
    and WAC (jobs by workplace) with an exponential deterrence function, fitted
    by iterative proportional fitting so row sums reproduce workers and column
    sums reproduce jobs. Used when the OD table is unavailable. The deterrence
    parameter is calibrated to a target mean commute distance rather than
    guessed.

Both are *commute* flows. Non-work travel is not represented; see the data-gap
table.
"""
from __future__ import annotations

import gzip
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


@dataclass
class ZoneSystem:
    """Zones (block groups) with a projected centroid and access stops."""

    zone_ids: list[str]
    index: dict[str, int]
    x: np.ndarray
    y: np.ndarray
    workers: np.ndarray
    jobs: np.ndarray
    # access: zone -> (stop index, walk minutes)
    access_offsets: np.ndarray = field(default_factory=lambda: np.zeros(1, dtype=np.int64))
    access_stop: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    access_walk: np.ndarray = field(default_factory=lambda: np.zeros(0))

    @property
    def n(self) -> int:
        return len(self.zone_ids)

    def access_of(self, z: int) -> tuple[np.ndarray, np.ndarray]:
        a, b = self.access_offsets[z], self.access_offsets[z + 1]
        return self.access_stop[a:b], self.access_walk[a:b]


@dataclass
class ODTable:
    """Sparse OD flows between zone indices."""

    origin: np.ndarray          # zone index
    dest: np.ndarray            # zone index
    flow: np.ndarray            # daily trips
    source: str = "UNKNOWN"
    notes: str = ""

    def total(self) -> float:
        return float(self.flow.sum())

    def __len__(self) -> int:
        return len(self.flow)


def build_zone_system(bg: "pd.DataFrame", stops_projected, radius_m: float,
                      walk_speed_m_per_min: float,
                      stop_index: dict[str, int],
                      max_access_stops: int = 8) -> ZoneSystem:
    """Zones from the block-group frame, each linked to nearby stops."""
    bg = bg[(bg["workers"] > 0) | (bg["jobs"] > 0)].reset_index(drop=True)
    zone_ids = bg["geoid_bg"].astype(str).tolist()
    index = {z: i for i, z in enumerate(zone_ids)}
    x = bg.geometry.x.to_numpy()
    y = bg.geometry.y.to_numpy()

    sp = stops_projected[stops_projected["stop_id"].isin(stop_index)]
    sp = sp.set_index("stop_id")
    order = sorted(stop_index, key=lambda s: stop_index[s])
    sp = sp.loc[[s for s in order if s in sp.index]]
    sgeom = sp.geometry.to_numpy()
    sids = [stop_index[s] for s in sp.index]
    sidx = sp.sindex

    offsets = np.zeros(len(zone_ids) + 1, dtype=np.int64)
    a_stop, a_walk = [], []
    for i, geom in enumerate(bg.geometry):
        cand = list(sidx.query(geom.buffer(radius_m)))
        d = [(k, geom.distance(sgeom[k])) for k in cand]
        d = [(k, dist) for k, dist in d if dist <= radius_m]
        d.sort(key=lambda t: t[1])
        for k, dist in d[:max_access_stops]:
            a_stop.append(sids[k])
            a_walk.append(dist / walk_speed_m_per_min)
        offsets[i + 1] = len(a_stop)

    zs = ZoneSystem(zone_ids=zone_ids, index=index, x=x, y=y,
                    workers=bg["workers"].to_numpy(float),
                    jobs=bg["jobs"].to_numpy(float),
                    access_offsets=offsets,
                    access_stop=np.asarray(a_stop, dtype=np.int64),
                    access_walk=np.asarray(a_walk, float))
    n_with = int((np.diff(offsets) > 0).sum())
    log.info("zones: %d (%d with transit access within %.0f m), %d access links",
             zs.n, n_with, radius_m, len(a_stop))
    return zs


def from_lodes_od(path: Path, zs: ZoneSystem, county_fips: set[str] | None = None,
                  top_k: int | None = None) -> ODTable:
    """Real LODES OD flows, aggregated block→block into block group→block group."""
    opener = gzip.open if str(path).endswith(".gz") else open
    keep_o, keep_d, keep_f = [], [], []
    total_read = 0
    with opener(path, "rt") as f:
        for chunk in pd.read_csv(f, dtype={"w_geocode": str, "h_geocode": str},
                                 usecols=["w_geocode", "h_geocode", "S000"],
                                 chunksize=1_000_000):
            total_read += len(chunk)
            h = chunk["h_geocode"].str.zfill(15)
            w = chunk["w_geocode"].str.zfill(15)
            if county_fips:
                m = h.str[:5].isin(county_fips) & w.str[:5].isin(county_fips)
                chunk, h, w = chunk[m], h[m], w[m]
                if chunk.empty:
                    continue
            oz = h.str[:12].map(zs.index)
            dz = w.str[:12].map(zs.index)
            m = oz.notna() & dz.notna()
            if not m.any():
                continue
            keep_o.append(oz[m].to_numpy(np.int64))
            keep_d.append(dz[m].to_numpy(np.int64))
            keep_f.append(chunk.loc[m, "S000"].to_numpy(float))
    if not keep_o:
        raise ValueError(f"no LODES OD rows matched the zone system in {path}")
    o = np.concatenate(keep_o)
    d = np.concatenate(keep_d)
    fl = np.concatenate(keep_f)
    # collapse duplicate (bg, bg) pairs produced by block aggregation
    key = o.astype(np.int64) * zs.n + d
    uniq, inv = np.unique(key, return_inverse=True)
    flow = np.bincount(inv, weights=fl)
    o2, d2 = (uniq // zs.n).astype(np.int64), (uniq % zs.n).astype(np.int64)
    log.info("LODES OD: %d block rows read, %d block-group pairs, %.0f trips",
             total_read, len(flow), flow.sum())
    od = ODTable(o2, d2, flow, source="LEHD LODES8 2022 OD (JT00 main)",
                 notes="Real block-to-block home→work flows, aggregated to block groups.")
    return _top_k(od, top_k) if top_k else od


def from_gravity(zs: ZoneSystem, mean_trip_km: float = 12.0,
                 max_km: float = 60.0, top_k: int | None = None,
                 iterations: int = 30) -> ODTable:
    """Doubly-constrained gravity model over zones with transit access.

    ``exp(-beta d)`` deterrence, with ``beta`` solved so the flow-weighted mean
    OD distance equals ``mean_trip_km``. Iterative proportional fitting then
    forces row sums to workers and column sums to jobs.
    """
    has_access = np.diff(zs.access_offsets) > 0
    oi = np.flatnonzero(has_access & (zs.workers > 0))
    dj = np.flatnonzero(has_access & (zs.jobs > 0))
    if len(oi) == 0 or len(dj) == 0:
        raise ValueError("no zones with both transit access and demand")

    dx = zs.x[oi][:, None] - zs.x[dj][None, :]
    dy = zs.y[oi][:, None] - zs.y[dj][None, :]
    dist_km = np.sqrt(dx * dx + dy * dy) / 1000.0
    within = dist_km <= max_km

    O = zs.workers[oi].copy()
    D = zs.jobs[dj].copy()
    D = D * (O.sum() / D.sum())          # balance the two margins

    def weighted_mean(beta: float) -> tuple[float, np.ndarray]:
        f = np.where(within, np.exp(-beta * dist_km), 0.0)
        T = _ipf(O, D, f, iterations)
        tot = T.sum()
        return (float((T * dist_km).sum() / tot) if tot > 0 else np.inf), T

    lo, hi = 0.005, 2.0
    T = None
    for _ in range(40):                   # bisection on beta
        mid = 0.5 * (lo + hi)
        m, T = weighted_mean(mid)
        if m > mean_trip_km:
            lo = mid                      # too long -> stronger decay
        else:
            hi = mid
        if abs(m - mean_trip_km) < 0.05:
            break
    beta = 0.5 * (lo + hi)
    log.info("gravity: beta=%.4f per km, mean trip %.2f km (target %.2f)",
             beta, weighted_mean(beta)[0], mean_trip_km)

    nz = np.flatnonzero(T.ravel() > 1e-9)
    rows, cols = np.unravel_index(nz, T.shape)
    od = ODTable(oi[rows], dj[cols], T.ravel()[nz],
                 source="gravity model from LODES RAC/WAC",
                 notes=(f"Doubly-constrained gravity, exp(-{beta:.4f}·d_km) "
                        f"deterrence calibrated to a {mean_trip_km:.1f} km mean "
                        "commute. A modelling assumption, not observed flows."))
    return _top_k(od, top_k) if top_k else od


def _ipf(O: np.ndarray, D: np.ndarray, f: np.ndarray, iters: int) -> np.ndarray:
    a = np.ones_like(O)
    b = np.ones_like(D)
    for _ in range(iters):
        row = (f * b[None, :]).sum(axis=1)
        a = np.divide(O, row, out=np.zeros_like(O), where=row > 0)
        col = (f * a[:, None]).sum(axis=0)
        b = np.divide(D, col, out=np.zeros_like(D), where=col > 0)
    return a[:, None] * f * b[None, :]


def filter_to_accessible(od: ODTable, zs: ZoneSystem) -> ODTable:
    """Keep only OD pairs with a transit stop in walking range at BOTH ends.

    This is the transit-relevant market. Pairs outside it cannot be served by
    any frequency plan, so including them would only dilute the metrics with a
    constant; the share of total commute flow they represent is reported
    separately as a coverage statistic.
    """
    has = np.diff(zs.access_offsets) > 0
    m = has[od.origin] & has[od.dest]
    kept = float(od.flow[m].sum())
    log.info("accessible OD: %d of %d pairs, %.1f%% of commute flow",
             int(m.sum()), len(od), kept / od.total() * 100)
    return ODTable(od.origin[m], od.dest[m], od.flow[m], source=od.source,
                   notes=od.notes + " Restricted to pairs with a stop within "
                                    "walking range at both ends "
                                    f"({kept / od.total() * 100:.1f}% of commute flow).")


def _top_k(od: ODTable, k: int) -> ODTable:
    if len(od) <= k:
        return od
    keep = np.argpartition(-od.flow, k)[:k]
    keep = keep[np.argsort(-od.flow[keep])]
    kept = float(od.flow[keep].sum())
    log.info("OD truncated to top %d pairs of %d — %.1f%% of total flow",
             k, len(od), kept / od.total() * 100)
    out = ODTable(od.origin[keep], od.dest[keep], od.flow[keep],
                  source=od.source,
                  notes=od.notes + f" Truncated to the top {k:,} pairs "
                                   f"({kept / od.total() * 100:.1f}% of flow).")
    return out


def scale_to(od: ODTable, total: float) -> ODTable:
    """Rescale flows so they sum to an assumed daily transit trip total."""
    cur = od.total()
    if cur <= 0:
        raise ValueError("cannot scale an empty OD table")
    return ODTable(od.origin, od.dest, od.flow * (total / cur),
                   source=od.source,
                   notes=od.notes + f" Rescaled to {total:,.0f} daily trips.")


def split_by_period(od: ODTable, shares: dict[str, float]) -> dict[str, ODTable]:
    tot = sum(shares.values())
    if abs(tot - 1.0) > 1e-6:
        raise ValueError(f"period shares must sum to 1.0, got {tot}")
    return {p: ODTable(od.origin, od.dest, od.flow * s, od.source, od.notes)
            for p, s in shares.items()}
