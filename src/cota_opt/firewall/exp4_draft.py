"""DRAFT Experiment 4 contracts. Not imported by any runner, not yet in force.

Written as code rather than prose because a contract is a set of claims about
what may differ, and claims are worth more when something can fail them. The
tests in `tests/test_exp4_contract_draft.py` check that the D27 class of
failure is still fatal here, that a whole-network comparison is possible at
all, and that the certification contract cannot exist without asserting
convergence.

These become active only when Gen1 is frozen and the Gen1->Gen2 bridge suite
has run (METHODOLOGY.md). Until then they are a design artifact.
"""
from __future__ import annotations

from .contract import ExperimentContract
from .policy import CERTIFICATION, DISCOVERY, SolverPolicy, StartPolicy

#: The treatment in Experiment 4 is the whole network, which makes the
#: whitelist the hardest part of the design: two networks may share almost
#: nothing, so a careless list permits almost everything and the firewall
#: passes anything. Each entry names one consequence of changing the network
#: and says why it is not a confound.
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

#: NOT declared, deliberately: starts_attempted, starts_rejected,
#: fallback_occurred, repair_occurred, restarts_completed, termination,
#: converged, and every opportunity_events.* type. The D27 class of failure --
#: an execution difference decided by the treatment -- must stay fatal in a
#: search where adaptive per-network behaviour makes it far more likely.

#: OPEN, and not to be settled by whoever first hits it: networks with
#: different route counts have different numbers of frequency decisions, so
#: `evaluations_performed` differs structurally rather than incidentally. The
#: honest instrument is a tolerance normalised by decision count -- search per
#: dimension, not search in total -- which the firewall does not yet express.
#: Until it does, this draft declares a plain relative tolerance and flags it.
_EVALUATION_TOLERANCE_IS_PROVISIONAL = True

EXP4_DISCOVERY_DRAFT = ExperimentContract(
    experiment="exp4", version="4.0-draft", stage="discovery",
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
    opportunity_tolerances={"evaluations_performed": 2.0},
    # No noise floor. D32: the pipeline is deterministic, so replicate spread
    # is zero and bounds nothing. Experiment 4's threshold comes from its own
    # gap benchmark, run before its search, and is not set here.
    noise_floor=None,
)

EXP4_CERTIFICATION_DRAFT = ExperimentContract(
    experiment="exp4", version="4.0-draft", stage="certification",
    objective="lambda_scalarized_path_level", objective_version="lambda=2.0",
    evaluator="same_route", envelope="pinned_exp3_certified_baseline",
    # Certification re-enumerates exactly. The discovery supernetwork is a
    # shared master path set, which is a different evidence class, and the
    # firewall will refuse to compare across the two -- correctly.
    pathset_policy="rebuilt_per_network", pool_version="exp4-pool-v1",
    methodology_generation="gen2", solver=CERTIFICATION,
    allowed_treatment_differences=frozenset(NETWORK_DIFFERENCES),
    justifications=dict(NETWORK_DIFFERENCES),
    opportunity_tolerances={"evaluations_performed": 2.0},
    noise_floor=None,
)
