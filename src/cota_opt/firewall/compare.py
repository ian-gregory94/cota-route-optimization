"""The one operation that may produce a treatment effect.

Core rule
---------
A treatment effect is a property of a validated comparison, not the difference
between two numbers. `compare()` is therefore the only place in this codebase
permitted to subtract one arm's objective from another's for a reported result.

Default
-------
Any undeclared difference between how control and treatment were ACTUALLY
executed makes the comparison inadmissible. Not the configuration they asked
for -- what the receipts say happened.

Design purpose
--------------
The harness does not need to know the next bug. It needs to notice that the
next bug made evidence in two different ways.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .contract import ExperimentContract
from .core import Sem, digest
from .observation import ComparableObservation, Inadmissible, admit
from .receipt import ExecutionReceipt


@dataclass(frozen=True)
class Difference:
    dimension: str
    control: object
    treatment: object
    kind: str = "identity"

    def __str__(self) -> str:
        return (f"{self.dimension}\n        control:   {self.control!r}\n"
                f"        treatment: {self.treatment!r}")


@dataclass(frozen=True)
class InadmissibleComparison:
    contract: ExperimentContract
    allowed: tuple[str, ...]
    undeclared: tuple[Difference, ...]
    notes: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return False

    def __str__(self) -> str:
        lines = ["COMPARISON REFUSED", "", "allowed difference:"]
        lines += [f"    {a}" for a in (self.allowed or ("(none)",))]
        if self.undeclared:
            lines += ["", "undeclared differences:"]
            lines += [f"    {d}" for d in self.undeclared]
        if self.notes:
            lines += ["", "notes:"] + [f"    {n}" for n in self.notes]
        lines += ["", "No treatment effect was computed."]
        return "\n".join(lines)


@dataclass(frozen=True)
class ComparisonResult:
    contract: ExperimentContract
    control: ComparableObservation
    treatment: ComparableObservation
    effect: float
    effect_pct: float
    components: dict = field(default_factory=dict)
    declared_differences: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return True

    @property
    def id(self) -> str:
        return f"cmp-{digest((self.control.receipt.digest, self.treatment.receipt.digest, self.contract.digest))}"

    @property
    def above_noise_floor(self) -> bool | None:
        """None when the contract declares no floor -- not False."""
        f = self.contract.noise_floor
        return None if f is None else abs(self.effect_pct / 100.0) > f

    def as_dict(self) -> dict:
        return {"comparison_id": self.id, "contract": self.contract.digest,
                "methodology_generation": self.contract.methodology_generation,
                "control_receipt": self.control.receipt.digest,
                "treatment_receipt": self.treatment.receipt.digest,
                "control_state": self.control.receipt.spec.state_key,
                "treatment_state": self.treatment.receipt.spec.state_key,
                "effect": self.effect, "effect_pct": self.effect_pct,
                "components": self.components,
                "declared_differences": list(self.declared_differences),
                "above_noise_floor": self.above_noise_floor,
                "control_signatures": self.control.signatures(),
                "treatment_signatures": self.treatment.signatures()}


def _within_tolerance(name: str, a, b, contract: ExperimentContract) -> bool:
    tol = contract.opportunity_tolerances.get(name)
    if tol is None:
        return False
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    # Relative to the SMALLER arm: a tolerance of 1.0 means "one may do up to
    # twice the other". Scaling by the larger instead would call 4,000
    # evaluations against 400,000 a 99% difference and wave it through.
    scale = max(min(abs(a), abs(b)), 1.0)
    return abs(a - b) / scale <= tol


def compare(control, treatment, contract: ExperimentContract
            ) -> ComparisonResult | InadmissibleComparison:
    """Compare two cells, or refuse and say exactly which dimensions differ."""
    notes: list[str] = []
    obs = []
    for label, x in (("control", control), ("treatment", treatment)):
        o = admit(x, contract) if isinstance(x, ExecutionReceipt) else x
        if isinstance(o, Inadmissible):
            notes.append(f"{label} observation inadmissible: " +
                         "; ".join(o.reasons))
        obs.append(o)
    if notes:
        return InadmissibleComparison(contract, tuple(sorted(
            contract.allowed_treatment_differences)), (), tuple(notes))
    c, t = obs

    # Everything that is not the measurement itself must match, unless the
    # contract named it. IDENTITY and OPPORTUNITY both, because equal
    # configuration with unequal execution is exactly the D27 failure.
    undeclared: list[Difference] = []
    for kind, cm, tm in (("identity", c.identity, t.identity),
                         ("opportunity", c.opportunity, t.opportunity)):
        for k in sorted(set(cm) | set(tm)):
            cv, tv = cm.get(k, "<absent>"), tm.get(k, "<absent>")
            if cv == tv or contract.allows(k):
                continue
            if kind == "opportunity" and _within_tolerance(k, cv, tv, contract):
                continue
            undeclared.append(Difference(k, cv, tv, kind))

    # An event that changed one arm's opportunity and not the other's is a
    # difference even when every field happens to agree.
    ce = {e.type.value for e in c.receipt.opportunity_changing}
    te = {e.type.value for e in t.receipt.opportunity_changing}
    if ce != te and not contract.allows("opportunity_events"):
        undeclared.append(Difference("opportunity_events", sorted(ce),
                                     sorted(te), "events"))

    if contract.certification_requires_matched_convergence and \
            contract.solver.require_convergence:
        if not (c.receipt.converged and t.receipt.converged):
            notes.append("certification requires both arms converged")

    if undeclared or notes:
        return InadmissibleComparison(
            contract, tuple(sorted(contract.allowed_treatment_differences)),
            tuple(undeclared), tuple(notes))

    a, b = c.receipt.objective, t.receipt.objective
    comps = {k: (t.receipt.metrics.get(k), c.receipt.metrics.get(k))
             for k in sorted(set(c.receipt.metrics) | set(t.receipt.metrics))}
    declared = tuple(sorted(
        k for k in set(c.identity) | set(c.opportunity)
        if contract.allows(k) and
        {**c.identity, **c.opportunity}.get(k) !=
        {**t.identity, **t.opportunity}.get(k)))
    return ComparisonResult(contract, c, t, b - a,
                            100.0 * (b - a) / a if a else float("nan"),
                            comps, declared)
