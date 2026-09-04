# Experiment 3 — closure package

Route-shape mutation of the COTA network under a frozen Model B evaluator, at
λ=2, scored on the λ-scalarized objective `generalized_cost + λ·w_unserved·
unserved_demand`. This document is the terminal record. It is written to be
read by someone deciding how much of it to believe, so the limits are given the
same prominence as the result.

---

## 1. The result

**§8 outcome (1): a certified leader.**

| | |
|---|---|
| leader | `add_stop-010#22c4c35ac5b2` |
| effect | **−0.18657%** on the λ=2 objective vs the unedited control |
| paired SD across 5 seeds | 0.002375% |
| \|mean Δ\| / SD | **78.6** (criterion: > 3) |
| distinguishable from | all 28 other certified candidates, 28/28 resolved |
| measured at | **20 restarts** (Stage B), 400,000 evaluation ceiling, full width |

Of 84 census states, 39 were promoted, 30 certified at Stage B, and **29 remain
certified** after the §6 escalation.

The edit adds a stop. The mechanism is not established here — the objective
improves, and *why* is a separate question this experiment does not answer.

## 2. What "certified" means, and what it does not

Certified means: **distinguishable from solver variance at the effort stated in
its row.** Nothing more. It is not a claim that the improvement is real in
Columbus, that it would survive a different demand model, or that it is large
enough to act on. −0.19% of a scalarized objective is a small number and is
reported as one.

Three named limits, each established elsewhere in this repo and none of them
retired by this result:

* **D33 (local optimality).** The differential-error diagnostic enumerates a
  neighbourhood of at most 10 of 173 route-periods over three ladder rungs. It
  is a *lower* bound on differential solver error; the full-problem figure can
  only be larger. A margin above it is *not excluded*, which is much weaker
  than *established*.
* **Model B waiting couples the objective.** A ride leg is priced on the
  combined frequency of every same-route pattern serving boarding then alighting
  stop, in that order. The objective therefore does not separate, which is why
  no MILP benchmark appears here — one would be dishonest about what it bounds.
* **The demand model is an input, not a finding.** Every number is conditional
  on it.

## 3. The design, and where it was fixed

| artifact | fixed before | what it fixes |
|---|---|---|
| `EXPERIMENT3_STAGE_B_PREREGISTRATION.md` | any Stage B cell ran | §4 criterion, §5 pairwise, §6 escalation triggers, §7 D33 re-measurement, §8 outcomes |
| `scripts/exp3_stage_b_report.py` (`3a21ba57`) | any Stage B cell ran | the analysis |
| `EXPERIMENT3_D33_STAGEB_DESIGN.md` | any Stage B-effort gap computed | the veto rule, the adversarial subset |
| `outputs/exp3/escalation_manifest.json` | any escalated cell ran | the literal 33-candidate escalation set |
| `EXPERIMENT3_PHASE5_DESIGN.md` | any escalated effect was read | how the two regimes combine |
| `scripts/exp3_escalation_report.py` (`636a19bb`) | any escalated effect was read | the Phase 5 recompute |

The escalation set was generated mechanically from the frozen Stage B report by
`scripts/exp3_escalation_manifest.py` and committed before the batch started. It
was not narrowed retrospectively.

## 4. D33 at Stage B effort — the veto that did not fire

§7 required the differential-error diagnostic re-measured at Stage B effort.
375 enumerations across 5 networks × 5 seeds × 5 strata × 3 sizes, on 25
Stage B-effort anchor solves.

**Verdict: PASS. 0 of 30 certified candidates vetoed.** Largest
\|differential\| across all measured treatments: **0.0018970%**. The leader's
margin is **98×** that bound.

The subset was chosen after the Stage B results were visible, and that is
disclosed rather than hidden: it deliberately included both the leader and
`straighten-021#110f4a755fe7`, the smallest certified margin and the most
veto-vulnerable claim in the set. A subset chosen to make a veto *more* likely
cannot manufacture a pass.

