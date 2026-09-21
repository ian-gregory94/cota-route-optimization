# Experiment 4 out-of-band audit — closeout

**Stopped by decision at 15 of 200 certified, 2026-09-21.** Ian ended the audit
rather than spend the remaining ~37 h. This document reports what was obtained,
what it supports, and — at greater length — what it does not.

The preregistered design is `EXPERIMENT4_AUDIT_DESIGN.md`, frozen 2026-09-14
before any candidate was certified. It is not amended here. This closeout
reports against it and marks each preregistered item answered or unanswered.

---

## 1. What ran

| | |
|---|---|
| certified | **15 of 200** |
| errors | 0 |
| `PathsetScopeViolation` | 0 |
| empty-scope `CertificationError` | 0 |
| non-converged | 0 |
| compute | 3.00 h (mean 720 s, range 516–892 s) |
| wall-clock elapsed | 7 days |
| candidates beating the incumbent | **1** |

Pipeline unchanged from Exp 4 throughout: same `LAM`, `SEED`, pool version,
envelope digest, `assemble`, `certify`, contract digest, error handling and
resume semantics. `src/cota_opt` was not touched. The frozen sample was not
re-seeded, reordered or substituted. `outputs/exp4/run/` was not modified and
Exp 4 history was not rewritten.

The 3 h of compute sits inside 7 days of wall clock because of two outages,
neither of them a pipeline failure: a 30-hour keeper-chain lapse on 14–15 Sep,
and a six-day period from 15–21 Sep in which the keeper beats fired on schedule
and queued while the container stayed reclaimed and the session never resumed.
Both are recorded in `EXPERIMENT4_AUDIT_BEAT.md`.

## 2. The finding that survives: the 200-cap was invalid

One of the 15 beats the Exp 4 incumbent.

```
state_key        exp4|exp4-pool-v1|65lines#eca7a2a1fb46
discovery rank   237 of 2000   (excluded by the top-200 promotion cap)
objective_EXACT  3,510,666.7802095017
incumbent        3,511,184.5657525407
difference       517.7855  =  0.014747% better
rounds           12, converged
```

Recomputed against the completed promoted 200, it inserts at **exact rank 1 of
201**. Full record in `EXPERIMENT4_AUDIT_INCUMBENT_BEATEN.md`.

This is an **existence claim**, and existence claims are immune to the sampling
problems that disable everything in §4. It does not matter how the 15 were
drawn: a candidate outside the promoted band certifies better than every
candidate inside it. Therefore selecting the top 200 by discovery score did not
capture the best candidate available in the 2000-proposal pool.

**Decision-gate outcome: branch three — CAP INVALID**, on its literal
preregistered trigger ("if an out-of-band candidate beats the incumbent").

The margin is 0.0147%, which is operationally nothing. That is not the point and
should not be reported as if it were. For scale: the promoted 200 spanned
2.2788% best-to-worst, the Exp 4 leader beat its runner-up by 0.0106%, and the
top nine sat within 0.18%. The finding is about the **selection rule**, not
about having found a better network.

Why the rule failed is visible in one comparison. The candidate's discovery
score missed the rank-200 cut by **0.002932%** of the cut score, while its own
discovery overstatement was **3.2463%** of its exact objective. Promotion was
decided by a quantity roughly **1,100× smaller than the error in that
quantity**. A cap drawn on that axis is a coin flip dressed as a ranking.

## 3. The preregistered question: UNANSWERED

> **Does discovery provide useful population-level enrichment even though it
> does not provide useful ordinal ranking inside the promoted band?**

**This audit does not answer it, and nothing in the 15 results should be read as
answering it.** The reason is structural, not a matter of degree.

The audit certifies the frozen sample **in discovery-rank order**. Stopping
early therefore does not yield a small random sample; it yields a prefix that is
biased at two levels:

1. **Stratum coverage.** All 15 fall in stratum 201–400. Strata 401–800,
   801–1200, 1201–1600 and 1601–2000 have **zero** certified candidates. The
   design's central comparison is across strata; four of the five are empty.
