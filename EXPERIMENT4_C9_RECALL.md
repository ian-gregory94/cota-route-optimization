# C9 — proposal recall: **OPEN**

**2026-09-06. Experiment 4 not launched.** The blocker is new, it is not the one
anyone was watching, and it is not fixable by widening the promotion rule.

`outputs/exp4/c9_recall.json` · promotion rule `ec6288fc8ec9b7d0` ·
certification contract `5d4d3d0e1a2b...` (see receipt)

## What C9 now asks

D18 emitted no promotion band, so "identify the exact leader inside the band" is
not a test that can be run. Under the architecture the band's absence forced —
**discovery proposes, exact optimization decides** — exactly one question about
discovery still matters:

> Can proposal-only discovery discard a candidate that exact certification would
> have selected?

Agreement between discovery scores and certified scores is explicitly **not**
the criterion. D18 established they diverge structurally.

Criteria, fixed in the source before any recall number existed: the certified
winner is promoted in **100%** of cells (required), and recall of the certified
top-5 is at least **90%** across all cells (required).

## Method

On five reduced instances the complete candidate space was enumerated and
**every candidate exact-certified** — 112 candidates, 91 minutes, all converged
— to establish ground truth. The production discovery + promotion pipeline was
then run **independently**, with no access to that ground truth, and its
promoted set compared against the certified winner and frontier.

## Result

| cell | space | proposed | promoted | coverage | winner | top-5 recall |
|---|---|---|---|---|---|---|
| sparse_wide_pool | 21 | 18 | 18 | 86% | RETAINED | 100% |
| sparse_to_mid | 25 | 18 | 18 | 72% | **LOST** | 80% |
| dense | 16 | 13 | 13 | 81% | RETAINED | **40%** |
| many_off | 25 | 17 | 17 | 68% | **LOST** | **40%** |
| other_pool | 25 | 23 | 23 | 92% | RETAINED | 100% |
| **total** | **112** | **89** | **89** | **79%** | **3/5** | **worst 40%** |

**Certified winner retained in 3 of 5 cells.** Required: all.
**Worst top-5 recall 40%.** Required: ≥90%.

**C9: OPEN.**

## The diagnosis, and it is not what the design anticipated

Look at the `promoted` column. **The promotion rule promoted 89 of 89 proposals
— 100% in every single cell.** The cap never bound. The window never bound. The
policy was as permissive as a policy can possibly be: it certified everything it
was handed.

The failure is upstream of it. Gen2's discovery search **proposed only 79% of a
space small enough to enumerate entirely**, and the certified winner sat in the
missing 21% twice.

    the promotion frontier is bounded by discovery's proposal set,
    and no promotion rule can promote a candidate that was never proposed.

Both lost winners are the same network — `3lines#04ab844078de`, certified at
3,588,676.7800 — never scored by discovery in either cell it appears in.
`feasible_at_discovery` is `None`, not `False`: discovery did not reject it. It
never looked at it.

This is inherent to what Gen2 is. It is a local neighbourhood search — adds,
drops, swaps, paired adds — seeded at one point and terminating when no move
improves. It stopped after 13–23 evaluations against a `max_evaluations` of 400,
because it reached a local optimum, not because it ran out of budget. A local
search does not cover a space; it walks one basin of it.

## Why this is worse at Experiment 4 scale, not better

These cells have 16–25 candidates and can be enumerated on a laptop. The real
Experiment 4 space is subsets of a 206-line pool with roughly 40 active. A local
search that misses 21% of a 25-candidate space will visit a vanishingly small
fraction of that one, and there is no reason its coverage gaps would be
better-placed.

Proposal recall was correctly identified as the residual risk when gate 4-7 was
disposed of by architecture. It is now measured, and it does not hold.

## What must NOT be done about it

**Do not tune the promotion rule.** It is already at 100% promotion of
everything proposed; there is no slack in it to give. Widening the window, the
floor or the cap changes nothing, because none of them bound. A rule change
would also require, per the execution contract, a new preregistered revision and
a completely fresh validation suite — for an intervention that cannot work.

**Do not weaken the criterion.** "Winner retained in 3 of 5" is not a pass under
any reading of the recall question, and lowering the frontier threshold to fit
40% would be choosing a criterion after seeing the number it adjudicates.

**Do not launch.** The execution contract is explicit: Experiment 4 does not
launch until C9 is MET.

## What would fix it

The gap is in the **proposal generator**, and the architecture needs it to have
a coverage property that a pure local search does not have. Three routes, none
chosen here:

1. **Multi-start / restart discovery.** Run Gen2 from many deterministic seeds
   rather than one, so it walks many basins. Cheap — discovery is 11–24 seconds
   per cell against 4–25 minutes of certification — and it directly attacks the
   observed failure, which is basin confinement rather than budget exhaustion.
2. **Stratified structural sampling alongside the local search.** Add candidates
   by construction — every cardinality, every line represented, deterministic
   coverage of the structural dimensions D18 showed matter — so the frontier is
   not defined solely by where the search happened to walk.
3. **Enumerate the proposal space wherever it is tractable**, and treat local
   search as the fallback only where it is not. This is exact for the cells C9
   tests and gives a clean recall guarantee on them, but it does not scale to
   the real pool and so cannot be the whole answer.

(1) and (2) are complementary and both are cheap relative to certification,
which is where the compute actually goes: discovery cost **89 seconds total**
across all five cells against **91 minutes** of certification. There is a great
deal of room to make proposal more thorough before it becomes the bottleneck.

Any of them is a change to the pipeline and therefore, per the execution
contract, a new preregistered revision followed by a fresh validation suite.
That is the next decision, and it is not one to make inside a benchmark receipt.

## What the run also established

The architecture below the proposal stage works.

* **Certification is uniform and reproducible.** 112 candidates certified, every
  one converged to its `(8,3)`-block-local fixed point. The dense cell's winner
  certified to 3,587,974.7859 here and to the identical value in an independent
  earlier probe.
* **The recall failure is deterministic.** An independent re-run reproduced the
  `sparse_to_mid` loss exactly — same winner, same objective, same verdict.
  A flaky failure would have been much worse news than a repeatable one.
* **The inference boundary holds.** 29 boundary tests pass, including that a
  discovery score cannot be sorted, converted to float, or become a final rank,
  and that rewriting every discovery score after promotion changes no certified
  conclusion.

## Status

| item | state |
|---|---|
| D18 | MET — forbidding branch preserved, receipt byte-identical |
| C9 | **OPEN** — proposal recall fails: winner retained 3/5, worst frontier recall 40% |
| C15 | MANUAL — not silently closed |
| gate 4-7 | ARMED — non-operative for inference by architecture; the residual risk is the one C9 just failed |
| Experiment 4 | **NOT LAUNCHED** |

Readiness 21 MET · 1 OPEN · 1 MANUAL. Gates 10 MET · 5 ARMED · 0 OPEN.
693 tests pass; ALL CLAIMS VERIFIED; ALL INTEGRITY CHECKS PASS; GEN1 VERIFIED;
BASELINE VERIFIED.
