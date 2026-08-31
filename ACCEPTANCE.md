# Acceptance gates

Committed **before** the results they judge. A gate is not a checklist item to
be argued with once a number is in hand: if a result fails a gate, the result is
provisional, and the gate does not move.

Recorded at commit time: the Experiment 1 fixpoint (`scripts/fixpoint.py`) and
the Experiment 2 geometry screen (`scripts/run_exp2_screen.py`) were both still
running. No final numbers from either had been seen.

---

## Experiment 1 — final only if all of these hold

| # | Gate | How it is checked |
|---|------|-------------------|
| 1 | The fixpoint converges | `outputs/fixpoint_history.csv`: worst improvable flow share moves less than `--tol` (0.002) between consecutive iterations, or the iteration cap is reached **and** the last two iterations are within tolerance |
| 2 | The converged path set is frozen | its cache key is recorded in the experiment record and used unchanged for every subsequent comparison. **Amended 2026-08-26 23:25 UTC:** the enumeration cache key is now a content hash of the scenario plans. It was previously a join of scenario *names*, which are stable across runs while the plans they carry are not — so a re-solved iteration silently reused the previous run's path sets. A recorded key only means something if it is derived from the thing it names. |
| 3 | The frontier is rerun at L4 on that same set | `final\|lam*` cells in `outputs/fixpoint.jsonl`, 400,000 iterations / 20 restarts / full width |
| 4 | The L4 plans pass adequacy against the frozen set ⚠️ **PARTIAL — Model A, 2026-08-27 09:37 UTC** | `final\|adequacy`: worst flow-share improvable under any final plan is below the tolerance the loop converged at (1.029%). **Result:** λ = 1, 2, 4, 8 pass at 0.66–0.69%; λ = 16 passes at 0.988%; **λ = 0.5 fails at 1.618% and λ = 0.25 fails at 9.721%.** The probe loop ran λ ∈ {0.5, 1, 2, 8} and the final frontier runs λ ∈ {0.25, …, 16}, so the extreme cost-favouring corner was solved at an effort and a λ the enumeration never saw. λ = 0.25 also carries 1.13% mean overstatement against 0.09% elsewhere. **No headline may rest on λ ≤ 0.5 until this is certified**; the balanced region is unaffected. **Model B, 2026-08-27 13:34 UTC** (line 0.671%): λ = 0.5, 1, 2, 8, 16 pass at 0.53–0.63%; **λ = 4 fails marginally at 0.726% and λ = 0.25 fails at 3.177%.** Same structural cause, milder — Model B's candidate set is 5.8% larger because of the gate-11 route-level scenario. `scripts/frontier_certify.py` repairs both: the full-effort plans go back in as enumeration scenarios and every λ is re-solved on the widened set. **Model A repair result, 2026-08-27 17:20 UTC** (233,589 paths): λ = 2, 4, 8, 16 **certified** at 0.73–0.81%; λ = 0.25 improved 9.721% → 3.893% but still fails, λ = 0.5 held at 1.792%, and λ = 1.0 **regressed** 0.691% → 1.115% from pass to fail. See D15: aggregate convergence is not pointwise convergence, and re-enumerating around an extreme plan just moves the target. **Resolution, per this file's own pre-committed language: the frontier is quoted from λ = 2 upward and the corner is reported as uncertified — the line does not move.** The balanced point is inside the certified range and barely moved between sets (+0.531%/−6.973% frozen, +0.535%/−7.035% widened). **Model B repair result, 2026-08-27 19:05 UTC** (243,257 paths, line 0.671%): the same split, in the same place — λ = 2, 4, 8, 16 **certified** at 0.51–0.56%; λ = 0.25 (1.371%), 0.5 (0.926%) and 1.0 (0.789%) still fail. Two independent models, two candidate sets differing by 4%, and the boundary lands between λ = 1 and λ = 2 in both. That makes D15 structural rather than a property of either run. **Both frontiers are quoted from λ = 2 upward.** |
| 5 | Previously saved plans are repriced on the same yardstick | `outputs/fixpoint_rescored.csv` covers every plan in `outputs/matrix_plans/`. **Why this gate is not bookkeeping:** `generalized_cost` is a *total* over served trips plus the unserved penalty, not a per-trip mean, so a larger candidate set that retains more demand can raise it. Baseline gc drifts across fixpoint iterations for exactly this reason (1.787982e6 to 1.788020e6, +0.0021%, as the set grew from 203k to 226k paths), and that drift is correct behaviour rather than a defect. Two numbers scored on different candidate sets are not comparable in either direction; every cross-set comparison uses one evaluator, or `mean_cost_per_served_trip`. |
| 6 | Decision-relevant λ points stay coherent | λ = 1, 2, 4, 8 remain monotone in the intended direction: unserved demand non-increasing in λ, generalized cost non-decreasing in λ, within seed noise |
| 7 | Important λ results are seed-stable | at least three seeds at λ = 2; the reported effect must exceed its own standard deviation by a clear margin. **Second job added 2026-08-27:** the same replicates decide whether the plan *composition* is identified at all. D14 found two plans differing on ~25% of route-periods (mean 8 min of headway) whose objectives differ by 0.01%. If independent seeds also disagree that widely, the optimum is flat and no per-route headway may be stated as a recommendation; the aggregate result is unaffected either way. Report the route-period disagreement across seeds alongside the objective's standard deviation. **Model A result, 2026-08-27 19:48 UTC** (3 seeds, λ=2, one shared 233,589-path set): unserved −7.000% ± 0.127 = **55.2σ**, cost +0.538% ± 0.067 = 8.0σ, cost per served trip −3.131% ± 0.018 = 177σ. **Effect: PASSES.** Plan: the worst seed pair differs on **26.0% of route-periods** (mean 22.5%, average move 7.63 min, max 30 min) against a 10% line. **Plan: FAILS.** See D17 — the optimum is flat, so the aggregate result stands and no individual route headway may be quoted as a recommendation. Experiment 2 comparisons must use frontier positions, not plan diffs. **Model B result, 2026-08-27 21:40 UTC** (3 seeds, λ=2, one shared 243,257-path set): unserved −6.652% ± 0.064 = **104.4σ**, cost +0.878% ± 0.041 = 21.5σ, cost per served trip −2.344% ± 0.011 = 215σ. **Effect: PASSES.** Plan: worst seed pair differs on **19.7% of route-periods** (mean 19.1%, average move 6.92 min). **Plan: FAILS.** Same verdict as Model A, on a different set with different seeds — better conditioned (half the objective spread, a quarter less plan disagreement) and nowhere near enough to cross the line. |
| 8 | Vehicle-hour and baseline assertions still pass | `vh_relative_error < 1e-9` in `build_setup`; every plan within the 2,517-hour envelope |
| 9 | Residual path-set inadequacy cannot change the interpretation | the remaining overstatement, applied in full and in the direction that most favours the headline, does not move the balanced point across a qualitative boundary |
| 11 | **Model B discovery adequacy** ✅ **PASSED 2026-08-27 00:43 UTC** (Case C on first pass, closed by augmentation and confirmed non-material) | per-pattern RAPTOR must be shown not to omit a material number of route sequences that become competitive *only* under Model B combined-frequency repricing. Distinct from gate 1: that asks whether the candidate set contains the paths new *headway scenarios* make attractive; this asks whether it contains the paths the corrected *valuation* makes attractive. Thresholds fixed below, before the diagnostic was written. **First pass:** 4.877% of tested flow (material) on 0.185% of tested cost (negligible) — Case C on the flow bound alone. Response as pre-committed: route-level search scenario added to Model B enumeration. **Rerun:** Case A, zero omissions — a consistency check, as flagged in advance, not independent evidence. **Follow-up (the evidence that counts):** solved on both sets at matched effort and scored both plans on the augmented evaluator; gaps ≤0.057% gc and ≤0.03% unserved against 0.25%/1.0% lines, at every λ. Not material. `outputs/discovery_adequacy_modelB.json`, `outputs/gate11_sensitivity.json`. |
| 10 | **Same-route common-lines residual is small enough not to matter** ✅ **PASSED 2026-08-26 22:29 UTC** | after the Model B correction, re-run the common-lines diagnostic: the same-route component must collapse to a level shown not to materially alter the final frontier. Added 2026-08-26, when the defect was identified; the thresholds above are unchanged. **Result:** same-route component 4.301% → 0.000% (−5.3e-14 min, floating-point zero); legs whose alternatives are all same-route 19,049 → 0; total bound 5.095% → 0.516%, now entirely cross-route and below the 0.79% already accepted as non-blocking. Block-derived fleet figures bit-identical across the two runs, confirming nothing else moved. `outputs/model_diagnostics_modelB.json`. |

