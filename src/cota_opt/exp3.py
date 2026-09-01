"""Experiment 3's primary objective, its reported metrics, and state identity.

Three things live here, all of them decided before any candidate was scored:

**The objective.** One number a search can be run against —
``generalized_cost + λ · w_unserved · unserved_demand`` at λ=2, with the weight
**read from config**, never hardcoded. A constant copied into the search would
silently diverge the moment `config/cost_weights.yaml` changed, and the
objective would then be a different objective wearing the same name.

**The six components.** The objective compresses a plan into a scalar, and the
compression hides the thing Experiment 1 turned on: total generalized cost
*rises* when a plan serves more people, while cost per served trip falls. A
table showing only the objective cannot tell those apart, so every result
reports all six.

**State identity.** A network state is a SET of mutations. Its digest must not
depend on the order they were listed in, or two searches reaching the same
state by different paths would cache, compare and de-duplicate as different
things. That the digest *can* be order-free is a property of `apply_edits`
enforcing one mutation per route, asserted in `tests/test_geometry_order.py`.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from .configs import load_cost_weights
from .geometry import GeometryEdit

#: The λ Experiment 3 searches at. λ≥2 is the certified range (gate 4); λ≤1
#: fails path-set adequacy on both waiting models, so a search run there would
#: be optimizing inside a region the project cannot certify.
PRIMARY_LAMBDA = 2.0

#: The identity of the empty state. Every search includes it, always: without
#: the null in the pool a search reports the best mutation it found rather than
#: whether mutating helps at all, and Experiment 2B's answer was the null.
NULL_STATE = "<none>"

#: Bumped whenever the mutation pool's generation rules change. It is part of
#: every cache key, so a pool regenerated under different rules cannot be
#: served scores computed under the old ones.
POOL_VERSION = "exp3-pool-v1"


def unserved_weight(base=None) -> float:
    """The unserved-demand weight, read from `config/cost_weights.yaml`.

    Read rather than hardcoded, and read *here* rather than in five callers, so
    there is exactly one place the objective's definition can change and
    exactly one place to look when it does.
    """
    w = load_cost_weights(base)
    try:
        return float(w["unserved"])
    except (KeyError, TypeError):
        return float(w["weights"]["unserved"])       # nested layout


def objective(fitness, lam: float = PRIMARY_LAMBDA, base=None) -> float:
    """Experiment 3's primary criterion. Lower is better."""
    return float(fitness.generalized_cost
                 + lam * unserved_weight(base) * fitness.unserved_demand)


#: The six metrics every result reports alongside the objective, in the order
#: they are reported. Names match FitnessVector's fields so nothing is
#: translated on the way out.
COMPONENTS = ("generalized_cost", "unserved_demand", "served_demand",
              "gc_per_served_trip", "revenue_veh_hours", "peak_vehicles")


def metrics(fitness, lam: float = PRIMARY_LAMBDA, base=None) -> dict[str, float]:
    """The objective and all six components. Never one without the others."""
    out = {"objective": objective(fitness, lam, base), "lambda": float(lam)}
    for k in COMPONENTS:
        out[k] = float(getattr(fitness, k))
    return out


# ---------------------------------------------------------------------------
# noise floors — for the quantity actually being compared
# ---------------------------------------------------------------------------

@dataclass
class NoiseFloor:
    """3σ of the zero-edit replicate spread, per quantity.

    Gate 3-3. The project's existing 0.130-point and 0.287-point figures are
    floors on *unserved demand* at two efforts; the objective has different
    units and a different variance, so applying them to it would be comparing a
    margin against a floor measured for something else. Every quantity that
    gets compared gets its own floor, measured in the same run at the same
    effort.
    """

    n_replicates: int
    effort: str
    absolute: dict[str, float] = field(default_factory=dict)
    relative_pct: dict[str, float] = field(default_factory=dict)
    means: dict[str, float] = field(default_factory=dict)

    def clears(self, quantity: str, margin_pct: float) -> bool:
        floor = self.relative_pct.get(quantity)
        if floor is None:
            raise KeyError(
                f"no floor was measured for {quantity!r}; a margin may not be "
                f"compared against a floor measured for a different quantity "
                f"(gate 3-3). Measured: {sorted(self.relative_pct)}")
        return abs(margin_pct) > floor

    def as_dict(self) -> dict[str, Any]:
        return {"n_replicates": self.n_replicates, "effort": self.effort,
                "absolute_3sigma": self.absolute,
                "relative_3sigma_pct": self.relative_pct,
                "replicate_means": self.means,
                "note": "3 sigma of the zero-edit replicate spread, measured "
                        "in this run at this effort. Floors from other runs or "
                        "other quantities do not transfer."}


