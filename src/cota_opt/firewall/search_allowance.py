"""Search opportunity per decision dimension — the Experiment 4 effort contract.

IN FORCE from 2026-09-04. Staged outside `src/cota_opt` until then because
OPERATIONS 24 freezes that path while a batch runs: any edit changes
`code_version` and splits a running batch into two incomparable halves. It moved
here after Generation 1 was frozen (`gen1-frozen-v1`), which is the declared
boundary the source digest is allowed to cross -- Gen1 results stay verifiable
because every receipt carries the `code_version` it was produced under.

The invariant
-------------
**Allocated search opportunity, not realised evaluations.**

Experiment 3 could compare realised evaluation counts because every state had
the same number of frequency decisions. Experiment 4 cannot: a network with 38
active lines has fewer decision dimensions than one with 41, so its search
consumes fewer evaluations *mechanically*, and requiring the counts to match
would refuse every honest comparison while a plain relative tolerance would
wave through a genuine difference in entitlement.

So the thing held equal is the **allowance**, fixed before the search:

    d_N                  eligible frequency decision dimensions of network N,
                         computed after geometry construction and eligibility
                         checks and BEFORE optimization begins
    k                    preregistered evaluations per decision dimension
    budget_N             min(k * d_N, absolute_ceiling)

Realised `evaluations_performed` is **diagnostic only**. It may differ because a
search converged, exhausted its neighbourhood, or terminated under the common
stopping contract — all of which are the same contract producing different
outcomes, which is what an outcome is.

Why the allocation must precede the search
------------------------------------------
Normalising realised evaluations *after* the fact would let convergence
behaviour and network-specific failures determine effective search effort — an
outcome-dependent confound, and the same shape as D27. The budget is a function
of the network's structure alone, computed before any objective value exists.

The ceiling is honest about itself
----------------------------------
A very large reconstructed network would otherwise buy unbounded compute. When
the ceiling binds, the evaluation is marked `budget_limited` and **is not
treated as having received equivalent normalised opportunity**. A comparison
where either arm is budget-limited is refused unless the contract explicitly
defines and justifies that case.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class AllowanceError(ValueError):
    """An allowance that cannot mean what it says."""


@dataclass(frozen=True)
class SearchAllowance:
    """The preregistered budget function. Every field is declared, none inferred."""

    k: int                                  # evaluations per decision dimension
    absolute_ceiling: int
    minimum_budget: int = 0
    #: Deterministic and declared, per the contract. "none" means k*d exactly.
    rounding: str = "none"
    function: str = "min(max(k*d, minimum), ceiling)"

    def __post_init__(self) -> None:
        if self.k <= 0:
            raise AllowanceError("k must be positive: an allowance of zero "
                                 "evaluations per dimension is not a search")
        if self.absolute_ceiling <= 0:
            raise AllowanceError("the absolute ceiling must be positive")
        if self.minimum_budget < 0:
            raise AllowanceError("the minimum budget cannot be negative")
        if self.rounding not in ("none", "up_to_1000", "up_to_10000"):
            raise AllowanceError(
                f"rounding {self.rounding!r} is not one of the declared "
                f"deterministic rules; an undeclared rule is a free parameter")

    def _round(self, n: int) -> int:
        if self.rounding == "up_to_1000":
            return ((n + 999) // 1000) * 1000
        if self.rounding == "up_to_10000":
            return ((n + 9999) // 10000) * 10000
        return n

    def allocate(self, d: int) -> tuple[int, bool]:
        """Return ``(evaluation_budget, budget_limited)`` for d dimensions.

        Deterministic in ``d`` alone. Nothing about the network's performance,
        or about anything observed during the search, can reach this number.
        """
        if d <= 0:
            raise AllowanceError(
                f"a network with {d} eligible decision dimensions has nothing "
                f"to optimize; it is not a comparable cell")
        raw = self._round(max(self.k * int(d), self.minimum_budget))
        capped = min(raw, self.absolute_ceiling)
        return capped, capped < raw

    @property
    def digest_fields(self) -> dict:
        """Everything that defines the allowance, for the identity digest."""
        return {"k": self.k, "absolute_ceiling": self.absolute_ceiling,
                "minimum_budget": self.minimum_budget,
                "rounding": self.rounding, "function": self.function}


@dataclass(frozen=True)
class AllowanceRecord:
    """What one cell was allocated, as it goes into the ExecutionReceipt.

    ``decision_dimensions`` is a property of the network and may differ between
    arms — that is the whole point. ``allowance_digest`` may not: both arms must
    have been allocated by the same function with the same k and the same
    ceiling.
    """

    decision_dimensions: int
    allowance_digest: str
    evaluation_budget: int
    budget_limited: bool
    evaluations_performed: int = 0       # DIAGNOSTIC ONLY, never compared

    def consistent_with(self, allowance: SearchAllowance) -> tuple[bool, str]:
        """Was this cell allocated by the function it claims?

        This is what makes a post-hoc budget increase detectable: a receipt can
        say anything, but it cannot say something the declared function would
        not have produced from its own decision count.
        """
        try:
            budget, limited = allowance.allocate(self.decision_dimensions)
        except AllowanceError as e:
            return False, str(e)
        if budget != self.evaluation_budget:
            return False, (
                f"budget {self.evaluation_budget} is not what the declared "
                f"function allocates for {self.decision_dimensions} dimensions "
                f"({budget}). A budget that does not follow from the function "
                f"is a budget someone chose after seeing something.")
        if limited != self.budget_limited:
            return False, (
                f"budget_limited={self.budget_limited} contradicts the "
                f"allocation (ceiling {'binds' if limited else 'does not bind'} "
                f"at {self.decision_dimensions} dimensions)")
        return True, ""


def comparable(a: AllowanceRecord, b: AllowanceRecord,
               allowance: SearchAllowance,
               permit_budget_limited: str = "") -> tuple[bool, list[str]]:
    """Do two cells have equivalent allocated search opportunity?

    Checks, in order: both were allocated by the declared function; both used
    the same allowance; and neither hit the ceiling — unless the contract has
    explicitly defined and justified the budget-limited case, in which case the
    justification is required to be non-empty and is recorded.

    Realised evaluation counts are NOT compared. They differ whenever the same
    stopping contract produces different outcomes, which is what a stopping
    contract is for.
    """
    bad: list[str] = []
    for label, r in (("control", a), ("treatment", b)):
        ok, why = r.consistent_with(allowance)
        if not ok:
            bad.append(f"{label}: {why}")
    if a.allowance_digest != b.allowance_digest:
        bad.append(
            f"different search allowances ({a.allowance_digest} vs "
            f"{b.allowance_digest}): the two arms were not entitled to the "
            f"same search per decision dimension")
    if a.budget_limited or b.budget_limited:
        if not permit_budget_limited.strip():
            which = [n for n, r in (("control", a), ("treatment", b))
                     if r.budget_limited]
            bad.append(
                f"{' and '.join(which)} hit the absolute evaluation ceiling, so "
                f"the arms did not receive equivalent normalised search "
                f"opportunity. The contract must define and justify the "
                f"budget-limited case before such a comparison may be made.")
    return (not bad), bad


# ---------------------------------------------------------------------------
# The preregistered Experiment 4 allowance.
#
# Declared 2026-09-04, BEFORE any Experiment 4 network has been scored, because
# EXPERIMENT4_DESIGN.md section 9 item 22 requires k, the ceiling, the minimum
# and the rounding rule to be preregistered rather than settled by whoever
# first hits them.
#
# k = 2000. Chosen from D28, not from taste: at Experiment 3 certification
# effort each restart terminated after roughly 4,000 of its 400,000 permitted
# evaluations, and Gen1's networks carry 173 route-periods. So a whole solve
# used on the order of 4,000 evaluations per restart against ~173 decisions --
# about 23 per decision per restart. At 40 restarts that is ~900 per decision.
# k = 2000 is a little over double the observed need, which is the point: the
# allowance must not bind in ordinary cases, or it silently becomes the
# stopping rule and the stopping contract stops meaning anything.
#
# absolute_ceiling = 400,000. Carried over from Gen1's certification effort so
# that the ceiling is a number this project has already lived with, not a new
# free parameter. It binds at 200 decision dimensions, which is above Gen1's
# 173 but reachable by a large reconstructed network -- which is exactly the
# case the ceiling exists for, and it is marked `budget_limited` when it fires.
#
# minimum_budget = 20,000. A network reduced to a handful of active lines still
# needs enough search to be worth comparing; without a floor, a 3-decision
# network would be allocated 6,000 evaluations and its result would say more
# about its allowance than about the network.
#
# rounding = "up_to_1000". Deterministic, declared, and rounds UP so the
# adjustment can never quietly reduce an allowance.
#
# None of these may be changed once an Experiment 4 result exists. Changing k
# after seeing a result is the search-budget form of moving a threshold.
EXP4_ALLOWANCE = SearchAllowance(
    k=2000,
    absolute_ceiling=400_000,
    minimum_budget=20_000,
    rounding="up_to_1000",
)
