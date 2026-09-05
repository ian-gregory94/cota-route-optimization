"""Generation 2's inner solver — the EXACT frequency optimizer.

`METHODOLOGY.md`'s order of work puts "the exact frequency benchmark" and "the
optimization-gap measurement" immediately after the Gen1 freeze, and they are
what a generation bridge needs: a *different algorithm answering the same
question*, so that agreement means something. A "Gen2" that called
`optimize_frequencies` would agree with Gen1 trivially and prove nothing.

So this enumerates. Given the frequency model, its per-route-period ladders and
the resource envelope that Gen1's own setup produced, it evaluates **every**
combination of ladder rungs and returns the best feasible one. On a space it can
enumerate, the answer is the exact optimum of the frequency subproblem, not an
approximation of it -- which makes Gen1's heuristic answer measurable against a
known one rather than against another heuristic.

It **refuses rather than approximates**. A truncated enumeration is not an exact
solver, and returning the best of a sampled subset would look exactly like
success. `max_combinations` is the honest boundary, and exceeding it raises.

Class B under `METHODOLOGY.md`: same objective, same feasible set, same
envelope, same evaluator -- a better solver for the same problem. Nothing here
prices anything; it consumes the model Gen1's setup built and calls that model's
own `evaluate_array`.
"""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from .frequency import FrequencyPlan, is_off


class ExactSolveTooLarge(ValueError):
    """The ladder space is too large to enumerate. Not an approximation cue."""


@dataclass
class ExactResult:
    plan: FrequencyPlan
    objective: float
    n_combinations: int
    n_feasible: int
    seconds: float
    meta: dict[str, Any] = field(default_factory=dict)


def space_size(ladders: dict, keys: Sequence) -> int:
    n = 1
    for k in keys:
        n *= max(1, len(ladders.get(k, ())))
        if n > 10 ** 12:                       # stop early; it is already hopeless
            return n
    return n


def solve_exact(model, budget, ladders: dict, *, unserved_multiplier: float,
                max_combinations: int = 2_000_000,
                pinned_off: frozenset | None = None) -> ExactResult:
    """Every ladder combination, scored by the model Gen1's setup built.

    ``pinned_off`` fixes those route-periods to OFF and removes them from the
    enumeration, which is what makes a PINNED_OFF an input constraint rather
    than something the optimizer could undo: the rung is not offered.
    """
    t0 = time.time()
    keys = list(model.keys)
    pinned = frozenset(pinned_off or ())

    options: list[list[float]] = []
    for k in keys:
        if k in pinned:
            off = [v for v in ladders.get(k, ()) if is_off(v)]
            if not off:
                raise ValueError(
                    f"{k} is pinned OFF but its ladder offers no OFF rung; the "
                    f"ladder must be built with allow_off=True")
            options.append([off[0]])
            continue
        lad = list(ladders.get(k, ()))
        if not lad:
            raise ValueError(f"{k} has an empty ladder; nothing to choose from")
        options.append(lad)

    total = 1
    for o in options:
        total *= len(o)
        if total > max_combinations:
            raise ExactSolveTooLarge(
                f"the ladder space has more than {max_combinations:,} "
                f"combinations over {len(keys)} route-periods; enumerating a "
                f"sample would not be an exact solve, so this refuses. Reduce "
                f"the network, or raise max_combinations deliberately.")

    # Gen1's OWN feasibility predicate, imported rather than re-implemented: a
    # bridge whose arms disagree about what "feasible" means is not a bridge.
    from .frequency import _feasible

    best_vec = None
    best_obj = float("inf")
    n_feasible = 0
    for combo in itertools.product(*options):
        vec = np.asarray(combo, dtype=float)
        fit = model.evaluate_array(vec)
        if not _feasible(model, fit, budget):
            continue
        n_feasible += 1
        # The IDENTICAL scalarization Gen1 optimizes, read off the same model
        # rather than re-derived: optimize_frequencies uses
        # f.scalarized(w_uns, unserved_multiplier) with w_uns from the model's
        # own CostWeights. A bridge whose two arms optimize different objectives
        # measures nothing.
        obj = fit.scalarized(model.w.unserved, unserved_multiplier)
        if obj < best_obj:
            best_obj, best_vec = obj, vec

    if best_vec is None:
        raise ValueError(
            "no ladder combination fits the envelope; that is a broken budget, "
            "not a startable plan")

    return ExactResult(
        plan=FrequencyPlan({k: float(v) for k, v in zip(keys, best_vec)}),
        objective=float(best_obj), n_combinations=total, n_feasible=n_feasible,
        seconds=time.time() - t0,
        meta={"solver": "gen2_exact_enumeration", "n_route_periods": len(keys),
              "n_pinned_off": len(pinned),
              "refuses_rather_than_samples": True})
