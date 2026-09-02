# D33 at Stage B effort — design, frozen before any gap is measured

Preregistration §7 requires the differential-error diagnostic to be
**re-measured at Stage B effort** on a subset of the promoted states, because
D33's discovery-effort figure does not transfer. This document fixes the design.
It is committed before a single Stage B-effort gap is computed.

D33 is a **veto**. It can refuse a margin; it can never *establish* one, and it
is never added to the certification threshold. That is unchanged here.

## What is being re-measured, and what is not

D33's method is unchanged and is not re-derived: all but *N* of 173
route-periods are pinned to a one-rung ladder, the free ones keep *K*=3 rungs
centred on a delivered plan, and **every** one of the 3^N combinations is priced
with the real production evaluator. The exact reference is therefore exact by
construction and carries **no effort parameter at all** — enumeration does not
get better with more search. The relationship between benchmark objective and
production objective is identity.

**Exactly one thing changes: the anchor.** At discovery effort the delivered
plan came from a 2-restart, width-32 solve on a single seed. At Stage B effort
it comes from the frozen Stage B configuration — 20 restarts, evaluation ceiling
400,000, full candidate width, `StartPolicy.BOTH` — on each of the five
predeclared Stage B seeds. A harder-solved plan should sit closer to its
neighbourhood optimum, so the Stage B gap is expected to be **smaller** than the
discovery-effort gap. That expectation is stated now so that finding the
opposite is a result and not a surprise to be explained away.

## The anchor is verified, not assumed

Stage B receipts store `plan_digest` but not the plan. The anchor is therefore
reproduced by re-running `run_cell` under the frozen `EXP3_STAGE_B` contract for
that exact `(state, seed)`, and then:

> **`digest(reproduced_plan)` MUST equal the stored receipt's `plan_digest`.**
> A mismatch is a reproducibility failure, not a nuisance. On any mismatch the
> run stops, nothing is reported, and the mismatch is escalated to Ian.

This makes the re-measurement double as an independent reproducibility check of
Stage B, which Phase 9 requires anyway. It also means the anchor is not a
re-solve that resembles the Stage B answer — it is provably the Stage B answer.

## The subset — declared, and deliberately adversarial

§7 says "a subset of the promoted states". Five networks, preserving D33's own
control + two-lengthening + two-shortening shape so the two measurements are
comparable, but with **every treatment pinned to an actual Stage B state** so
its plan digest can be verified:

| role | state | Stage B effect | why this one |
|---|---|---|---|
| control | `<none>` | — | the reference arm |
| lengthen | `add_stop-010#22c4c35ac5b2` | −0.1866% | **the leader**; the headline margin |
| lengthen | `extend-025#441ece050fe8` | −0.0767% | D33's original `lengthen_extend`, keeps continuity |
| shorten | `truncate-035#7cdb09a45253` | −0.1371% | largest shortening margin |
| shorten | `straighten-021#110f4a755fe7` | −0.0078% | **the smallest certified margin** — the most veto-vulnerable claim in the whole set |

**This subset is chosen after the Stage B results were visible**, and that is
disclosed rather than hidden. The selection rule is adversarial by construction:
it includes the single margin most likely to be vetoed and the single margin the
experiment most wants to keep. A subset chosen to make a veto *more* likely
cannot manufacture a pass. If the smallest certified margin survives this, every
larger one does too.

* **Strata:** all five — `peak`, `offpeak`, `common_lines`, `weak_interaction`,
  `seeded_random`. Not narrowed to where D33 found error, because a benchmark
  that samples only the interesting strata reports a number that means nothing
  about the rest.
* **Sizes:** *N* ∈ {6, 8, 10}, unchanged. D33 found the three sizes gave almost
  the same answer; keeping all three preserves that check rather than assuming
  it still holds.
* **Seeds:** all five Stage B seeds. D33 used one. Five is what Stage B's
  estimand requires, and it is what makes the differential *paired*.

Cells: 5 networks × 5 seeds × 5 strata × 3 sizes = **375 enumerations**, on top
of **25 Stage B-effort anchor solves**. The enumerations are cheap — D33
measured N=8 at 0.6 s median and N=10 at 5.6 s — so essentially all the cost is
the 25 anchor solves.

## The statistic

The quantity that matters is the one D33's Q3 asked, now paired on seed exactly
as Stage B pairs:

```
gap(net, seed, stratum, N)  = delivered_objective − exact_objective        (≥ 0)
differential(t, seed, ...)  = gap(control, seed, ...) − gap(t, seed, ...)
```

`differential` is the part of a measured treatment effect that could be an
artifact of the two arms sitting different distances from their own optima. A
generic mean or maximum gap is **not** an effect floor and none is emitted.

Reported: per-treatment max |differential| and the distribution across strata
and sizes, plus the same by seed.

## The veto rule — fixed now, applied without discretion later

For each certified candidate *c* with Stage B margin |mean Δ(c)|:

> **VETO(c) ⟺ max over the measured cells of |differential| for that treatment
> ≥ |mean Δ(c)|.**

That is, a margin is vetoed when the treatment-correlated solver error measured
here is **comparable to or larger than** the margin itself. Comparable is
operationalised as *greater than or equal to*, with no safety multiplier in
either direction, because inventing a multiplier now would be inventing a
threshold and §7 forbids D33 from becoming one.

A candidate not measured directly is judged against the **largest**
|differential| observed across all measured treatments — the conservative
choice, since nothing licenses assuming an unmeasured treatment is better
behaved than the worst measured one.

**A veto is not a demotion to "uncertified".** The candidate remains certified
against solver *variance* by the §4 criterion; the veto says its margin is not
*reportable* because it is not distinguishable from solver *error*. Both facts
get stated wherever the result appears.

If any veto fires: closure work stops, the §6 escalation does **not** run, the
Stage B leader is preserved as an observed result, Experiment 3 is marked
**not certified / vetoed by D33**, and a diagnostic report is produced.
**D33 is not modified after seeing the failure.**

## What this still cannot establish

Unchanged from D33's Q4, and it must be restated wherever the figure is quoted:
this is a **local** optimality check over a neighbourhood of at most 10 of 173
route-periods across three ladder rungs. It is a *lower* bound on the
differential-error bound; the full-problem differential can only be larger. A
margin above it is **not thereby established** — it is only *not excluded* by
this measurement, which is a much weaker statement.
