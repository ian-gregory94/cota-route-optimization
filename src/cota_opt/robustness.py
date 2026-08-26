"""Which conclusions survive the demand assumptions, and which only survive them.

The demand side is the weakest part of this model and always has been. LODES
gives home-to-work flows for one year; 24.7% of regional flow is
transit-accessible, the top 20,000 pairs carry 64.9% of that, and the period
profile that spreads it across the day was shaped from typical US bus demand
rather than from anything COTA observed. None of that is fixable with the data
available. All of it is testable.

The point is not to produce error bars. It is to find out which *statements*
are load-bearing on which assumption. A result that moves by 15% under a
plausible demand perturbation but keeps its sign, its ordering and its shape is
a different kind of result from one that inverts, and only the second is a
problem — so conclusions are written down as predicates with a direction and a
margin, before the sweep runs, and the sweep reports which ones broke.

Nothing here estimates non-commute travel. The blend is a *stress direction*:
a deliberately different demand shape, flatter across the day and symmetric in
orientation, used to ask whether a conclusion depends on commute geometry. If a
conclusion holds under both, it does not rest on that geometry. If it flips,
that is the honest headline and not a number to be tuned away.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from .odmatrix import ODTable
from .pathset import PathSet


# -- perturbing the demand ---------------------------------------------------

@dataclass(frozen=True)
class Perturbation:
    """One named change to the demand inputs, with the reason it is plausible."""

    name: str
    kind: str
    params: dict = field(default_factory=dict)
    rationale: str = ""

    def __post_init__(self) -> None:
        if self.kind not in ("scale", "periods", "noncommute", "retention",
                             "none"):
            raise ValueError(f"unknown perturbation kind {self.kind!r}")


def scale_od(od: ODTable, factor: float) -> ODTable:
    """Every flow multiplied by the same number.

    The one perturbation with a predictable answer: generalized cost per trip
    and unserved *share* are both ratios, so a uniform scale cancels out of
    them exactly unless something in the model is nonlinear in load. Crowding
    is the only such term, and D5 found it does not bind at this demand. Which
    makes this a test of that finding rather than of the demand figure: if a
    percentage result moves under a pure rescale, crowding is binding after
    all and D5 is wrong.
    """
    if factor <= 0:
        raise ValueError("scale factor must be positive")
    return ODTable(od.origin, od.dest, od.flow * float(factor),
                   f"{od.source} x{factor:g}",
                   f"{od.notes}; uniformly scaled by {factor:g}")


def tilt_periods(shares: dict[str, float], toward: Iterable[str],
                 strength: float) -> dict[str, float]:
    """Move demand between periods, renormalized to sum to one.

    ``strength`` is the relative weight added to the named periods: 0.5 makes
    them half again as attractive before renormalization. Negative strengths
    move demand away from them.
    """
    if strength <= -1.0:
        raise ValueError("strength <= -1 would zero the named periods")
    tgt = set(toward)
    missing = tgt - set(shares)
    if missing:
        raise ValueError(f"unknown periods {sorted(missing)}")
    w = {k: v * (1.0 + strength if k in tgt else 1.0) for k, v in shares.items()}
    tot = sum(w.values())
    if tot <= 0:
        raise ValueError("tilt produced no demand at all")
    return {k: v / tot for k, v in w.items()}


def noncommute_proxy(od: ODTable, zone_weight: np.ndarray,
                     decay_km: float = 4.0,
                     distance: Callable[[int, int], float] | None = None
                     ) -> ODTable:
    """A deliberately different demand shape over the same OD pairs.

    Product-form attraction with exponential distance decay, evaluated only on
    the pairs the commute matrix already contains, then symmetrized. Shorter
    and less directional than commuting, which is the direction non-commute
    travel is known to differ in.

    This is a stress direction, not an estimate. It is confined to the existing
    pairs on purpose: introducing new pairs would confound "different shape"
    with "more coverage", and the question is whether a conclusion depends on
    the shape.
    """
    o, d = od.origin, od.dest
    w = np.asarray(zone_weight, float)
    a = w[o] * w[d]
    if distance is not None:
        km = np.array([distance(int(i), int(j)) for i, j in zip(o, d)], float)
        a = a * np.exp(-km / max(decay_km, 1e-9))
    if a.sum() <= 0:
        raise ValueError("proxy weights sum to zero; check zone_weight")
    flow = a / a.sum() * od.flow.sum()
    # symmetrize: pair (i,j) and (j,i) share the mean where both exist
    key = {(int(i), int(j)): k for k, (i, j) in enumerate(zip(o, d))}
    out = flow.copy()
    for k, (i, j) in enumerate(zip(o, d)):
        r = key.get((int(j), int(i)))
        if r is not None and r > k:
            m = 0.5 * (flow[k] + flow[r])
            out[k] = out[r] = m
    return ODTable(o, d, out, "noncommute_proxy",
                   f"product-form attraction, {decay_km:g} km decay, "
                   "symmetrized; a STRESS DIRECTION, not an estimate of "
                   "non-commute travel")


def blend(a: ODTable, b: ODTable, share_b: float) -> ODTable:
    """Convex blend of two OD tables over identical pair lists."""
    if not (0.0 <= share_b <= 1.0):
        raise ValueError("share must be in [0, 1]")
    if len(a) != len(b) or not np.array_equal(a.origin, b.origin) \
            or not np.array_equal(a.dest, b.dest):
        raise ValueError("blend needs the same pairs in the same order")
    f = (1.0 - share_b) * a.flow + share_b * b.flow
    return ODTable(a.origin, a.dest, f, f"{a.source}+{b.source}",
                   f"{share_b:.0%} {b.source}")


# -- what a conclusion is ----------------------------------------------------

@dataclass(frozen=True)
class Claim:
    """A conclusion stated so that a sweep can break it.

    ``test`` receives one result row and returns True if the claim holds there.
    Writing these down before the sweep runs is the whole discipline: a claim
    invented afterwards can always be made to survive.
    """

    key: str
    statement: str
    test: Callable[[dict], bool]
    rests_on: str = ""


def check(claims: Iterable[Claim], rows: Iterable[dict]) -> pd.DataFrame:
    """Every claim against every perturbation, with the failures named."""
    rows = list(rows)
    out = []
    for c in claims:
        broke = []
        for r in rows:
            try:
                ok = bool(c.test(r))
            except Exception as e:                      # a claim that cannot
                ok = False                              # be evaluated is broken
                broke.append(f"{r.get('perturbation', '?')} ({type(e).__name__})")
                continue
            if not ok:
                broke.append(str(r.get("perturbation", "?")))
        out.append({"claim": c.key, "statement": c.statement,
                    "n_tested": len(rows), "n_broken": len(broke),
                    "survives": not broke,
                    "broken_under": "; ".join(broke),
                    "rests_on": c.rests_on})
    return pd.DataFrame(out)


def summary(verdict: pd.DataFrame) -> dict:
    if verdict.empty:
        return {"n_claims": 0, "note": "no claims tested"}
    broke = verdict[~verdict["survives"]]
    return {
        "n_claims": int(len(verdict)),
        "n_survived": int(verdict["survives"].sum()),
        "n_broken": int(len(broke)),
        "broken": list(broke["claim"]),
        "interpretation": (
            "a claim that survives every perturbation is not thereby true -- "
            "it is not resting on the demand assumptions that were varied. A "
            "claim that breaks names the assumption it was resting on."),
    }


# -- perturbing a built path set ---------------------------------------------

def reweight_pathset(ps: PathSet, factor) -> PathSet:
    """A path set with different demand on the same paths.

    Which paths exist depends on headways and costs, not on how many people
    walk them, so a demand perturbation does not require re-enumeration -- it
    requires replacing one vector. That is what makes a dense sweep affordable
    at all: re-enumerating six periods per perturbation would put a ten-point
    sweep out of reach and a two-point one is not a sweep.

    ``factor`` is a scalar or a per-OD vector. The path set is copied
    shallowly, so the original keeps its own flows and a sweep cannot
    contaminate the run it is testing.
    """
    from dataclasses import replace as _replace
    f = np.asarray(factor, float)
    if f.ndim == 0:
        if f <= 0:
            raise ValueError("scale factor must be positive")
        new = ps.od_flow * float(f)
    elif f.shape == ps.od_flow.shape:
        if np.any(f < 0):
            raise ValueError("per-OD factors must be non-negative")
        new = ps.od_flow * f
    else:
        raise ValueError(f"factor shape {f.shape} does not match "
                         f"{ps.od_flow.shape} OD pairs")
    return _replace(ps, od_flow=new)
