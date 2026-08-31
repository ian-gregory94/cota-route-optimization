"""The experiment that is INTENDED to occur, frozen before it occurs.

The one field that matters is ``allowed_treatment_differences``. It is a
whitelist, not a blacklist, and that choice is the whole architecture: a
blacklist can only catch confounds someone already thought of, and D27 was not
one of those. With a whitelist, a dimension nobody has invented yet defaults to
"may not differ", so the comparison that first exercises it is refused rather
than quietly reported.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .core import Sem, digest, semfield
from .policy import DISCOVERY, SolverPolicy


class ContractError(ValueError):
    """A contract that cannot mean what it says."""


@dataclass(frozen=True)
class ExperimentContract:
    experiment: str
    version: str
    stage: str
    objective: str
    objective_version: str
    evaluator: str
    envelope: str
    pathset_policy: str
    pool_version: str
    #: Which methodological generation produced this. Gen1 is the frozen
    #: definitions of path construction, assignment, Model B waiting, the
    #: objective, the envelope, the headway ladder, the frequency optimizer,
    #: the mutation representation, the search strategy and the certification
    #: policy. A Gen2 artifact is not a correction of a Gen1 artifact: it is a
    #: different generation's answer, and both are kept.
    methodology_generation: str = "gen1"
    solver: SolverPolicy = field(default_factory=lambda: DISCOVERY)

    #: The ONLY dimensions on which control and treatment may differ. Dotted
    #: names as they appear in the flattened spec/receipt maps.
    allowed_treatment_differences: frozenset[str] = frozenset()

    #: Opportunity fields that are permitted to differ by a relative amount,
    #: e.g. {"evaluations_performed": 0.5}. Absent means EXACT match required,
    #: which is deliberate: a cell that quietly did half the search of its
    #: partner should fail closed until someone declares how much slack the
    #: experiment tolerates.
    opportunity_tolerances: dict[str, float] = field(default_factory=dict)

    #: Below this (as a fraction, e.g. 0.000391 for 0.0391%) an effect is not
    #: distinguishable from replicate spread.
    noise_floor: float | None = None

    #: A comparison whose arms carry severe events is refused outright.
    forbid_severe_events: bool = True

    #: Promotion needs an admissible comparison, not a score.
    promotion_requires_comparison: bool = True
    certification_requires_matched_convergence: bool = True

    def __post_init__(self) -> None:
        if self.stage == "certification" and not self.solver.require_convergence:
            raise ContractError(
                "a certification contract whose solver policy does not require "
                "convergence certifies nothing (D28: nominal effort is not "
                "convergence)")
        if not self.solver.start_policy.treatment_independent:
            if "starts_attempted" not in self.allowed_treatment_differences:
                raise ContractError(
                    f"start policy {self.solver.start_policy.value!r} lets the "
                    "realised start set depend on the state, so the optimizer "
                    "becomes a function of the treatment (D27). Either use a "
                    "treatment-independent policy or declare "
                    "'starts_attempted' as a treatment dimension and explain "
                    "why that is the experiment you meant to run.")

    @property
    def digest(self) -> str:
        return digest(self)

    def allows(self, dotted: str) -> bool:
        """Whether this flattened dimension may differ between arms.

        An entry matches a dimension exactly, or as its trailing path segment:
        ``state_key`` permits ``spec.state_key``. Writing the leaf keeps
        contracts readable and stops them breaking every time a structure is
        nested one level deeper — but it is still a whitelist, so a dimension
        nobody wrote down is refused however it is spelled.
        """
        if dotted in self.allowed_treatment_differences:
            return True
        return any(dotted.endswith("." + a)
                   for a in self.allowed_treatment_differences)


#: Experiment 3 Stage A: geometry is the treatment and nothing else is.
EXP3_STAGE_A = ExperimentContract(
    experiment="exp3", version="3.1", stage="discovery",
    objective="lambda_scalarized_path_level", objective_version="lambda=2.0",
    evaluator="same_route", envelope="pinned_unedited_baseline",
    pathset_policy="rebuilt_per_state", pool_version="exp3-pool-v1",
    solver=DISCOVERY,
    allowed_treatment_differences=frozenset({
        "state_digest", "state_key", "cardinality", "members",
        "pathset_digest",      # a different network HAS a different path set
    }),
    # Two states legitimately need different amounts of search to converge;
    # what may not differ is the OPPORTUNITY to search, which is the fields
    # above this one. Declared rather than assumed.
    opportunity_tolerances={"evaluations_performed": 1.0},
    noise_floor=0.000391,
)
