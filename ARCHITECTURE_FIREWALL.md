# The semantic comparison firewall

## Core rule

A treatment effect is a property of a **validated comparison**, not the
difference between two scores.

`compare(control, treatment, contract)` is the only operation in this codebase
permitted to produce a reportable effect. Scripts may subtract two numbers for
a diagnostic, clearly marked non-authoritative; nothing that reaches a
promotion, a certification, a canonical table, a figure or a finding may.

## Default

Any **undeclared difference between how control and treatment were actually
executed** makes the comparison inadmissible — not the configuration they
asked for, what the receipts say happened.

The permitted differences are a **whitelist**, never a blacklist. A blacklist
can only catch confounds someone already imagined, and D27 was not one of
those. With a whitelist, a dimension nobody has invented yet defaults to *may
not differ*, so the first comparison that exercises it is refused rather than
quietly reported.

## Recovery rule

A recovery that can change mathematical opportunity **is experimental state**
and must appear in the receipt. Retrying a file read is operationally neutral.
Falling back to a different optimizer is not, however well it works. An event
whose author has not decided defaults to semantic.

## Design purpose

The harness should not need to know the next bug. It should notice that the
next bug **made evidence in two different ways**.

---

## What went wrong, and why nothing caught it

`optimize_frequencies` accepted an `initial` plan only if that plan, once
snapped to the headway ladder, still fit the envelope. `fit_incumbent` fits in
continuous headway space; the snap moves about half the route-periods to a
shorter headway, which costs vehicle-hours, so the fitted incumbent landed back
outside the envelope. The optimizer then discarded it and ran `_greedy_build` —
the build the caller had disabled with `greedy_start=False`.

Whether that happened was decided by the treatment: route-lengthening edits
pushed the incumbent over the envelope, route-shortening edits and the unedited
control never did. Over 156 Stage A solves: `extend` 40/40, `reroute` 21/22,
`splice` 12/13, `add_stop` 52/63, every k=2 and k=3 state 46/46 — against
`truncate` 0/14, `straighten` 0/12, and the zero-edit control 0/3.

Every individual number looked reasonable. Every configuration field matched.
The only visible trace was a `log.warning`, printing in every log of four
experiments, that nothing was counting.

**Four separate things had to be absent for that to survive:**

| absent | now |
|---|---|
| the policy was a boolean whose meaning depended on the data | `StartPolicy` enum; a policy that cannot be honoured is a structured failure, never a substitution |
| the fallback existed only as prose in a log | `ExecutionEvent`, typed, with `changes_opportunity` declared |
| comparisons were two floats subtracted | `compare()` diffs the receipts and refuses on any undeclared difference |
| nobody asked whether execution correlated with treatment | `balance_audit` sweeps every event type and opportunity field, fails closed |

## The objects

```
ExperimentContract     what SHOULD happen, frozen before it does.
                       Owns `allowed_treatment_differences` -- the whitelist.
EvaluationSpec         what should happen to ONE cell. One canonical builder,
                       because two scripts that assemble identity differently
                       produce two identities that can hash the same.
ExecutionReceipt       what ACTUALLY happened. No field may require parsing a
                       log to populate.
ExecutionEvent         a thing that happened, with its effect on comparability
                       declared rather than inferred.
ComparableObservation  a receipt that has passed its own contract. An
                       inadmissible result is kept for debugging and barred
                       from effects.
ComparisonResult       the only source of a reportable effect.
```

Every field of the spec and receipt declares what it *means* — `Sem.IDENTITY`,
`Sem.OPPORTUNITY`, `Sem.OUTCOME`, `Sem.NONE` — on the type, not in the
comparator. The comparator walks the dataclasses generically, so a field added
anywhere is compared from the moment it exists and there is no list of
exceptions to fall out of date.

* **IDENTITY** — what the evaluation was: evaluator, objective, envelope,
  contract, state. Must match unless whitelisted.
* **OPPORTUNITY** — what the execution got: starts attempted, restarts
  completed, fallbacks, termination reason. Also must match, because equal
  nominal effort with unequal search is precisely the D27 failure.
* **OUTCOME** — what it found. Never an admissibility input; that is the
  measurement.
* **NONE** — wall-clock, pids, timestamps.

## Four signatures

`treatment` (fields the contract permits to differ) · `nuisance` (everything
that must not) · `evidence` (model, data, path-set, evaluator provenance) ·
`execution` (actual algorithmic opportunity). Serializable, hashed, stored with
every artifact.

## Discovery and certification are policies, not numbers

D28: at certification effort each restart terminated after roughly **4,000 of
its 400,000 permitted evaluations** — the ceiling was never binding. Calling
400000/20 "6.7x the search" of 60000/20 described nothing that happened. The
lever is **restart diversity**, so it is a field of `SolverPolicy` and
convergence is asserted (`require_convergence`) rather than inferred from an
iteration count. A certification contract whose solver does not require
convergence is refused at construction.

## Fail-closed points

1. **Contract construction** — a start policy whose realised start set can
   depend on the state is refused unless the asymmetry is explicitly declared.
2. **Observation admission** — a cell that did not receive the search the
   contract promised is inadmissible.
3. **Comparison** — any undeclared identity or opportunity difference, or an
   opportunity-changing event present in one arm only, refuses.
4. **Balance audit** — execution behaviour associated with treatment identity
   fails the stage before promotion, even when every pairwise comparison passed.

## Schema and migration

`SCHEMA_VERSION = "firewall/1"`, recorded on every receipt. Artifacts written
before the firewall carry no receipt: they are readable, and they are not
admissible. That is the intended migration path — historical results are
preserved for provenance and are not silently promoted to evidence. Re-scoring
under the firewall is what makes an old result citable again.

