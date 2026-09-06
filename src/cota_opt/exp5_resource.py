"""Experiment 5 — the resource envelope, as a first-class object.

Experiment 5 holds network TOPOLOGY fixed and varies the resource envelope
around it. Experiment 4 chooses structure; Experiment 5 asks what structure is
worth at different operating capacities. The only treatment is the envelope.

This module is the §18 half: everything that can be built and tested before
Experiment 4 closes, because none of it depends on which network wins. It takes
a *generic frozen network artifact* and knows nothing about Experiment 4's
result.

WHAT IS CANONICAL AND WHAT IS DERIVED
-------------------------------------
`config/constraints.yaml` sets both resource limits to the sentinel
``baseline``, which production resolves to the **unedited network's own
fitness**: `fit.revenue_veh_hours` for hours and `fit.peak_by_period` for
fleet. Those are the canonical constants and Experiment 5 reads them from the
same place rather than retyping a number into a second file — §4 exists because
a constant copied twice is a constant that will eventually disagree with itself.

Measured on the frozen baseline: 2507.763673 revenue vehicle-hours, peak
176.132352 at the maximum period. Those figures appear here only in this
comment. Nothing in the code hard-codes them.

TWO RESOURCES, NEVER ONE
------------------------
Hours and buses are not interchangeable and are never collapsed into a
"resources" scalar. A system can be hours-rich and fleet-poor -- long spans of
infrequent service -- or the reverse. `ResourceEnvelope` carries both, and
`peak_by_period` stays a **per-period dict** because that is what
`ResourceBudget` and `_feasible` actually enforce: a single peak scalar would
be a different constraint than production applies.

CAPS, NOT SPENDING REQUIREMENTS
-------------------------------
A cell given 125% may spend 108% if the rest buys nothing. That is a result, not
a failure to use the budget, and `ResourceUsage` reports allowed, used, slack
and binding separately so the distinction survives into the report.

FLEET SCALING, AND WHY NO ROUNDING RULE FIRES
---------------------------------------------
§8 requires the production fleet representation, and asks for a preregistered
deterministic rounding rule *if* an integer limit is required. It is not:
`ResourceBudget.peak_vehicles_by_period` holds floats and `_feasible` compares
against `peak_cap(p)`, a continuous proxy. So the canonical cap is scaled
exactly and no rounding occurs anywhere in the frontier.

The rule is still declared, because "we did not need one" is only checkable if
the alternative was written down: were an integer limit ever required, it would
be ``floor`` -- never permitting more resources than the nominal percentage.
`FLEET_ROUNDING` records that, `scale()` refuses any other rule, and it is fixed
for every cell rather than chosen per cell.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping

from .firewall.core import digest

#: The preregistered resource levels, as fractions of the canonical COTA
#: envelope. Relative to COTA's envelope, never to whatever the frozen network
#: happens to consume -- a frontier indexed to the winner's own appetite would
#: move whenever the winner moved.
LEVELS: tuple[float, ...] = (0.75, 0.90, 1.00, 1.10, 1.25, 1.50)

#: Declared and fixed for every cell. See the module docstring: the production
#: fleet constraint is continuous, so this never fires. It exists so that the
#: absence of rounding is a checkable claim rather than an omission.
FLEET_ROUNDING = "none_continuous_proxy"
_FLEET_ROUNDING_ALLOWED = ("none_continuous_proxy", "floor")

STAGE_A = "diagonal"
STAGE_B_HOURS = "hours_axis"
STAGE_B_FLEET = "fleet_axis"


class ResourceError(ValueError):
    """An envelope or cell that cannot mean what it says."""


def cell_id(hours_pct: float, fleet_pct: float) -> str:
    """Deterministic, readable, and unique per (hours, fleet) pair.

    R### on the diagonal, H###/F### off it, so a cell's identifier says which
    axis it probes without a lookup.
    """
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
    """One resource cap pair. Hours is scalar; fleet is per period, as production."""

    revenue_veh_hours: float
    peak_by_period: Mapping[str, float]
    tolerance: float = 0.0
    #: what this was scaled from, for provenance
    hours_pct: float = 1.0
    fleet_pct: float = 1.0
    source: str = "canonical_baseline"
    fleet_rounding: str = FLEET_ROUNDING

    def __post_init__(self) -> None:
        if not math.isfinite(self.revenue_veh_hours) or \
                self.revenue_veh_hours <= 0:
            raise ResourceError(
                f"revenue vehicle-hours must be positive and finite, got "
                f"{self.revenue_veh_hours!r}")
        if not self.peak_by_period:
            raise ResourceError(
                "peak fleet must be given per period; a single scalar is a "
                "different constraint than production enforces")
        for p, v in self.peak_by_period.items():
            if not math.isfinite(v) or v < 0:
                raise ResourceError(f"peak cap for {p!r} is {v!r}")
        if self.fleet_rounding not in _FLEET_ROUNDING_ALLOWED:
            raise ResourceError(
                f"fleet rounding {self.fleet_rounding!r} is not one of the "
                f"declared deterministic rules {_FLEET_ROUNDING_ALLOWED}")

    # -- construction ------------------------------------------------------
    @classmethod
    def canonical(cls, revenue_veh_hours: float,
                  peak_by_period: Mapping[str, float],
                  tolerance: float = 0.0) -> "ResourceEnvelope":
        """The 100% envelope, from production's own resolved baseline values."""
        return cls(float(revenue_veh_hours),
                   {str(k): float(v) for k, v in peak_by_period.items()},
                   float(tolerance), 1.0, 1.0, "canonical_baseline")

    def scale(self, hours_pct: float, fleet_pct: float,
              rounding: str = FLEET_ROUNDING) -> "ResourceEnvelope":
        """A scaled envelope. Exact; the declared rounding rule never fires."""
        if rounding not in _FLEET_ROUNDING_ALLOWED:
            raise ResourceError(f"undeclared fleet rounding {rounding!r}")
        if hours_pct <= 0 or fleet_pct <= 0:
            raise ResourceError("resource percentages must be positive")
        base = self if self.source == "canonical_baseline" else None
        if base is None:
            raise ResourceError(
                "scale() must be applied to the canonical envelope, not to an "
                "already-scaled one: percentages are defined against COTA's "
                "envelope, and chaining would silently compound them")

        def fleet(v: float) -> float:
            x = v * fleet_pct
            return math.floor(x) if rounding == "floor" else x

        return ResourceEnvelope(
            revenue_veh_hours=self.revenue_veh_hours * hours_pct,
            peak_by_period={p: fleet(v)
                            for p, v in sorted(self.peak_by_period.items())},
            tolerance=self.tolerance,
            hours_pct=float(hours_pct), fleet_pct=float(fleet_pct),
            source="scaled_from_canonical", fleet_rounding=rounding)

    # -- semantics ---------------------------------------------------------
    def dominates(self, other: "ResourceEnvelope") -> bool:
        """True when every cap here is at least `other`'s.

        This is what §7's nesting means operationally: a plan feasible under
        `other` is feasible here, because every constraint it satisfied is no
        tighter now.
        """
        if self.revenue_veh_hours < other.revenue_veh_hours - 1e-9:
            return False
        for p, v in other.peak_by_period.items():
            if self.peak_by_period.get(p, float("-inf")) < v - 1e-9:
                return False
        return True

    def to_constraints(self, base_constraints: dict) -> dict:
        """This envelope expressed as production's own constraints dict.

        Built by overriding only the resource block of the constraints
        production already loaded, so every other service rule -- ladder, span
        preservation, policy headway bounds -- is carried through untouched
        rather than reconstructed.
        """
        res = dict(base_constraints.get("resource", {}))
        res["weekday_revenue_vehicle_hours"] = float(self.revenue_veh_hours)
        res["peak_fleet_by_period"] = {p: float(v) for p, v in
                                       sorted(self.peak_by_period.items())}
        res["budget_tolerance"] = float(self.tolerance)
        return {**base_constraints, "resource": res}

    @property
    def digest(self) -> str:
        return digest({"vh": round(self.revenue_veh_hours, 9),
                       "peak": {p: round(v, 9) for p, v in
                                sorted(self.peak_by_period.items())},
                       "tolerance": self.tolerance,
                       "rounding": self.fleet_rounding})

    def payload(self) -> dict:
        return {"revenue_veh_hours_cap": self.revenue_veh_hours,
                "peak_by_period_cap": {p: v for p, v in
                                       sorted(self.peak_by_period.items())},
                "tolerance": self.tolerance,
                "hours_pct": self.hours_pct, "fleet_pct": self.fleet_pct,
                "source": self.source, "fleet_rounding": self.fleet_rounding,
                "envelope_digest": self.digest}


