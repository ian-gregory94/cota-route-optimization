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

| set | members | measured unserved vs no edit | sum of member singles | interaction |
|---|---|---|---|---|
| k=1 | 033+034 WESHIGW | −0.9363% | −0.9363% | 0.000 pts |
| k=2 | + 005+006 NMURBEAN | −0.4853% | −1.6200% | **+1.135 pts** (3.9× floor) |
| k=4 | + 001+021 PICBETS, 008+035 BOASHAN | +0.4733% | −2.6225% | **+3.096 pts** (10.8× floor) |

Stage A re-derives all three through a different script and a different code
path. **They must agree to within the 0.288-point noise floor.** If they do not,
the 2B pipeline is measuring something other than what the ladder measured, and
the whole sweep is void regardless of how sensible its rankings look — that is
the failure a 240-row table of plausible numbers would otherwise hide.

The table also settles that the interaction term is measurable at all: at 3.9
and 10.8 times the floor, it is not a quantity 2B has to strain to see. It
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


## Standing rules

1. These gates are not revised after seeing results.
2. A failed gate makes a result provisional and says so in the write-up. It
   does not make the gate wrong.
3. Every reported number carries its evidence class: **strongly supported**,
   **supported but model-dependent**, or **requires outside data or
   transportation expertise**.
4. Search effort is matched whenever two things are compared. An effort gap is
   a confound, and this project has already been burned by one.