## The completion criterion

Not "Experiment 3 now uses both starts."

> A future developer should be able to introduce a completely different
> treatment-correlated fallback, model substitution, convergence asymmetry,
> cache mismatch, or execution-path change, and the harness should refuse the
> resulting comparison without needing a bespoke guard for that specific
> failure.

`tests/test_firewall.py::test_the_exp3_start_asymmetry_is_caught_generically`
reconstructs D27 and asserts only that no `ComparisonResult` can be produced.
Nothing in the firewall knows what a start set is.

---

## The required-test checklist

| # | requirement | test |
|---|---|---|
| 1 | control incumbent-only vs treatment greedy-only cannot produce an effect | `test_the_exp3_start_asymmetry_is_caught_generically` |
| 2 | a hidden fallback in only one arm cannot produce an effect | `test_a_fallback_in_only_one_arm_is_refused_even_with_matching_fields` |
| 3 | same requested policy, different actual opportunity | `test_execution_difference_alone_refuses_when_both_arms_are_admissible`, `test_same_nominal_effort_but_different_completed_search_refuses` |
| 4 | mismatched evaluator | `test_any_undeclared_mismatch_refuses[evaluator_used]` |
| 5 | mismatched budget | `test_any_undeclared_mismatch_refuses[envelope_used_vh]` |
| 6 | mismatched path-set policy | `test_mismatched_pathset_policy_refuses` |
| 7 | stale cache from an incompatible contract | `test_a_stale_cache_entry_from_another_contract_refuses`, `test_the_store_refuses_an_entry_from_an_incompatible_contract` |
| 8 | resume vs uninterrupted comparable when semantically identical | `test_resume_is_comparable_only_when_declared_equivalent`, `test_two_paths_declared_equivalent_must_agree` |
| 9 | identical states compare to null | `test_identical_states_compare_to_null`, `test_identical_state_through_admissible_routes_compares_to_null` |
| 10 | allowed treatment geometry differences remain comparable | `test_a_matched_comparison_is_admitted` |
| 11 | promotion refuses raw scores without valid comparison receipts | `test_promotion_refuses_states_without_comparison_receipts` |
| 12 | canonical result generation refuses inadmissible comparisons | `test_a_finding_cannot_rest_on_a_refused_comparison` |
| 13 | execution-event imbalance surfaced automatically | `test_balance_audit_surfaces_treatment_correlated_execution`, `test_health_report_fails_closed_on_imbalance` |
| 14 | the Experiment 3 asymmetry caught with no bespoke guard | `test_the_exp3_start_asymmetry_is_caught_generically` |
| 15 | existing valid matched comparisons remain possible | `test_a_matched_comparison_is_admitted`, `test_a_declared_no_op_mutation_compares_as_null` |

Plus metamorphic properties in `tests/test_firewall_metamorphic.py`: identity,
serialization round-trip, digest insertion-order insensitivity, comparison and
evaluation order invariance, cache on/off equivalence, shard-freedom of
identity, neutral-recovery signature preservation, and the split between the
treatment, nuisance, evidence and execution signatures.

## Findings know what they rest on

`finding(claim, comparisons)` refuses to build a claim from a refused
comparison — a claim whose evidence was inadmissible is not a weaker claim, it
is not a claim — and refuses to build one from no comparisons at all. A
`FindingLog` can name every live claim that depended on a given observation, so
superseding evidence supersedes the slides that used it instead of leaving them
looking current.

---

## Amendment — two things the first real batch caught (2026-08-31)

The Experiment 2B confirmation was the firewall's first use on a live batch. It
refused every comparison, for two reasons, and both were right.

**1. `code_version` identified the wrong thing.** It was the repo HEAD. HEAD
moves when a shell script or a markdown file changes, and the batch's control
cells and treatment cells were separated by exactly such a commit — so two
cells that could not possibly have differed were refused for differing. A
markdown edit is not a different evaluator.

`code_version` is now a content digest of `src/cota_opt/**/*.py` plus the two
scripts the scoring chain imports: the code that can actually change a number.
The commit is kept separately as `repo_revision`, provenance only, never an
identity field.

The operational rule that follows: **do not commit into the evaluation path
while a comparison batch is running.** With the narrower digest that is now a
real constraint rather than an accidental one.

**2. A declared difference now needs a written reason.** The other refusal was
`repair_occurred` / `repair_steps` / `INCUMBENT_REPAIRED`: under
`starts="both"` the treatment's incumbent still lands outside the envelope
after the ladder snap, so it needs repair and the control does not. That is
treatment-dependent by construction.

The temptation is to add it to the whitelist and move on — which is how a
whitelist becomes a place to put anything inconvenient. So
`allowed_treatment_differences` is now paired with `justifications`, and a
dimension declared without a written reason is **refused at contract
construction**. The reasons hash into the contract digest, so a waiver cannot
be added quietly.

The repair waiver's reason is evidence, not assertion: D30 measured the
repaired incumbent losing to greedy on 8 of 8 stratified states across four
cardinalities, with bit-identical objectives and identical plan hashes. It is
falsifiable and says so — if a repaired incumbent ever wins a cell, the
justification is void and the declaration comes out.

**And the waiver had to be narrowed.** Declaring `opportunity_events`
wholesale would have waived *every* event type at once, buying a blanket
exemption for model fallbacks and early termination on the strength of one
benign repair. The test suite caught it. Events are now compared **per type** —
`opportunity_events.INCUMBENT_REPAIRED` is declared;
`opportunity_events.MODEL_FALLBACK` and everything invented later still refuse.
