"""Solver policy as an explicit choice, never as a boolean with a fallback.

`greedy_start=False` meant "no greedy build -- unless the incumbent turns out
to be infeasible, in which case greedy, silently". A boolean whose meaning
depends on the data is not a policy; it is a coin flip correlated with the
treatment. These enums say what shall happen, and a policy that cannot be
honoured is a structured failure rather than a substitution.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .core import Sem, semfield


class StartPolicy(str, Enum):
    INCUMBENT_ONLY = "incumbent_only"
    GREEDY_ONLY = "greedy_only"
    BOTH = "both"
    REPAIRED_INCUMBENT_ONLY = "repaired_incumbent_only"
    REPAIRED_INCUMBENT_AND_GREEDY = "repaired_incumbent_and_greedy"

    @property
    def wants_incumbent(self) -> bool:
        return self in (StartPolicy.INCUMBENT_ONLY, StartPolicy.BOTH,
                        StartPolicy.REPAIRED_INCUMBENT_ONLY,
                        StartPolicy.REPAIRED_INCUMBENT_AND_GREEDY)

    @property
    def wants_repair(self) -> bool:
        return self in (StartPolicy.REPAIRED_INCUMBENT_ONLY,
                        StartPolicy.REPAIRED_INCUMBENT_AND_GREEDY,
                        StartPolicy.BOTH)

    @property
    def wants_greedy(self) -> bool:
        return self in (StartPolicy.GREEDY_ONLY, StartPolicy.BOTH,
                        StartPolicy.REPAIRED_INCUMBENT_AND_GREEDY)

    @property
    def treatment_independent(self) -> bool:
        """Whether the START SET this policy produces can depend on the state.

        ``INCUMBENT_ONLY`` is the dangerous one: whether the incumbent survives
        the ladder snap depends on the geometry, so the realised start set is a
        function of the treatment. Every other policy either always repairs
        into feasibility or always includes greedy.
        """
        return self is not StartPolicy.INCUMBENT_ONLY


class StopRule(str, Enum):
    NO_IMPROVING_MOVE = "no_improving_move"
    EVALUATION_BUDGET = "evaluation_budget"
    DEADLINE = "deadline"
    ERROR = "error"


@dataclass(frozen=True)
class SolverPolicy:
    """What search the cell is entitled to.

    Discovery and certification are not two numbers on an iteration ceiling.
    D28 measured each certification restart terminating after ~4,000 of its
    400,000 permitted evaluations: the ceiling was never the binding
    constraint, and calling 400000/20 "6.7x the search" of 60000/20 described
    nothing that happened. Restart diversity is the lever, so it is a field in
    its own right and convergence is asserted rather than assumed.
    """

    name: str = semfield(Sem.IDENTITY, default="discovery")
    start_policy: StartPolicy = semfield(Sem.IDENTITY,
                                         default=StartPolicy.BOTH)
    restarts: int = semfield(Sem.IDENTITY, default=2)
    evaluation_ceiling: int = semfield(Sem.IDENTITY, default=60_000)
    candidate_width: int = semfield(Sem.IDENTITY, default=32)
    require_convergence: bool = semfield(Sem.IDENTITY, default=False)
    seeds: tuple[int, ...] = semfield(Sem.IDENTITY, default=(20260825,))


DISCOVERY = SolverPolicy(
    name="discovery", start_policy=StartPolicy.BOTH, restarts=2,
    evaluation_ceiling=60_000, candidate_width=32, require_convergence=False,
    seeds=(20260825,))

CERTIFICATION = SolverPolicy(
    name="certification", start_policy=StartPolicy.BOTH, restarts=20,
    evaluation_ceiling=400_000, candidate_width=0, require_convergence=True,
    seeds=(20260825, 20260826, 20260827))
