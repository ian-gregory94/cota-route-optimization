"""Generation 2 — the Experiment 4 outer search over whole networks.

Targets the boundary frozen in `EXPERIMENT4_SCORING_INTERFACE.md` and calls the
shared network-agnostic scoring path. It contains **no evaluator logic**: it
decides which networks to score and nothing about what a score means.

    Exp4Selection ──assemble──▶ (TransitNetwork, tstats) ──solve_on_network──▶ fit
                                                    ▲
                              gen2_search only chooses the left-hand side

Three route-period states, kept distinct
----------------------------------------
A pinned OFF and an optimizer-chosen OFF can produce the same operational
service level and mean completely different things, so the result records which
mechanism produced every route-period:

===============  ====================================================
`ABSENT`         the line is not in the selection. It has no
                 route-periods, no patterns, no stops of its own.
`PINNED_OFF`     the line is selected and this (line, period) is fixed
                 to OFF by the search state. **An input constraint.**
`CHOSEN_OFF`     the line is selected, the route-period was eligible,
                 and the frequency optimizer returned OFF as best.
                 **An optimization result.**
`ACTIVE`         selected, eligible, and given a finite headway.
===============  ====================================================

`provenance()` reconstructs all four from the selection plus the returned plan,
and `RouteFate` carries them into the result. Collapsing them would make it
impossible to say whether the search declined to run a service or discovered
that running it was not worth the vehicle-hours.
"""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Sequence

from .exp4_network import Exp4Selection
from .frequency import is_off


class Fate(str, Enum):
    ABSENT = "absent"
    PINNED_OFF = "pinned_off"
    CHOSEN_OFF = "chosen_off"
    ACTIVE = "active"


@dataclass(frozen=True)
class RouteFate:
    line_id: str
    period: str
    fate: Fate
    headway_min: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"line_id": self.line_id, "period": self.period,
                "fate": self.fate.value, "headway_min": self.headway_min}


def provenance(selection: Exp4Selection, plan: Mapping[str, float],
               all_lines: Iterable[str], periods: Sequence[str]
               ) -> list[RouteFate]:
    """Classify every (line, period) in the pool, not just the selected ones.

    An absent line is part of the answer: "this search chose not to run line X"
    is a finding, and a result that lists only what it selected cannot express
    it.
    """
    out: list[RouteFate] = []
    for line in sorted(all_lines):
        for period in periods:
            if line not in selection.lines:
                out.append(RouteFate(line, period, Fate.ABSENT))
                continue
            if selection.is_pinned_off(line, period):
                out.append(RouteFate(line, period, Fate.PINNED_OFF))
                continue
            h = plan.get(f"{line}|{period}")
            if h is None:
                # selected and not pinned, but the plan has no entry: the
                # route-period never reached the frequency model. That is a
                # gap, not an OFF, and it is reported as its own thing rather
                # than being folded into either.
                out.append(RouteFate(line, period, Fate.ABSENT))
                continue
            out.append(RouteFate(line, period,
                                 Fate.CHOSEN_OFF if is_off(h) else Fate.ACTIVE,
                                 None if is_off(h) else float(h)))
    return out


@dataclass
class Candidate:
    """One scored network, with enough provenance to rebuild it."""

    selection: Exp4Selection
    objective: float
    fitness: dict[str, float]
    feasible: bool
    fates: list[RouteFate]
    parent: str | None = None
    move: str = "seed"
    evaluations: int = 0
    seconds: float = 0.0

    @property
    def key(self) -> str:
        return self.selection.state_key

    def as_dict(self) -> dict[str, Any]:
        return {
            "state_key": self.selection.state_key,
            "state_digest": self.selection.state_digest,
            "lines": sorted(self.selection.lines),
            "pinned_off": sorted(map(list, self.selection.pinned_off)),
            "objective": self.objective,
            "fitness": self.fitness,
            "feasible": self.feasible,
            "parent": self.parent,
            "move": self.move,
            "evaluations": self.evaluations,
            "seconds": round(self.seconds, 4),
            "route_fates": [f.as_dict() for f in self.fates],
            "n_active": sum(1 for f in self.fates if f.fate is Fate.ACTIVE),
            "n_chosen_off": sum(1 for f in self.fates
                                if f.fate is Fate.CHOSEN_OFF),
            "n_pinned_off": sum(1 for f in self.fates
                                if f.fate is Fate.PINNED_OFF),
            "n_absent": sum(1 for f in self.fates if f.fate is Fate.ABSENT),
        }


@dataclass
class SearchResult:
    best: Candidate | None
    evaluated: list[Candidate] = field(default_factory=list)
    n_evaluations: int = 0
    seconds: float = 0.0
    mode: str = ""
    notes: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "n_evaluations": self.n_evaluations,
                "seconds": round(self.seconds, 3),
                "best": self.best.as_dict() if self.best else None,
                "evaluated": [c.as_dict() for c in self.evaluated],
                "notes": self.notes}


#: A scorer maps a selection to (objective, fitness_dict, feasible, plan).
Scorer = Callable[[Exp4Selection], tuple[float, dict, bool, dict]]


def _evaluate(sel: Exp4Selection, scorer: Scorer, pool_lines, periods,
              parent: str | None, move: str) -> Candidate:
    t = time.time()
    obj, fitness, feasible, plan = scorer(sel)
    return Candidate(selection=sel, objective=obj, fitness=fitness,
                     feasible=feasible,
                     fates=provenance(sel, plan, pool_lines, periods),
                     parent=parent, move=move, seconds=time.time() - t)


