"""The promotion frontier: deliberately permissive, deterministic, preregistered.

D18 emitted **no promotion band** and must not be made to. This replaces the
band with a proposal-only policy whose job is the opposite of a band's: a band
decides what is *good enough to conclude*, and none is licensed. This decides
only what is *worth certifying*, which is a compute question.

THE ASYMMETRY THAT SETS THE POLICY
----------------------------------
False positives cost compute and nothing else: exact certification removes them,
and a promoted candidate that certifies badly simply loses. A false negative is
unrecoverable -- a candidate discovery discards is a candidate certification
never sees, and the reported winner is then wrong in a way no downstream check
can detect. So the policy favours recall, and the only reason not to promote
everything is that certification has to fit in a machine.

WHY THE WINDOW IS THE SIZE IT IS
--------------------------------
Not chosen for convenience. D18 measured how wrong a discovery score can be:

    maximum absolute gap of the delivered plan            0.645892 %
    largest structure-paired differential                 0.381749 pp
    ------------------------------------------------------------------
    worst case a discovery score can misplace a candidate ~1.03 %

`WINDOW_REL = 0.05` is **5%**, roughly five times that worst case. For a true
winner to fall outside the window, discovery would have to be about five times
more wrong than the worst case D18 actually observed. That is the margin, and
it is stated so it can be argued with rather than assumed.

`FLOOR_N = 25` promotes the 25 best proposals whatever their scores, so a space
whose objectives are tightly bunched -- where 5% captures everything and the
window stops discriminating -- still certifies a meaningful set, and a space
whose objectives are spread wide still certifies more than a handful.

`CAP_N = 200` is the compute constraint, and it is honest about being one.
Certification was measured at ~145 s for a 30-route-period network, so 200
candidates is roughly eight hours at that size and considerably more at
Experiment 4 scale. **Hitting the cap is recorded as a recall risk on the
receipt**, because at that point the policy has stopped being permissive and has
started being a budget.

Ordering by discovery score is permitted and is the only permitted use of it:
section 1 of the execution contract allows discovery scores to determine
"whether a candidate enters a deliberately broad certification frontier" and
nothing else. The ordering never leaves this module.
"""
from __future__ import annotations

from dataclasses import dataclass

from .exp4_inference import PromotionDecision, ProposalRecord
from .firewall.core import digest

WINDOW_REL = 0.05          # 5% of the best discovery objective
FLOOR_N = 25               # always promote at least this many, if they exist
CAP_N = 200                # compute ceiling; hitting it is a recorded risk

PROMOTION_RULE = {
    "name": "permissive_frontier",
    "version": 1,
    "statement": (
        "Promote every FEASIBLE proposal whose discovery objective is within "
        "WINDOW_REL of the best discovery objective; if that yields fewer than "
        "FLOOR_N, promote the FLOOR_N best instead; never promote more than "
        "CAP_N, and record cap_binding when the cap truncates the set."),
    "window_rel": WINDOW_REL,
    "floor_n": FLOOR_N,
    "cap_n": CAP_N,
    "order": "ascending discovery objective, then state_key for determinism",
    "justification": {
        "d18_max_absolute_gap_pct": 0.645892,
        "d18_largest_structure_paired_differential_pp": 0.381749,
        "worst_case_discovery_misplacement_pct": 1.03,
        "window_is_multiple_of_worst_case": 4.85,
    },
    "asymmetry": ("false positives cost only compute because certification "
                  "removes them; false negatives are unrecoverable"),
    "may_decide": "frontier membership only; never a conclusion",
}
PROMOTION_DIGEST = digest(PROMOTION_RULE)


@dataclass(frozen=True)
class PromotionOutcome:
    decisions: list[PromotionDecision]
    promoted_keys: list[str]
    n_proposals: int
    n_feasible: int
    n_promoted: int
    window_absolute: float
    best_discovery_objective: float
    cap_binding: bool
    floor_binding: bool
    window_binding: bool
    rule_digest: str

    def payload(self) -> dict:
        return {"rule": PROMOTION_RULE, "rule_digest": self.rule_digest,
                "n_proposals": self.n_proposals,
                "n_feasible": self.n_feasible,
                "n_promoted": self.n_promoted,
                "window_absolute_APPROXIMATE": self.window_absolute,
                "best_discovery_objective_APPROXIMATE":
                    self.best_discovery_objective,
                "cap_binding": self.cap_binding,
                "floor_binding": self.floor_binding,
                "window_binding": self.window_binding,
                "recall_risk": (
                    "CAP BOUND -- the frontier was truncated by the compute "
                    "ceiling, so a true winner ranked below CAP_N by discovery "
                    "would not have been certified"
                    if self.cap_binding else "none recorded"),
                "promoted_keys": list(self.promoted_keys)}


def promote(proposals: list[ProposalRecord],
            feasible: dict[str, bool] | None = None) -> PromotionOutcome:
    """Apply the preregistered rule. Deterministic in its input, and total.

    `proposals` may arrive in any order; the result does not depend on it.
    Ties in discovery objective are broken by `state_key` so the promoted set is
    a function of the proposals alone.
    """
    feasible = feasible or {}
    live = [p for p in proposals if feasible.get(p.state_key, True)]
    n_prop, n_feas = len(proposals), len(live)
    if not live:
        return PromotionOutcome([], [], n_prop, 0, 0, float("nan"),
                                float("nan"), False, False, False,
                                PROMOTION_DIGEST)

    # The one permitted use of a discovery score, and it never leaves here.
    ordered = sorted(live,
                     key=lambda p: (p.score.for_promotion_only(), p.state_key))
    best = ordered[0].score.for_promotion_only()
    window_abs = abs(best) * WINDOW_REL
    in_window = [p for p in ordered
                 if p.score.for_promotion_only() <= best + window_abs]

    floor_binding = len(in_window) < FLOOR_N
    chosen = ordered[:max(len(in_window), FLOOR_N)]
    window_binding = len(in_window) >= FLOOR_N and len(in_window) < len(ordered)
    cap_binding = len(chosen) > CAP_N
    chosen = chosen[:CAP_N]
    keys = {p.state_key for p in chosen}

    decisions = []
    for i, p in enumerate(ordered):
        promoted = p.state_key in keys
        if promoted:
            why = ("within the 5% window of the best discovery objective"
                   if p.score.for_promotion_only() <= best + window_abs
                   else f"inside the floor of {FLOOR_N} best proposals")
        else:
            why = (f"beyond the compute cap of {CAP_N}" if cap_binding
                   else f"outside the {WINDOW_REL:.0%} window and the "
                        f"{FLOOR_N}-proposal floor")
        decisions.append(PromotionDecision(
            state_key=p.state_key, promoted=promoted,
            rule=PROMOTION_RULE["name"], rule_digest=PROMOTION_DIGEST,
            reason=why, rank_within_proposals=i))
    for p in proposals:
        if p.state_key not in {d.state_key for d in decisions}:
            decisions.append(PromotionDecision(
                state_key=p.state_key, promoted=False,
                rule=PROMOTION_RULE["name"], rule_digest=PROMOTION_DIGEST,
                reason="infeasible at proposal stage", rank_within_proposals=-1))

    return PromotionOutcome(
        decisions=decisions,
        promoted_keys=sorted(keys),
        n_proposals=n_prop, n_feasible=n_feas, n_promoted=len(keys),
        window_absolute=window_abs, best_discovery_objective=best,
        cap_binding=cap_binding, floor_binding=floor_binding,
        window_binding=window_binding, rule_digest=PROMOTION_DIGEST)