Two findings the design did not predict, recorded because they were predicted
otherwise:

* the gap did **not** shrink with 10× the restarts (0.0018970% vs D33's
  0.0018370% at discovery effort);
* it **moved into the control** — the leader had 0 of 75 nonzero cells, the
  control 9 of 75. That is the D24 asymmetry, 98× too small to affect anything.

**All 25 D33-B anchors reproduced their Stage B `plan_digest` exactly.** That is
an independent reproducibility check of Stage B, satisfying Phase 9's
verification requirement.

## 5. The §6 escalation

33 candidates + control × 5 seeds = **170 cells at 40 restarts**, all else held
identical to Stage B. Triggers: 24 unresolved-pairwise, 9 failed-criterion,
1 ddof-sensitive (inside the 9).

Integrity, verified rather than assumed:

| control | result |
|---|---|
| contract digests in the escalated store | 1 (`45e23ae01be4d071`) |
| code versions | 1 (`src-bd82ac5a6dae`, = `EVAL_PATH_FROZEN`) |
| Stage B receipts in the escalated store | 0 — no mixed regime |
| restarts completed | 40/40 on all 170 |
| duplicate `(state, seed)` keys | 0 |
| key set vs frozen manifest | exact — 0 unexpected, 0 missing |
| firewall refusals | 0 |
| escalated control spread 3σ | 0.00936% (flag at 0.01971%) — normal |

**One verdict changed**, and it is the one named in advance:
`straighten-021#110f4a755fe7` lost certification — −0.00780% (SD 0.002379%,
ratio 3.28) at 20 restarts → −0.00616% (SD 0.003120%, ratio 1.97) at 40.
No candidate gained certification.

## 6. Effort robustness, and the Experiment 2 contrast

Full table in `EXPERIMENT3_ROBUSTNESS.md`. Diagnostic only; not a gate.

| | transition | median \|shift\| | sign changes |
|---|---|---|---|
| Exp 2 geometry leaders (n=2) | 60,000/2/32 → 400,000/20 | **0.645 pts** | **2 of 2** |
| Exp 3 promoted (n=39) | 60,000/2/32 → 400,000/20 | **0.00207 pts** | 1 of 39 |
| Exp 3 escalated (n=33) | 20 → 40 restarts | 0.00130 pts | 0 of 33 |

The first two rows are the **same effort transition on the same network under
the same evaluator** — the one that reversed Experiment 2's geometry claim and
forced its withdrawal. Experiment 3's effects do not move across it. The one
sign change is on the smallest effect in the set, uncertified at both efforts.

## 7. The two-regime asymmetry — the weakest part of this result

§6 escalates what is *unresolved or failing*, which is by construction the
*smaller* margins. The consequence:

* the leader is **not in the escalation manifest** and has never been solved
  above 20 restarts;
* **all 28** of the leader's pairwise comparisons are at 20 restarts;
* **all 50** unresolved pairs are in the escalated regime;
* the best margin *confirmed* at 40 restarts is `straighten-102#4dd646541565`
  at −0.08017%, **2.33× smaller** than the leader's.

So the leader leads, and it leads on the softer measurement. Everything tested
harder came in at less than half its margin, which is reassuring but is not the
same as testing the leader.

Per `EXPERIMENT3_PHASE5_DESIGN.md`, frozen before these numbers were read, the
leader was **not** re-run at 40 restarts after this became visible — that would
be a measurement chosen by its expected answer. Closing the asymmetry requires
escalating **all six** non-escalated candidates, a rule that does not depend on
which candidate it favours.

**Status of that step: attempted and abandoned; the asymmetry stands.** Phase 5b
was designed, its manifest frozen, and its workers launched twice on 2026-09-04.
Both launches were killed by container reclaim before a single cell completed —
a 40-restart cell needs ~28 minutes of continuous uptime against an ~8-minute
idle window, and the foreground hold that is the only measured way to bridge that
gap was declined. **Zero Phase 5b cells exist**, verified against the observation
store: 0 of the 6 target states are present and the store equals the §6 design
exactly. The abandonment therefore cannot have been influenced by Phase 5b
results, because there are none. Full record in
`EXPERIMENT3_PHASE5B_ABANDONED.md`.