**Language gate.** If generalized cost at the balanced point lands near zero,
that is **not** a free lunch and must not be described as one. The permitted
form is:

> approximately 6% less unserved demand with no measurable generalized-cost
> penalty under the converged path set.

"No measurable penalty" is a statement about resolution, not about absence of
cost, and it is only permitted when the seed standard deviation actually
straddles zero.

---

## Experiment 2 — substantive only if all of these hold

| # | Gate |
|---|------|
| 1 | Geometry is followed by frequency **re-optimization**, never scored at fixed frequency |
| 2 | Total weekday revenue vehicle-hours stay at 2,517 (`vh_vs_budget_pct` within the configured tolerance) |
| 3 | Evaluated on the **finalized** path set from Experiment 1, not an interim one |
| 4 | Compared against the finalized Experiment 1 **frontier**, not against today's schedule alone |
| 5 | Serious candidates run at matched search effort against the Experiment 1 points they are compared with |
| 6 | Stochastic results checked across seeds wherever the claimed effect is within a few times the seed spread |
| 7 | Runtime assumptions observed or independently validated — see the primary/novel split below |
| 8 | No gain from accidental service deletion or bookkeeping artifact: stops dropped, vehicle-hours freed, and headway rescaling all inspected per candidate |
| 9 | The geometry change is legible as a real transit proposal, inspected by hand against the network. ✅ **PASSED for the promoted candidate, 2026-08-27 23:20 UTC.** `splice|033|034|WESHIGW`: routes **33 HENDERSON** (78 daily trips) and **34 MORSE** (154) both *terminate* at WESTVIEW TURNAROUND, so the edit through-routes two lines that already meet — a crosstown Henderson–Morse via Westview, 97 stops and 93.5 min end to end. `modelled_share_pct = 0.0` (every link one COTA already operates), `stops_added = 0`, 2 patterns changed, vehicle-hours 2517.18 → 2517.74 (+0.02%). The trip-count asymmetry is handled the way an agency would: only ~25 trips per direction run through, and the short-turns are preserved (77 trips MEIJER↔WESTVIEW, 20 WESTVIEW→METRO PL, 19 WESTVIEW→SUMMER DR). Contrast the rejected `extend|102`, which grafted a downtown–Dublin peak express onto a local route and was caught by this same gate rather than by any metric. |

### Primary vs novel-link candidates

* **Primary** — the edited alignment is composed of links COTA's schedule
  already operates. `modelled_share_pct` is a decision variable, not a
  footnote: the headline Experiment 2 frontier is built from primary
  candidates only.
* **Novel-link** — a meaningful share of the alignment needs estimated running
  time. These stay exploratory unless the novel-link estimator is separately
  validated as unbiased on held-out observed links, and they are reported
  separately either way.

The threshold: **`modelled_share_pct` ≤ 2.0 %** to be primary. Chosen before
results, from the measured distribution over the first 60 candidates (median
≈ 2.8 %, max ≈ 10.8 %), so it is neither vacuous nor tuned to admit a
particular proposal.

### Credit rule

Experiment 2 gets no credit for anything Experiment 1 already offers. The
quantity reported is the improvement **beyond** the best frequency-only
solution at comparable generalized cost — vertical distance from the
finalized Experiment 1 frontier, not distance from today.

---

## Estimator gates

* The novel-link running-time estimator is validated **out of sample**: hide an
  observed link's time, predict it with the same estimator used for novel
  links, compare. MAE, median absolute percentage error, and **bias** are
  reported.
* Directional bias is the dangerous failure. Random error widens uncertainty;
  systematic **under**estimation is exploitable — the optimizer would buy
  frequency with running time that does not exist. A recalibration is permitted
  only if it reduces bias out of sample and introduces no leakage, and it is
  never adopted because it makes a particular proposal look better.

---

## Model B discovery-adequacy decision rule

Committed 2026-08-26, **before the diagnostic was implemented and before any of
its output was seen**.

RAPTOR searches with per-pattern headways, which is Model A's valuation. Model B
prices a movement on the combined frequency of the route's qualifying patterns,
so a route sequence can be cheap under Model B that RAPTOR, searching under
Model A, never had reason to explore. Correct valuation is not sufficient if
the corrected model cannot discover its own preferred alternatives.

**Method.** For every tested OD-period, run RAPTOR again with *route-level*
headways — every pattern priced at its route's full frequency. Because a Model B
multiplier can never be better than the whole direction's combined frequency,
that run is a strict **lower bound** on any Model B path cost. Where the bound
is not below the candidate set's best Model B cost, no omission is possible and
the pair is cleared outright. Where it is below, reconstruct the bound-optimal
journey, price it *exactly* under Model B, and compare. That turns "might be
omitted" into "is omitted, and by this much", with the route sequence named.

**A path counts as materially better** when it beats the candidate set's best
Model B cost by **at least 1.0 generalized minute AND at least 1%** of that
cost. Below that is float noise and detours nobody would notice.

**Materiality is flow-weighted**, not counted:

| Case | Flow share with a materially better omitted path | Flow-weighted gc improvement over tested flow | Action |
|---|---|---|---|
| **A — negligible** | < 1.0% | < 0.25% | document, keep per-pattern enumeration, proceed |
| **B — local** | 1.0–3.0% | 0.25–1.0% | document the residual, optionally augment those corridors, name it as a limitation |
| **C — material** | ≥ 3.0% | ≥ 1.0% | **do not freeze the yardstick.** Augment candidate generation, rerun the diagnostic, proceed only once the residual is non-material |