@dataclass(frozen=True)
class ResourceCell:
    """One point of the frontier: an id, a stage, and an envelope."""

    id: str
    stage: str
    hours_pct: float
    fleet_pct: float
    envelope: ResourceEnvelope

    def payload(self) -> dict:
        return {"cell_id": self.id, "stage": self.stage,
                "hours_pct": self.hours_pct, "fleet_pct": self.fleet_pct,
                **self.envelope.payload()}


def stage_a_grid(canonical: ResourceEnvelope,
                 levels: tuple[float, ...] = LEVELS) -> list[ResourceCell]:
    """The diagonal frontier: hours and fleet move together. §5."""
    return [ResourceCell(cell_id(p, p), STAGE_A, p, p,
                         canonical.scale(p, p)) for p in levels]


def stage_b_grid(canonical: ResourceEnvelope,
                 levels: tuple[float, ...] = LEVELS) -> list[ResourceCell]:
    """Hours axis and fleet axis, each holding the other at 100%. §6.

    The shared 100/100 cell is Stage A's R100 and is deliberately NOT emitted
    again: recomputing it as a separate experiment would invite two numbers for
    one cell, and §6 says it is the same result.
    """
    out: list[ResourceCell] = []
    for p in levels:
        if p != 1.0:
            out.append(ResourceCell(cell_id(p, 1.0), STAGE_B_HOURS, p, 1.0,
                                    canonical.scale(p, 1.0)))
    for p in levels:
        if p != 1.0:
            out.append(ResourceCell(cell_id(1.0, p), STAGE_B_FLEET, 1.0, p,
                                    canonical.scale(1.0, p)))
    return out


