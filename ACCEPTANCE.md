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
| 4 | The L4 plans pass adequacy against the frozen set ⚠️ **PARTIAL — Model A, 2026-08-27 09:37 UTC** | `final\|adequacy`: worst flow-share improvable under any final plan is below the tolerance the loop converged at (1.029%). **Result:** λ = 1, 2, 4, 8 pass at 0.66–0.69%; λ = 16 passes at 0.988%; **λ = 0.5 fails at 1.618% and λ = 0.25 fails at 9.721%.** The probe loop ran λ ∈ {0.5, 1, 2, 8} and the final frontier runs λ ∈ {0.25, …, 16}, so the extreme cost-favouring corner was solved at an effort and a λ the enumeration never saw. λ = 0.25 also carries 1.13% mean overstatement against 0.09% elsewhere. **No headline may rest on λ ≤ 0.5 until this is certified**; the balanced region is unaffected. |
| 5 | Previously saved plans are repriced on the same yardstick | `outputs/fixpoint_rescored.csv` covers every plan in `outputs/matrix_plans/`. **Why this gate is not bookkeeping:** `generalized_cost` is a *total* over served trips plus the unserved penalty, not a per-trip mean, so a larger candidate set that retains more demand can raise it. Baseline gc drifts across fixpoint iterations for exactly this reason (1.787982e6 to 1.788020e6, +0.0021%, as the set grew from 203k to 226k paths), and that drift is correct behaviour rather than a defect. Two numbers scored on different candidate sets are not comparable in either direction; every cross-set comparison uses one evaluator, or `mean_cost_per_served_trip`. |
| 6 | Decision-relevant λ points stay coherent | λ = 1, 2, 4, 8 remain monotone in the intended direction: unserved demand non-increasing in λ, generalized cost non-decreasing in λ, within seed noise |
| 7 | Important λ results are seed-stable | at least three seeds at λ = 2; the reported effect must exceed its own standard deviation by a clear margin. **Second job added 2026-08-27:** the same replicates decide whether the plan *composition* is identified at all. D14 found two plans differing on ~25% of route-periods (mean 8 min of headway) whose objectives differ by 0.01%. If independent seeds also disagree that widely, the optimum is flat and no per-route headway may be stated as a recommendation; the aggregate result is unaffected either way. Report the route-period disagreement across seeds alongside the objective's standard deviation. |
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
| 9 | The geometry change is legible as a real transit proposal, inspected by hand against the network |

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

The Experiment 1 headline is not final until Model B completes. Until then the
result is described as: *the pre-correction model finds roughly 6-7% lower
unserved demand from frequency redistribution, but a newly identified
same-route waiting-cost bias systematically undervalues high-frequency trunk
service; the corrected frontier is being rerun.*

Cross-route common lines (0.79% of generalized cost) stays a documented
limitation and follow-on task, and is promoted to a required correction only if
a later diagnostic shows it could reorder the frontier.

## Standing rules

1. These gates are not revised after seeing results.
2. A failed gate makes a result provisional and says so in the write-up. It
   does not make the gate wrong.
3. Every reported number carries its evidence class: **strongly supported**,
   **supported but model-dependent**, or **requires outside data or
   transportation expertise**.
4. Search effort is matched whenever two things are compared. An effort gap is
   a confound, and this project has already been burned by one.
