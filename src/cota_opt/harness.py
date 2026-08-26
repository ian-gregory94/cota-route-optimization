"""One cached entry point for the expensive build chain.

Every experiment needs the same stack: GTFS baseline, RAPTOR network, zone
system, OD table, per-period path sets, and a configured model. Building that
takes ~12 minutes; caching it makes properly-searched experiments affordable,
which is the difference between measuring a result and manufacturing one.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from . import geo
from .baseline import CENTRAL_OHIO_FIPS, build_baseline
from .cache import cached
from .configs import period_of_seconds, service_periods
from .exp2 import Exp2Setup, build_setup
from .odmatrix import (_top_k, build_zone_system, filter_to_accessible,
                       from_lodes_od, scale_to)
from .raptor import build_raptor_network
from .registry import Registry
from .routeclass import classify_routes

log = logging.getLogger(__name__)

UPLOADS = Path("/mnt/user-data/uploads/Downloads")
DEMAND_FILES = {"rac": UPLOADS / "oh_rac_S000_JT00_2022.csv.gz",
                "wac": UPLOADS / "oh_wac_S000_JT00_2022.csv.gz",
                "centroids": UPLOADS / "CenPop2020_Mean_BG39.txt"}


@dataclass
class Harness:
    baseline: Any
    raptor: Any
    zones: Any
    od: Any
    classes: dict
    pathsets: dict
    assumptions: dict
    common_lines: str = "pattern"

    def setup(self, with_crowding: bool, lock_classes: tuple[str, ...],
              seed: int = 20260825,
              pathsets: dict | None = None) -> Exp2Setup:
        return build_setup(self.baseline, self.raptor, self.zones, self.od,
                           seed=seed, route_classes=self.classes,
                           with_crowding=with_crowding,
                           lock_classes=lock_classes,
                           common_lines=self.common_lines,
                           pathset_cache=pathsets if pathsets is not None
                           else self.pathsets)

    def pathsets_with(self, extra_scenarios: list[tuple[str, dict]],
                      tag: str, seed: int = 20260825,
                      use_cache: bool = True) -> dict:
        """Path sets enumerated with extra headway scenarios folded in.

        ``tag`` must identify the scenario list exactly -- it is the cache key,
        so two different scenario lists sharing a tag would silently return
        each other's path sets.
        """
        fp = _gtfs_fingerprint()
        pa = self.assumptions["path_assignment"]
        od_rec = Registry().get("lodes_od_oh")
        return cached("pathsets", {"gtfs": fp,
                                   "lodes": od_rec.sha256[:16] if od_rec else "NA",
                                   "top_k": pa["od_top_k"],
                                   "scale": self.assumptions["demand_proxy"]
                                   ["assumed_weekday_linked_trips"],
                                   "max_rounds": pa["max_rounds"],
                                   "max_paths": pa["max_paths_per_od"],
                                   "scenarios": pa["n_random_scenarios"],
                                   "walk_radius": pa["walk_radius_m"],
                                   "access_radius": pa["access_radius_m"],
                                   "seed": seed,
                                   "cap_rule": "max(cfg,n_scenarios)",
                                   "common_lines": self.common_lines,
                                   "extra": tag},
                      lambda: _build_all_pathsets(
                          self.baseline, self.raptor, self.zones, self.od,
                          self.classes, seed, extra_scenarios,
                          common_lines=self.common_lines), use_cache)


def _gtfs_fingerprint() -> str:
    rec = Registry().get("cota_gtfs_static")
    return rec.sha256[:16] if rec else "UNKNOWN"


def build_harness(seed: int = 20260825, use_cache: bool = True,
                  common_lines: str | None = None,
                  with_pathsets: bool = True) -> Harness:
    """Assemble everything, reusing cached pieces where the inputs match."""
    fp = _gtfs_fingerprint()

    b = cached("baseline", {"gtfs": fp},
               lambda: build_baseline(demand_files=DEMAND_FILES, write=False),
               use_cache)
    a = b.assumptions
    pa = a["path_assignment"]
    periods = service_periods(a)
    proj = a["crs"]["projected"]

    sg = geo.stops_gdf(b.feed, proj)
    rn = cached("raptor", {"gtfs": fp, "proj": proj,
                           "walk_radius": pa["walk_radius_m"],
                           "walk_speed": pa["walk_speed_m_per_min"],
                           "periods": periods},
                lambda: build_raptor_network(
                    b.feed, b.network, b.tstats, sg,
                    walk_radius_m=float(pa["walk_radius_m"]),
                    walk_speed_m_per_min=float(pa["walk_speed_m_per_min"]),
                    periods=periods, with_timetable=False), use_cache)

    zs = cached("zones", {"gtfs": fp, "proj": proj,
                          "access_radius": pa["access_radius_m"],
                          "walk_speed": pa["walk_speed_m_per_min"]},
                lambda: build_zone_system(
                    b.demand["bg_frame"], sg,
                    radius_m=float(pa["access_radius_m"]),
                    walk_speed_m_per_min=float(pa["walk_speed_m_per_min"]),
                    stop_index=rn.stop_index), use_cache)

    reg = Registry()
    od_rec = reg.get("lodes_od_oh")
    od = cached("od", {"lodes": od_rec.sha256[:16] if od_rec else "NA",
                       "top_k": pa["od_top_k"],
                       "scale": a["demand_proxy"]["assumed_weekday_linked_trips"],
                       "access_radius": pa["access_radius_m"]},
                lambda: scale_to(
                    _top_k(filter_to_accessible(
                        from_lodes_od(reg.path_for("lodes_od_oh"), zs,
                                      county_fips=CENTRAL_OHIO_FIPS), zs),
                        int(pa["od_top_k"])),
                    float(a["demand_proxy"]["assumed_weekday_linked_trips"])),
                use_cache)

    ts = b.tstats.copy()
    ts["period"] = ts["first_dep_sec"].map(lambda s: period_of_seconds(s, periods))
    classes = classify_routes(ts.dropna(subset=["period"]), b.feed.routes)

    cl = str(common_lines if common_lines is not None
             else pa.get("common_lines", "pattern"))
    if not with_pathsets:
        # A descriptive job needing only the network, zones and demand should
        # not pay for a path-set enumeration, nor contend with the
        # authoritative run for the one core it would use.
        return Harness(baseline=b, raptor=rn, zones=zs, od=od, classes=classes,
                       pathsets={}, assumptions=a, common_lines=cl)
    ps = cached("pathsets", {"gtfs": fp, "lodes": od_rec.sha256[:16] if od_rec else "NA",
                             "top_k": pa["od_top_k"],
                             "scale": a["demand_proxy"]["assumed_weekday_linked_trips"],
                             "max_rounds": pa["max_rounds"],
                             "max_paths": pa["max_paths_per_od"],
                             "scenarios": pa["n_random_scenarios"],
                             "walk_radius": pa["walk_radius_m"],
                             "access_radius": pa["access_radius_m"],
                             "seed": seed,
                             "cap_rule": "max(cfg,n_scenarios)",
                             "common_lines": cl},
                lambda: _build_all_pathsets(b, rn, zs, od, classes, seed,
                                            common_lines=cl),
                use_cache)

    return Harness(baseline=b, raptor=rn, zones=zs, od=od, classes=classes,
                   pathsets=ps, assumptions=a, common_lines=cl)


def _build_all_pathsets(b, rn, zs, od, classes, seed,
                        extra_scenarios: list | None = None,
                        common_lines: str | None = None) -> dict:
    """Build every period's path set once (the ~9-minute step)."""
    store: dict = {}
    build_setup(b, rn, zs, od, seed=seed, route_classes=classes,
                with_crowding=False, lock_classes=(), pathset_cache=store,
                extra_scenarios=extra_scenarios, common_lines=common_lines)
    return store