@dataclass(frozen=True)
class ResourceUsage:
    """Allowed, used, slack and binding -- kept apart on purpose.

    §12: "resources made available" and "resources actually used by the
    optimum" are different quantities, and an optimizer that stops spending
    before the cap is a finding rather than a shortfall.
    """

    hours_cap: float
    hours_used: float
    peak_cap_by_period: Mapping[str, float]
    peak_used_by_period: Mapping[str, float]
    tolerance: float = 0.0

    @property
    def hours_slack(self) -> float:
        return self.hours_cap - self.hours_used

    @property
    def hours_binding(self) -> bool:
        return self.hours_used >= self.hours_cap * (1.0 - 1e-6)

    def peak_slack(self) -> dict[str, float]:
        return {p: self.peak_cap_by_period[p] - self.peak_used_by_period.get(p, 0.0)
                for p in sorted(self.peak_cap_by_period)}

    def peak_binding(self) -> dict[str, bool]:
        return {p: self.peak_used_by_period.get(p, 0.0)
                >= self.peak_cap_by_period[p] * (1.0 - 1e-6)
                for p in sorted(self.peak_cap_by_period)}

    @property
    def any_peak_binding(self) -> bool:
        return any(self.peak_binding().values())

    def within_caps(self) -> tuple[bool, list[str]]:
        """E5-8: hours and fleet each independently satisfy their own cap."""
        bad = []
        if self.hours_used > self.hours_cap * (1.0 + self.tolerance) + 1e-6:
            bad.append(f"hours {self.hours_used:.6f} > cap "
                       f"{self.hours_cap:.6f}")
        for p, cap in sorted(self.peak_cap_by_period.items()):
            used = self.peak_used_by_period.get(p, 0.0)
            if used > cap * (1.0 + self.tolerance) + 1e-6:
                bad.append(f"peak[{p}] {used:.6f} > cap {cap:.6f}")
        return (not bad), bad

    def payload(self) -> dict:
        ok, why = self.within_caps()
        return {"hours_cap": self.hours_cap, "hours_used": self.hours_used,
                "hours_slack": self.hours_slack,
                "hours_binding": self.hours_binding,
                "peak_cap_by_period": dict(sorted(self.peak_cap_by_period.items())),
                "peak_used_by_period": dict(sorted(self.peak_used_by_period.items())),
                "peak_slack_by_period": self.peak_slack(),
                "peak_binding_by_period": self.peak_binding(),
                "any_peak_binding": self.any_peak_binding,
                "within_caps": ok, "cap_violations": why}


def nested(cells: list[ResourceCell]) -> tuple[bool, list[str]]:
    """E5-4: whenever one cell's caps dominate another's, say so explicitly.

    Returns the pairs that ARE nested, and complains only about pairs that
    should nest by construction and do not. Off-diagonal cells need not be
    comparable at all -- an hours-rich cell does not dominate a fleet-rich one --
    and that is not an error.
    """
    problems: list[str] = []
    by_id = {c.id: c for c in cells}
    for a in cells:
        for b in cells:
            if a.id == b.id:
                continue
            if a.hours_pct >= b.hours_pct and a.fleet_pct >= b.fleet_pct:
                if not a.envelope.dominates(b.envelope):
                    problems.append(
                        f"{a.id} has percentages at least {b.id}'s but its "
                        f"envelope does not dominate: caps are not nested, so "
                        f"a plan feasible at {b.id} may be infeasible at {a.id}")
    return (not problems), problems


def grid_digest(cells: list[ResourceCell]) -> str:
    return digest([c.payload() for c in
                   sorted(cells, key=lambda c: (c.stage, c.id))])
