"""Proposal generation: deterministic multi-start with structural seeding.

PREREGISTERED REVISION 2, 2026-09-06. Committed before any new C9 outcome was
examined.

WHY THIS EXISTS
---------------
C9 revision 1 failed, and the diagnosis was unambiguous. The promotion rule
promoted 89 of 89 proposals -- 100% in every cell, cap never binding, window
never binding -- so promotion was not the constraint. Discovery proposed only
79% of a space small enough to enumerate exhaustively, and the certified winner
sat in the missing 21% in two of five cells. Both misses were the same network,
with `feasible_at_discovery = None`: discovery did not reject it, it never
looked at it.

The cause is structural. `gen2_search.search` is a single steepest-descent
trajectory from one seed. It halts when no move improves, which on these cells
happened after 13-23 evaluations against a budget of 400. It was not short of
budget; it was finished. **A local search walks one basin. It does not cover a
space.**

So the revision is to proposal generation only. Nothing in the inference
architecture changes: D18, `ProposalScore`, exact certification, the 5% window,
the floor of 25, the cap of 200, the C9 pass criteria and exact-only inference
are all untouched.

WHAT CHANGES
------------
Each cell now runs the SAME neighbourhood search from many deterministic
starting networks, and the proposal set is the union of **every unique candidate
visited on every trajectory** -- not just the terminal optima. A trajectory that
walks past a good network on its way to a worse one still contributes it.

The budget becomes a shared pool rather than a per-start ceiling. A start that
converges early releases what it did not use, and starts keep launching until
the pool is exhausted or the preregistered family is finished. One start
reaching a local optimum no longer stops anything.

Scoring is memoized across starts, so re-visiting a candidate costs nothing.
Duplicate visits are counted and reported (they are the saturation signal) but
only unique evaluations are charged against the budget.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from .firewall.core import digest

#: Total UNIQUE scored evaluations available to a cell, shared across all
#: starts. Revision 1 gave each single start 400 and saw 13-23 used, which
#: measured nothing: the ceiling was never the binding constraint, the basin
#: was. Discovery cost 89 seconds against 91 minutes of certification in
#: revision 1, so this is deliberately generous -- proposal has three orders of
#: magnitude of headroom before it becomes the bottleneck.
TOTAL_EVAL_BUDGET = 2000

#: How many diversified pseudo-random starts follow the structural family.
#: Fixed here, not tuned per cell.
N_DIVERSIFIED = 24

#: The base of the diversified seed schedule. One number, used for every cell,
#: so no cell gets its own seeds.
SEED_SCHEDULE_BASE = 20260906


def _spread(pool: Sequence[str], k: int) -> tuple[str, ...]:
    """k lines spread evenly across the canonical ordering, not the first k.

    Taking the first k concentrates every seed in one corner of the pool, which
    is the opposite of basin coverage.
    """
    n = len(pool)
    if k <= 0 or n == 0:
        return ()
    if k >= n:
        return tuple(pool)
    idx = sorted({min(n - 1, round(i * n / k)) for i in range(k)})
    # round() can collide; fill deterministically from the front
    for c in range(n):
        if len(idx) >= k:
            break
        if c not in idx:
            idx.append(c)
            idx.sort()
    return tuple(pool[i] for i in idx[:k])


@dataclass
class StartSpec:
    """One preregistered starting network, with why it is in the family."""

    name: str
    lines: tuple[str, ...]
    kind: str
    rationale: str


def build_seed_family(pool: Sequence[str], lo: int, hi: int,
                      *, pinned_lines: Sequence[str] = (),
                      incumbent: Sequence[str] | None = None,
                      greedy_add: Sequence[str] | None = None,
                      greedy_drop: Sequence[str] | None = None,
                      ) -> list[StartSpec]:
    """The preregistered seed family, in preregistered order.

    Order is fixed here and is not a function of any score. It spans the
    treatment dimension -- how many lines are active, and which -- because that
    is the dimension D18 showed the solver's behaviour varies along.
    """
    pool = list(pool)
    hi = min(hi, len(pool))
    out: list[StartSpec] = []

    def add(name, lines, kind, why):
        t = tuple(sorted(set(lines)))
        if lo <= len(t) <= hi and t:
            out.append(StartSpec(name, t, kind, why))

    # 1. maximum feasible activation -- the dense corner
    add("max_lines", _spread(pool, hi), "structural",
        "every line the cell allows, the dense end of the treatment dimension")

    # 2. minimum feasible activation -- the sparse corner
    add("min_lines", _spread(pool, lo), "structural",
        "the sparsest admissible network, the end where D18 found the gap "
        "largest")

    # 3. every intermediate cardinality, spread across the canonical ordering
    for k in range(lo, hi + 1):
        add(f"spread_k{k}", _spread(pool, k), "structural",
            f"{k} lines spread evenly across the canonical ordering rather "
            f"than the first {k}, so seeds do not all start in one corner")

    # 3b. a second spread per cardinality, offset by half a stride, so two
    #     seeds of the same size do not sit on the same lines
    for k in range(lo, hi + 1):
        n = len(pool)
        if k < n:
            rot = pool[max(1, n // (2 * max(k, 1))):] + \
                pool[:max(1, n // (2 * max(k, 1)))]
            add(f"spread_k{k}_offset", _spread(rot, k), "structural",
                f"{k} lines spread on a half-stride offset, so the two "
                f"same-size structural seeds cover different lines")

    # 4. the incumbent / current network, where the cell has one
    if incumbent:
        add("incumbent", incumbent, "structural",
            "the current network, where the cell corresponds to one")

    # 5/6. greedy constructions, supplied by the caller because they cost
    #      evaluations and must be charged against the budget
    if greedy_add:
        add("greedy_add", greedy_add, "constructed",
            "built by greedily adding the best single line at each step")
    if greedy_drop:
        add("greedy_drop", greedy_drop, "constructed",
            "built by greedily dropping the worst single line from the "
            "maximum network")

    # 7. OFF-density variants: where the cell pins route-periods OFF, include
    #    seeds that DO and DO NOT activate the pinned line, so the basin where
    #    the pin actually binds is entered deliberately rather than by luck.
    #
    #    Built from the pool WITHOUT the pinned line and then adding it, rather
    #    than spreading over the whole pool and unioning the pin in. The first
    #    version did the latter and the result collided with an existing spread
    #    seed, so de-duplication silently removed the only seed that activates
    #    the pin -- in the `many_off` cell, which is one of the two cells
    #    revision 1 missed. A seed family that drops the seed it was written
    #    for is worse than one that never had it, because the intent is on the
    #    page and the coverage is not.
    for pl in pinned_lines:
        rest = [x for x in pool if x != pl]
        for k in range(max(lo, 1), hi + 1):
            with_pin = tuple(sorted({pl} | set(_spread(rest, k - 1))))
            if lo <= len(with_pin) <= hi and pl in with_pin:
                add(f"off_dense_k{k}_{pl[-6:]}", with_pin, "off_density",
                    f"activates the pinned-off line alongside {k - 1} others, "
                    f"so the OFF constraint binds and that basin is seeded")
        without = tuple(x for x in _spread(pool, hi) if x != pl)
        add(f"off_sparse_{pl[-6:]}", without, "off_density",
            "excludes the pinned-off line entirely, the complementary OFF "
            "density")

    # de-duplicate by line set, keeping the first (preregistered) occurrence
    seen, uniq = set(), []
    for s in out:
        if s.lines in seen:
            continue
        seen.add(s.lines)
        uniq.append(s)

    # A pinned line must end up activated by SOMETHING. De-duplication is
    # allowed to remove a redundant seed; it is not allowed to remove the only
    # representative of a basin. Asserted rather than hoped for.
    for pl in pinned_lines:
        if not any(pl in s.lines for s in uniq):
            for k in range(max(lo, 1), hi + 1):
                cand = tuple(sorted({pl} | set(_spread(
                    [x for x in pool if x != pl], k - 1))))
                if lo <= len(cand) <= hi and cand not in seen:
                    uniq.append(StartSpec(
                        f"off_dense_fallback_{pl[-6:]}", cand, "off_density",
                        "guaranteed representative of the basin where the pin "
                        "binds; the preferred variants were all duplicates"))
                    seen.add(cand)
                    break
    return uniq


def diversified_starts(pool: Sequence[str], lo: int, hi: int, n: int,
                       *, base: int = SEED_SCHEDULE_BASE) -> list[StartSpec]:
    """Deterministic pseudo-random starts from a fixed schedule.

    Pseudo-random, never stochastic inference: the schedule is the same for
    every cell, so no cell receives seeds chosen for it. Their purpose is basin
    coverage.
    """
    pool = list(pool)
    hi = min(hi, len(pool))
    out = []
    for i in range(n):
        rng = random.Random(f"{base}:{i}")
        k = rng.randint(lo, hi)
        lines = tuple(sorted(rng.sample(pool, k)))
        out.append(StartSpec(f"div_{i:02d}", lines, "diversified",
                             f"diversified start {i} from the fixed schedule "
                             f"{base}"))
    return out


PROPOSAL_RULE = {
    "name": "multi_start_structural",
    "revision": 2,
    "supersedes": ("revision 1: a single steepest-descent trajectory from one "
                   "seed, which covered 79% of an enumerable space and missed "
                   "the certified winner in 2 of 5 C9 cells"),
    "starts": ("the preregistered structural family (max, min, per-cardinality "
               "spread and half-stride offset, incumbent where applicable, "
               "greedy-add, greedy-drop, OFF-density variants), followed by "
               f"{N_DIVERSIFIED} diversified starts from fixed schedule "
               f"{SEED_SCHEDULE_BASE}"),
    "proposal_set": ("the union of EVERY unique candidate visited on every "
                     "trajectory, not only the terminal optima"),
    "budget": ("a shared pool of "
               f"{TOTAL_EVAL_BUDGET} unique scored evaluations per cell; a "
               "start that converges early releases the remainder; starts "
               "continue until the pool is exhausted or the family is "
               "finished"),
    "stopping_rule": ("never stop globally because one start reached a local "
                      "optimum"),
    "memoization": ("scores are memoized across starts; duplicate visits are "
                    "counted and reported but charged nothing"),
    "total_eval_budget": TOTAL_EVAL_BUDGET,
    "n_diversified": N_DIVERSIFIED,
    "seed_schedule_base": SEED_SCHEDULE_BASE,
    "changes_to_inference": "none",
}
PROPOSAL_DIGEST = digest(PROPOSAL_RULE)


@dataclass
class MultiStartResult:
    candidates: dict                       # state_key -> Candidate
    feasible: dict                         # state_key -> bool
    starts_run: list[dict] = field(default_factory=list)
    saturation: list[int] = field(default_factory=list)   # cumulative unique
    marginal: list[int] = field(default_factory=list)     # new per start
    unique_evaluations: int = 0
    duplicate_visits: int = 0
    budget_exhausted: bool = False
    seconds: float = 0.0

    def payload(self) -> dict:
        return {"rule": PROPOSAL_RULE, "rule_digest": PROPOSAL_DIGEST,
                "n_starts": len(self.starts_run),
                "unique_evaluations": self.unique_evaluations,
                "duplicate_visits": self.duplicate_visits,
                "unique_candidates": len(self.candidates),
                "budget_exhausted": self.budget_exhausted,
                "saturation_cumulative_unique": self.saturation,
                "marginal_unique_per_start": self.marginal,
                "starts": self.starts_run,
                "seconds": self.seconds}


def run_multi_start(pool, scorer, periods, *, lo, hi, pins, pool_version,
                    seed_family: list[StartSpec],
                    budget: int = TOTAL_EVAL_BUDGET,
                    search_fn=None) -> MultiStartResult:
    """Run the preregistered family, sharing one evaluation budget.

    `scorer` is wrapped so that a candidate scored on one trajectory is free on
    every later one. Only first-time scores are charged, which is what makes a
    shared budget meaningful across overlapping trajectories.
    """
    import time

    from .gen2_search import search as _search
    search_fn = search_fn or _search

    memo: dict[tuple, Any] = {}
    charged = {"n": 0}
    dupes = {"n": 0}

    def wrapped(sel):
        key = (tuple(sorted(sel.lines)), tuple(sorted(sel.pinned_off)))
        if key in memo:
            dupes["n"] += 1
            return memo[key]
        charged["n"] += 1
        r = scorer(sel)
        memo[key] = r
        return r

    t0 = time.time()
    cands: dict = {}
    feas: dict = {}
    starts_run, saturation, marginal = [], [], []
    exhausted = False

    for spec in seed_family:
        remaining = budget - charged["n"]
        if remaining <= 0:
            exhausted = True
            break
        before = len(cands)
        try:
            res = search_fn(list(pool), wrapped, list(periods),
                            seed_lines=spec.lines, max_lines=hi, min_lines=lo,
                            pinned_off=tuple(pins), pool_version=pool_version,
                            allow_swaps=True, pair_adds=True,
                            max_evaluations=max(remaining, 1))
        except Exception as e:
            starts_run.append({"name": spec.name, "kind": spec.kind,
                               "lines": list(spec.lines),
                               "error": f"{type(e).__name__}: {e}"[:160]})
            continue
        for c in res.evaluated:
            k = c.selection.state_key
            if k not in cands:
                cands[k] = c
                feas[k] = bool(c.feasible)
        new = len(cands) - before
        marginal.append(new)
        saturation.append(len(cands))
        starts_run.append({"name": spec.name, "kind": spec.kind,
                           "lines": list(spec.lines),
                           "rationale": spec.rationale,
                           "evaluated": len(res.evaluated),
                           "new_unique": new,
                           "cumulative_unique": len(cands)})

    return MultiStartResult(
        candidates=cands, feasible=feas, starts_run=starts_run,
        saturation=saturation, marginal=marginal,
        unique_evaluations=charged["n"], duplicate_visits=dupes["n"],
        budget_exhausted=exhausted or charged["n"] >= budget,
        seconds=time.time() - t0)
