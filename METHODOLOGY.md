# Methodology generations

> Do not rerun a completed experiment merely because a better algorithm becomes
> available. First determine whether the new method solves the same
> mathematical problem, and whether it reveals material optimization error in
> the old method.

A generation is a frozen set of methodological definitions. An artifact carries
the generation that produced it, in its `EvaluationSpec`, its
`ExecutionReceipt`, its cache key, its `ComparisonResult` and any `Finding`
built from it — so a Gen2 number can never be mistaken for a correction of a
Gen1 number. They are two generations' answers, and both are kept.

## Generation 1

The methodology of Experiments 1, 2, 2B and 3. Frozen once those close.

| component | Gen1 definition |
|---|---|
| passenger path construction | RAPTOR round-based enumeration, cap 4 paths/OD, per-period |
| passenger assignment | path-level, re-priced under each headway vector |
| waiting treatment | Model B — combined frequency of every same-route pattern serving boarding stop then alighting stop, priced per **leg** |
| objective | `generalized_cost + λ · w_unserved · unserved_demand`, λ=2, `w_unserved` from `config/cost_weights.yaml` |
| envelope | weekday revenue vehicle-hours, pinned once from the unedited baseline |
| frequency decisions | one headway per route-period |
| headway ladder | discrete, per-route-period, honouring the minimum-service policy |
| frequency optimizer | greedy build and/or repaired-incumbent start, then exchange search with perturbation restarts |
| mutation representation | 8 geometry kinds over a deterministic predeclared pool |
| outer search | multi-start first-improvement, ordered by measured singles |
| certification | 400000/20/0, three seeds, matched convergence |
| comparison | the semantic comparison firewall (`ARCHITECTURE_FIREWALL.md`) |

`methodology_generation = "gen1"`.

## Classifying an algorithm change

Every proposed change is classified **before** implementation.

| class | meaning | requirement | historical rerun |
|---|---|---|---|
| **A** — computationally equivalent | caching, vectorization, incremental rebuild, parallelism, checkpointing. Intends to compute exactly the same quantity. | prove equivalence before replacing Gen1 behaviour | not required unless equivalence testing fails |
| **B** — better solver, same problem | stronger local search, MILP/CP-SAT for the frequency subproblem, more starts, LNS. Same objective, feasible set, model, budget and assignment problem. | benchmark against Gen1 and estimate the optimization gap | only if the measured gap threatens an existing conclusion |
| **C** — different question | ε-constraint instead of λ scalarization, robust or stochastic optimization, elastic demand, column generation that widens the route universe, new constraints or demand model. | version and report the new formulation separately | not required — the old results are not wrong, they answer a different question |

## When an old experiment is reopened

Only when at least one of these is **shown**:

1. the new algorithm finds a materially better control or treatment state that changes the treatment effect;
2. optimization error is treatment-correlated;
3. an existing result changes sign;
4. a ranking used substantively in a conclusion changes materially;
5. a certification threshold is crossed;
6. the old feasible set or objective turns out to have been implemented incorrectly;
7. the historical comparison is inadmissible under the semantic firewall.

Not reopened because code is faster, because a newer algorithm exists, because
the exact plan changed while the aggregate effect held, or because Gen2 found
an improvement below the applicable noise floor.

Note that **(7) has already fired** for Experiment 3's Phase A1/A2 discovery
census (D27) — that reopening rests on inadmissibility, not on any algorithm
being newer.

## Artifact policy

Gen1 findings are never overwritten with Gen2 values. Labels are explicit:
`exp1_gen1_certified`, `exp1_gen2_bridge`. Gen2 agreement marks Gen1
**confirmed by Gen2 bridge**; Gen2 disagreement retains both and marks Gen1
**superseded by Gen2 because …** with the specific reason.

## Success criterion

Not that the repository contains more sophisticated algorithms. That the
existing heuristic has a *quantified* optimality profile, that evaluation gets
cheaper without changing semantics, that a new search buys more solution
quality per expensive evaluation, that historical results are reopened only
when evidence requires it, and that the audit trail survives each adoption.

    better algorithm -> bridge evidence -> compatible or selectively reopen

not

    better algorithm -> rerun everything

## Order of work

Current remediation is finished **before** any algorithm change begins:
firewall, Experiment 2/2B repair, Experiment 3 rescore, rebuilt frontier,
Experiment 3 certification, then Gen1 freeze. Only then the exact frequency
benchmark, the optimization-gap measurement, the evidence-based reopening
decision, incremental evaluation with full-rebuild canaries, and Gen2.