Either bound triggers the worse case. The 1.0% generalized-cost line is chosen
against the effect being claimed: Experiment 1's is roughly 2% of generalized
cost, and the cross-route common-lines bound already accepted as non-blocking is
0.79%. A discovery gap at or above 1% is therefore comparable to the result
itself; a quarter of that is not.

If Case C occurs, the response is targeted candidate-generation augmentation
around the affected corridors — **not** replacing RAPTOR with a full
common-lines assignment engine, and not compensating anywhere else in the model.

## Gate 11 follow-up: does the augmentation change the answer?

Committed 2026-08-26 23:05 UTC, **before the comparison was run**.

A clean rerun of the discovery diagnostic after augmenting candidate generation
is close to circular: the diagnostic finds suspects with route-level RAPTOR and
the augmentation adds route-level RAPTOR's optima to the set. It proves the
wiring works — which is not nothing, given that the first attempt silently
contributed no paths at all — but it is not evidence of discovery adequacy.

The non-circular question is whether the wider candidate set changes the plan
the optimizer recommends. Method:

1. Solve Model B at matched effort on the **un-augmented** set → `plan_plain`.
2. Solve Model B at matched effort on the **augmented** set → `plan_wide`.
3. Score **both plans on the augmented evaluator**. The augmented set is a
   superset, so it is the legitimate common yardstick and neither plan is
   graded on its own homework.

**Thresholds**, mirroring the negligible line already in force: the
augmentation **changed the answer** if, at any decision-relevant λ (1, 2, 4),
`plan_plain` scored on the common yardstick is worse than `plan_wide` by
**≥0.25% of generalized cost or ≥1.0% of unserved demand**. Below both, the
omission was real, widespread, and irrelevant to the recommendation — which is
what gate 11's 0.185% cost share predicts.

If it did change the answer, the augmented set is the basis for every Model B
result and the un-augmented frontier is discarded, not averaged with it.

Either way the plan diff is reported: how many route-periods differ and by how
much, so "no material change" is visible as a fact about the plans rather than
only as two close numbers.

**Known residual, recorded now rather than after it bites.** The route-level
search scenario runs at *baseline* headways only, and gate 11 tested at baseline
headways only. Under an optimized plan the route headways move, so the set of
sequences that only win once patterns combine moves with them — a discovery gap
could reopen at a plan the diagnostic never saw. This is the same shape as the
gap the fixpoint exists to close, and the fixpoint's own adequacy check runs
under the optimized plans, so the mechanism to catch it is already in place.
The Model B fixpoint's adequacy trace is where it would show up; if improvable
flow stays elevated there while the discovery diagnostic reports clean, this is
the first place to look. Adding route-level variants of every optimized
scenario would roughly double enumeration cost and is not justified before the
data asks for it.


## Gate 7 thresholds, committed before the replicates ran

Committed 2026-08-27 15:10 UTC. Gate 7 asked for "a clear margin" and three
seeds; both are made numeric here, before any replicate existed.

**The effect.** The reported coverage change must exceed its own across-seed
standard deviation by at least **3 sigma**. Below that it is not a measured
effect and may not be quoted as one — no softening to "suggests" or "trends
toward".

**The plan.** D14's second job. If the worst pair of independent seeds
disagrees on **10% or more** of route-periods, the optimum is flat and **no
individual route headway may be quoted as a recommendation**. The aggregate
result is unaffected either way; what changes is the unit of claim. D14 saw
~25% disagreement across two candidate sets, so this is a live possibility
rather than a formality.

The replicates share **one** candidate set. Varying the seed and the set at
once would confound the two, which is precisely the confound D14 could not
resolve.

## Experiment 2 screen: bracketing rule, committed before the second screen ran

Committed 2026-08-27 14:10 UTC.

The 60-candidate screen was run under Model A. Rescoring it under Model B is
**not possible**, and that is a fact about the screen rather than an oversight:
Model B's multiplier depends on the boarding stop, the alighting stop and their
order, so it is a property of a *leg*. The screen has no path set — it prices
straight out of RAPTOR's labels, where waiting is a per-pattern quantity fixed
before the alighting stop is known.

