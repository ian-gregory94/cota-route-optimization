"""A result becomes evidence only by passing its own contract.

`EvaluationResult + ExecutionReceipt + ExperimentContract -> ComparableObservation`

An inadmissible result is kept, not discarded -- it is the debugging record.
It simply may not enter a treatment effect.
"""
from __future__ import annotations

from dataclasses import dataclass

from .contract import ExperimentContract
from .core import Sem, digest, fields_by_sem
from .receipt import ExecutionReceipt


@dataclass(frozen=True)
class Inadmissible:
    """Why one observation may not be compared. Truthy-false on purpose."""

    receipt: ExecutionReceipt
    reasons: tuple[str, ...]

    def __bool__(self) -> bool:
        return False

    def __str__(self) -> str:
        return ("OBSERVATION INADMISSIBLE\n  " + "\n  ".join(self.reasons))


@dataclass(frozen=True)
class ComparableObservation:
    receipt: ExecutionReceipt
    contract: ExperimentContract

    def __bool__(self) -> bool:
        return True

    @property
    def identity(self) -> dict:
        return fields_by_sem(self.receipt, Sem.IDENTITY)

    @property
    def opportunity(self) -> dict:
        return fields_by_sem(self.receipt, Sem.OPPORTUNITY)

    @property
    def outcome(self) -> dict:
        return fields_by_sem(self.receipt, Sem.OUTCOME)

    # --- the four signatures, stored with artifacts ------------------------
    @property
    def treatment_signature(self) -> str:
        both = {**self.identity, **self.opportunity}
        return digest({k: v for k, v in both.items() if self.contract.allows(k)})

    @property
    def nuisance_signature(self) -> str:
        both = {**self.identity, **self.opportunity}
        return digest({k: v for k, v in both.items()
                       if not self.contract.allows(k)})

    @property
    def evidence_signature(self) -> str:
        r = self.receipt
        return digest({"evaluator": r.evaluator_used, "objective": r.objective_used,
                       "envelope_vh": r.envelope_used_vh,
                       "pathset": r.pathset_digest,
                       "pathset_policy": r.spec.pathset_policy,
                       "config": r.spec.config_digest, "data": r.spec.data_digest,
                       "code": r.code_version, "schema": r.schema_version})

    @property
    def execution_signature(self) -> str:
        return digest(self.opportunity)

    def signatures(self) -> dict[str, str]:
        return {"treatment": self.treatment_signature,
                "nuisance": self.nuisance_signature,
                "evidence": self.evidence_signature,
                "execution": self.execution_signature,
                "receipt": self.receipt.digest,
                "spec": self.receipt.spec.digest,
                "contract": self.contract.digest}


def admit(receipt: ExecutionReceipt, contract: ExperimentContract
          ) -> ComparableObservation | Inadmissible:
    """Check a single observation against the contract it claims to satisfy."""
    bad: list[str] = []
    s = receipt.spec

    if s.contract_digest != contract.digest:
        bad.append(f"built under contract {s.contract_digest} but judged "
                   f"against {contract.digest}")
    if receipt.evaluator_used != contract.evaluator:
        bad.append(f"evaluator {receipt.evaluator_used!r} != contract "
                   f"{contract.evaluator!r}")
    if receipt.objective_used != contract.objective:
        bad.append(f"objective {receipt.objective_used!r} != contract "
                   f"{contract.objective!r}")
    if s.pathset_policy != contract.pathset_policy:
        bad.append(f"path-set policy {s.pathset_policy!r} != contract "
                   f"{contract.pathset_policy!r}")
    if s.pool_version != contract.pool_version:
        bad.append(f"pool {s.pool_version!r} != contract {contract.pool_version!r}")

    pol = contract.solver
    got = receipt.start_policy_requested
    if got != pol.start_policy:
        bad.append(f"start policy {got.value!r} != contract "
                   f"{pol.start_policy.value!r}")
    # Requesting a policy is not receiving it.
    if pol.start_policy.wants_greedy and "greedy" not in receipt.starts_attempted:
        bad.append("contract requires a greedy start; none was attempted")
    if pol.start_policy.wants_incumbent and not any(
            x.startswith(("incumbent", "repaired")) for x in receipt.starts_attempted):
        bad.append("contract requires an incumbent start; none was attempted")
    if receipt.restarts_completed < pol.restarts:
        bad.append(f"{receipt.restarts_completed} of {pol.restarts} restarts "
                   f"completed")
    if pol.require_convergence and not receipt.converged:
        bad.append(f"contract requires convergence; terminated on "
                   f"{receipt.termination.value}")
    if not receipt.feasible:
        bad.append("solution is infeasible")
    if contract.forbid_severe_events and receipt.severe:
        bad.append("severe events: " +
                   ", ".join(e.type.value for e in receipt.severe))
    if receipt.objective != receipt.objective:      # NaN
        bad.append("objective is NaN")

    return Inadmissible(receipt, tuple(bad)) if bad else \
        ComparableObservation(receipt, contract)
