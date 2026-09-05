"""The Experiment 4 contracts, IN FORCE.

Promoted from `exp4_draft.py` on 2026-09-05 under the condition the draft set
itself: *active only when Gen1 is frozen and the Gen1->Gen2 bridge suite has
run* (METHODOLOGY.md). Both are now true -- `gen1-frozen-v1` and the bridge in
`outputs/exp4/gen_bridge.json`. The draft module stays where it is, unmodified,
as the record of what was written before the condition was met.

Two things changed on promotion, and neither relaxes anything.

1. The provisional evaluation tolerance is GONE, because it was already inert.
   ------------------------------------------------------------------------
   The draft carried ``opportunity_tolerances={"evaluations_performed": 2.0}``
   and flagged it provisional, pending an instrument that normalises search by
   decision count. On 2026-09-04 `evaluations_performed` was reclassified
   Sem.OPPORTUNITY -> Sem.OUTCOME in `receipt.py`. `compare()` walks only the
   identity and opportunity maps, so from that moment the tolerance entry
   matched no field and constrained nothing. Carrying it forward into an
   in-force contract would advertise effort protection that does not exist,
   which is worse than having none: it is the kind of entry someone later
   points at to argue the comparison was guarded.

   It is dropped, and the guard it was standing in for is made mandatory below.

2. The allowance check is REQUIRED, by signature.
   ----------------------------------------------
   With `evaluations_performed` an outcome, `SearchAllowance` is the only thing
   left that holds search entitlement equal between two networks with different
   decision counts. `compare_exp4` therefore takes both `AllowanceRecord`s as
   required keyword arguments and refuses without them. A caller cannot forget
   the effort check and still get a verdict, because there is no call that
   omits it and succeeds.

   `compare_exp4` runs `firewall.compare` unchanged and then adds the allowance
   verdict. It can only turn an admissible comparison inadmissible. It can
   never admit one that `compare` refused.
"""
from __future__ import annotations

from .compare import (ComparisonResult, Difference, InadmissibleComparison,
                      compare)
from .contract import ExperimentContract
from .policy import CERTIFICATION, SolverPolicy, StartPolicy
from .search_allowance import EXP4_ALLOWANCE, AllowanceRecord, comparable

#: Verbatim from `exp4_draft.NETWORK_DIFFERENCES`. Copied rather than imported
#: so that the in-force whitelist is readable in one place and cannot be
#: changed by editing a module labelled "draft, not in force".
NETWORK_DIFFERENCES = {
    "state_digest":
        "The network itself. This IS the treatment.",
    "state_key":
        "The network's name. Follows from state_digest.",
    "cardinality":
        "How many lines the network activates. Part of the treatment: service "
        "activation, including OFF, is a decision variable in this experiment.",
    "members":
        "Which lines it activates. Part of the treatment.",
    "pathset_digest":
        "A different route structure has different shortest paths. Requiring "
        "identical path sets would admit only a comparison of a network with "
        "itself. The path-set POLICY is an identity field of its own and must "
        "still match exactly -- that is what stops one arm being enumerated "
        "differently from the other.",
}

#: NOT declared, deliberately, and unchanged from the draft: starts_attempted,
#: starts_rejected, fallback_occurred, repair_occurred, restarts_completed,
#: termination, converged, and every opportunity_events.* type. The D27 class
#: of failure -- an execution difference decided by the treatment -- stays
#: fatal in a search where adaptive per-network behaviour makes it likelier.

EXP4_DISCOVERY = ExperimentContract(
    experiment="exp4", version="4.0", stage="discovery",
    objective="lambda_scalarized_path_level", objective_version="lambda=2.0",
    evaluator="same_route", envelope="pinned_exp3_certified_baseline",
    pathset_policy="supernetwork_master", pool_version="exp4-pool-v1",
    methodology_generation="gen2",
    solver=SolverPolicy(name="exp4_discovery",
                        start_policy=StartPolicy.BOTH, restarts=2,
                        evaluation_ceiling=60_000, candidate_width=32,
                        require_convergence=False, seeds=(20260825,)),
    allowed_treatment_differences=frozenset(NETWORK_DIFFERENCES),
    justifications=dict(NETWORK_DIFFERENCES),
    # See module docstring, point 1. Effort is held equal by EXP4_ALLOWANCE
    # via compare_exp4, not by a tolerance on a field that is now an outcome.
    opportunity_tolerances={},
    # No noise floor. D32: the pipeline is deterministic, so replicate spread
    # is zero and bounds nothing. Experiment 4's threshold comes from its own
    # gap benchmark, run before its search, and is not set here.
    noise_floor=None,
)

EXP4_CERTIFICATION = ExperimentContract(
    experiment="exp4", version="4.0", stage="certification",
    objective="lambda_scalarized_path_level", objective_version="lambda=2.0",
    evaluator="same_route", envelope="pinned_exp3_certified_baseline",
    # Certification re-enumerates exactly. The discovery supernetwork is a
    # shared master path set, which is a different evidence class, and the
    # firewall will refuse to compare across the two -- correctly.
    pathset_policy="rebuilt_per_network", pool_version="exp4-pool-v1",
    methodology_generation="gen2", solver=CERTIFICATION,
    allowed_treatment_differences=frozenset(NETWORK_DIFFERENCES),
    justifications=dict(NETWORK_DIFFERENCES),
    opportunity_tolerances={},
    noise_floor=None,
)

#: The allowance these contracts are enforced against. Bound here so that the
#: contract and the effort instrument travel together.
ALLOWANCE = EXP4_ALLOWANCE


def compare_exp4(control, treatment, contract: ExperimentContract, *,
                 control_allowance: AllowanceRecord,
                 treatment_allowance: AllowanceRecord,
                 allowance=ALLOWANCE,
                 permit_budget_limited: str = "",
                 ) -> ComparisonResult | InadmissibleComparison:
    """`compare`, plus the search-allowance check that `compare` cannot make.

    Both allowance records are required. There is no call signature that skips
    the effort check, which is the point: `evaluations_performed` is an outcome
    field now, so nothing in `compare` looks at search entitlement at all.

    `permit_budget_limited` must carry a written justification to allow a
    comparison in which either arm hit the absolute ceiling; empty means such a
    comparison is refused, per `search_allowance.comparable`.
    """
    result = compare(control, treatment, contract)
    ok, reasons = comparable(control_allowance, treatment_allowance,
                             allowance, permit_budget_limited)
    if ok:
        return result
    diffs = (Difference("search_allowance",
                        control_allowance.allowance_digest,
                        treatment_allowance.allowance_digest,
                        "opportunity"),)
    if isinstance(result, InadmissibleComparison):
        return InadmissibleComparison(
            contract, result.allowed, tuple(result.undeclared) + diffs,
            tuple(result.notes) + tuple(reasons))
    return InadmissibleComparison(
        contract, tuple(sorted(contract.allowed_treatment_differences)),
        diffs, tuple(reasons))
