"""What ACTUALLY happened to one cell.

The receipt is the evidence. The score is only one of its fields, and by
itself it cannot support a comparison: two identical scores produced by
different amounts of search are not two observations of the same thing.

No field here may require parsing a log to populate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .core import SCHEMA_VERSION, Sem, digest, semfield
from .events import EventType, ExecutionEvent, Severity
from .policy import StartPolicy, StopRule
from .spec import EvaluationSpec


@dataclass(frozen=True)
class ExecutionReceipt:
    spec: EvaluationSpec

    # --- what the evaluation actually ran with (asserted, not requested) ----
    evaluator_used: str = semfield(Sem.IDENTITY, default="")
    objective_used: str = semfield(Sem.IDENTITY, default="")
    envelope_used_vh: float = semfield(Sem.IDENTITY, default=0.0)
    pathset_digest: str = semfield(Sem.IDENTITY, default="")
    code_version: str = semfield(Sem.IDENTITY, default="")
    schema_version: str = semfield(Sem.IDENTITY, default=SCHEMA_VERSION)

    # --- the search opportunity this cell actually received ----------------
    start_policy_requested: StartPolicy = semfield(
        Sem.OPPORTUNITY, default=StartPolicy.BOTH)
    starts_attempted: tuple[str, ...] = semfield(Sem.OPPORTUNITY, default=())
    starts_rejected: tuple[str, ...] = semfield(Sem.OPPORTUNITY, default=())
    rejection_reasons: tuple[str, ...] = semfield(Sem.OPPORTUNITY, default=())
    winning_start: str = semfield(Sem.OUTCOME, default="")
    fallback_occurred: bool = semfield(Sem.OPPORTUNITY, default=False)
    repair_occurred: bool = semfield(Sem.OPPORTUNITY, default=False)
    repair_steps: int = semfield(Sem.OPPORTUNITY, default=0)
    restarts_requested: int = semfield(Sem.OPPORTUNITY, default=0)
    restarts_completed: int = semfield(Sem.OPPORTUNITY, default=0)
    evaluations_performed: int = semfield(Sem.OPPORTUNITY, default=0)
    termination: StopRule = semfield(Sem.OPPORTUNITY,
                                     default=StopRule.NO_IMPROVING_MOVE)
    converged: bool = semfield(Sem.OPPORTUNITY, default=False)
    resumed: bool = semfield(Sem.OPPORTUNITY, default=False)

    # --- what it found ------------------------------------------------------
    objective: float = semfield(Sem.OUTCOME, default=float("nan"))
    metrics: dict = semfield(Sem.OUTCOME, default_factory=dict)
    plan_digest: str = semfield(Sem.OUTCOME, default="")
    feasible: bool = semfield(Sem.OUTCOME, default=True)
    objective_trajectory: tuple[float, ...] = semfield(Sem.OUTCOME, default=())

    # --- provenance ---------------------------------------------------------
    events: tuple[ExecutionEvent, ...] = semfield(Sem.NONE, default=())
    cache_hit: bool = semfield(Sem.NONE, default=False)
    seconds: float = semfield(Sem.NONE, default=0.0)
    at: str = semfield(Sem.NONE, default="")

    @property
    def digest(self) -> str:
        return digest(self)

    @property
    def severe(self) -> tuple[ExecutionEvent, ...]:
        return tuple(e for e in self.events if e.severity == Severity.SEVERE)

    @property
    def opportunity_changing(self) -> tuple[ExecutionEvent, ...]:
        """Events that altered what this cell was able to find.

        Not "errors" -- a fallback that succeeds is not an error. It is a
        different search, which is a different experiment.
        """
        return tuple(e for e in self.events if e.changes_opportunity)

    def has(self, t: EventType) -> bool:
        return any(e.type == t for e in self.events)