So the screen is **bracketed** instead. It is re-run with every pattern priced
at its route's whole frequency, which is a strict *lower* bound on any Model B
path cost (Model B's qualifying set is always a subset of the direction). Model A
is the upper end. Any real Model B ranking lies between them.

The question the bracket answers is not "what are the Model B screen numbers"
but "does the candidate *ranking* depend on the waiting model". Thresholds,
fixed before the second screen was read:

| Spearman ρ | top-10 overlap | Verdict |
|---|---|---|
| ≥ 0.80 | ≥ 7 / 10 | The ranking is not waiting-model-sensitive. The Model A shortlist stands as triage; proceed to evaluate it. |
| 0.50 – 0.80 | 4 – 6 / 10 | Model-sensitive. Re-derive the shortlist from the intersection of both rankings and say so in the write-up. |
| < 0.50 | ≤ 3 / 10 | The screen is not measuring a model-independent property. All screening evidence becomes bracket-only, and no candidate is promoted on screen evidence alone. |

Whichever bound is worse decides the verdict, matching every other two-bound
rule in this file.

**Independent of the outcome:** a screen number is never a result. The screen
holds frequency fixed, so it ranks candidates and cannot size them. Only the
evaluation tier — geometry with frequency re-optimized on the frozen yardstick —
produces an Experiment 2 number.


## Methodology decision — Model B is the sole authoritative evaluator

Recorded 2026-08-28. Governing rule: **Model A may tell us where to look; Model
B decides whether what we found is real.**

Model A misprices waiting because it treats a route's patterns independently: a
rider who could board any of several patterns serving the same movement is
charged one pattern's headway. Model B prices waiting at the **leg** level, on
the combined frequency of the patterns that qualify — those serving the boarding
stop, the alighting stop, and in that order.

**Model A is demoted to screening and diagnostic status.** It remains admissible
for RAPTOR and path-set integrity checks, candidate triage, historical
comparison against the preserved control, and debugging. **No Experiment 2
conclusion rests on a Model A score.** Every candidate, plan, treatment and
frontier used inferentially is evaluated under the frozen Model B evaluator.

**Candidate generation is non-authoritative triage, structurally.** The screen
cannot represent leg-level pricing: it prices out of RAPTOR's labels, where
waiting is fixed per pattern at boarding, before the alighting stop is known.
Forcing a Model B flag through it would produce Model A numbers under a Model B
label. D16 therefore *brackets* the unavailable screen between Model A at one
end and route-level combined-frequency pricing — a strict lower bound on any
Model B path cost — at the other, and candidates promoted by **either** endpoint
are conservatively retained. See D16 and its amendment for the evidence; it is
cross-referenced here rather than repeated.

**Frozen artifacts, written before Experiment 2 optimization began:**

| artifact | what it fixes |
|---|---|
| `outputs/exp1_baseline_modelB.json` | the certified Model B Experiment 1 frontier, per-λ, with adequacy, vehicle-hours, served/unserved and a `certified` flag. Not replaced during Experiment 2. |
| `outputs/exp2_candidate_set.json` | the shared candidate universe both treatments optimize over, with provenance for every member |

The frozen baseline carries its own quoting rule (λ ≥ 2 only, per gate 4 and
D15) and its own identification rule (aggregate only, per gate 7 and D17). Both
travel with the file so a reader cannot pick up the frontier without them.


## Model versions

Two complete model versions, both preserved. Later results never overwrite
earlier ones.

**Model A — pattern-specific waiting.** A ride leg is priced at the chosen
pattern's headway. The Experiment 1 fixpoint and the 60-candidate geometry
screen were run under it and are kept as the control: the original converged
result, the path-set adequacy analysis, and a reproducible record of the
common-lines bias.

**Model B — same-route common-lines corrected.** A ride leg is priced on the
combined frequency of every same-route pattern that serves the boarding stop,
the alighting stop, and in that order. Model A is the special case where one
pattern qualifies, so B is a strict generalisation.

**Model B completed 2026-08-27; the Experiment 1 headline is final.** The
condition this section was waiting on has been met, so the interim wording is
retired. It is kept here because retiring it is a status change and not a
revision of a gate:

> *Retired 2026-08-29, condition satisfied.* "The Experiment 1 headline is not
> final until Model B completes. Until then the result is described as: the
> pre-correction model finds roughly 6-7% lower unserved demand from frequency
> redistribution, but a newly identified same-route waiting-cost bias
> systematically undervalues high-frequency trunk service; the corrected
> frontier is being rerun."

The final Model B headline, three seeds at λ=2 sharing one 243,257-path
candidate set, at full effort (400,000 iterations / 20 restarts):

| quantity | mean | sd |
|---|---|---|
| unserved demand | **−6.65%** | 0.06 |
| trips served | **+3.30%** | 0.03 |
| generalized cost | +0.88% | 0.04 |
| cost per trip actually served | **−2.34%** | 0.01 |

at 2,516.5 of 2,517.2 revenue vehicle-hours and **197.0 against 197.0 peak
vehicles** — no additional buses (D18). Certified for λ≥2 (gate 4); λ≤1 remains
uncertified and is quoted only as an uncertified corner. The aggregate is what
is claimed; no individual route headway is identified (gate 7, D17), and that
restriction travels with every quotation of these numbers.

Cross-route common lines (0.79% of generalized cost) stays a documented
limitation and follow-on task, and is promoted to a required correction only if
a later diagnostic shows it could reorder the frontier.

## Experiment 2B gates, committed 2026-08-29 before the joint search ran

Experiment 2B asks a question the single-candidate evidence cannot answer:
**what is the best SET of geometry edits**, given D20's finding that a set's
effect is not the sum of its members'. These gates are fixed now, before any
subset has been solved.

**Gate 2B-1 — the search space is enumerated, not sampled.** The frozen
candidate set admits 240 structurally feasible subsets (including the empty
set), maximum cardinality 6, after removing pairs of splices that share a route
— which `geometry.apply_edits` rejects outright, since a splice removes both of
its routes from the live set. 240 is small enough to enumerate completely, so
Stage A evaluates **every** feasible subset. No subset is skipped for looking
unpromising, and in particular no subset is skipped because a member scores
badly alone. A run that evaluates fewer than 240 subsets fails this gate and is
reported as partial, naming which were not run.

**Gate 2B-2 — no set is ranked by anything but its own measured score.** Every
subset is solved with frequency re-optimized inside the same pinned envelope and
scored by the frozen Model B evaluator, exactly as the singles were. Screen
scores, single-candidate scores and sums of single-candidate scores may appear
in the analysis as comparisons; none may order the search or select a winner.
This is D19 and D20 stated as a procedure.

**Gate 2B-3 — cardinality winners are reported non-nested.** The best set of
size k is reported for each k, and it is *not* required to contain the best set
of size k−1. If it does, that is a finding about this network and is stated as
one; if the search is arranged so that it must, the gate fails.

**Gate 2B-4 — a headline set must clear the floor measured at its own effort.**
An improvement is reportable only if it exceeds 3σ of the zero-edit replicate
spread at the effort it was measured at. Stage A's floor is the one already
measured at 60,000/2/32 (0.288 points of unserved at λ=2). A headline claim must
additionally clear the floor at the effort it is certified at, which is measured
in the same run rather than carried over.

**Gate 2B-5 — only the headline is certified.** Stage C runs full effort and
three seeds on the single best set and on the incumbent it must beat
(`splice|033|034|WESHIGW`, the best single), and on nothing else. Every other
number in Experiment 2B is explicitly a Stage A or Stage B number and is
labelled with its effort. Certifying the whole frontier is not affordable and
pretending otherwise is the failure mode this gate exists to prevent.

**Gate 2B-6 — interaction is measured, not inferred.** For every set reported,
the difference between its measured effect and the sum of its members' measured
single effects is computed and published as the interaction term. A set is
called synergistic, substituting or cannibalizing on the sign and size of that
term against the noise floor, and on nothing else.

**Gate 2B-7 — the incumbent may win.** The experiment's null result — that no
multi-edit set beats the best single — is a permitted and publishable outcome,
and D20 makes it the prior. A 2B write-up that cannot state what it would have
taken for the incumbent to win has failed this gate.

**Gate 2B-8 — the sweep must reproduce the ladder it replaces.** Three of the
240 subsets are the rungs of D20's measured-order ladder, and they were already
solved, independently, by `run_exp2_eval.py` at the same effort under the same
evaluator:

**Restated 2026-08-30.** The values first committed here were computed from the
mislabelled Model A run (see the defect note above). They are kept below the
line because a gate whose expectations quietly change is not a gate; the Model B
values are what Stage A must now reproduce, and they were fixed before Stage A
reached any of these three subsets.

| set | members | measured unserved vs no edit | sum of member singles | interaction |
|---|---|---|---|---|
| k=1 | 011+034 WESHIGW | −0.585% | −0.585% | 0.000 pts |
| k=2 | + 005+006 NMURBEAN | −0.066% | −0.857% | **+0.791 pts** (6.1× floor) |
| k=4 | + 007+101 EMO4THW, 008+035 BOASHAN | +1.639% | −0.448% | **+2.086 pts** (16.0× floor) |

Floor: **0.130** points, measured under Model B at this effort.

> *Superseded — the Model A values this gate was first written with, kept for
> the record:* k=1 `033+034` −0.9363% (interaction 0.000); k=2 `+005+006`
> −0.4853% against a −1.6200% sum (**+1.135 pts**, 3.9× the then-floor of
> 0.288); k=4 `+001+021, +008+035` +0.4733% against −2.6225% (**+3.096 pts**,
> 10.8×). The measured-order ladder's membership changed under Model B because
> the single-candidate ordering did, so these are not the same three subsets.

Stage A re-derives all three through a different script and a different code
path. **They must agree to within the 0.288-point noise floor.** If they do not,
the 2B pipeline is measuring something other than what the ladder measured, and
the whole sweep is void regardless of how sensible its rankings look — that is
the failure a 240-row table of plausible numbers would otherwise hide.

The table also settles that the interaction term is measurable at all: at 6.1
and 16.0 times the floor, it is not a quantity 2B has to strain to see. It
predicts what Stage A should find, which is the point — a check is only a check
if its expected value was written down first.

**Eligibility, frozen with these gates.** All 12 candidates are eligible,
including the two that are harmful alone. Nothing is excluded on performance.
The only exclusions are structural (gate 2B-1) and are properties of the edit
algebra rather than of any measurement. Recorded in
`outputs/exp2_candidate_classes.json`.


## Pre-registration note: representation stability across geometry

Recorded 2026-08-29 15:30 UTC, **with 5 of the 12 candidate networks scored and
visible.** This is written down now precisely because it is contaminated, and
the contamination has to travel with the claim rather than be discovered later.

While the treatment frontier was running, the partial results showed something
the experiment was not designed to test. Across the five networks scored so
far, at λ=2, measured unserved demand under the **route-level** representation
ranges −1.09% to −7.45% — a spread of 6.4 points — while under the
**path-level** representation on the same five networks it ranges −5.11% to
−6.42%, a spread of 1.3 points. Same envelope, same evaluator, same effort, so
the spread is a property of the representation and not of the networks.

If that survives all twelve, it is a stronger statement than D21's: the
route-level representation would be not merely more expensive but substantially
less stable under a change of geometry.

**It will be reported as exploratory.** It was noticed mid-run, its threshold
was not committed in advance, and the remaining seven networks were already
queued when it was written down — so nothing here is a test, and no p-value or
sigma may be attached to it. Promoting it to a finding requires either a
pre-registered threshold applied to an independent candidate set, or the
Experiment 2B networks, which are a different set and were enumerated before
this was noticed. Whichever is used must be named in the write-up.


## Defect: the Experiment 2 evaluator was Model A, 2026-08-27 to 2026-08-29

Recorded here rather than only in the commit log, because it changes which
results a reader may trust and the gates are where that is decided.

**What happened.** `run_exp2_eval.py` constructed its evaluator with
`build_setup(...)` and did not pass `common_lines`. The parameter falls back to
`config/assumptions.yaml`, which says `pattern` — Model A. Runs launched with
`--common-lines same_route` set the harness to Model B, logged *"waiting model:
same_route"* from that harness, and scored every plan under Model A. No
artifact recorded the evaluator's own pricing, so the run's outputs could not
be used to detect it.

**Confirmed, not inferred.** The same script re-run with the fix scores the
zero-edit rung at **9,812** unserved where it previously scored **10,371** —
and 9,812 is what `exp2b_subsets.py`, which always passed the pricing
explicitly, independently reports for the same network. The two pipelines
enumerate identical path sets (152,241 paths, same six periods, same seed,
same effort); pricing was the only difference and it is now gone.

**Affected**, all marked provisional in place and re-running:

* the twelve single-candidate evaluations and their classification
* both complexity ladders, screen-ordered and measured-ordered
* both noise floors (0.288 pts at ranking effort, 0.172 at full effort)
* the full-effort D19 falsification recheck
* D19, D20, and gate 2B-8's expected values, which are derived from the above

**Not affected**, verified by reading the call sites rather than assuming:

* everything through `harness.setup()`, which passes `common_lines` — the
  Experiment 1 fixpoint, gate 4 certification and gate 7 seed checks, so the
  −6.65% headline stands
* `exp2_treatments.py`, which passes it explicitly — the thirteen-network
  representation frontier
* `exp2b_subsets.py`, which passes it explicitly — the Experiment 2B sweep
* the geometry screen and its D16 bracket, which are Model A by design and
  labelled so

Four further scripts share the omission — `run_ablation.py`,
`fairness_checks.py`, `frontier_extend.py`, `run_exp2.py` — and every one of
them predates the Model B correction, so Model A was what they were built to
use. Their outputs were checked against DISCOVERIES, ACCEPTANCE and HANDOFF:
**none is cited in any finding.** They now log their pricing like everything
else, so the next run of any of them states which model it used rather than
leaving it to be reconstructed.

**What makes it not recur.** `build_setup` decides the pricing once and logs it
as `explicit` or `CONFIG DEFAULT — caller did not specify`, and records both
the value and its source in `checks`. `run_exp2_eval.py` asserts the setup came
back with the model the run asked for and refuses to score otherwise. The
pricing is part of the result-store cell key, so a corrected re-run cannot
resume the old cells and silently reproduce the numbers it exists to replace.
Three tests hold all of that in place.

**The general lesson, for the gates.** A run's log reported the model the
*harness* held, not the model the *evaluator* used, and those were different
objects. Any future claim of the form "this was run under model X" must cite an
artifact written by the thing that did the scoring, not by something adjacent
to it.


## Experiment 3 gates, committed 2026-08-30, renumbered 2026-08-30 after the identity split

**What Experiment 3 is.** A search over **network states** produced by route
mutation — shorten, extend, reroute, straighten, change terminal, change
transfer point, splice, split — inside COTA's existing stop inventory and
vehicle-hour envelope, with frequency re-optimized on every state.

**What Experiment 3 is not.** It is **not stop consolidation**, and it is not
greenfield network design. The gates below were first written for the
stop-consolidation question — walking traded against vehicle running time —
because that was what Experiment 3 was going to be. It is not that any more.
Those gates are preserved verbatim further down under the `SC-` prefix and
marked **deferred**; they are not operative for this experiment. Leaving them in
force would have meant an experiment governed by gates about a quantity it never
measures, and — worse — a stop-consolidation search could have slipped in under
Experiment 3's name because the gates still permitted it.

The renumbering is a rename, not a relaxation. Every operative gate below is
either one of the old gates that was always general (3-6, 3-7, 3-9), the
surviving operative *prohibition* from the stop audit (old 3-1 and 3-5), or new
and stricter.

| old | new | what happened |
|---|---|---|
| 3-1 no measured stop penalty | **SC-1** + **3-4** | deferred as a claim rule; survives as an operative prohibition on crediting skipped stops |
| 3-2 survive the plausible range | **SC-2** | deferred with the consolidation question |
| 3-3 conservative break-even | **SC-3** | deferred with the consolidation question |
| 3-4 schedule relationship not causal | **SC-4** | deferred as a regression rule; the underlying finding is quoted in 3-4 |
| 3-5 sole-access stops excluded | **3-5** | operative, restated as a mutation constraint |
| 3-6 Model B asserted | **3-1** | operative, unchanged in force |
| 3-7 the screen does not select | **3-2** | operative, unchanged in force |
| 3-8 sets not sums | **3-6** | operative, strengthened — 2B's evidence replaces D20's inference |
| 3-9 noise floor in the same run | **3-3** | operative, strengthened — now on the scalarized objective too |
| — | **3-7, 3-8, 3-9, 3-10** | new |

---

**Gate 3-1 — Model B, and the pricing is asserted.** Every evaluator is built
with `common_lines` passed explicitly and the run asserts the setup came back
with it. This is not boilerplate: an unasserted evaluator scored three days of
Experiment 2 under the wrong model (see the defect note above). In Experiment 3
the assertion moves out of the run script and into the state validator, which
refuses to score a state whose evaluator cannot state its own waiting model.

**Gate 3-2 — the screen does not select what gets evaluated.** D19 found the
screen's first-ranked candidate of sixty to be the worst of twelve on
evaluation, and D23 found the ranking to move again under a corrected model. No
mutation is discarded, and no state is ranked, on a fixed-frequency score.
Frequency is re-optimized on every state that is scored at all.

**Gate 3-3 — the noise floor is measured in the same run, at the same effort,
for the quantity actually being compared.** Three zero-edit replicates, 3σ.
Experiment 3's primary quantity is the **scalarized objective**, not unserved
demand, so it needs its own floor: the existing 0.130-point and 0.287-point
figures are floors on *unserved demand* and may not be applied to a different
quantity. A floor is measured for the objective **and** for every component
metric reported alongside it. A candidate clearing a floor by a hair clears
nothing — the floor itself is estimated from three seeds and is noisy.

**Gate 3-4 — no runtime credit for skipping stops on an unchanged alignment.**
The exchange rate between passenger walking and vehicle running time is the time
a bus loses serving one more stop, and **this feed cannot measure it** (the
finding is preserved in full under SC-1 below). So a mutation may not be
credited with a running-time saving that comes from serving fewer stops along
the same path. Mutations that change the *alignment* are priced by the runtime
model as usual; a mutation that keeps the alignment and drops stops from it
gets no runtime benefit at all. The validator enforces this structurally rather
than trusting the scorer, because this is the single most likely way for the
deferred consolidation question to re-enter Experiment 3 wearing a disguise.

**Gate 3-5 — a stop that is anyone's only access is protected.** The audit
identifies 13 stops that are the sole transit access for their catchment,
carrying 3,045 units of flow. No mutation may leave one of them unserved. This
is checked on the resulting network state, not on the mutation's intent —
truncating a route can strand a stop that the mutation never names.

**Gate 3-6 — states are scored, not sums of edits.** Experiment 2B settled this
with evidence rather than inference: across all 240 structurally feasible
subsets, **every one of the 227 multi-edit sets delivers less than the sum of
its members** at λ≥2, without a single exception. A search that ranks mutations
individually and takes the top N is therefore forbidden as a *procedure*; it is
permitted only as an explicit object of study whose expected failure is already
on record. Interaction terms are measured and published for every promoted
state.

**Gate 3-7 — the margin is over the conservative incumbent, re-solved in the
same run.** The comparison object is COTA's **unchanged** geometry with
frequency re-optimized inside the same envelope under the same evaluator —
there is no geometry component, because Experiment 2 promoted nothing and
Experiment 2B certified the null. The frozen Experiment 1 record is the
reference, but **every promoted comparison additionally re-solves the unchanged
network at matched effort in the same run**, with replicates. Beating the raw
published schedule is context and is reported as context; it is not an
Experiment 3 result, because Experiments 1 and 2 already did it and reporting it
again counts the same gain twice.

**Gate 3-8 — the envelope binds, and both halves are checked.** Weekday revenue
vehicle-hours must not exceed the pinned budget, and the block-derived peak
vehicle count must not exceed the baseline's 197.0. Hours are not buses: a plan
can respect the hour budget and still need more vehicles, and that would be a
different experiment with a different cost.

**Gate 3-9 — modelled-link exposure is recorded, and it sets the evidence
class.** Every state records `modelled_share_pct`, the share of its segment
running time priced by the estimator rather than observed in the feed. At or
below **2.0%** a result is *primary* evidence. Above it the result is
*secondary* and may not carry a headline unless its margin is large against the
estimator's 20.5% median single-link error. The class is recorded with the
score, not decided afterwards.

**Gate 3-10 — mutation identity stability.** If independent seeds at matched
effort produce structurally different networks that score within the noise floor
of each other, the **structure is not identified** and must be reported that way
— exactly as Experiment 1 reports its headways. Structural disagreement is
measured and published alongside the effect, as gate 7 does for route-periods.
No map is promoted because it came from seed 1, and no seed is chosen for
producing the prettiest network.

**Gate 12 applies to every Experiment 3 comparison.** Convergence must be
matched, not merely nominal effort. See the gate 12 section below; D24 is why it
exists.

---

### Deferred: the stop-consolidation gates (SC-1 … SC-4)

**These are not operative for Experiment 3.** They govern a question this
project has deferred: whether COTA should remove stops, trading passenger
walking against vehicle running time. The code that supports it —
`stopedits.py`, `stopevidence.py`, the break-even framework, the sole-access
audit — remains in the repository and remains correct. It must not become the
Experiment 3 search by default, which is why the gates are marked rather than
deleted: a future experiment that takes up this question inherits them already
written, and Experiment 3 cannot quietly satisfy them instead of its own.

The finding underneath them is preserved in full, and is the reason gate 3-4
exists:

> **The exchange rate is not measurable from this feed.** The eleven natural
> experiments COTA's schedule offers rest on five stops, three of which are bays
> on one platform at Spring St Terminal **nine metres apart**, and the other two
> downtown intersection corners about sixty-four metres from the stop they are
> being distinguished from. COTA's median stop spacing is 331 m. Relaxing every
> threshold — dropping the period control, cutting the minimum segment from
> 120 s to 30 s, raising the skipped-stop cap from 12 to 40 — takes the
> comparison count from 11 to 15 and the *wayside* comparison count from **0 to
> 0**. The scarcity is in the feed, not the filter
> (`outputs/exp3_stopprice_diagnosis.json`).

**Gate SC-1 (deferred) — no measured stop penalty may be claimed, ever.** A
consolidation experiment reports a **break-even** penalty per candidate: the
seconds per stop an edit must save to pay for the walking it imposes. Any
sentence of the form "a stop costs N seconds" is out of scope for this project
on this data. The `-157 s/stop` pooled estimate is a diagnostic that the natural
experiment failed; it is not a number.

**Gate SC-2 (deferred) — a recommendation must survive the whole plausible
range, or it is not a recommendation.** A consolidation may be recommended only
if its break-even threshold sits **outside** the range of dwell figures a
reasonable planner might assume, so the conclusion does not depend on which
figure is chosen. The range must be stated, with its source, before candidates
are scored. Candidates whose break-even falls inside the range are reported as
*decided by the assumption* and recommended to nobody — a finding about what
this data can settle, and expected to be most of them.

**Gate SC-3 (deferred) — the break-even stays conservative.** It counts only the
in-vehicle time of riders passing the stop, and does not credit the
vehicle-hours a removal frees. Crediting them would lower every threshold and
make removal easier to justify; leaving them out errs in the direction that
makes consolidation harder to argue for, which is the correct direction when the
penalty is unmeasured. If this is ever relaxed, it is a new gate, not a
refinement of this one.

**Gate SC-4 (deferred) — the schedule relationship is not causal and is never
presented as one.** Routes with more stops are scheduled slower *and* run on
denser, slower corridors; the feed cannot separate those. No regression on
scheduled running time against stop count enters a conclusion, in any direction,
including the one that would support consolidation.

## Experiment 3 treatment contract

The rules for what Experiment 3 may mutate — legal operations, the terminal
movement limit, the route removal cap, the stop rule, the novel-link rule, the
15% network-edit-distance boundary between Experiment 3 and Experiment 4, how
frequency optimization nests inside a mutation, the interaction-first search
requirement and its tractable benchmark, the staged effort ladder, and gate
3-10 on mutation identity stability — are committed in
[`EXPERIMENT3_CONTRACT.md`](EXPERIMENT3_CONTRACT.md), written before any
candidate was generated.

## Experiment 4 gates, committed 2026-08-31 before any synthetic route was scored

**What Experiment 4 is.** A search over networks built from scratch on COTA's
existing stop universe and observed-link graph, inside today's resource
envelope. Route identity, route count, termini, transfer architecture and
network edit distance are all released. See
[`EXPERIMENT4_CONTRACT.md`](EXPERIMENT4_CONTRACT.md).

**Gates 3-1, 3-2, 3-3, 3-4, 3-6, 3-8, 3-9, 3-10 and 12 carry over unchanged.**
The evaluator still asserts its own waiting model, a fixed-frequency screen
still may not select, floors are still measured in the same run for the quantity
compared, no runtime credit for skipping stops on an unchanged alignment, states
are scored rather than sums of routes, the envelope still binds on both halves,
modelled exposure still sets the evidence class, structure must still be
identified before a map is shown, and convergence must still be matched.

**Gate 3-5 does NOT carry over**, and its removal is deliberate. Experiment 3
protects the 13 sole-access stops because it asks for a recognizable
modification of COTA. Forcing the unconstrained greenfield optimum to preserve
every current catchment would destroy the very baseline Experiment 6 is meant to
measure against. Lost coverage is **reported, not forbidden** — gate 4-8.

**Gate 4-1 — the primary evidence class is the observed-link graph.** A headline
Experiment 4 claim rests only on networks whose every segment is a stop-to-stop
movement some COTA route already operates, at that movement's observed running
time. Networks using genuinely novel links are **secondary and exploratory**. A
high-modelled-share network may not displace the observed-link winner as the
headline without a new runtime-validation argument. The estimator's median
absolute error on a single link is 20.5%; a network that is half modelled is
mostly a statement about the estimator.

**Gate 4-2 — the peak-express layer is frozen and is not redesigned.**
Experiment 1 established that treating those 14 routes as frequency service
manufactured 1.5–3 percentage points of fake improvement, because the optimizer
stretched a designed timetable as though it were random-arrival service. Being
"more greenfield" is not a licence to reintroduce a known modeling error. Their
links are excluded from the graph as well, so a generated local route cannot
borrow a freeway hop as a cheap teleport.

**Gate 4-3 — the stop universe is fixed.** No stop is created, none is moved. A
generated route serves the nodes it traverses; the generator may not traverse an
observed chain and declare intermediate stops skipped to manufacture speed.

**Gate 4-4 — the frozen pool must contain the current network.** Every supported
current local route, and Experiment 3's promoted result where representable,
must be inside the search space, demonstrated by reconstruction rather than
asserted. Without it, a poor Experiment 4 result cannot be distinguished from a
generator that failed to propose what COTA already runs.
*Status: PASSES — 41 synthetic lines from 25 legacy routes, all 2,763 stops
covered, zero canonical-id collisions (`outputs/exp4/reconstruction.json`).*

**Gate 4-5 — service activation is a real decision.** A synthetic route-period
may be OFF, consuming no vehicle-hours and no peak vehicles and contributing no
frequency. No synthetic route is given a copied "baseline headway": a route that
did not exist yesterday has no baseline, and inventing one invents a service
commitment nobody made.

**Gate 4-6 — search bounds must be proved inactive.** One-way running time is
bounded to 10–120 minutes and route count to a generous cap. Both are
computational bounds, not claims. **If the winning network's routes sit on a
bound, the result is censored** and the bound must be raised or the finding
reported as bounded. Today's local routes run 23.7–99.9 minutes one way, all
inside the bound, which is the sanity check that the bound is not already
binding on the incumbent.

**Gate 4-7 — the discovery approximation is benchmarked, and buys no
conclusions.** Discovery may score networks against a frozen supernetwork master
path set rather than rebuilding paths per state — 311 of every 413 seconds is
the rebuild, and a greenfield search needs thousands of evaluations. It may
**not** reuse the incumbent's paths. On a preregistered sample the approximation
is compared against exact rebuilds for objective gap, unserved gap, ranking
stability, omitted and improvable flow, and whether the promoted set changes; if
it cannot identify the exact leader within the promotion band, it is widened or
abandoned. **Every promoted network is rebuilt exactly.**

**Gate 4-8 — what the optimizer abandons is reported.** Stops losing service,
demand losing access, neighborhoods affected, one-seat rides lost, transfer
burden created. These are not constraints on the primary objective. They are the
handoff to Experiments 6 and 7, and suppressing them would hide the price of the
freedom being measured.

**Gate 4-9 — path-model adequacy is re-established, not inherited.** Every
assumption below was measured on today's map and does not transfer to a network
the optimizer designed:

* **transfer depth** — promoted networks are rerun with a deeper limit than two;
  if `max_rounds` materially moves the winner or its score, the path model is
  inadequate for this network;
* **paths per OD** — the 4→6 candidate-cap result was measured on the existing
  network; the sensitivity is redone;
* **OD truncation** — the top 20,000 pairs are about 65% of transit-accessible
  commute flow, and certification evaluates promoted networks on a materially
  wider set. The optimizer does not get to redesign Columbus around the
  computationally convenient top of the OD table.

**Gate 4-10 — common-lines exposure is re-measured.** Model B's remaining
approximation is overlapping *different* routes, about 0.516% of generalized
cost today. A generated trunk network may create far more. Every promoted
network reruns the diagnostic; if exposure balloons, either the general waiting
model is implemented or the result is classified model-dependent and may not
headline a margin of comparable size.

**Gate 4-11 — crowding is re-checked.** It did not bind on the existing network.
A greenfield optimizer may concentrate passengers onto a few strong trunks.
Promoted networks get segment load profiles, peak load factors and overloaded
segments, with a crowding-enabled sensitivity if exposure becomes meaningful.
*"Crowding didn't matter in Experiment 1"* is not evidence about a different
network.

**Gate 4-12 — demand robustness is preregistered.** The demand model is this
project's largest external-validity limitation, and structural freedom gives the
optimizer many more ways to exploit artifacts in the LODES proxy. Claims are
written before the winner is known, and tested against altered period shares,
demand scaling, the implemented noncommute stress direction, blends, and a wider
or held-out OD universe. The admissible claim is *"substantial benefit survives
materially different demand shapes"* or *"the apparent gain disappears when
commute geometry is perturbed"* — **not** a decimal-place margin on one demand
model.

**Gate 4-13 — structural identity uses geometry, not route ids.** Exp 4 route
ids are synthetic, so id disagreement is meaningless. Distance is measured on
service geometry — directed edge overlap, service-weighted overlap, stop
incidence, one-seat connectivity. If independently optimized networks score
within the certification floor of each other while their maps differ, the
conclusion is that **the value of greenfield redesign is identified and the
exact network is not** — the analogue of Experiment 1's flat headway optimum.

**Gate 4-14 — the search is benchmarked on a space that can defeat it.** As in
Experiment 3, but harder: a tractable route pool, every feasible network in a
small envelope enumerated, and recovery of the true optimum demanded from
incumbent, random and deliberately deceptive starts. The benchmark must include
a case where the optimum requires **dropping a locally good route**, one where
the optimum is **not nested**, one where a **swap is required**, and one where
the **incumbent is actually optimal**. Passing the 2B benchmark is explicitly
insufficient — its winner is a singleton adjacent to the null.

**Gate 4-15 — what Experiment 4 may conclude.** At most: *holding COTA's current
operating-resource envelope fixed, releasing legacy route structure produces
approximately X additional benefit beyond the best constrained redesign.* Not
"COTA should implement this map", and not "COTA planners failed to find this
map" — this project has not represented the constraints they solve. **The null
is precommitted as a fine result**: that a greenfield redesign buys little once
frequencies and constrained mutations are optimized would be a strong statement
in favour of COTA's existing topology, and it is not a failed experiment.

### Rejection conditions

An Experiment 4 finding is rejected if **any** of these holds, however good the
headline:

* its margin over the Experiment 3 incumbent is inside the noise floor measured
  in the same run, at the same effort, for the same quantity;
* the margin shrinks when both sides are solved at higher effort (gate 12);
* the incumbent it beat was a stored score rather than the Exp 3 network
  re-solved at matched effort in the same run;
* Experiment 3 certified a tied set and only one arbitrary member was used as
  the incumbent;
* its winning routes sit on the length or route-count search bound;
* it rests on modelled links beyond the primary class without a new
  runtime-validation argument;
* it was scored by the discovery approximation and never rebuilt exactly;
* the discovery approximation was never benchmarked against exact rebuilds;
* it redesigned the peak-express layer;
* it invented or moved a stop, or claimed runtime for skipping stops on an
  unchanged alignment;
* the frozen pool did not contain the current network;
* transfer depth, path cap or OD cap materially move the result and were not
  re-established;
* common-lines exposure ballooned and the margin is of comparable size;
* crowding became material and was not re-checked;
* the demand-robustness claims were written after the winner was known;
* independent seeds produce structurally different networks inside the floor and
  a single map is nonetheless presented as the answer;
* the evaluator that produced it cannot state its own waiting model.

Every entry on that list is either something that has already happened in this
project or something the contract identifies as newly possible once route
structure is released.

## Gate 12 — matched effort is not enough; convergence must be matched

**Added 2026-08-30, after D24.** This is a standing gate on every comparison
between two networks or two models from here on, including Experiments 2B and 3.

The existing standing rule says *search effort is matched whenever two things
are compared*. It was satisfied. Both the edited and unedited networks were
solved at 60,000 iterations and 2 restarts, and the comparison was still wrong,
because the same nominal effort was not equally sufficient for both. The
unedited network was the harder of the two to solve well, so it arrived less
converged, and the difference was booked as a geometry benefit worth half a
point. At 400,000 iterations and 20 restarts the gap closes entirely.

### Amended 2026-08-31, after D27 and D28 — what "effort" actually means

**The iteration ceiling is not the lever.** D28 measured every certification
restart terminating after roughly **4,000 of its 400,000 permitted
evaluations**: the exchange search runs out of improving moves long before it
runs out of budget. A run described as "400000/20/0" is not doing 6.7× the
search of a "60000/20/0" run — it is doing the same search. What separates
discovery from certification here is **restart diversity**, 2 against 20.

So gate 12 is restated in terms of what is actually received, not what was
requested:

> **Gate 12 — optimization convergence.** Treatment and control must receive
> **treatment-independent start sets** and enough **restart diversity** that
> residual variation attributable to the allowed start strategy is below the
> applicable noise floor. Nominal effort settings are recorded for
> reproducibility; they do not establish convergence and may not be cited as
> if they did.

Three obligations follow, all mechanised in the semantic comparison firewall
(`ARCHITECTURE_FIREWALL.md`) rather than left to a reviewer:

1. **Start sets must not depend on the treatment.** D27: whether the optimizer
   accepted the incumbent start was decided by the edit applied to the network,
   so the control was optimized by one method and the treatments by another. A
   contract whose start policy can vary with the state is now refused at
   construction.
2. **Completed search is compared, not requested search.** Restarts completed,
   evaluations performed, termination reason and convergence status live in the
   `ExecutionReceipt` and are compared between arms; an undeclared difference
   refuses the comparison. Two arms with identical configuration and different
   realised search are not comparable.
3. **Certification must assert convergence.** A certification contract whose
   solver policy does not require convergence is refused at construction, and a
   comparison in which either arm did not converge is inadmissible.

Effort should be quoted as restarts and measured convergence. Quoting an
iteration ceiling as evidence of search depth describes something that did not
happen.

**The gate.** A comparison between two networks may be quoted only if it is
accompanied by evidence that both sides are converged, in one of these forms:

1. **Two effort levels.** The comparison is computed at the reporting effort and
   at a materially higher one, and the difference between the two effects is
   inside the noise floor. This is the cheapest sufficient check and is the
   default.
2. **Replicates on both sides.** Independent seeds on *each* network, not only
   on the baseline, with the effect stable across them relative to the pooled
   floor.
3. **A convergence trace.** The objective's improvement per restart on both
   networks, shown to have flattened before the run stopped.

A comparison with none of these is a **discovery-stage** number. It may order
candidates for further work and may not appear in a conclusion, a figure caption
or a headline.

**What this does not require.** Certifying everything at full effort — that is
unaffordable and gate 2B-5 already forbids it. Two effort levels on the handful
of candidates a claim actually rests on is enough, and would have cost about
three hours here against the days the wrong answer would have propagated
through.

**Applied retrospectively.** Every Experiment 2 number measured at 60,000/2/32
is now labelled discovery-stage, including the candidate classification, both
ladders and the interaction terms. They order candidates. They are not
conclusions. The two conclusions Experiment 2 does support — that six candidates
do measurable harm, and that none does measurable good — rest on full-effort
comparisons with same-run replicates and clear this gate.

**One comparison to watch.** The thirteen-network representation result (D21)
also ran at 60,000/2/32. Its two treatments are solved on the *same* network, so
the asymmetry D24 found between networks does not apply directly — but the
route-level model solves in about 3 seconds against the path-level model's 25,
so route-level is plausibly the better-converged of the two at equal effort. If
so, path-level's advantage is *understated*, and the direction of D21 is safe
while its magnitude is not. D21's own falsification test (both treatments at L4)
is now also a gate 12 obligation.


## Standing rules

1. These gates are not revised after seeing results.
2. A failed gate makes a result provisional and says so in the write-up. It
   does not make the gate wrong.
3. Every reported number carries its evidence class: **strongly supported**,
   **supported but model-dependent**, or **requires outside data or
   transportation expertise**.
4. Search effort is matched whenever two things are compared. An effort gap is
   a confound, and this project has already been burned by one.
