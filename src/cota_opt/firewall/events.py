"""Structured execution events: the things that happened, as data.

A `log.warning` is for a human reading a log. It is not evidence. D27 fired
`incumbent plan is infeasible under this budget` in every log of four
experiments and nothing counted it, because counting it required parsing prose.
Events exist so the harness can ask "did anything change this arm's search
opportunity?" without reading English.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .core import Sem, semfield


class EventType(str, Enum):
    START_REJECTED = "START_REJECTED"
    START_FALLBACK = "START_FALLBACK"
    INCUMBENT_REPAIRED = "INCUMBENT_REPAIRED"
    BUDGET_PROJECTION = "BUDGET_PROJECTION"
    PATHSET_REBUILT = "PATHSET_REBUILT"
    CACHE_INVALIDATED = "CACHE_INVALIDATED"
    CHECKPOINT_RESUMED = "CHECKPOINT_RESUMED"
    EARLY_TERMINATION = "EARLY_TERMINATION"
    NUMERICAL_RETRY = "NUMERICAL_RETRY"
    MODEL_FALLBACK = "MODEL_FALLBACK"
    DATA_FALLBACK = "DATA_FALLBACK"
    PARTIAL_RESULT = "PARTIAL_RESULT"
    CONVERGENCE_FAILURE = "CONVERGENCE_FAILURE"
    CONTRACT_DEVIATION = "CONTRACT_DEVIATION"


class Severity(str, Enum):
    INFO = "info"
    NOTABLE = "notable"
    SEVERE = "severe"


@dataclass(frozen=True)
class ExecutionEvent:
    """One thing that happened, with its effect on comparability declared.

    ``changes_opportunity`` and ``changes_semantics`` are the fields that
    matter. An event that changes neither is operational noise. An event that
    changes either is part of the experiment's execution history and must be
    matched across arms or declared in the contract.

    Classification defaults to the unsafe answer: an event whose author did not
    decide is treated as changing opportunity, because the alternative is a
    silent confound (corrective plan, section 17).
    """

    type: EventType
    reason: str
    component: str
    changes_opportunity: bool = True
    changes_semantics: bool = True
    severity: Severity = Severity.NOTABLE
    before: Any = None
    after: Any = None

    @property
    def operationally_neutral(self) -> bool:
        return not (self.changes_opportunity or self.changes_semantics)


def neutral(type_: EventType, reason: str, component: str,
            **kw) -> ExecutionEvent:
    """An event whose equivalence to not-happening is provable.

    Re-reading a file, rebuilding a deterministic cache, resuming the identical
    computation after process death. Use only when equivalence is provable, not
    merely likely -- everything else defaults to semantic.
    """
    return ExecutionEvent(type_, reason, component, changes_opportunity=False,
                          changes_semantics=False, severity=Severity.INFO, **kw)


def event_rates(receipts, classify) -> dict[str, dict[str, float]]:
    """Share of receipts carrying each event type, broken down by class.

    This is the table that would have made D27 obvious on day one:

        event                control  add_stop  extend  truncate
        START_FALLBACK          0%       83%     100%      0%

    ``classify(receipt) -> str`` names the experimental class of an arm.
    """
    groups: dict[str, list] = {}
    for r in receipts:
        groups.setdefault(classify(r), []).append(r)
    types = {e.type.value for r in receipts for e in r.events}
    out: dict[str, dict[str, float]] = {}
    for t in sorted(types):
        out[t] = {g: round(100.0 * sum(
            1 for r in rs if any(e.type.value == t for e in r.events)) / len(rs), 1)
            for g, rs in sorted(groups.items()) if rs}
    return out
