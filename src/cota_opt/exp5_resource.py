"""Experiment 5 — the resource envelope, as a first-class object.

Experiment 5 holds network TOPOLOGY fixed and varies the resource envelope
around it. Experiment 4 chooses structure; Experiment 5 asks what structure is
worth at different operating capacities. The only treatment is the envelope.

TWO RESOURCES, NEVER ONE, AND THE SECOND ONE IS NOT WHAT IT LOOKS LIKE
----------------------------------------------------------------------
    hours   scheduled weekday revenue vehicle-hours.  2517.183333.
    fleet   BLOCK-DERIVED peak vehicles, per period.
            early 135 · am_peak 187 · midday 173 · pm_peak 197 ·
            evening 178 · owl 149.

Both come from `outputs/CANONICAL_ENVELOPE.json` and from nowhere else. This
module hard-codes neither, computes neither, and rounds neither.

The fleet resource is **not** `FitnessVector.peak_vehicles`. That is peak
CONCURRENCY -- the max over periods of Σ cycle/headway -- an evaluation output
that reads 176.49 on the baseline against the block-derived 197 at the same
period, because it cannot see one bus finish route 8 and start route 35 twenty
minutes later. `contract.py` already refuses to compare concurrency against a
block-derived budget, on the grounds that doing so "would pass every plan while
appearing to check something".

There is also a third proxy, `blocks.routewise_peak`, at 150.73 -- the same
route-by-route sum under a different cycle definition than the frequency
model's. Three proxies, one cap. `REJECTED_AS_CAP` names all of them so that a
future reader does not have to rediscover which is which.

Concurrency may inform search. It may not define an envelope, establish
feasibility, certify anything, define a cell, or stand in for fleet in a report.
And no fixed multiplier converts one into the other: the measured 1.307
interlining factor is evidence of proxy error, not an exchange rate.

THE ROUNDING RULE, AND A SUPERSEDED ONE
---------------------------------------
    fleet_cap_p(m) = floor(m * canonical_fleet_p)

Floor, because a nominal resource level must never grant more vehicles than the
stated percentage: at m = 1.10, pm_peak gives floor(216.7) = 216, not 217.

An earlier revision of this file declared ``none_continuous_proxy`` instead.
That choice is **superseded, not silently changed**: it was predicated on the
fleet resource being the continuous concurrency proxy, which is exactly the
error this correction removes. Block-derived fleet is a count of vehicles, so
it is integral and floor applies. The old identifier is retained in
`_SUPERSEDED_ROUNDING` so the change is visible rather than merely absent.

Hours are NOT rounded. Vehicle-hours are continuous and scale exactly.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .firewall.core import digest

#: The preregistered resource levels, as fractions of the canonical COTA
#: envelope. Relative to COTA's envelope, never to whatever the frozen network
#: happens to consume.
LEVELS: tuple[float, ...] = (0.75, 0.90, 1.00, 1.10, 1.25, 1.50)

#: Fleet is integral, so a scaled cap is floored. See the module docstring.
FLEET_ROUNDING = "floor"
_SUPERSEDED_ROUNDING = "none_continuous_proxy"

#: Everything that looks like a fleet cap and is not one. Kept as data so tests
#: can assert against it rather than restating the list.
REJECTED_AS_CAP: dict[str, str] = {
    "FitnessVector.peak_vehicles": (
        "peak CONCURRENCY, an evaluation output; 176.49 on the baseline "
        "against the block-derived 197 at the same period"),
    "routewise_peak": (
        "the route-by-route cycle/headway sum, 150.73; a third proxy under a "
        "different cycle definition again"),
    "ntd_voms_198": (
        "NTD's independently reported vehicles operated in maximum service; an "
        "external validation of the 197 figure, not the figure itself"),
    "optimized_plan_realized_veh_hours": (
        "e.g. 2507.763673, an optimized plan spending 99.63% of its cap; a cap "
        "may never be read off a plan's usage"),
    "scalar_fleet_cap": (
        "a single number such as 197 or 200 applied to every period; the "
        "canonical envelope is a six-period vector and a scalar is a different "
        "constraint even when the number is right"),
    "concurrency_times_interlining_factor": (
        "the measured 1.307 ratio is evidence of proxy error, not a conversion "
        "constant; calibrating concurrency into fleet is forbidden"),
}

STAGE_A = "diagonal"
STAGE_B_HOURS = "hours_axis"
STAGE_B_FLEET = "fleet_axis"

_DEFAULT_ARTIFACT = "outputs/CANONICAL_ENVELOPE.json"


class ResourceError(ValueError):
    """An envelope or cell that cannot mean what it says."""


def load_canonical(root: Path | str | None = None) -> "ResourceEnvelope":
    """The one way to obtain the canonical envelope. No other path exists.

    Reads `outputs/CANONICAL_ENVELOPE.json`, which itself does not compute the
    constants -- it reads the committed receipts and refuses to write unless
    they agree with EXPERIMENT4_CONTRACT section 3.
    """
    root = Path(root) if root else Path(__file__).resolve().parents[2]
    p = root / _DEFAULT_ARTIFACT
    if not p.exists():
        raise ResourceError(
            f"{_DEFAULT_ARTIFACT} does not exist. The canonical envelope is "
            f"read from that artifact and from nowhere else; run "
            f"scripts/exp4_freeze_envelope.py --write. It is not recomputed "
            f"here, because a second computation is a second opinion.")
    d = json.loads(p.read_text())
    return ResourceEnvelope(
        revenue_veh_hours=float(d["weekday_revenue_vehicle_hours"]),
        fleet_by_period={str(k): int(v) for k, v in
                         d["peak_vehicles_by_period"].items()},
        hours_pct=1.0, fleet_pct=1.0, source="canonical_artifact",
        canonical_digest=str(d["envelope_digest"]))


def cell_id(hours_pct: float, fleet_pct: float) -> str:
    h, f = round(hours_pct * 100), round(fleet_pct * 100)
    if h == f:
        return f"R{h:03d}"
    if f == 100:
        return f"H{h:03d}"
    if h == 100:
        return f"F{f:03d}"
    return f"X{h:03d}x{f:03d}"


@dataclass(frozen=True)
class ResourceEnvelope:
    """Hours (continuous) and BLOCK-DERIVED fleet per period (integral)."""

    revenue_veh_hours: float
    fleet_by_period: Mapping[str, int]
    hours_pct: float = 1.0
    fleet_pct: float = 1.0
    source: str = "canonical_artifact"
    fleet_rounding: str = FLEET_ROUNDING
    fleet_semantics: str = "block_derived_peak_vehicles"
    canonical_digest: str = ""

    def __post_init__(self) -> None:
        if not math.isfinite(self.revenue_veh_hours) or \
                self.revenue_veh_hours <= 0:
            raise ResourceError(
                f"revenue vehicle-hours must be positive and finite, got "
                f"{self.revenue_veh_hours!r}")
        if not self.fleet_by_period:
            raise ResourceError(
                "fleet must be given per period. The canonical envelope is a "
                "six-period vector; a scalar is a different constraint even "
                "when the number is right.")
        if len(self.fleet_by_period) < 2:
            # A one-entry mapping is a scalar cap in a dict costume, and it
            # would satisfy every "is it per-period?" check that only asks
            # whether the value is a mapping. 197 alone is not the envelope
            # either: the envelope is six numbers, and pm_peak's happens to be
            # the largest of them.
            raise ResourceError(
                f"fleet_by_period has one entry ({sorted(self.fleet_by_period)}"
                f"): that is a scalar cap in a dict costume. The canonical "
                f"envelope covers every service period independently, and all "
                f"of them must pass -- a single number, 197 included, is not "
                f"the fleet envelope.")
        for p, v in self.fleet_by_period.items():
            if int(v) != v or v < 0:
                raise ResourceError(
                    f"fleet cap for {p!r} is {v!r}; block-derived fleet is a "
                    f"count of vehicles and must be a non-negative integer")
        if self.fleet_rounding != FLEET_ROUNDING:
            raise ResourceError(
                f"fleet rounding {self.fleet_rounding!r} is not the "
                f"preregistered rule {FLEET_ROUNDING!r} "
                f"(superseded: {_SUPERSEDED_ROUNDING!r})")
        if self.fleet_semantics != "block_derived_peak_vehicles":
            raise ResourceError(
                f"fleet semantics {self.fleet_semantics!r}: the Experiment 5 "
                f"fleet resource is block-derived peak vehicles. "
                f"{sorted(REJECTED_AS_CAP)} are not caps.")

    # -- scaling -----------------------------------------------------------
    def scale(self, hours_pct: float, fleet_pct: float) -> "ResourceEnvelope":
        """hours * m exactly; fleet floor(m * canonical_p), per period."""
        if hours_pct <= 0 or fleet_pct <= 0:
            raise ResourceError("resource percentages must be positive")
        if self.source != "canonical_artifact":
            raise ResourceError(
                "scale() applies to the canonical envelope only: percentages "
                "are defined against COTA's envelope, and chaining would "
                "compound them silently")
        return ResourceEnvelope(
            revenue_veh_hours=self.revenue_veh_hours * hours_pct,
            fleet_by_period={p: int(math.floor(v * fleet_pct))
                             for p, v in sorted(self.fleet_by_period.items())},
            hours_pct=float(hours_pct), fleet_pct=float(fleet_pct),
            source="scaled_from_canonical",
            canonical_digest=self.canonical_digest)

    # -- semantics ---------------------------------------------------------
    def dominates(self, other: "ResourceEnvelope") -> bool:
        """Every cap here is at least `other`'s -- §7/E5-4 nesting."""
        if self.revenue_veh_hours < other.revenue_veh_hours - 1e-9:
            return False
        for p, v in other.fleet_by_period.items():
            if self.fleet_by_period.get(p, -1) < v:
                return False
        return True

    def feasible(self, hours_used: float,
                 fleet_used_by_period: Mapping[str, float]
                 ) -> tuple[bool, list[str]]:
        """§7: BOTH dimensions, and all six fleet periods independently.

        `fleet_used_by_period` must be block-derived. Passing concurrency here
        tests the wrong quantity, which is why the caller is required to say
        where its numbers came from (`Exp5Feasibility`).
        """
        bad: list[str] = []
        if hours_used > self.revenue_veh_hours + 1e-6:
            bad.append(f"hours {hours_used:.6f} > cap "
                       f"{self.revenue_veh_hours:.6f}")
        for p, cap in sorted(self.fleet_by_period.items()):
            used = float(fleet_used_by_period.get(p, 0.0))
            if used > cap + 1e-9:
                bad.append(f"fleet[{p}] {used:g} > cap {cap}")
        missing = sorted(set(self.fleet_by_period) - set(fleet_used_by_period))
        if missing:
            bad.append(f"no fleet figure for {missing}; all six periods must "
                       f"pass independently, so a missing one is a failure")
        return (not bad), bad

    @property
    def digest(self) -> str:
        return digest({"vh": round(self.revenue_veh_hours, 9),
                       "fleet": {p: int(v) for p, v in
                                 sorted(self.fleet_by_period.items())},
                       "rounding": self.fleet_rounding,
                       "semantics": self.fleet_semantics,
                       "canonical": self.canonical_digest})

    def payload(self) -> dict:
        return {"revenue_veh_hours_cap": self.revenue_veh_hours,
                "fleet_by_period_cap": {p: int(v) for p, v in
                                        sorted(self.fleet_by_period.items())},
                "hours_pct": self.hours_pct, "fleet_pct": self.fleet_pct,
                "source": self.source, "fleet_rounding": self.fleet_rounding,
                "fleet_semantics": self.fleet_semantics,
                "canonical_envelope_digest": self.canonical_digest,
                "envelope_digest": self.digest}