2. **Within the stratum.** The 15 are not 15 of the 40 frozen stratum-1 picks
   drawn at random. They are the **15 lowest-ranked of those 40**, spanning
   discovery ranks 201–261 out of a band running to 399 — the top ~31% of the
   band by discovery score.

Every population-level statement the design asked for requires either the
cross-stratum contrast or an unbiased within-stratum draw. Neither exists.
A larger prefix would not have fixed this; only completing the strata, or
re-ordering the run to interleave them, would have.

### Preregistered analysis items, one by one

| # | item | status |
|---|---|---|
| 1 | best exact objective, difference vs incumbent | **answered** — §2 |
| 2 | audit distribution vs promoted 200 | **unanswered** — biased prefix |
| 3 | discovery-rank vs certified-rank within the audit | **not usable** — see §5 |
| 4 | discovery-score vs exact-objective relationship | **answered, and it reframes D36** — §5 |
| 5 | overstatement behaviour and its correlation with exact | **answered** — §5 |
| 6 | count beating the promoted-200 median | **unanswered as a rate** — §4 |
| 7 | count beating the promoted-200 top quartile | **unanswered as a rate** — §4 |
| 8 | count beating the incumbent | **answered as existence, not as a rate** — §2 |
| 9 | all of the above by stratum, and monotonicity | **unanswered** — four strata empty |
| 10 | convergence-rounds behaviour vs D37 | **not usable** — n=15, one candidate at ≤8 rounds |

## 4. Descriptive statistics of the 15 — these are not estimates of anything

Reported because hiding obtained data is worse than reporting it with its
defects named. **None of these numbers is an estimate of a population
quantity.** They describe fifteen specific candidates drawn from the top third
of the best stratum, and they will be biased *optimistic* relative to the
out-of-band pool for exactly that reason.

| | value |
|---|---|
| best | 3,510,666.7802 |
| median | 3,552,238.6069 |
| worst | 3,571,345.1003 |
| spread | 1.7284% |
| beating the promoted-200 median (3,538,297.7479) | 6 of 15 |
| beating the promoted-200 top quartile (3,525,259.2912) | 2 of 15 |
| beating the incumbent (3,511,184.5658) | 1 of 15 |

**Do not turn "6 of 15" into 40%.** The denominator is a biased draw and the
numerator inherits the bias. The honest reading is: *among fifteen candidates
selected to be the best-looking of the excluded ones, some certify competitively
with the promoted set.* That is consistent with discovery enriching weakly, with
discovery not enriching at all, and with the pool being near-uniform. The design
anticipated precisely this ambiguity and forbade picking the flattering reading.

## 5. What the 15 DO establish: discovery scores are flat, and D36's mechanism is largely arithmetic

This is the substantive result of the audit, and it does not depend on the
sampling defect, because it is a relationship between two quantities measured on
the same candidates rather than a claim about a population.

Across the 15:

```
spearman(exact objective, overstatement)   = -1.0000     [Exp 4 in-band: -0.9930]
discovery-score span across the 15         =  0.00771%
exact-objective span across the same 15    =  1.72840%   -> 224x wider
overstatement range                        =  1.4967% - 3.2463%
```

A **perfect** rank inversion. Range restriction — which selecting on discovery
rank imposes — normally *attenuates* a correlation, so obtaining −1.0000 under
it is stronger evidence rather than weaker.

But the interpretation is the opposite of impressive, and this is the point:

> `objective_APPROXIMATE` is very nearly **constant** across these candidates —
> it varies by 0.0077% while the exact objective varies by 1.7284%. When the
> approximate score is effectively a constant, overstatement
> `(approx − exact)/exact` is a strictly decreasing function of `exact`, so a
> Spearman of −1 is close to **arithmetically forced**. It is not independent
> evidence that discovery "knows" anything, inverted or otherwise.

