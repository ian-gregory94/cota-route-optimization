"""Semantic comparison firewall.

    Core rule     A treatment effect is a property of a validated comparison,
                  not the difference between two scores.
    Default       Any undeclared difference between how control and treatment
                  were actually executed makes the comparison inadmissible.
    Recovery      A recovery that can change mathematical opportunity is
                  experimental state, and must appear in the receipt.
    Purpose       The harness should not need to know the next bug. It should
                  notice that the next bug made evidence in two different ways.
"""
from .compare import (ComparisonResult, Difference, InadmissibleComparison,
                      compare)
from .contract import EXP3_STAGE_A, ContractError, ExperimentContract
from .core import SCHEMA_VERSION, Sem, canonical_json, digest, semfield
from .events import EventType, ExecutionEvent, Severity, event_rates, neutral
from .findings import Finding, FindingLog, finding
from .health import HealthReport, Imbalance, balance_audit, health_report
from .observation import ComparableObservation, Inadmissible, admit
from .policy import (CERTIFICATION, DISCOVERY, SolverPolicy, StartPolicy,
                     StopRule)
from .receipt import ExecutionReceipt
from .spec import EvaluationSpec, build_spec
from .store import CacheMiss, ObservationStore

__all__ = [
    "SCHEMA_VERSION", "Sem", "canonical_json", "digest", "semfield",
    "EventType", "ExecutionEvent", "Severity", "event_rates", "neutral",
    "StartPolicy", "StopRule", "SolverPolicy", "DISCOVERY", "CERTIFICATION",
    "ExperimentContract", "ContractError", "EXP3_STAGE_A",
    "EvaluationSpec", "build_spec", "ExecutionReceipt",
    "ComparableObservation", "Inadmissible", "admit",
    "compare", "ComparisonResult", "InadmissibleComparison", "Difference",
    "health_report", "HealthReport", "balance_audit", "Imbalance",
    "ObservationStore", "CacheMiss",
    "Finding", "FindingLog", "finding",
]
