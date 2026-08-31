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

    #: Why each declared difference does not confound the comparison. A
    #: whitelist without reasons is a place to put anything inconvenient; with
    #: them, every waiver is written down, hashed into the contract digest, and
    #: readable by whoever inherits the result. Dimensions declared without a
    #: justification are refused at construction.
    justifications: dict[str, str] = field(default_factory=dict)

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
        missing = sorted(d for d in self.allowed_treatment_differences
                         if not self.justifications.get(d, "").strip())
        if missing:
            raise ContractError(
                "every declared treatment difference needs a written reason it "
                "does not confound the comparison; missing for: "
                + ", ".join(missing))
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
GEOMETRY_DIFFERENCES = {
    "state_digest": "The geometry itself. This IS the treatment.",
    "state_key": "The geometry's name. Follows from state_digest.",
    "cardinality": "How many edits the state applies. Part of the treatment.",
    "members": "Which edits the state applies. Part of the treatment.",
    "pathset_digest":
        "A different network has a different set of shortest paths; requiring "
        "identical path sets would only ever admit a comparison of a network "
        "with itself. What must match is the path-set POLICY, which is an "
        "identity field of its own and is not declared here.",
}

#: Repair is treatment-dependent by construction -- a route-lengthening edit
#: pushes its incumbent further outside the envelope, so it needs more steps to
#: get back in. Declaring it is only defensible because D30 measured what it
#: is worth: over eight stratified states at four cardinalities, the repaired
#: incumbent NEVER won. Greedy won 8/8, the objectives were bit-identical and
#: the frequency plans hashed the same. The repair changes how the start set is
#: assembled and demonstrably not what the search returns.
#:
#: This waiver is falsifiable and should be re-checked whenever the repair or
#: the start policy changes: if a repaired incumbent ever wins a cell, the
#: justification is void and the declaration must come out.
REPAIR_DIFFERENCES = {
    "repair_occurred":
        "D30: across eight stratified previously-fallback states the repaired "
        "incumbent never won -- greedy won 8/8, bit-identical objectives, "
        "identical plan hashes. Under starts=BOTH each arm is entitled to the "
        "same two starts; only the work needed to construct one of them "
        "differs, and that work does not reach the result.",
    "repair_steps": "Ladder steps taken by the repair above. Same reason.",
    "opportunity_events.INCUMBENT_REPAIRED":
        "The event for the repair above, declared BY TYPE. Every other "
        "opportunity-changing event -- START_FALLBACK, MODEL_FALLBACK, "
        "EARLY_TERMINATION, and anything added later -- is its own dimension "
        "and still refuses the comparison.",
}

EXP3_STAGE_A = ExperimentContract(
    experiment="exp3", version="3.1", stage="discovery",
    objective="lambda_scalarized_path_level", objective_version="lambda=2.0",
    evaluator="same_route", envelope="pinned_unedited_baseline",
    pathset_policy="rebuilt_per_state", pool_version="exp3-pool-v1",
    solver=DISCOVERY,
    allowed_treatment_differences=frozenset(
        set(GEOMETRY_DIFFERENCES) | set(REPAIR_DIFFERENCES)),
    justifications={**GEOMETRY_DIFFERENCES, **REPAIR_DIFFERENCES},
    # Two states legitimately need different amounts of search to converge;
    # what may not differ is the OPPORTUNITY to search, which is the fields
    # above this one. Declared rather than assumed.
    opportunity_tolerances={"evaluations_performed": 1.0},
    noise_floor=0.000391,
)
