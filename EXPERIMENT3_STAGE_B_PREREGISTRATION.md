# Experiment 3 Stage B — certification, preregistered

**Written before any Stage B cell was run.** Frozen at the commit that adds it.
Stage A's corrected census is frozen at `exp3-frozen-v1` / source
`src-74b02d24b77f`, verified by `FREEZE_MANIFEST.json`.

Stage A was descriptive. It ranked 84 single mutations against the control and
established nothing about whether any of them is materially beneficial. Stage B
asks that question and is allowed to answer **no**.

---

## 1. The promotion set

**All 39 corrected-negative mutations.** Not a band around the leader — the
band would have to be drawn with a floor, and Stage A has no floor to draw it
with (D32, and `decisions/2026-08-31-replicate-spread-is-not-a-materiality-floor.md`).
Every state whose corrected effect is negative goes forward, and the analysis
decides.

Span: **−0.1888%** to **−0.0005%**. By kind: 10 `straighten`, 8 `add_stop`,
8 `truncate`, 5 `reroute`, 4 `extend`, 4 `change_terminal`. No `splice`, no
`split` — both were positive throughout.

| # | state | kind | Stage A effect |
|---|---|---|---|
| 1 | `add_stop-010#22c4c35ac5b2` | add_stop | -0.1888% |
| 2 | `reroute-031#dfd049714f7d` | reroute | -0.1594% |
| 3 | `truncate-035#7cdb09a45253` | truncate | -0.1394% |
| 4 | `truncate-025#d3209fe02367` | truncate | -0.1340% |
| 5 | `truncate-101#3d4f770cd393` | truncate | -0.0988% |
| 6 | `straighten-102#4dd646541565` | straighten | -0.0830% |
| 7 | `extend-025#441ece050fe8` | extend | -0.0701% |
| 8 | `straighten-025#f0732765f122` | straighten | -0.0699% |
| 9 | `truncate-007#e0327cd10f50` | truncate | -0.0670% |
| 10 | `add_stop-007#02161399a599` | add_stop | -0.0582% |
| 11 | `straighten-024#6a687792ef0b` | straighten | -0.0475% |
| 12 | `straighten-011#f2a996066a3d` | straighten | -0.0446% |
| 13 | `truncate-007#a14f6e0894dd` | truncate | -0.0434% |
| 14 | `straighten-007#830e388b3427` | straighten | -0.0432% |
| 15 | `truncate-032#00b89519f00f` | truncate | -0.0394% |
| 16 | `add_stop-033#273b2cd43dfd` | add_stop | -0.0392% |
| 17 | `change_terminal-007-EMO4THW#16606ceb331e` | change_terminal | -0.0345% |
| 18 | `straighten-004#600ca164ad60` | straighten | -0.0288% |
| 19 | `extend-024#26db14321a47` | extend | -0.0273% |
| 20 | `extend-032#228795f35539` | extend | -0.0265% |
| 21 | `reroute-006#dbfb2f9ee60d` | reroute | -0.0259% |
| 22 | `change_terminal-101-EMO4THW#56a30c84c920` | change_terminal | -0.0225% |
| 23 | `straighten-031#d0ecad5fc231` | straighten | -0.0200% |
| 24 | `add_stop-006#9aecfd5100eb` | add_stop | -0.0176% |
| 25 | `add_stop-004#27407b151153` | add_stop | -0.0174% |
| 26 | `reroute-023#1dc299b50907` | reroute | -0.0166% |
| 27 | `truncate-012#584263ee6bf8` | truncate | -0.0165% |
| 28 | `truncate-023#3ef9178c6974` | truncate | -0.0157% |
| 29 | `change_terminal-141-STAHIGW#b5ce9b1e03b5` | change_terminal | -0.0125% |
| 30 | `straighten-021#110f4a755fe7` | straighten | -0.0101% |
| 31 | `add_stop-008#f178c37040f5` | add_stop | -0.0082% |
| 32 | `change_terminal-023-EASHAMN#357bdf4fa511` | change_terminal | -0.0070% |
| 33 | `straighten-001#95a4287b6fa0` | straighten | -0.0070% |
| 34 | `reroute-012#fb24f651cbc5` | reroute | -0.0068% |
| 35 | `straighten-002#716a0b294c2c` | straighten | -0.0065% |
| 36 | `add_stop-102#78da77548338` | add_stop | -0.0054% |
| 37 | `reroute-009#8323c2fb0368` | reroute | -0.0052% |
| 38 | `extend-023#292a06c5a525` | extend | -0.0034% |
| 39 | `add_stop-141#2fc0aa211ecb` | add_stop | -0.0005% |

One of the 39 sits below D33's 0.0018-point differential-error figure. It is
still promoted; D33 does not filter the input (see §7).

## 2. Design

| | |
|---|---|
| cells | control + 39 candidates = **40 states** |
| seeds | **5, predeclared**: 20260825, 20260826, 20260827, 20260828, 20260829 |
| effort | **20 restarts**, evaluation ceiling 400,000, full candidate width |
| total | **200 cells** |
| start policy | `both`, identical for every cell |
| everything else | identical: evaluator, objective, envelope, path-set policy, pool, contract |

The first three seeds are Experiment 2B's own certification seeds, extended by
two. Effort is stated in **restarts** because D28 measured the iteration
ceiling as non-binding; it is recorded for reproducibility and is not evidence
of search depth.

**Path sets are rebuilt per (state, seed).** They could be shared across seeds
for roughly nine hours less compute, and they are not: if enumeration depends
on the seed at all, then that dependence is part of the seed-to-seed variation
being measured, and sharing would understate it. The conservative choice is
also the correct one here.

Estimated cost: **~27 hours** across two shards.