So this section describes the experiment's terminal state, not a temporary one.
The certified set is **not** uniform in effort: 23 of the 29 certified
candidates carry 40-restart verdicts, and 6 — every one of the states §6 never
triggered on, the leader among them — carry 20-restart verdicts. Anyone quoting the leader should quote this paragraph with
it. The remedy is scoped and ready to run unchanged: 30 cells, ~7 hours under a
foreground hold, manifest at `outputs/exp3/phase5b_manifest.json` and worker at
`scripts/exp3_phase5b_shard.sh`.

## 8. Disclosed post-hoc code changes

Both were made while results were visible. Both are bounded by demonstration,
not assertion — the machine-readable payload is byte-identical across each fix.

| | what | payload sha256 (16) | stdout delta |
|---|---|---|---|
| §8 classifier | required *all* 435 pairs to resolve; §8(1) is existential and per-candidate | `0598f5a526484568` unchanged | 1 line |
| Phase 5 label | inverted ternary printed a real demotion as "not certified → not certified" | `e419947d389376b2` unchanged | 1 line |

Full disclosures: `outputs/exp3/classifier_audit/CLASSIFIER_CORRECTION.md`,
`outputs/exp3/phase5_audit/LABEL_CORRECTION.md`. Original code and output are
preserved in both cases; no history was rewritten.

The project's standing rule — *analysis code edited while the numbers are
visible is analysis code shaped by the numbers* — applies to both. The defence
is not innocence; it is that the effect of each edit is fully observable and
bounded to one line of prose, with the payload digest unchanged.

---

### Provenance

| | |
|---|---|
| branch | `exp3-clean` |
| evaluation path | `src-bd82ac5a6dae` (`EVAL_PATH_FROZEN`) |
| Stage B contract | `ec7e566dc028f94d` |
| escalation contract | `45e23ae01be4d071` |
| Stage B cells | 200/200 |
| escalation cells | 170/170 |
| D33-B cells | 375 enumerations + 25 anchor solves |
| firewall refusals, all batches | 0 |

---

## 9. The freeze

Experiment 3 is frozen at tag **`exp3-final-v1`**.

| | |
|---|---|
| branch | `exp3-clean` |
| tag | `exp3-final-v1` |
| working tree at tag | clean, 0 uncommitted entries |
| verification at tag time | `exp3_verify_closure.py` 27 claims PASS; `exp3_freeze_integrity.py` 21 checks PASS |

Both suites are committed and re-runnable, and both read the observation stores
rather than any report — a report is what the pipeline said about the work; a
receipt is the work.

**The freeze does not assert a uniform effort regime, because there is not one.**
23 of the 29 certified candidates carry 40-restart verdicts and 6 — including
the leader — carry 20-restart verdicts. Phase 5b was designed to remove that
split and was abandoned before producing a cell
(`EXPERIMENT3_PHASE5B_ABANDONED.md`). Its manifest and worker are committed and
will run unchanged if anyone wants to close it later: 30 cells, ~7 hours under a
foreground container hold.

### What would move this result

In rough order of how much each could move it:

1. **Escalating the remaining six** — the only outstanding step inside the
   existing method. It can only cost the leader something; it cannot help it.
2. **A demand model that is not commute-only LODES.** 24.7% of regional flow is
   transit-accessible in the current input, and that is the largest unquantified
   error in the project.
3. **A differential-error measurement over more than 10 of 173 route-periods.**
   D33 bounds a neighbourhood, and the full-problem figure can only be larger.
4. **A cross-route hyperpath model.** 0.516% of generalized cost, deferred.

None of these is a defect in what was run. They are the edges of what a −0.19%
effect on a scalarized objective, certified against solver variance at one
effort, is entitled to claim — which is: this edit is distinguishable from the
solver's own noise, and nothing more.
