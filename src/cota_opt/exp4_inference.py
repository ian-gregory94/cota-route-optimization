"""The proposal/certification boundary: discovery proposes, exact decides.

D18 measured the Gen1 heuristic's distance from optimal and found it **tracks
network structure**: sparse networks sit 2.27x further from optimal than dense
ones, with a structure-paired differential of 0.381749 pp against a median gap
of 0.297432 pp (ratio 1.283 against a limit of 0.5 declared in advance). Section
3's forbidding branch was taken, `discovery_effort_comparison_permitted` is
false, and no promotion band was emitted.

That is D27's shape one level up. D27 was the optimizer being *chosen* by the
treatment; this is the optimizer's *answer quality* being correlated with the
treatment. The firewall catches the first and structurally cannot catch the
second, because both arms genuinely run the same optimizer under the same
contract.

So the remedy is not a better firewall rule. It is an architecture:

    **Discovery proposes. Exact optimization decides.**

Discovery output may do exactly one thing -- decide whether a candidate enters a
deliberately broad certification frontier. It may not reach any conclusion.
Nothing that is reported, ranked, compared, promoted to leader, or described as
an effect may be a function of a discovery score.

WHY A TYPE AND NOT A CONVENTION
-------------------------------
A rule that says "do not use discovery scores for inference" is a rule someone
breaks in six months with a one-line sort. `ProposalScore` makes it fail
instead: it holds the number and refuses to be compared, ordered, or converted
to a float. The only way to read it is `for_promotion_only()`, whose name is
the audit trail. Everything downstream therefore has to be written with the
boundary in view, and a violation is an exception at the call site rather than a
quiet reordering nobody notices.

Certified values are ordinary floats, because they are the ones allowed to
decide things.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .firewall.core import digest


class InferenceViolation(RuntimeError):
    """A proposal-stage value was used where only an exact result may decide."""


_WHY = (
    "This is a DISCOVERY (proposal-stage) value. D18 established that the "
    "discovery heuristic's distance from optimal tracks network structure, so a "
    "discovery score may not order, compare, select, or describe anything. It "
    "may only decide whether a candidate enters the certification frontier. "
    "Call .for_promotion_only() if that is genuinely what you are doing, or use "
    "the certified value instead."
)


class ProposalScore:
    """A discovery objective that refuses to be used for inference.

    Deliberately not a float subclass: inheriting from float would make every
    comparison and arithmetic operation work by default, and the whole point is
    that they must not.
    """

    __slots__ = ("_v", "_stage")

    def __init__(self, value: float, stage: str = "gen2_discovery") -> None:
        self._v = float(value)
        self._stage = str(stage)

    # -- the ONE permitted accessor ---------------------------------------
    def for_promotion_only(self) -> float:
        """Read the number for a promotion decision and nothing else."""
        return self._v

    @property
    def stage(self) -> str:
        return self._stage

    def __repr__(self) -> str:
        return f"ProposalScore({self._v!r}, stage={self._stage!r})"

    # -- everything that would let it decide something --------------------
    def _refuse(self, *_a: Any, **_k: Any):
        raise InferenceViolation(_WHY)

    __float__ = _refuse
    __int__ = _refuse
    __index__ = _refuse
    __lt__ = _refuse
    __le__ = _refuse
    __gt__ = _refuse
    __ge__ = _refuse
    __eq__ = _refuse
    __ne__ = _refuse
    __hash__ = None                     # type: ignore[assignment]
    __add__ = __radd__ = _refuse
    __sub__ = __rsub__ = _refuse
    __mul__ = __rmul__ = _refuse
    __truediv__ = __rtruediv__ = _refuse
    __neg__ = __abs__ = _refuse
    __round__ = _refuse
    __format__ = _refuse


@dataclass(frozen=True)
class ProposalRecord:
    """What discovery said, and the fact that it may not decide anything."""

    state_key: str
    state_digest: str
    score: ProposalScore
    #: how the proposal was produced, for the receipt
    solver: str = "gen2_search"
    pathset_policy: str = "supernetwork_master"
    approximate: bool = True
    notes: str = ""

    def payload(self) -> dict:
        return {"stage": "proposal", "approximate": True,
                "state_key": self.state_key, "state_digest": self.state_digest,
                "solver": self.solver, "pathset_policy": self.pathset_policy,
                "discovery_objective_APPROXIMATE":
                    self.score.for_promotion_only(),
                "may_decide": [],
                "notes": self.notes}


@dataclass(frozen=True)
class PromotionDecision:
    """Why a candidate did or did not enter the certification frontier."""

    state_key: str
    promoted: bool
    rule: str
    rule_digest: str
    reason: str
    rank_within_proposals: int = -1

    def payload(self) -> dict:
        return {"stage": "promotion", "state_key": self.state_key,
                "promoted": self.promoted, "rule": self.rule,
                "rule_digest": self.rule_digest, "reason": self.reason,
                "rank_within_proposals_APPROXIMATE":
                    self.rank_within_proposals}


@dataclass(frozen=True)
class CertifiedResult:
    """The exact result. The only thing permitted to decide anything."""

    state_key: str
    state_digest: str
    objective: float
    fitness: dict
    plan_digest: str
    #: the optimality property actually established, in words
    guarantee: str
    n_keys: int
    k_rungs: int
    rounds: int
    converged: bool
    block_enumerations: int
    combinations: int
    seconds: float
    code_version: str = ""
    contract_digest: str = ""

    def payload(self) -> dict:
        return {"stage": "certification", "approximate": False,
                "state_key": self.state_key, "state_digest": self.state_digest,
                "objective_EXACT": self.objective,
                "fitness_EXACT": dict(self.fitness),
                "plan_digest": self.plan_digest,
                "guarantee": self.guarantee,
                "n_keys": self.n_keys, "k_rungs": self.k_rungs,
                "rounds": self.rounds, "converged": self.converged,
                "block_enumerations": self.block_enumerations,
                "combinations": self.combinations,
                "seconds": self.seconds,
                "code_version": self.code_version,
                "contract_digest": self.contract_digest,
                "may_decide": ["ordering", "leader", "separation",
                               "treatment_effect", "frontier_membership"]}


@dataclass
class Exp4Candidate:
    """One candidate, with its three stages kept apart on purpose.

    Reading `final_objective` on an uncertified candidate raises. That is the
    architecture in one line: a candidate that has not been certified has no
    number anyone may use.
    """

    proposal: ProposalRecord
    promotion: PromotionDecision | None = None
    certification: CertifiedResult | None = None
    inferential_status: str = "proposed"

    @property
    def state_key(self) -> str:
        return self.proposal.state_key

    @property
    def certified(self) -> bool:
        return self.certification is not None

    @property
    def final_objective(self) -> float:
        if self.certification is None:
            raise InferenceViolation(
                f"{self.state_key} has no certified result, so it has no value "
                f"that may decide anything. Its discovery score is a proposal "
                f"and D18 forbids using it for inference.")
        return self.certification.objective

    @property
    def final_fitness(self) -> dict:
        if self.certification is None:
            raise InferenceViolation(
                f"{self.state_key} is not certified; there is no exact fitness")
        return dict(self.certification.fitness)

    def payload(self) -> dict:
        return {"state_key": self.state_key,
                "inferential_status": self.inferential_status,
                "proposal": self.proposal.payload(),
                "promotion": self.promotion.payload() if self.promotion else None,
                "certification": (self.certification.payload()
                                  if self.certification else None)}


# ---------------------------------------------------------------------------
# The tie-break, preregistered and structural.
#
# Declared here, before any Experiment 4 result exists, and deliberately
# independent of every discovery quantity. If two candidates certify to the
# same objective they are genuinely indistinguishable on the measure the
# experiment reports, and the tie must be broken by something about the
# NETWORK, not by which one discovery happened to like.
#
# Order, applied in sequence until one differs:
#   1. fewer active lines     -- the more parsimonious network wins; a network
#                                that achieves the same objective with less
#                                structure is the better answer on every
#                                secondary ground the project cares about
#                                (gate 4-8's abandonment reporting, operating
#                                simplicity, evidence class exposure).
#   2. fewer OFF route-periods in the certified plan -- less latent structure
#                                that is carried but unused.
#   3. lexicographically smallest sorted line-id tuple -- an arbitrary but
#                                TOTAL and deterministic final order, so the
#                                result never depends on iteration order.
# ---------------------------------------------------------------------------
TIE_BREAK = ("fewer_active_lines", "fewer_off_route_periods",
             "lexicographic_line_ids")
TIE_BREAK_DIGEST = digest({"tie_break": list(TIE_BREAK), "version": 1})


def tie_break_key(cand: Exp4Candidate, lines: list[str], n_off: int) -> tuple:
    """The preregistered structural tie-break. No discovery quantity appears."""
    return (len(lines), int(n_off), tuple(sorted(lines)))


def rank_certified(cands: list[Exp4Candidate],
                   lines_of, n_off_of) -> list[Exp4Candidate]:
    """Order candidates by CERTIFIED objective, then the structural tie-break.

    Refuses outright if any candidate is uncertified: an ordering that mixes
    exact and approximate values is exactly the confusion this module exists to
    prevent.
    """
    bad = [c.state_key for c in cands if not c.certified]
    if bad:
        raise InferenceViolation(
            f"cannot rank: {len(bad)} candidate(s) are not certified "
            f"({bad[:3]}). Ranking is an exact-stage operation.")
    return sorted(cands, key=lambda c: (c.final_objective,
                                        tie_break_key(c, lines_of(c),
                                                      n_off_of(c))))