@dataclass(frozen=True)
class ResourceCell:
    """A cell's identity is its ENVELOPE, not its label.

    `__eq__` and `__hash__` come from the envelope digest, so two cells both
    displayed as "100%" that resolve to different caps are different cells, and
    a relabelling cannot make two different envelopes compare equal.
    """

    id: str
    stage: str
    envelope: ResourceEnvelope

    @property
    def hours_pct(self) -> float:
        return self.envelope.hours_pct

    @property
    def fleet_pct(self) -> float:
        return self.envelope.fleet_pct

    @property
    def key(self) -> str:
        return self.envelope.digest

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ResourceCell) and self.key == other.key

    def __hash__(self) -> int:
        return hash(self.key)

    def payload(self) -> dict:
        return {"cell_id": self.id, "stage": self.stage,
                "hours_multiplier": self.hours_pct,
                "fleet_multiplier": self.fleet_pct,
                "scaling_rule": FLEET_ROUNDING,
                **self.envelope.payload()}


def stage_a_grid(canonical: ResourceEnvelope,
                 levels: tuple[float, ...] = LEVELS) -> list[ResourceCell]:
    """The diagonal frontier: hours and fleet move together. §5."""
    return [ResourceCell(cell_id(p, p), STAGE_A, canonical.scale(p, p))
            for p in levels]