def noise_floor(replicates: Sequence[Any], effort: str,
                lam: float = PRIMARY_LAMBDA, base=None) -> NoiseFloor:
    """Measure a floor for the objective and for every reported component.

    `replicates` are FitnessVectors from zero-edit solves in this run. Fewer
    than three and the spread is not an estimate of anything, so it raises
    rather than returning a floor of zero — a floor of zero would let every
    margin clear.
    """
    if len(replicates) < 3:
        raise ValueError(
            f"a noise floor needs at least 3 zero-edit replicates, got "
            f"{len(replicates)}. Two points have a spread but not a standard "
            f"deviation, and a floor that is accidentally zero lets every "
            f"margin through.")
    rows = [metrics(f, lam, base) for f in replicates]
    keys = ["objective", *COMPONENTS]
    absolute, relative, means = {}, {}, {}
    n = len(rows)
    for k in keys:
        xs = [r[k] for r in rows]
        mu = sum(xs) / n
        var = sum((x - mu) ** 2 for x in xs) / (n - 1)
        sd = var ** 0.5
        absolute[k] = 3.0 * sd
        means[k] = mu
        relative[k] = (100.0 * 3.0 * sd / abs(mu)) if mu else float("inf")
    return NoiseFloor(n_replicates=n, effort=effort, absolute=absolute,
                      relative_pct=relative, means=means)


def margins(candidate, incumbent, lam: float = PRIMARY_LAMBDA,
            base=None) -> dict[str, float]:
    """Percent change of every reported quantity, candidate vs incumbent.

    Sign convention throughout the project: negative is better for costs and
    for unserved demand, positive is better for served demand. Reported raw so
    a reader applies the convention themselves rather than trusting that this
    function applied it correctly.
    """
    c, i = metrics(candidate, lam, base), metrics(incumbent, lam, base)
    out = {}
    for k in ["objective", *COMPONENTS]:
        out[f"{k}_pct"] = (100.0 * (c[k] - i[k]) / i[k]) if i[k] else float("nan")
    return out


# ---------------------------------------------------------------------------
# state identity
# ---------------------------------------------------------------------------

def mutation_id(e: GeometryEdit) -> str:
    """A mutation's canonical identity: stable, and the same for equal edits.

    `GeometryEdit.key` is close but not canonical — it truncates stop lists to
    their first or last element, so two different truncations of one route can
    collide. This hashes everything that changes what the mutation does and
    nothing that does not: `description` and `evidence` are excluded, because
    rewording a description must not create a new candidate.
    """
    payload = {
        "kind": e.kind,
        "route": e.route_id,
        "with_route": e.with_route,
        "junction": e.junction,
        "drop": sorted(e.drop_stops),
        "append": list(e.append_stops),
        "between": list(e.replace_between) if e.replace_between else None,
        "with": list(e.replace_with),
    }
    h = hashlib.sha256(json.dumps(payload, sort_keys=True,
                                  separators=(",", ":")).encode()).hexdigest()
    tag = "-".join(x for x in (e.kind, e.route_id, e.with_route, e.junction)
                   if x)
    return f"{tag}#{h[:12]}"


def state_key(edits: Iterable[GeometryEdit]) -> str:
    """Human-readable state name: sorted mutation ids joined by '+'.

    Sorted, so `[a, b]` and `[b, a]` are one state and not two. That is only
    legitimate because `apply_edits` refuses two mutations on one route, which
    is what makes application order irrelevant.
    """
    ids = sorted(mutation_id(e) for e in edits)
    return "+".join(ids) if ids else NULL_STATE


def state_digest(edits: Iterable[GeometryEdit]) -> str:
    """Permutation-invariant content digest of a network state."""
    ids = sorted(mutation_id(e) for e in edits)
    return hashlib.sha256(("|".join(ids) or NULL_STATE).encode()).hexdigest()


def cache_key(edits: Iterable[GeometryEdit], *, waiting_model: str,
              lam: float, seed: int, effort: str,
              config_digest: str, pool_version: str = POOL_VERSION,
              stage: str = "") -> str:
    """Everything that changes a score, in the key that stores it.

    The Experiment 2 defect is the argument for every term here: a cell keyed
    on the candidate alone was silently reused across two waiting models, and
    the run that resumed it inherited three days of Model A numbers under a
    Model B label. A cache key that omits anything the score depends on is a
    way of serving one experiment's answer to another's question.
    """
    parts = [f"state={state_digest(edits)}",
             f"model={waiting_model}",
             f"lambda={lam:g}",
             f"seed={seed}",
             f"effort={effort}",
             f"config={config_digest}",
             f"pool={pool_version}"]
    if stage:
        parts.append(f"stage={stage}")
    return "|".join(parts)


def config_digest(base=None) -> str:
    """Hash of every config that can move a score.

    Held short, and computed from file contents rather than mtimes, so a config
    edited and reverted produces the same key it started with.
    """
    from pathlib import Path
    root = Path(base) if base else Path(__file__).resolve().parents[2] / "config"
    h = hashlib.sha256()
    for name in sorted(("assumptions.yaml", "cost_weights.yaml",
                        "constraints.yaml")):
        p = root / name
        h.update(name.encode())
        h.update(p.read_bytes() if p.exists() else b"MISSING")
    return h.hexdigest()[:16]


def pathset_cache_params(edits, seed: int, common_lines: str) -> dict:
    """Cache key for a state's path sets: everything they actually depend on.

    Path sets are five and a half of a discovery evaluation's seven minutes and
    depend only on the network, zones, OD and baseline headways -- none of
    which vary with the start set, the effort or lambda. Keying them here, in
    one place, keeps the re-score driver and the resumable certification runner
    from drifting into two subtly different keys and silently missing each
    other's cache.
    """
    return {"state": state_digest(edits), "seed": int(seed),
            "common_lines": common_lines, "config": config_digest(),
            "pool": POOL_VERSION}
