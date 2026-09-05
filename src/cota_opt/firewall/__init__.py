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
from .contract import (EXP3_STAGE_A, EXP3_STAGE_B,
                       EXP3_STAGE_B_ESCALATED, ContractError,
                       ExperimentContract)
from .core import SCHEMA_VERSION, Sem, canonical_json, digest, semfield
from .events import EventType, ExecutionEvent, Severity, event_rates, neutral
from .exp4 import (ALLOWANCE, EXP4_CERTIFICATION, EXP4_DISCOVERY,
                   NETWORK_DIFFERENCES, compare_exp4)
from .findings import Finding, FindingLog, finding
from .health import HealthReport, Imbalance, balance_audit, health_report
from .observation import ComparableObservation, Inadmissible, admit
from .policy import (CERTIFICATION, DISCOVERY, SolverPolicy, StartPolicy,
                     StopRule)
from .receipt import ExecutionReceipt
from .search_allowance import (EXP4_ALLOWANCE, AllowanceError,
                               AllowanceRecord, SearchAllowance, comparable)
from .spec import EvaluationSpec, build_spec
from .store import CacheMiss, ObservationStore

__all__ = [
    "SCHEMA_VERSION", "Sem", "canonical_json", "digest", "semfield",
    "EventType", "ExecutionEvent", "Severity", "event_rates", "neutral",
    "StartPolicy", "StopRule", "SolverPolicy", "DISCOVERY", "CERTIFICATION",
    "ExperimentContract", "ContractError", "EXP3_STAGE_A",
    "EXP3_STAGE_B", "EXP3_STAGE_B_ESCALATED",
    "EvaluationSpec", "build_spec", "ExecutionReceipt",
    "ComparableObservation", "Inadmissible", "admit",
    "compare", "ComparisonResult", "InadmissibleComparison", "Difference",
    "health_report", "HealthReport", "balance_audit", "Imbalance",
    "ObservationStore", "CacheMiss",
    "Finding", "FindingLog", "finding",
    # Experiment 4's effort contract: allocated search opportunity per decision
    # dimension. In force from 2026-09-04 (gen1-frozen-v1).
    "SearchAllowance", "AllowanceRecord", "AllowanceError", "comparable",
    "EXP4_ALLOWANCE",
    # Experiment 4's contracts, in force from 2026-09-05 under the
    # condition exp4_draft.py set itself: Gen1 frozen AND the Gen1->Gen2
    # bridge suite run. compare_exp4 requires the allowance check.
    "EXP4_DISCOVERY", "EXP4_CERTIFICATION", "NETWORK_DIFFERENCES",
    "compare_exp4", "ALLOWANCE",
]
