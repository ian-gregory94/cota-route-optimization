# The Experiment 4 scoring interface — frozen for Gen2 to target

Gen2 will replace how a network is *solved*. It must not redefine what a network
*is* or what a score *means*, or a Gen2 number stops being comparable to a Gen1
one and `METHODOLOGY.md`'s whole generation scheme collapses. This file fixes
the boundary.

## The pipeline

```
Exp4Selection  ──assemble──▶  (TransitNetwork, tstats)  ──solve_on_network──▶  fit
    ▲                              ▲                            ▲
 what runs                  the shared boundary          Gen1 evaluation core
```

The middle term is the contract. Experiments 1–3 reach it via
`geometry.apply_edits`; Experiment 4 reaches it via `exp4_assemble.assemble`.
Everything after it is one code path for both.

## What Gen2 may replace, and what it may not

| | |
|---|---|
| **May replace** | the frequency solver inside `solve_on_network` — `optimize_frequencies`, its start policy, its restart scheme. That is a class-B change under `METHODOLOGY.md`: better solver, same problem. |
| **May NOT replace without a class-C declaration** | the objective, the feasible set, the envelope, the demand model, the assignment problem, RAPTOR semantics, the waiting model, or vehicle-hour and peak-vehicle accounting. Changing any of those asks a different question and gets versioned separately. |
| **May NOT change at all silently** | the `(TransitNetwork, tstats)` boundary. A Gen2 that assembles differently is not solving the same problem better; it is solving a different problem. |

## The three modules

**`exp4_network.Exp4Selection`** — frozen, hashable, validated at construction.
`pool_version`, `lines`, `pinned_off`. Two distinct ways a route-period does not
run are kept distinct: *not selected* (absent from the network) and *pinned OFF*
(present, fixed to `frequency.OFF`). A pinned OFF is a constraint; an
optimizer-chosen OFF is a result.

**`exp4_assemble.assemble`** — deterministic. Sorted iteration, content-derived
pattern ids, per-segment times from the observed link graph, one trip per
pattern-period. Fails closed on: unknown line, pool-version mismatch,
unobserved link, stop outside the fixed universe, a direction with fewer than
two stops. Nothing is repaired.

**`exp4_score.score_exp4_network`** — returns `(ScoredExp4Network,
AssembledNetwork)`, so a caller can inspect what was scored without
re-assembling and hoping the two agree.

## Invariants, with the numbers behind them

* **Assembly reproduces the legacy path exactly.** 0.000e+00 relative
  difference on `generalized_cost`, `unserved_demand`, `served_demand`,
  `revenue_veh_hours`, `peak_vehicles`, `mean_wait_min`, `gc_per_served_trip`
  (`outputs/exp4/equivalence_isolated.json`).
* **Pattern order is not neutral (D34).** Renaming and re-sorting the same
  network moves the score by up to **8.568e-04** (peak vehicles). Experiment 4
  is internally deterministic because `assemble` always sorts, but a comparison
  against a legacy-ordered network cannot be finer than this. **Gen2 must not
  reorder patterns without treating it as a class-B change with a bridge
  measurement** — and the peak-vehicle case is a feasibility boundary, not just
  a reported quantity.
* **OFF costs nothing, exactly.** Infinite headway gives zero trips, zero
  vehicle-hours, zero peak vehicles, zero fleet, and an unboardable pattern, all
  arithmetically rather than by special case.
* **`allow_off` defaults False** through `build_ladders`, `build_setup` and
  `solve_on_network`. Gen1 cannot represent OFF and is bit-identical.
* **A route-period with no baseline cannot be laddered without an OFF rung** —
  `build_ladders` refuses, rather than inventing a finite worst headway and with
  it a service commitment nobody made (gate 4-5).

## What this interface does not yet provide

No outer search. `score_exp4_network` scores one named network; choosing which
network to score is Experiment 4's search problem and is deliberately absent.
Gate 4-14's benchmark needs it, and needs the production evaluator rather than a
surrogate — weighted set coverage is submodular, so greedy is provably
near-optimal on it and no surrogate fixture can defeat a search.