def enumerate_exact(pool_lines: Sequence[str], scorer: Scorer,
                    periods: Sequence[str], *, max_lines: int | None = None,
                    min_lines: int = 1,
                    pinned_off: Iterable[tuple[str, str]] = (),
                    pool_version: str = "bench",
                    max_networks: int = 4096) -> SearchResult:
    """The oracle. Every feasible selection, scored with the real evaluator.

    Not the production algorithm -- it exists so Gen2's answer can be checked
    against a known one. Refuses rather than truncates when the space is too
    large: a partial enumeration is not an oracle, and silently returning the
    best of a subset would look exactly like success.
    """
    t0 = time.time()
    lines = sorted(pool_lines)
    hi = len(lines) if max_lines is None else min(max_lines, len(lines))
    total = sum(1 for r in range(min_lines, hi + 1)
                for _ in itertools.combinations(lines, r))
    if total > max_networks:
        raise ValueError(
            f"{total} selections exceeds max_networks={max_networks}; a "
            f"truncated enumeration is not an oracle. Shrink the space or "
            f"raise the cap deliberately.")

    pin = frozenset(pinned_off)
    out: list[Candidate] = []
    for r in range(min_lines, hi + 1):
        for combo in itertools.combinations(lines, r):
            keep = frozenset((a, b) for a, b in pin if a in combo)
            sel = Exp4Selection(pool_version, frozenset(combo), keep)
            out.append(_evaluate(sel, scorer, lines, periods, None, "enumerate"))
    feas = [c for c in out if c.feasible]
    best = min(feas, key=lambda c: c.objective) if feas else None
    return SearchResult(best=best, evaluated=out, n_evaluations=len(out),
                        seconds=time.time() - t0, mode="exact_enumeration",
                        notes={"n_selections": total,
                               "n_feasible": len(feas),
                               "complete": True})


def search(pool_lines: Sequence[str], scorer: Scorer, periods: Sequence[str],
           *, seed_lines: Iterable[str] | None = None,
           max_lines: int | None = None, min_lines: int = 1,
           pinned_off: Iterable[tuple[str, str]] = (),
           pool_version: str = "bench",
           max_evaluations: int = 500,
           allow_swaps: bool = True) -> SearchResult:
    """Gen2's outer search: steepest-descent over add / drop / swap moves.

    Swaps are included because add-and-drop alone cannot cross a valley, and the
    Experiment 4 objective has them: two lines meeting at a junction can be
    worth more together than either is alone, so a search that only ever adds
    the single best next line walks past the pair. Gate 4-14 names exactly that
    structure.

    Every candidate records its parent and the move that produced it, so a
    disagreement with the oracle is diagnosable as a path rather than reported
    as a different number.
    """
    t0 = time.time()
    lines = sorted(pool_lines)
    hi = len(lines) if max_lines is None else min(max_lines, len(lines))
    pin = frozenset(pinned_off)
    seen: dict[str, Candidate] = {}
    evaluated: list[Candidate] = []

    def mk(combo) -> Exp4Selection | None:
        combo = tuple(sorted(combo))
        if not (min_lines <= len(combo) <= hi):
            return None
        keep = frozenset((a, b) for a, b in pin if a in combo)
        return Exp4Selection(pool_version, frozenset(combo), keep)

    def ev(sel, parent, move) -> Candidate:
        c = seen.get(sel.state_key)
        if c is not None:
            return c
        c = _evaluate(sel, scorer, lines, periods, parent, move)
        seen[sel.state_key] = c
        evaluated.append(c)
        return c

    start = tuple(sorted(seed_lines)) if seed_lines else (lines[0],)
    sel0 = mk(start)
    if sel0 is None:
        raise ValueError(f"seed {start} is outside [{min_lines}, {hi}] lines")
    cur = ev(sel0, None, "seed")
    best = cur if cur.feasible else None

    while len(evaluated) < max_evaluations:
        moves: list[tuple[tuple, str]] = []
        cl = tuple(sorted(cur.selection.lines))
        for x in lines:                                   # add
            if x not in cl:
                moves.append((cl + (x,), f"add:{x}"))
        for x in cl:                                      # drop
            moves.append((tuple(y for y in cl if y != x), f"drop:{x}"))
        if allow_swaps:                                   # swap
            for x in cl:
                for y in lines:
                    if y not in cl:
                        moves.append((tuple(z for z in cl if z != x) + (y,),
                                      f"swap:{x}->{y}"))
        cands: list[Candidate] = []
        for combo, mv in moves:
            s = mk(combo)
            if s is None:
                continue
            c = ev(s, cur.key, mv)
            if c.feasible:
                cands.append(c)
            if len(evaluated) >= max_evaluations:
                break
        if not cands:
            break
        cands.sort(key=lambda c: c.objective)
        if best is not None and cands[0].objective >= best.objective - 1e-12:
            break                                          # local optimum
        cur = cands[0]
        best = cur if (best is None or cur.objective < best.objective) else best

    return SearchResult(best=best, evaluated=evaluated,
                        n_evaluations=len(evaluated), seconds=time.time() - t0,
                        mode="steepest_descent_add_drop_swap",
                        notes={"max_evaluations": max_evaluations,
                               "hit_evaluation_cap":
                                   len(evaluated) >= max_evaluations,
                               "allow_swaps": allow_swaps,
                               "seed": list(start)})