**This reframes D36.** D36 reported spearman(exact, overstatement) = −0.9930
inside the promoted 200 and treated it as the mechanism behind discovery's
inverted ranking. In band, the discovery span was 0.15891% against an exact span
of 2.2788% — a ratio of 14×, less extreme than the 224× here but the same
structure. So a large part of that −0.9930 was also implied by discovery scores
being nearly flat, not by discovery carrying inverted information.

The corrected statement is simpler and worse for the architecture: **across this
region of the proposal pool, `objective_APPROXIMATE` carries almost no
information about `objective_EXACT`.** It is not an inverted ranker. It is close
to a constant with noise, and the "inversion" is what a constant looks like when
you correlate its residual against the truth.

Filed as **D38**.

### Two correlations that are NOT usable

`spearman(discovery rank, certified rank) = +0.2857` within the 15, against
−0.3361 in band. Sign flipped — and it means nothing. n=15, biased selection,
and the discovery scores being ranked span 0.0077%. This is noise being ranked.
It neither confirms nor contradicts D36.

`rounds` behaviour likewise: exactly one of the 15 converged in ≤8 rounds, so
D37's threshold claim cannot be checked out of band. The bucket is far below the
~20-member floor this project adopted after the Exp 4 enrichment tables had to
be retracted.

## 6. Retractions

Three, all from interim reports during the run. Numbers were recomputed at n=15;
so were the claims.

1. **"Throughput is running at ~54% efficiency, ~86 h for the rest."**
   Wrong. Built on three results and three container reclaims — the exact error
   this project had already named ("do not build a rate out of a few events").
   Measured over the 15 Sep window: 12 results in 136 minutes against a
   12.0-minute mean compute per candidate. Efficiency is effectively 100% while
   the container is alive. Outages are the cost, not throughput.

2. **"The full certification is really 700–900 h, not ~326 h."**
   Wrong, and it followed from (1). At the audit's 720 s mean, 1800 candidates is
   **360 h**; at Exp 4's 652 s mean it is **326 h**. The original ~326 h estimate
   was right.

3. **"Audit per-candidate compute is all above the entire Exp 4 range."**
   True of the first three results, false by the fifteenth. The audit minimum is
   516 s, inside Exp 4's 413–735 s. Final audit spread 516–892 s, mean 720 s
   against Exp 4's mean of 652 s.

## 7. What is still open, and what should not be claimed

- **The remaining 1,785 out-of-band proposals are uncertified.** Nothing here
  certifies, bounds or clears any of them individually.
- **No fleet or deployability claim is made or implied.** Every audit candidate
  returns `UNDECIDABLE` for the same reasons all 200 Exp 4 candidates did:
  deadhead provenance is OPEN and terminal identity is degenerate on synthesised
  candidates (D24). Fleet is REPORTED, NOT GATED.
- **No global-optimality claim.** The `(N,K)`-block-local guarantee is local, its
  residual is unmeasured, and that is as true out of band as in band.
- **"Discovery does not enrich" is NOT established.** §5 shows discovery scores
  are nearly flat *in the region sampled* — ranks 201–261 of 2000. Flatness over
  a 61-rank window is not flatness over the pool. Strata 401–2000 were never
  touched and could behave differently.
- **"The pool is uniform in exact objective" is NOT established** either, and is
  the alternative the design flagged as indistinguishable from the above on this
  evidence.

## 8. Recommendation

**Do not start the ~326–360 h full certification.** Not because the cap is
valid — it is not — but because the axis the expansion would be organised around
has just been shown to carry almost no information in the only region measured.
Certifying 1,800 more candidates on a discovery ranking that is near-constant is
paying 326 hours to sample the pool in an arbitrary order.

**Do not run a second audit of this design either.** The design's failure was
not its size. It was that a rank-ordered execution makes every partial result
unanalysable, and that it tests a selector whose scores turn out not to vary
enough to select on. Any successor should (a) interleave strata so partial
results stay balanced, and (b) begin by measuring the variance of
`objective_APPROXIMATE` across the pool, because if that variance is small
everywhere, the discovery-proposes architecture has no ranking signal to offer
and the question is not worth 326 hours to answer.

That is the finding worth carrying into Experiment 5.