def stage_b_grid(canonical: ResourceEnvelope,
                 levels: tuple[float, ...] = LEVELS) -> list[ResourceCell]:
    """Hours axis and fleet axis, each holding the other at 100%. §6.

    The shared 100/100 cell is Stage A's R100 and is deliberately not emitted
    again: §6 says it is the same result, not a separate experiment.
    """
    out: list[ResourceCell] = []
    for p in levels:
        if p != 1.0:
            out.append(ResourceCell(cell_id(p, 1.0), STAGE_B_HOURS,
                                    canonical.scale(p, 1.0)))
    for p in levels:
        if p != 1.0:
            out.append(ResourceCell(cell_id(1.0, p), STAGE_B_FLEET,
                                    canonical.scale(1.0, p)))
    return out


@dataclass(frozen=True)
class Exp5Feasibility:
    """A feasibility verdict that has to say where its fleet number came from.

    `fleet_source` must be a block-derived instrument. Concurrency is carried
    alongside as a diagnostic and can never move the boolean -- §7.
    """

    cell_id: str
    feasible: bool
    reasons: list[str]
    hours_used: float
    fleet_used_by_period: Mapping[str, float]
    fleet_source: str
    concurrency_diagnostic: Mapping[str, float] | None = None

    def __post_init__(self) -> None:
        if not self.fleet_source.startswith("block"):
            raise ResourceError(
                f"fleet_source {self.fleet_source!r} is not a block-derived "
                f"instrument. Experiment 5 feasibility is decided on "
                f"block-derived fleet; concurrency belongs in "
                f"concurrency_diagnostic, where it cannot move the verdict.")

    def payload(self) -> dict:
        return {"cell_id": self.cell_id, "feasible": self.feasible,
                "reasons": list(self.reasons),
                "hours_used": self.hours_used,
                "fleet_used_by_period": dict(self.fleet_used_by_period),
                "fleet_source": self.fleet_source,
                "concurrency_diagnostic_NOT_A_CAP":
                    dict(self.concurrency_diagnostic or {})}


