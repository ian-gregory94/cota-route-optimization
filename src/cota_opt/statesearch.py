"""Search over network STATES, with a benchmark it has to pass first.

Experiment 2B measured, across all 240 structurally feasible subsets, that
every one of the 227 multi-edit sets delivers less than the sum of its members.
So a search that scores mutations individually and takes the top N is not a
weaker version of the right search — it is a search for a quantity that does not
predict the thing being optimized. Gate 3-6 forbids it as a procedure.

What replaces it is a neighbourhood search over states, with restarts. Each step
considers adding one compatible mutation, removing one, or swapping one for
another, and takes the best neighbour by the primary objective. That is a
heuristic, and heuristics are trusted only where they have been checked:
`benchmark()` runs this same search over the exhaustively enumerated 2B space
and demands the known optimum back, under every declared seed.

The scoring function is injected. This module knows nothing about RAPTOR, path
sets or frequency optimization — which is what lets the benchmark drive it with
2B's own already-computed table and compare like with like.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

log = logging.getLogger(__name__)

#: The empty state is in every search, always. Without it a search reports the
#: best mutation it found rather than whether mutating helps at all — and
#: Experiment 2B's answer was the null.
NULL = "<none>"


@dataclass(frozen=True)
class State:
    """A set of mutation ids. Frozen and sorted, so it is genuinely a set."""

    ids: tuple[str, ...]

    @staticmethod
    def of(ids: Iterable[str]) -> "State":
        return State(tuple(sorted(set(ids))))

    @property
    def key(self) -> str:
        return "+".join(self.ids) if self.ids else NULL

    def __len__(self) -> int:
        return len(self.ids)


@dataclass
class SearchTrace:
    """Everything a reader needs to check the search did what it claims."""

    evaluated: int = 0
    steps: list[dict[str, Any]] = field(default_factory=list)
    best_key: str = NULL
    best_score: float = float("inf")
    restarts: int = 0
    resumed_from: int = 0
    stopped_early: bool = False
    local_optima: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"evaluated": self.evaluated, "restarts": self.restarts,
                "best": self.best_key, "best_score": self.best_score,
                "resumed_from_cached": self.resumed_from,
                "stopped_early": self.stopped_early,
                "local_optima": self.local_optima,
                "steps": self.steps}


class Checkpoint:
    """Scores on disk, keyed below the state level so a resume is exact.

    Sub-state checkpointing matters because a state's score is the expensive
    thing — path-set rebuild plus a frequency solve — and a run that dies
    mid-sweep should lose one state, not the sweep. Append-only JSONL: a crash
    during a write costs the last line, never the file.
    """

    def __init__(self, path: Path | None) -> None:
        self.path = Path(path) if path else None
        self.scores: dict[str, float] = {}
        if self.path and self.path.exists():
            for line in self.path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                    self.scores[r["state"]] = float(r["score"])
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue          # a torn final line is expected, not fatal

    def get(self, key: str) -> float | None:
        return self.scores.get(key)

    def put(self, key: str, score: float, extra: dict | None = None) -> None:
        """Append and **fsync**. The container can vanish between two states.

        Not a hypothetical: the sandbox running this was recycled at 20:42:45Z
        while the session was idle, killing every worker. The disk survived that
        one, but a write sitting in the page cache would not have. Experiment 2
        lost twenty-five minutes of path-set work to the same class of event
        before it started checkpointing per period.

        fsync costs about a millisecond against a 413-second state. There is no
        argument for skipping it.
        """
        self.scores[key] = score
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rec = {"state": key, "score": score,
               "at": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ",
                                                 __import__("time").gmtime()),
               **(extra or {})}
        import os
        with self.path.open("a") as f:
            f.write(json.dumps(rec) + "\n")
            f.flush()
            os.fsync(f.fileno())


def feasible(ids: Sequence[str], incompatible: set[tuple[str, str]]) -> bool:
    """No pair in the state may be structurally incompatible."""
    s = sorted(ids)
    for i, a in enumerate(s):
        for b in s[i + 1:]:
            if (a, b) in incompatible:
                return False
    return True


def neighbours(state: State, pool: Sequence[str],
               incompatible: set[tuple[str, str]],
               max_cardinality: int | None = None) -> list[State]:
    """Add one, drop one, or swap one — the whole move set, deterministic.

    Swap is not redundant with add-then-drop: 2B found cardinality winners are
    **not nested**, so the best 3-set is not the best 2-set plus one. A search
    that can only add and drop has to pass through a worse state to reach a
    better one, and a greedy search will not.
    """
    cur = set(state.ids)
    out: list[State] = []
    for m in pool:
        if m in cur:
            continue
        cand = sorted(cur | {m})
        if max_cardinality and len(cand) > max_cardinality:
            continue
        if feasible(cand, incompatible):
            out.append(State.of(cand))
    for m in sorted(cur):
        out.append(State.of(cur - {m}))
    for out_m in sorted(cur):
        rest = cur - {out_m}
        for in_m in pool:
            if in_m in cur:
                continue
            cand = sorted(rest | {in_m})
            if feasible(cand, incompatible):
                out.append(State.of(cand))
    seen, uniq = set(), []
    for s in out:
        if s.key not in seen:
            seen.add(s.key)
            uniq.append(s)
    return uniq


def ordered_neighbours(state: State, pool: Sequence[str],
                       incompatible: set[tuple[str, str]],
                       max_cardinality: int | None,
                       single_score: dict[str, float] | None = None,
                       rotate: int = 0) -> list[State]:
    """The move set in the order a first-improvement search will visit it.

    Order is preregistered, not tuned after seeing results:

    1. **drops**, worst member first — at most k of them, so undoing a bad
       start costs almost nothing;
    2. **adds**, best measured single first;
    3. **swaps**, best introduced single first.

    `single_score` is Phase A1's MEASURED single-mutation objective — frequency
    re-optimized on each, not a fixed-frequency screen — so gate 3-2 is not in
    play. It changes visit order only. Nothing is discarded and every neighbour
    stays reachable, which is the difference between a search bias (declarable)
    and a selection rule (forbidden by gate 3-6). The bias is reported.

    `rotate` shifts the add and swap orderings by a fixed offset, so a restart
    can explore the same neighbourhood from a different entry point without any
    randomness.
    """
    sc = single_score or {}
    cur = set(state.ids)
    big = float("inf")

    drops, adds, swaps = [], [], []
    for m in sorted(cur):
        drops.append((-sc.get(m, -big), State.of(cur - {m})))
    for m in sorted(pool):
        if m in cur:
            continue
        cand = sorted(cur | {m})
        if max_cardinality and len(cand) > max_cardinality:
            continue
        if feasible(cand, incompatible):
            adds.append((sc.get(m, big), State.of(cand)))
    for out_m in sorted(cur):
        rest = cur - {out_m}
        for in_m in sorted(pool):
            if in_m in cur:
                continue
            cand = sorted(rest | {in_m})
            if feasible(cand, incompatible):
                swaps.append((sc.get(in_m, big), State.of(cand)))

    def _rank(group):
        group.sort(key=lambda t: (t[0], t[1].key))
        if rotate and group:
            k = rotate % len(group)
            group = group[k:] + group[:k]
        return [s for _, s in group]

    out = _rank(drops) + _rank(adds) + _rank(swaps)
    seen, uniq = set(), []
    for s in out:
        if s.key not in seen and s.key != state.key:
            seen.add(s.key)
            uniq.append(s)
    return uniq


def search(pool: Sequence[str],
           score: Callable[[State], float],
           incompatible: set[tuple[str, str]] | None = None,
           seeds: Sequence[int] = (0,),
           max_cardinality: int | None = None,
           max_evaluations: int | None = None,
           checkpoint: Checkpoint | None = None,
           trace: SearchTrace | None = None,
           strategy: str = "best",
           single_score: dict[str, float] | None = None,
           starts: Sequence[State] | None = None,
           rotations: Sequence[int] | None = None,
           deadline: float | None = None,
           lane: str = "") -> tuple[State, float, SearchTrace]:
    """Neighbourhood search with restarts. Lower score wins.

    `strategy="best"` evaluates the whole neighbourhood each step and takes the
    minimum. It is what the 2B benchmark first validated, and it is unaffordable
    on the real pool: 84 mutations give neighbourhoods of 84 to 300 states at
    ~7 minutes each, so a single step costs hours.

    `strategy="first"` takes the FIRST neighbour that improves, visiting them in
    the preregistered order above. Both are benchmarked on the exhaustive space
    before either is trusted.

    Deterministic given its inputs: starts, rotations and visit order are all
    explicit rather than drawn from a global RNG, so a rerun reproduces the
    trajectory and not merely the answer.
    """
    import time as _time
    inc = set(incompatible or set())
    pool = list(pool)
    tr = trace or SearchTrace()
    cp = checkpoint or Checkpoint(None)

    def out_of_budget() -> bool:
        if max_evaluations and tr.evaluated >= max_evaluations:
            return True
        return bool(deadline and _time.time() >= deadline)

    def scored(s: State) -> float:
        hit = cp.get(s.key)
        if hit is not None:
            tr.resumed_from += 1
            return hit
        v = float(score(s))
        cp.put(s.key, v, {"cardinality": len(s), "lane": lane})
        tr.evaluated += 1
        return v

    # The null is evaluated first, always, and before any restart can consume
    # the evaluation budget.
    best, best_v = State.of([]), scored(State.of([]))
    tr.steps.append({"restart": -1, "lane": lane, "state": best.key,
                     "score": best_v,
                     "why": "the null state, evaluated before anything else"})

    rots = list(rotations or [0] * len(seeds))
    for r, sd in enumerate(seeds):
        if out_of_budget():
            tr.stopped_early = True
            break
        tr.restarts += 1
        cur = (starts[r] if starts is not None and r < len(starts)
               else _start_state(pool, inc, sd, max_cardinality))
        rot = rots[r] if r < len(rots) else 0
        cur_v = scored(cur)
        tr.steps.append({"restart": r, "lane": lane, "seed": sd,
                         "state": cur.key, "score": cur_v,
                         "cardinality": len(cur), "why": "restart start"})
        while True:
            if out_of_budget():
                tr.stopped_early = True
                break
            cands = (ordered_neighbours(cur, pool, inc, max_cardinality,
                                        single_score, rot)
                     if strategy == "first"
                     else neighbours(cur, pool, inc, max_cardinality))
            if not cands:
                break
            moved = False
            if strategy == "first":
                for c in cands:
                    if out_of_budget():
                        tr.stopped_early = True
                        break
                    v = scored(c)
                    if v < cur_v - 1e-12:
                        cur, cur_v, moved = c, v, True
                        break
            else:
                vals = [(scored(c), c.key, c) for c in cands]
                vals.sort(key=lambda t: (t[0], t[1]))
                v, _, nxt = vals[0]
                if v < cur_v - 1e-12:
                    cur, cur_v, moved = nxt, v, True
            if not moved:
                tr.local_optima.append({"restart": r, "lane": lane,
                                        "state": cur.key, "score": cur_v})
                break
            tr.steps.append({"restart": r, "lane": lane, "seed": sd,
                             "state": cur.key, "score": cur_v,
                             "cardinality": len(cur)})
        if cur_v < best_v - 1e-12 or (abs(cur_v - best_v) <= 1e-12
                                      and cur.key < best.key):
            best, best_v = cur, cur_v

    tr.best_key, tr.best_score = best.key, best_v
    return best, best_v, tr


def _start_state(pool: Sequence[str], inc: set[tuple[str, str]], seed: int,
                 max_cardinality: int | None) -> State:
    """Where a restart begins, by an explicit rule rather than a global RNG.

    seed 0 starts from the null. Every other seed starts from a single mutation
    chosen by stepping through the sorted pool, so the starts are spread across
    it deterministically and a rerun reproduces the path, not just the answer.
    """
    if not pool or seed == 0:
        return State.of([])
    return State.of([sorted(pool)[(seed - 1) % len(pool)]])


# ---------------------------------------------------------------------------
# the benchmark
# ---------------------------------------------------------------------------

def benchmark(pool: Sequence[str], table: dict[str, float],
              incompatible: set[tuple[str, str]],
              seeds: Sequence[int],
              expected_key: str,
              max_cardinality: int | None = None,
              checkpoint_dir: Path | None = None) -> dict[str, Any]:
    """Run the search on a space whose answer is already known, exhaustively.

    `table` maps state key -> score for **every** feasible state, so the true
    optimum is not a matter of opinion. The search must return it under every
    declared seed independently, not merely in aggregate — a heuristic that
    finds the answer from one lucky start has not been shown to find it.

    Resume is checked as part of the benchmark rather than separately: the
    search is run again against a checkpoint written by the first run, and must
    produce the same answer while evaluating strictly fewer states.
    """
    def lookup(st: "State") -> float:
        try:
            return table[st.key]
        except KeyError:
            raise KeyError(
                f"state {st.key!r} is feasible but absent from the benchmark "
                f"table. The table must be EXHAUSTIVE over the feasible space "
                f"— that is the whole reason this space can serve as a "
                f"benchmark. A partial table would let the search 'pass' by "
                f"never being offered the states it would have got wrong."
            ) from None

    truth_key = min(table, key=lambda k: (table[k], k))
    per_seed: dict[str, Any] = {}
    for sd in seeds:
        best, val, tr = search(pool, lookup, incompatible,
                               seeds=[sd], max_cardinality=max_cardinality)
        per_seed[str(sd)] = {"found": best.key, "score": val,
                             "evaluated": tr.evaluated,
                             "recovered": best.key == expected_key}

    all_seeds = search(pool, lookup, incompatible, seeds=seeds,
                       max_cardinality=max_cardinality)
    combined, combined_v, combined_tr = all_seeds

    resume: dict[str, Any] = {"checked": False}
    if checkpoint_dir:
        p = Path(checkpoint_dir) / "benchmark_resume.jsonl"
        if p.exists():
            p.unlink()
        cp1 = Checkpoint(p)
        b1, v1, t1 = search(pool, lookup, incompatible,
                            seeds=seeds, max_cardinality=max_cardinality,
                            checkpoint=cp1)
        cp2 = Checkpoint(p)                       # re-read from disk
        b2, v2, t2 = search(pool, lookup, incompatible,
                            seeds=seeds, max_cardinality=max_cardinality,
                            checkpoint=cp2)
        resume = {"checked": True,
                  "first_pass_evaluated": t1.evaluated,
                  "second_pass_evaluated": t2.evaluated,
                  "second_pass_reused": t2.resumed_from,
                  "same_answer": b1.key == b2.key,
                  "same_score": abs(v1 - v2) < 1e-12,
                  "second_pass_did_no_work": t2.evaluated == 0}

    ok = (all(v["recovered"] for v in per_seed.values())
          and combined.key == expected_key
          and truth_key == expected_key
          and (not resume["checked"]
               or (resume["same_answer"] and resume["same_score"]
                   and resume["second_pass_did_no_work"])))

    return {
        "pass": ok,
        "space_size": len(table),
        "expected": expected_key,
        "exhaustive_optimum": truth_key,
        "exhaustive_optimum_score": table[truth_key],
        "combined": {"found": combined.key, "score": combined_v,
                     "evaluated": combined_tr.evaluated},
        "per_seed": per_seed,
        "resume": resume,
        "note": "The discovery-stage optimum recovered here later CERTIFIED AS "
                "NULL (D22). This benchmark validates that the heuristic finds "
                "what the exhaustive table says is best; it says nothing about "
                "whether that intervention is worth making.",
    }


# ---------------------------------------------------------------------------
# the Stage A search policy, preregistered
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Policy:
    """Exactly what Phase A2 will do, fixed before any A2 state is scored.

    Held as one object for a specific reason: the benchmark has to replay the
    **complete policy**, not an approximation of it. A benchmark that validates
    a simpler search than the one that runs is a benchmark of something else,
    and the failure it would hide — a policy that works on 12 mutations and not
    on 84 — is precisely the one worth catching.

    Three lanes, each taking a third of the evaluation quota:

    1. **null-start, singles-ordered.** Begin at the empty state and visit
       neighbours in measured-A1-singleton order.
    2. **seeded rotations.** The same ordering, rotated by a fixed per-seed
       offset, so restarts enter the same neighbourhood at different points
       without randomness.
    3. **seeded random k=2/k=3 starts.** Compatible multi-mutation states drawn
       from a seeded generator, then first-improvement. This lane is the only
       one that can begin inside a region the other two would have to climb to,
       and 2B's non-nested cardinality winners are the reason it exists.

    Unused quota from a lane that reaches a local optimum early passes to lane
    3, because a lane that terminates has finished and a lane with random
    starts always has somewhere else to go.
    """

    lane_seeds: tuple[tuple[int, ...], ...] = ((0,), (1, 2, 3), (11, 12, 13, 14))
    rotations: tuple[tuple[int, ...], ...] = ((0,), (7, 23, 47), (0, 0, 0, 0))
    random_start_sizes: tuple[int, ...] = (2, 3)
    max_cardinality: int = 4
    strategy: str = "first"

    def as_dict(self) -> dict[str, Any]:
        return {"lane_seeds": [list(x) for x in self.lane_seeds],
                "rotations": [list(x) for x in self.rotations],
                "random_start_sizes": list(self.random_start_sizes),
                "max_cardinality": self.max_cardinality,
                "strategy": self.strategy,
                "lanes": ["null-start, ordered by measured A1 singles",
                          "seeded rotations of that ordering",
                          "seeded random compatible k=2/k=3 starts"],
                "quota_split": "one third each; unused quota from a terminated "
                               "lane passes to the seeded-random lane",
                "ordering_bias": "neighbours are visited drops-first (worst "
                                 "member first), then adds and swaps in "
                                 "measured-A1-singleton order. Nothing is "
                                 "discarded and every neighbour stays "
                                 "reachable — visit order only.",
                "dedup": "one shared checkpoint across all lanes; a state "
                         "scored in any lane is never re-scored"}


def random_start(pool: Sequence[str], incompatible: set[tuple[str, str]],
                 size: int, seed: int, tries: int = 500) -> State:
    """A compatible state of `size` mutations, from a seeded generator.

    Deterministic given (pool, incompatible, size, seed): the generator is
    constructed here rather than drawn from global randomness, so the starting
    states are part of the preregistered policy and can be listed in the
    artifact before the run.
    """
    import random as _random
    rng = _random.Random(f"exp3-start|{size}|{seed}")
    ordered = sorted(pool)
    for _ in range(tries):
        pick = rng.sample(ordered, min(size, len(ordered)))
        if feasible(pick, incompatible):
            return State.of(pick)
    return State.of([])


def run_policy(pool: Sequence[str], score: Callable[[State], float],
               incompatible: set[tuple[str, str]],
               single_score: dict[str, float],
               budget: int,
               policy: Policy | None = None,
               checkpoint: Checkpoint | None = None,
               deadline: float | None = None) -> dict[str, Any]:
    """Run the three lanes under one shared budget and one shared checkpoint.

    Returns the trajectory, not just the answer. Phase A2 is discovery: what it
    can support is which states to look at in Stage B, and a reader can only
    judge that from the starting states, the seeds, the ordering bias and the
    path actually walked.
    """
    pol = policy or Policy()
    cp = checkpoint or Checkpoint(None)
    per_lane = max(1, budget // 3)
    lanes: list[dict[str, Any]] = []
    spent = 0
    carry = 0

    starts_by_lane: list[list[State]] = [
        [State.of([])],
        [State.of([]) for _ in pol.lane_seeds[1]],
        [random_start(pool, incompatible,
                      pol.random_start_sizes[i % len(pol.random_start_sizes)],
                      sd)
         for i, sd in enumerate(pol.lane_seeds[2])],
    ]

    for li in (0, 1, 2):
        quota = per_lane + (carry if li == 2 else 0)
        if li == 2:
            quota = max(quota, budget - spent)
        tr = SearchTrace()
        best, val, tr = search(
            pool, score, incompatible, seeds=pol.lane_seeds[li],
            max_cardinality=pol.max_cardinality,
            max_evaluations=quota, checkpoint=cp, trace=tr,
            strategy=pol.strategy, single_score=single_score,
            starts=starts_by_lane[li], rotations=pol.rotations[li],
            deadline=deadline, lane=f"lane{li + 1}")
        used = tr.evaluated
        spent += used
        if li < 2 and used < quota:
            carry += quota - used
        lanes.append({"lane": li + 1,
                      "seeds": list(pol.lane_seeds[li]),
                      "rotations": list(pol.rotations[li]),
                      "starts": [s.key for s in starts_by_lane[li]],
                      "quota": quota, "used": used,
                      "best": best.key, "best_score": val,
                      "trace": tr.as_dict()})
        if deadline and __import__("time").time() >= deadline:
            break

    best_key, best_score = NULL, float("inf")
    for k, v in cp.scores.items():
        if v < best_score - 1e-12 or (abs(v - best_score) <= 1e-12
                                      and k < best_key):
            best_key, best_score = k, v

    return {"policy": pol.as_dict(), "budget": budget, "spent": spent,
            "carried_to_lane3": carry, "lanes": lanes,
            "best": best_key, "best_score": best_score,
            "unique_states_scored": len(cp.scores),
            "caveat": "DISCOVERY ONLY. This is a bounded multi-start search "
                      "over a space far too large to enumerate. It does not "
                      "establish exhaustive coverage, a global optimum, or "
                      "that every state was reachable."}
