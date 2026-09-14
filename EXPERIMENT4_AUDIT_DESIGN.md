# Experiment 4 out-of-band certification audit — design, frozen before execution

**Frozen 2026-09-14, before any audit candidate was certified.** Authorised by
Ian in-session. Sample digest `00676a1c26792297`.

## The question

> **Does discovery provide useful population-level enrichment even though it
> does not provide useful ordinal ranking inside the promoted band?**

D36 established that inside the promoted top 200, discovery rank
*anti*-correlates with certified rank (Spearman −0.3361) and that the certified
winner sat at discovery rank 196 of 200. That is a statement about **ordering
within a band whose discovery scores span 0.159%**. It says nothing about
whether the band itself was worth selecting.

Those are different claims and this project has repeatedly been burned by
letting one stand in for the other. A ruler can be useless for ordering two
adjacent objects and still be correct that one pile is taller than another.

## What is being tested, precisely

Experiment 4 certified the top 200 of 2000 proposals by discovery score. The
remaining 1800 were never certified. This audit certifies **200 of those 1800**,
drawn by stratified random sample, under the **identical pipeline**, and asks
whether their exact objectives are drawn from the same distribution as the
promoted 200 or a worse one.

**This is not a search for a better winner.** If one turns up, that is a
finding about the cap, not a new leader — the audit sample is not the
population and 1600 proposals remain uncertified either way.

## The incumbent is not touched

```
exp4|exp4-pool-v1|65lines#ecb2ffc4bcce
objective_EXACT  3,511,184.5657525407
```

The Exp 4 result stands as committed. This audit writes to
`outputs/exp4_audit/` and touches nothing under `outputs/exp4/run/`. Exp 4
history is not rewritten.

## Sample design

**Seed `20260914`.** Per-stratum RNG seeded from the string
`f"{AUDIT_SEED}|{lo}|{hi}|{n}"`, sampling band **indices** (not objects) with
`random.Random.sample`, then sorted. Seeding per stratum means a stratum can be
regenerated independently and adding one later cannot perturb an existing one.

**Discovery ranking** is ascending `objective_APPROXIMATE`, ties broken by
`state_key` ascending. This was **verified to reproduce the Exp 4 certified set
exactly at ranks 1–200** before sampling — the audit's rank axis and the run's
promotion decision are the same axis.

| stratum | band size | sampled | fraction | discovery score range |
|---|---|---|---|---|
| 201–400 | 200 | 40 | 20.0% | 3,624,534 – 3,626,015 |
| 401–800 | 400 | 40 | 10.0% | 3,626,022 – 3,628,060 |
| 801–1200 | 400 | 40 | 10.0% | 3,628,061 – 3,629,277 |
| 1201–1600 | 400 | 40 | 10.0% | 3,629,280 – 3,632,338 |
| 1601–2000 | 400 | 40 | 10.0% | 3,632,342 – 3,637,228 |

**Sampling fractions are NOT equal** — 20% in the first stratum, 10% in the
other four. Equal *n* per stratum buys within-stratum power; it means an
unweighted pool over-represents ranks 201–400 by 2×. **Every population-level
statistic in the analysis must be reported stratum-weighted**, and the
unweighted figure reported alongside it where they differ.

**No substitution, on any grounds, including apparent quality.** The frozen list
is `outputs/exp4_audit/audit_sample.json`. All 200 selected are `feasible:true`
(195 at 65 lines, 5 at 64), and none overlaps the Exp 4 certified set —
asserted at generation time.

## Method — the same pipeline, unchanged

`scripts/exp4_audit_launch.py` reproduces the certify loop of
`scripts/exp4_launch.py` verbatim, differing **only** in where the candidate
list comes from (the frozen sample instead of `promote()`) and where results are
written (`outputs/exp4_audit/certified/`).

Identical: `LAM = 2.0`, `SEED = 20260825`, `POOL_VERSION`, `MIN_LAYOVER_SEC`,
the canonical envelope (`b6c647d3766338a6`), `ContractLimits`, the same
`assemble(...)` call, the same `certify(...)` call under
`CERTIFICATION_DIGEST`, the same per-candidate try/except that records an error
payload and continues, the same write-the-instant-it-exists (OPERATIONS 31),
the same resume-by-file-existence, and the same shard bound checked at the
**top** of each candidate. `src/cota_opt` is not modified.

Expected cost ~36 h at the Exp 4 mean of 652 s per candidate.

## Preregistered analysis — computed on the complete audit set, not before

1. Best exact objective in the audit, and its difference versus the incumbent.
2. Distribution of audit exact objectives versus the promoted 200: min, quartiles,
   median, max, and the two distributions plotted against each other.
3. Discovery-rank vs certified-rank correlation **within the audit sample**.
4. Discovery-score vs exact-objective relationship (the D36 mechanism, re-measured
   out of band).
5. Discovery error / overstatement behaviour: range, and its correlation with the
   exact objective.
6. Count and percentage of audit candidates beating the promoted-200 **median**.
7. Count beating the promoted-200 **top quartile**.
8. Count beating the **incumbent**.
9. All of the above **broken out by each of the five strata**, and a test for
   monotonicity across strata.
10. Convergence-rounds behaviour, as a check on whether D37's threshold holds
    out of band.

Stratum-weighted and unweighted pooled figures both reported wherever they
differ.

## Preregistered decision gate

Written before any result exists, so that the outcome cannot select the rule.

* **STOP.** If the audit distribution is clearly worse than the promoted 200 and
  no audit candidate approaches the incumbent → recommend **not** certifying the
  remaining 1800. Discovery's band selection was doing real work even though its
  ordering inside the band was inverted.
* **SECOND AUDIT.** If the distributions **overlap materially** → recommend a
  larger second audit before any full certification. Do not jump to 1800 on an
  ambiguous 200.
* **CAP INVALID.** If an out-of-band candidate **beats the incumbent**, *or* the
  lower strata show equal-or-better exact performance than the higher ones →
  flag the 200-cap as invalid and recommend expanding certification
  substantially, up to the full remaining pool.

**Under no outcome does the full ~326 h certification start automatically.**
The audit stops after analysis and reports for a decision.

## What this design cannot answer

* **It cannot clear the remaining 1600.** 200 of 1800 is an 11.1% sample. A
  stratified sample bounds the *population* behaviour it was drawn from; it does
  not certify any individual candidate it did not include.
* **It cannot rescue a global-optimality claim.** The `(N,K)`-block-local
  guarantee is local and its residual is unmeasured, out of band exactly as in
  band.
* **It cannot say anything about the fleet question.** Deadhead provenance is
  OPEN, terminal identity is degenerate on synthesised candidates, and every
  audit candidate will return `UNDECIDABLE` for the same reasons all 200 Exp 4
  candidates did. Fleet is REPORTED, NOT GATED here too.
* **It cannot distinguish "discovery selected a good band" from "the pool is
  flat".** If the audit distribution matches the promoted 200, that is
  consistent with discovery adding nothing *and* with the whole 2000-proposal
  pool being near-uniform in exact objective. Separating those needs a
  comparison the 2000-proposal pool cannot supply on its own, and the closeout
  must say so rather than pick the flattering reading.