@dataclass(frozen=True)
class ResourceUsage:
    """Allowed, used, slack and binding -- kept apart on purpose (§12)."""

    hours_cap: float
    hours_used: float
    fleet_cap_by_period: Mapping[str, int]
    fleet_used_by_period: Mapping[str, float]

    @property
    def hours_slack(self) -> float:
        return self.hours_cap - self.hours_used

    @property
    def hours_binding(self) -> bool:
        return self.hours_used >= self.hours_cap * (1.0 - 1e-6)

    def fleet_slack(self) -> dict[str, float]:
        return {p: self.fleet_cap_by_period[p]
                - float(self.fleet_used_by_period.get(p, 0.0))
                for p in sorted(self.fleet_cap_by_period)}

    def fleet_binding(self) -> dict[str, bool]:
        return {p: float(self.fleet_used_by_period.get(p, 0.0))
                >= self.fleet_cap_by_period[p] - 1e-9
                for p in sorted(self.fleet_cap_by_period)}

    @property
    def any_fleet_binding(self) -> bool:
        return any(self.fleet_binding().values())

    def payload(self) -> dict:
        return {"hours_cap": self.hours_cap, "hours_used": self.hours_used,
                "hours_slack": self.hours_slack,
                "hours_binding": self.hours_binding,
                "fleet_cap_by_period": dict(sorted(
                    self.fleet_cap_by_period.items())),
                "fleet_used_by_period": dict(sorted(
                    self.fleet_used_by_period.items())),
                "fleet_slack_by_period": self.fleet_slack(),
                "fleet_binding_by_period": self.fleet_binding(),
                "any_fleet_binding": self.any_fleet_binding}


def nested(cells: list[ResourceCell]) -> tuple[bool, list[str]]:
    """E5-4: whenever one cell's multipliers dominate another's, its caps must.

    Off-diagonal cells need not be comparable -- an hours-rich cell does not
    dominate a fleet-rich one -- and that is not an error.
    """
    problems: list[str] = []
    for a in cells:
        for b in cells:
            if a.key == b.key:
                continue
            if a.hours_pct >= b.hours_pct and a.fleet_pct >= b.fleet_pct:
                if not a.envelope.dominates(b.envelope):
                    problems.append(
                        f"{a.id} has multipliers at least {b.id}'s but its "
                        f"caps do not dominate, so a schedule feasible at "
                        f"{b.id} may be infeasible at {a.id}")
    return (not problems), problems


def grid_digest(cells: list[ResourceCell]) -> str:
    return digest([c.payload() for c in
                   sorted(cells, key=lambda c: (c.stage, c.id))])
