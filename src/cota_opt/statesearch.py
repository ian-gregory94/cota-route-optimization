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

    def as_dict(self) -> dict[str, Any]:
        return {"evaluated": self.evaluated, "restarts": self.restarts,
                "best": self.best_key, "best_score": self.best_score,
                "resumed_from_cached": self.resumed_from,
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
        self.scores[key] = score
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rec = {"state": key, "score": score, **(extra or {})}
        with self.path.open("a") as f:
            f.write(json.dumps(rec) + "\n")


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


def search(pool: Sequence[str],
           score: Callable[[State], float],
           incompatible: set[tuple[str, str]] | None = None,
           seeds: Sequence[int] = (0,),
           max_cardinality: int | None = None,
           max_evaluations: int | None = None,
           checkpoint: Checkpoint | None = None,
           trace: SearchTrace | None = None) -> tuple[State, float, SearchTrace]:
    """Neighbourhood search with restarts. Lower score wins.

    Deterministic given (pool, seeds): the restart schedule is derived from the
    seed by an explicit rule rather than by a global RNG, so a rerun reproduces
    the path and not merely the answer. The benchmark demands that.
    """
    inc = set(incompatible or set())
    pool = list(pool)
    tr = trace or SearchTrace()
    cp = checkpoint or Checkpoint(None)

    def scored(s: State) -> float:
        hit = cp.get(s.key)
        if hit is not None:
            tr.resumed_from += 1
            return hit
        v = float(score(s))
        cp.put(s.key, v, {"cardinality": len(s)})
        tr.evaluated += 1
        return v

    # The null is evaluated first, always, and before any restart can consume
    # the evaluation budget.
    best, best_v = State.of([]), scored(State.of([]))
    tr.steps.append({"restart": -1, "state": best.key, "score": best_v,
                     "why": "the null state, evaluated before anything else"})

    for r, sd in enumerate(seeds):
        tr.restarts += 1
        cur = _start_state(pool, inc, sd, max_cardinality)
        cur_v = scored(cur)
        while True:
            if max_evaluations and tr.evaluated >= max_evaluations:
                break
            cands = neighbours(cur, pool, inc, max_cardinality)
            if not cands:
                break
            vals = [(scored(c), c.key, c) for c in cands]
            vals.sort(key=lambda t: (t[0], t[1]))   # ties break on key: stable
            v, _, nxt = vals[0]
            if v >= cur_v - 1e-12:
                break                       # local optimum
            cur, cur_v = nxt, v
            tr.steps.append({"restart": r, "seed": sd, "state": cur.key,
                             "score": cur_v, "cardinality": len(cur)})
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