## 3. The statistic — paired, same-run

For candidate *c* and seed *s*:

```
effect(c, s) = objective(c, s) − objective(control, s)
```

Pairing on the seed removes the component of variation the two arms share, so
what remains is the difference the treatment made in that solve.

Every comparison goes through `firewall.compare()` on the two receipts, so a
pair whose execution differed in any undeclared way produces no effect at all
rather than a suspect one.

## 4. The materiality criterion — no inherited floor

**Nothing is carried in.** Not Stage A's withdrawn 0.039%, not 2B's 0.287
points, not the 0.00657% measured on the control in an earlier probe. σ is
estimated **from this run's own 200 cells**.

### The criterion

For candidate *c*, over the five paired effects Δ_s(c):

```
certified  ⟺  |mean Δ(c)| > 3 · SD(Δ_s(c))   with mean Δ(c) < 0
```

**σ is the standard deviation of the candidate's own five paired differences,
and nothing else.**

The reason is the estimand. What Stage B is measuring is the **treatment
contrast**, not the absolute control objective. Pairing on the seed preserves
the covariance between the candidate's and the control's solver behaviour —
when a seed sends both arms to a slightly worse basin, the difference between
them is unaffected. A control-only σ discards exactly that covariance and can
be either too permissive or too conservative depending on how the absolute
control objective happens to wander between seeds. It would answer a different
question than the one being asked, and could reject a perfectly stable
treatment effect because the control moved underneath it.

### The control spread is a diagnostic, not a gate

SD of the control's five objectives is recorded, reported, and used as an
**experiment-level solver-stability measure**. No candidate has to clear it.

It has one operational role: if the control's spread is anomalously large
**relative to prior certification runs**, that triggers investigation and
possible escalation of the **whole run** rather than of any candidate. The
reference point is the 2B matched-start confirmation, whose control gave
3σ = 0.00657% over three seeds. A Stage B control spread more than 3× that is
flagged for investigation.

That reference is a **diagnostic trigger about solver stability**. It is not a
materiality threshold, is never compared against a candidate's effect, and
nothing certifies or fails to certify because of it.

## 5. Pairwise comparison among certified candidates

Candidates established against the control are then compared **to each other**,
using the same 200 observations — no new runs. For certified *a* and *b*:

```
effect(a, b, s) = objective(a, s) − objective(b, s)
```

and the identical rule applies: `|mean Δ(a,b)| > 3·SD(Δ_s(a,b))`, σ taken from
those five paired differences. This is what separates outcome (1) from outcome
(2): a single leader requires the leader to be distinguishable *from the other
certified candidates*, not merely from the control.

## 6. Escalation

Escalation is driven by **ambiguity in the paired contrast** — never by
disagreement between competing definitions of σ, because there is only one.

A candidate escalates to **40 restarts × the same 5 seeds** when either:

* it **fails the paired criterion** at 20 restarts — `|mean Δ| ≤ 3·SD(Δ)`. A
  candidate is not declared uncertified on an underpowered run; it gets the
  deeper search first.
* its **paired spread is unstable** — `SD(Δ_s(c))` exceeds **3× the median
  SD(Δ)** across the 39 candidates. A same-run comparison, no inherited
  constant.

A **pairwise relationship** between two certified candidates that cannot be
resolved escalates both.

Escalation changes the restart count and nothing else: same five seeds, same
contract, same start policy, same everything. Escalated results replace the
20-restart results for those states and are reported as escalated.

Run-level escalation is separate: an anomalous control spread (§4) triggers
investigation of the whole run, not of a candidate.

## 7. D33 is a veto, never a threshold

D33's differential-error measurement is an **independent diagnostic**. It may
**veto** a conclusion — if the treatment-correlated component of solver error
turns out comparable to a margin being claimed, that margin is not reportable
however it scores against σ.

It is **never** the materiality threshold, and it is **never added to** it.
0.0018 points is a lower bound on differential error from local neighbourhoods
at discovery effort; it is not a significance cutoff and must not become one by
accumulation. A margin above it is *not excluded* by that measurement, which is
not the same as *established*.

The Stage B differential-error diagnostic is re-measured at Stage B effort on a
subset of the promoted states, because D33's discovery-effort figure does not
transfer.

## 8. The three outcomes, all admissible

1. **A certified small route-mutation improvement** — one candidate certified
   against the control *and* distinguishable from every other certified
   candidate.
2. **Several indistinguishable small improvements** — two or more certified
   against the control, none distinguishable from the others. Reported as a
   set, with no leader named.
3. **Effectively NULL after certification** — none certified. Stage A's 39
   corrected-negative states do not survive matched-effort certification.

**Outcome 3 is a result, not a failure**, and is precommitted as such. Stage A's
39-of-84 split is close to a coin flip; a null here would say the coin was fair.

## 9. What Stage B cannot establish

* Nothing about mutations outside the promoted 39.
* Nothing about combinations — Phase A2 is disclosed as an incomplete search
  and its states carry no receipts.
* Nothing about consolidation, deferred under SC-1..SC-4.
* No claim that a certified margin is *operationally* meaningful. Certified
  means distinguishable from solver variance at this effort, and nothing more.

## 10. Implementation

Every cell runs through `exp3_cell.run_cell` under a Stage B
`ExperimentContract` (`stage="certification"`, `require_convergence=True`), and
writes an `ExecutionReceipt` to a Stage B observation store. Promotion,
comparison and reporting consume `ComparisonResult` only.

The evaluation path is frozen for the duration at the Stage B digest, enforced
by `test_repro_guards.py` (OPERATIONS 24). Stage A's frozen census is pinned to
`FREEZE_MANIFEST.json`'s recorded `source_digest` so it stays reproducible
across the Stage B code change.
