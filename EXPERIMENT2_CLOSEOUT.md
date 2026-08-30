# Experiment 2 and 2B — closed

**Closed 2026-08-30.** This is the consolidated conclusion. The reasoning behind
each claim is in `DISCOVERIES.md` (D16, D19–D24); the gates each result had to
clear are in `ACCEPTANCE.md`, all committed before the runs they judge.

---

## The question

> Holding COTA's operating envelope fixed at 2,517 weekday revenue
> vehicle-hours, does changing route geometry — through-routing pairs of
> existing routes at stops they already share — reduce passenger generalized
> cost beyond what frequency redistribution alone achieves?

## The answer

**No, and not marginally.**

> **Within this candidate space, no geometry intervention measurably helps, and
> every combination of them is worse than its best member.**

Twelve splice candidates, all 240 structurally feasible combinations of them,
frequency re-optimized on every network inside the same envelope, every plan
scored by one frozen Model B evaluator.

* **Six of the twelve candidates do measurable harm.** None does measurable
  good at the effort Experiment 1 is certified at.
* **The two best singles are inside the noise floor** when both they and the
  unedited baseline are solved to convergence: +0.060% and +0.160% against a
  0.287-point floor, where the baseline's own seed replicates span 9749.1 to
  9765.1 unserved.
* **Not one of the 227 multi-edit sets beats the best single** — not by the
  floor, at all — and **all 227 substitute**: every one delivers less than its
  members promised separately. There is no synergistic combination anywhere in
  the feasible space.
* **The certified leader is null**: +0.007% at full effort under three seeds,
  two hundredths of a floor.
* **The answer does not depend on the trade-off weight.** Re-solved at
  λ ∈ {1, 2, 4}, the same single edit leads at every weight, no multi-edit
  set beats it at any weight, and harm still rises monotonically with
  cardinality. At λ=1 every promoted set is outright harmful (+2.16% at best).
  One D22 claim does narrow: the universal substitution law holds at λ≥2 and
  inverts at λ=1, where the harm saturates instead of adding — see D25.

## What that means for COTA

Along the through-routing dimension this candidate generator explores, COTA's
route structure is **not leaving passenger benefit on the table** that a
vehicle-hour-neutral recombination could pick up. The binding constraint is the
budget, not the topology. Two splices cannot each have the whole envelope
reallocated to exploit them, and through-routing *consumes* budget as well as
competing for it — the merged line is longer, so hours that were buying
frequency go into running it.

This is a useful negative. It says the frequency result (Experiment 1,
**−6.65% unserved demand at no additional buses**) is the whole of what is
available conservatively, and it removes a plausible-sounding intervention from
the table with evidence rather than with an opinion.

## What Experiment 2 cost, and what it bought

Three results were withdrawn along the way. Each retraction is a finding.

| withdrawn | why | now |
|---|---|---|
| "the screen ranks candidates" | its first pick of sixty is the worst of twelve on evaluation | screens bound a pool; they never rank (D19) |
| "0.9% from through-routing 33+34" | the evaluator was Model A while reporting Model B | 0.5% under the correct model at ranking effort (D23) |
| "0.5% from through-routing 33+34" | the *unedited* network was the under-optimized one | 0.0% once both sides are solved to convergence (D24) |

The methodological residue is worth more than the geometry result would have
been:

* **A screen that holds frequency fixed cannot rank.** It rewards edits that
  make the network cheaper, and the cheapest edits are the ones that quietly
  drop demand (D19).
* **Edits do not compose, universally.** 227 sets, zero exceptions (D20, D22).
* **The waiting model changes the ranking.** Six of twelve candidates change
  sign between Model A and Model B; Spearman 0.657 (D23).
* **Matched effort is not enough — convergence must be matched.** Both sides ran
  at the same nominal effort and the same effort was not equally sufficient for
  both (D24, now gate 12).
* **An evaluator must state its own model, in the artifact.** A launcher log
  reporting the harness's setting is not evidence about the thing that did the
  scoring.

## What was not tested

* **Every edit kind that is not a splice.** Extends, truncates, straightens and
  reroutes took no top-ten slot at either end of the screen's bracket and were
  never evaluated. The negative result is about through-routing, not about
  geometry.
* **Anything outside one vehicle-hour envelope.** Every result here holds the
  budget fixed. A geometry change worth buying with *more* service is a
  different question and this says nothing about it.
* **Route structure rather than recombination.** These candidates join existing
  routes end to end. They do not reshape a route. That is Experiment 3.

## Certification status

| result | effort | certified |
|---|---|---|
| six candidates measurably harmful | 400,000/20, 3 replicates | **yes** |
| no candidate measurably beneficial | 400,000/20, 3 replicates | **yes** |
| no multi-edit set beats the best single | 60,000/2/32, exhaustive | discovery-stage (gate 12) |
| every multi-edit set substitutes | 60,000/2/32, exhaustive | discovery-stage (gate 12); λ≥2 only |
| the leader is the same at λ ∈ {1,2,4} | 60,000/2/32, 16 promoted sets | discovery-stage, single seed |
| the leader is null at full effort | 400,000/20, 3 seeds | **yes** |

The two exhaustive claims are discovery-stage by gate 12 and are quoted as
orderings rather than magnitudes. They do not need certifying to support the
conclusion: the conclusion rests on the certified rows, and the sweep's role is
to establish that no *combination* rescues what the singles could not.

## Gate verdicts

| gate | verdict |
|---|---|
| 2B-1 enumeration is complete, not sampled | **PASS** — 240 of 240, `exp2b_stageA_gaps.json` reports zero missing |
| 2B-2 nothing ranked by anything but its own measured score | PASS |
| 2B-3 cardinality winners reported non-nested | **PASS** — and they are not nested |
| 2B-4 headline clears the floor at its own effort | PASS — nothing cleared it, which is the result |
| 2B-5 only the headline certified | PASS |
| 2B-6 interaction measured for every set | PASS — 227 of 227 at λ=2, and for every computable multi-edit row at λ=1 and λ=4 |
| 2B-7 the incumbent may win | **PASS** — it did, and the null was named as expected beforehand |
| 2B-8 the sweep reproduces the ladder | **PASS** — 0.0004, 0.0001, 0.0002 points |
| 9 legible as a transit proposal | PASS on both leading candidates; moot, there is no effect to implement |
| 12 convergence matched, not just effort | **PASS** — and it fired automatically on the stage C leader |

## Artifacts

Canonical, per `outputs/CANONICAL_RESULTS.json`:

* `outputs/exp2_promotion.json` — the promotion decision, and why nothing was promoted
* `outputs/exp2b_certification.json` — the stage C verdict
* `outputs/exp2b_stageA.csv` — all 240 subsets
* `outputs/exp2b_stageB.csv` — the 16 promoted sets at λ ∈ {1, 2, 4}
* `outputs/exp2_candidate_classes.json` — the twelve, classified
* `outputs/exp2_ladder_measured.csv` — both ladder orderings
* `outputs/exp2_treatments.jsonl` — the thirteen-network representation frontier
* `outputs/exp2_summary.json` — every number above, assembled from the artifacts

Superseded artifacts are listed in `outputs/SUPERSEDED.md`. None is deleted; a
superseded artifact here looks entirely legitimate from the inside, which is the
point of listing them.

---

**Experiment 2 is closed.** Experiment 3 begins from `pre_exp3_baseline_v1`,
whose conservative incumbent is Experiment 1's certified frequency result on
COTA's **unchanged** geometry — because Experiment 2 promoted nothing.
