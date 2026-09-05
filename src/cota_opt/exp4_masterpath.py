"""Gate 4-7's actual object: a frozen supernetwork master path set.

Gate 4-7 permits discovery to score candidate networks against a master path set
enumerated once, instead of rebuilding paths per candidate. The naive thing --
sharing one `pathset_cache` across candidates -- is NOT that, and measuring it
showed why: the cache is keyed by PERIOD alone, so every candidate after the
first is scored against the previous candidate's paths, which gives worst 1.307
relative error on revenue vehicle-hours.

The real object:

1. **Enumerate once on the supernetwork** — every line the pool allows, active
   together. Its path set contains, by construction, every ride any candidate
   network could offer, because a candidate's patterns are a subset of the
   supernetwork's.
2. **Filter per candidate.** A master path is usable in a candidate iff *every*
   ride leg it uses belongs to a route the candidate actually runs. A path
   through a line the candidate does not select cannot be taken, and keeping it
   would credit the candidate with service it does not operate.
3. **Remap.** The evaluator indexes headways by the candidate's own
   route-period vector, so surviving legs are re-pointed at the candidate's
   `rp_keys`. A leg that cannot be remapped means the path was not usable, which
   step 2 already excluded -- and it is re-checked here rather than assumed.

Filtering is a **restriction of the choice set, not an approximation of it**:
every surviving path is a real path in the candidate, priced identically. What
reuse can lose is paths the supernetwork's enumeration never proposed because
they only become attractive once other lines are absent. That is exactly the
error gate 4-7 asks to be measured, and `scripts/exp4_masterpath_benchmark.py`
measures it against exact per-candidate rebuilds.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping

import numpy as np

from .pathset import PathSet


@dataclass
class MasterPathSet:
    """Path sets enumerated on the supernetwork, one per period, plus provenance."""

    by_period: dict[str, PathSet]
    supernetwork_lines: tuple[str, ...]
    digest: str = ""

    def stats(self) -> dict[str, Any]:
        return {"periods": sorted(self.by_period),
                "n_lines": len(self.supernetwork_lines),
                "paths_by_period": {p: int(ps.n_paths)
                                    for p, ps in sorted(self.by_period.items())},
                "od_by_period": {p: int(ps.n_od)
                                 for p, ps in sorted(self.by_period.items())},
                "digest": self.digest}


def filter_for_network(master: PathSet, candidate_rp_keys: list[tuple[str, str]]
                       ) -> tuple[PathSet, dict[str, Any]]:
    """Restrict a master path set to the paths a candidate can actually offer.

    Returns the filtered set and a provenance dict. Raises rather than guessing
    if the master lacks the route-period labels the filter needs.
    """
    if not master.rp_keys:
        raise ValueError(
            "master path set carries no rp_keys, so its legs cannot be "
            "attributed to routes and no honest filter exists")

    want = {k: i for i, k in enumerate(candidate_rp_keys)}
    # master rp index -> candidate rp index, or -1 when the candidate lacks it
    remap = np.full(len(master.rp_keys), -1, dtype=np.int64)
    for mi, key in enumerate(master.rp_keys):
        ci = want.get(key)
        if ci is not None:
            remap[mi] = ci

    leg_rp = master.leg_rp
    is_ride = leg_rp >= 0
    # a ride leg is usable iff its route-period exists in the candidate
    usable_leg = np.ones(len(leg_rp), dtype=bool)
    usable_leg[is_ride] = remap[leg_rp[is_ride]] >= 0

    # a path survives iff every one of its legs is usable
    n_paths = master.n_paths
    keep = np.ones(n_paths, dtype=bool)
    np.logical_and.at(keep, master.leg_path, usable_leg)

    kept_idx = np.flatnonzero(keep)
    prov = {"master_paths": int(n_paths), "kept_paths": int(len(kept_idx)),
            "dropped_paths": int(n_paths - len(kept_idx)),
            "survival_fraction": float(len(kept_idx) / n_paths) if n_paths else 0.0,
            "master_rp": len(master.rp_keys),
            "candidate_rp": len(candidate_rp_keys),
            "rp_shared": int((remap >= 0).sum())}

    # rebuild the flat arrays over the surviving paths, in order
    new_path_of_old = np.full(n_paths, -1, dtype=np.int64)
    new_path_of_old[kept_idx] = np.arange(len(kept_idx))

    leg_keep = keep[master.leg_path]
    lp = new_path_of_old[master.leg_path[leg_keep]]
    order = np.argsort(lp, kind="stable")
    lp = lp[order]

    def _sel(arr):
        return None if arr is None else arr[leg_keep][order]

    new_leg_rp = master.leg_rp[leg_keep][order].copy()
    ride = new_leg_rp >= 0
    new_leg_rp[ride] = remap[new_leg_rp[ride]]
    if (new_leg_rp[ride] < 0).any():
        raise AssertionError(
            "a surviving path still carries an unmappable ride leg; the filter "
            "and the survival test disagree")

    path_offsets = np.zeros(len(kept_idx) + 1, dtype=np.int64)
    np.cumsum(np.bincount(lp, minlength=len(kept_idx)), out=path_offsets[1:])

    path_od = master.path_od[kept_idx]
    # od_offsets must be rebuilt: paths are still grouped by OD because the
    # original order is preserved and OD groups are contiguous.
    od_counts = np.bincount(path_od, minlength=master.n_od)
    od_offsets = np.zeros(master.n_od + 1, dtype=np.int64)
    np.cumsum(od_counts, out=od_offsets[1:])

    out = replace(
        master,
        leg_path=lp, leg_rp=new_leg_rp,
        leg_ivt=_sel(master.leg_ivt), leg_walk=_sel(master.leg_walk),
        leg_is_boarding=_sel(master.leg_is_boarding),
        leg_is_transfer=_sel(master.leg_is_transfer),
        leg_pattern=_sel(master.leg_pattern),
        leg_board_pos=_sel(master.leg_board_pos),
        leg_alight_pos=_sel(master.leg_alight_pos),
        leg_headway_mult=_sel(master.leg_headway_mult),
        path_od=path_od, path_offsets=path_offsets, od_offsets=od_offsets,
        rp_keys=list(candidate_rp_keys),
    )
    return out, prov
