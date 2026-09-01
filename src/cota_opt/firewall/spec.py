"""What SHOULD happen to one cell, fixed before it happens.

Built in exactly one place. Experiment scripts that assemble their own
evaluation identity assemble it differently, and two subtly different
identities that hash the same are how a cache returns the wrong answer.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .contract import ExperimentContract
from .core import Sem, digest, semfield
from .policy import SolverPolicy


@dataclass(frozen=True)
class EvaluationSpec:
    contract_digest: str = semfield(Sem.IDENTITY, default="")
    experiment: str = semfield(Sem.IDENTITY, default="")
    stage: str = semfield(Sem.IDENTITY, default="")

    # what is being evaluated -- the treatment dimensions
    state_digest: str = semfield(Sem.IDENTITY, default="")
    state_key: str = semfield(Sem.IDENTITY, default="")
    cardinality: int = semfield(Sem.IDENTITY, default=0)
    members: tuple[str, ...] = semfield(Sem.IDENTITY, default=())

    # what it is evaluated WITH -- must match across arms
    evaluator: str = semfield(Sem.IDENTITY, default="")
    objective: str = semfield(Sem.IDENTITY, default="")
    objective_version: str = semfield(Sem.IDENTITY, default="")
    envelope_digest: str = semfield(Sem.IDENTITY, default="")
    pathset_policy: str = semfield(Sem.IDENTITY, default="")
    pool_version: str = semfield(Sem.IDENTITY, default="")
    config_digest: str = semfield(Sem.IDENTITY, default="")
    data_digest: str = semfield(Sem.IDENTITY, default="")
    code_version: str = semfield(Sem.IDENTITY, default="")
    solver: SolverPolicy | None = None
    seed: int = semfield(Sem.IDENTITY, default=0)

    @property
    def digest(self) -> str:
        return digest(self)

    @property
    def cache_key(self) -> str:
        """The ONE cache identity. A filename that matches is not a match.

        Keying on the state alone is what lets an entry built under one
        evaluator, envelope or objective satisfy a request made under another.
        """
        return f"cell-{self.digest}"


def build_spec(contract: ExperimentContract, *, state_digest: str,
               state_key: str, cardinality: int, members,
               envelope_digest: str, config_digest: str, data_digest: str = "",
               code_version: str = "", seed: int | None = None,
               solver: SolverPolicy | None = None) -> EvaluationSpec:
    """The canonical builder. Nothing else may construct a spec by hand."""
    sp = solver or contract.solver
    return EvaluationSpec(
        contract_digest=contract.digest, experiment=contract.experiment,
        stage=contract.stage, state_digest=state_digest, state_key=state_key,
        cardinality=int(cardinality), members=tuple(sorted(members)),
        evaluator=contract.evaluator, objective=contract.objective,
        objective_version=contract.objective_version,
        envelope_digest=envelope_digest,
        pathset_policy=contract.pathset_policy,
        pool_version=contract.pool_version, config_digest=config_digest,
        data_digest=data_digest, code_version=code_version, solver=sp,
        seed=int(sp.seeds[0] if seed is None else seed))
