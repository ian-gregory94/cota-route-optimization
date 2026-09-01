# Decision — same-run replicate spread estimates solver *variance*, not solver *error*

**Date** 2026-08-31 · **Status** adopted · **Generation** gen1
**Supersedes** the use of 3σ of zero-edit replicate spread as a materiality
threshold (gate 3-3 as originally written, and the 0.039% floor quoted in the
superseded Phase A1 census).

## The correction

Same-run replicate spread measures how much an answer moves when the seed
moves. That is **solver variance**. Materiality asks something else: how large a
difference can be attributed to the treatment rather than to the optimizer being
imperfect. That is **solver error**, and variance has never bounded it.

The two are usually confused because they are usually correlated — a noisy
solver is normally an inaccurate one, so its spread is a rough stand-in for its
error. The confusion becomes visible when they come apart.

**When the pipeline is deterministic, replicate spread is exactly zero and
bounds nothing at all.**

## How that happened here

Under `starts="both"` at 60000/2/32 the discovery pipeline is deterministic:

* `_greedy_build` takes no RNG;
* `starts="both"` selects greedy on every state measured (8/8 in D30, 4/4 in the
  re-score control);
* the perturbation restarts *are* seeded, but at two restarts they never escape
  greedy's basin, so the seed never reaches the answer.

Three replicates at three seeds therefore return bit-identical objectives, and
3σ of that is `0.00000%` (D32).

## What is not concluded from it

A zero spread is **not** evidence of precision, and must never be reported as a
0% floor. Determinism is not accuracy. A heuristic sitting 0.5% from optimum on
one geometry and 0.1% on another produces a 0.4% "effect" that is pure solver
artifact and reproduces perfectly at every seed.

The observed fact is preserved and labelled for what it is: **solver variance
only, measured as exactly zero at discovery effort.** The discovery same-run
floor is recorded as **undefined for materiality purposes** — not as zero.

## What replaces it

Nothing, yet, and deliberately nothing. The corrected Phase A1 census is
**descriptive only**: signed effect and magnitude for every state, normal
ranking, and no `clears_floor`, significance, or materiality-pass column of any
kind.

The threshold will come from an optimization-gap benchmark against exact or
bounded reference solutions, which measures error rather than variance. That
benchmark must answer four questions, and until the fourth is answered it
supplies no threshold:

1. the absolute heuristic gap against an exact/bounded reference;
2. the distribution of that gap across geometries;
3. whether the gap changes **systematically between control and treatment**;
4. therefore the magnitude of treatment effect distinguishable from
   treatment-correlated solver error.

**A generic mean or maximum optimization gap is not an effect floor.** What
matters is the error in the *difference* between treatment and control: if both
arms are 0.4% from optimum in the same direction, the difference is clean; if
one is 0.4% off and the other 0.1%, a 0.3% artifact is available. Only (3) and
(4) settle that, so no threshold is derived from (1) or (2) alone.

## Explicitly not done

**Randomised greedy tie-breaking is not implemented as part of this
remediation.** It would restore a non-zero replicate spread, and that spread
would measure something real — sensitivity to arbitrary solver choices. But it
changes the algorithm mid-remediation, and more importantly it would answer a
different question than the one at hand: it measures how much the answer depends
on solver choices, not how far the answer is from the truth. Logged as a later
solver-method experiment.

## Consequences

* Gate 3-3's replicate-spread threshold is withdrawn for the corrected census.
* The 0.039% floor in the superseded A1 census is not carried forward; it was
  measured on the contaminated path, where the seed reached the answer only
  because the incumbent start did.
* The 0.00657% certification-effort spread is **not** substituted. It is a
  different effort and cannot judge discovery-effort comparisons.
* Materiality classifications will be added to the census retrospectively, once
  the benchmark supplies a differential-error bound. The descriptive artifact is
  kept intact and the classified version derived from it, so provenance stays
  legible.
