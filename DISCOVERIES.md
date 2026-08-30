# Model-discovery log

Things the model **revealed**, as distinct from things the experimenter put in.
Each entry carries what would falsify it, so a later run can retire it rather
than having it quietly persist because nobody rechecked.

Confidence is one of **strong** (survives an independent attempt to break it),
**moderate** (consistent across the checks run so far), or **provisional** (one
run, or the run that produced it is still going).

---

### D1 — Frequency moves from already-frequent routes toward the 30–120 minute tier

**Evidence.** Balanced plan (config C, λ=2, matched effort): routes at ≤15 min
lose 9.6 min of headway on average and routes at 16–30 min lose 7.6, while the
31–60 tier gains 17.6 and the 61–120 tier gains 10.1. Biggest single gains are
11 Bryden/Maize (80→30 early, 68.6→24 evening) and 32 N Broadway (60→20 in
three periods); biggest payers are 22 OSU-Rickenbacker (15.7→60 pm peak) and 12
McKinley/Fields (20→60).

**Confidence.** Moderate. Direction is stable across λ and seeds; the specific
routes are not independently verified.

**Interpretation.** The square-root rule bites: with demand spread as the proxy
has it, marginal minutes buy more at 60 min than at 12. Whether COTA *should*
do this is a policy question the model does not answer — the 22 and the 12 are
real corridors carrying real riders.

**Falsified by.** A demand model with non-work trips concentrated on the trunk
routes; or observed boardings showing the ≤15 min tier is far busier than the
proxy implies.

---

### D2 — Frequency-only returns plateau fast

**Evidence.** Unserved demand: −6.33% at λ=2, −6.95% at λ=4, −6.88% at λ=8,
−6.95% at λ=16, while cost climbs +0.49 → +1.11%. Past λ=4 the optimizer buys
nothing and pays for it.

**Confidence.** High. The converged-path-set rerun this was pending has since
run on both models, and on Model B it is now the certified gate-4 frontier.

**Interpretation.** There is a ceiling near 7% on what redistributing frequency
inside this geometry and this budget can reach.

**Confirmed on the converged Model B frontier, 2026-08-27** (gate 4
certification, `outputs/certify_modelB.log`), and confirmed *better* than the
original evidence deserved:

| λ | gen. cost | unserved | certified |
|---|---|---|---|
| 2 | +0.842% | −6.602% | yes |
| 4 | +1.236% | −7.125% | yes |
| 8 | +1.460% | −7.247% | yes |
| 16 | +1.485% | −7.276% | yes |

Past λ=4 the last 0.151 points of unserved demand cost 0.249 points of
generalized cost — the plateau in the original entry, at the same place. The
improvement is in its shape: the pre-convergence sweep was **non-monotone**
(−6.95%, −6.88%, −6.95% at λ = 4, 8, 16), so what it actually showed was a
plateau indistinguishable from search noise. The converged sweep is monotone in
both columns across all four λ, which means the flattening is a property of the
problem and not of the search. The ceiling sits at **−7.28%**, marginally above
the ~7% originally claimed.

**Falsified by.** The converged path set moving the aggressive end of the
frontier enough to un-flatten it — the check this entry was waiting on. It did
not: path-set inadequacy at the aggressive end fell from 17.6% of flow
improvable to 0.52–0.56%, and the frontier flattened rather than opening up.

---

### D3 — Route-level scoring badly exaggerates the gain from cutting parallel service

**Evidence.** The route-level model's λ=4 plan: it believes −22.71% unserved at
−0.76% cost. The same plan, scored by path assignment: −7.16% at **+2.51%**.
All seven route-level plans are strictly dominated by path-level plans at
matched effort, same demand, same solver, same yardstick.

**Confidence.** Strong. This is a controlled comparison, and it is the most
transferable result in the project.

**Interpretation.** Without path assignment, cutting one of two parallel routes
looks free, because the model has no mechanism for the abandoned passengers to
walk to the other one — so it never charges for the walk, the wait, or the
transfer. Any network-redesign claim scored this way inherits the error.

**Falsified by.** A path-based scorer showing route-level plans are competitive
after all — not observed at any λ.

---

### D4 — Peak expresses need a separate class, not a headway

**Evidence.** 14 of 39 routes run in a peak with no midday and no evening
service. Treated as ordinary low-frequency service, the optimizer multiplied
their headways twelvefold and called it savings. Their 180-minute "headway" is
a timetable. Locking them is worth 1.5–3 pp of apparent unserved reduction.

Separately, in Experiment 2 a naive geometry generator read route 045's single
19-minute non-stop run as "86.3% of running time for 0.8% of demand, truncate
it" — which is deleting the route's purpose. Same misreading, different module.

**Confidence.** Strong.

**Falsified by.** Nothing in scope; this is a fact about the schedule.

---

### D5 — Crowding does not bind on this system at this demand scale

**Evidence.** Median bus at its route-period peak load point carries 9% of
capacity; peak-load factors run 0.32–0.42 median by period. NTD corroborates at
13.0 boardings per revenue hour. Model configurations with and without crowding
differ in the third decimal.

**Confidence.** Strong at the modelled demand scale; the scale itself is the
soft part (30,949 assumed weekday linked trips, NTD-derived).

**Falsified by.** A demand model two or three times larger, or observed
peak-point loads on trunk routes.

---

### D6 — Path-set inadequacy was about scenarios, not the per-OD cap

**Evidence.** Raising the per-OD candidate cap from 4 to 6 added 1,825 paths to
201,336 — under 1%. Meanwhile the measured improvable flow share runs 0.4% at
baseline, 6.4% under the balanced plan, and 17.6% under the most aggressive —
i.e. it scales with how far the plan is from the scenarios that were
enumerated.

**Confidence.** Moderate. The cap number is measured; the scenario explanation
is the surviving hypothesis and is being tested directly by the attribution
diagnostics (`cota_opt.attribution`), which name the mechanism behind each
recovered path.

**Interpretation.** A candidate set enumerated around today's timetable is
adequate for plans near today's timetable and progressively wrong as the
optimizer walks away from it. That is a general warning about pre-enumerated
path sets in frequency optimization, not a quirk of this feed.

**Falsified by.** Attribution showing the recovered paths are mostly
stop-relocations within the same routes, which would point at enumeration
granularity rather than scenario coverage.

---

### D7 — At fixed frequency, geometry moves cost, not reachability

**Evidence.** Screening 33 candidates at budget-matched headways: almost every
one sits exactly on unserved-change = 0. Only extensions move it, and the two
largest movers (routes 007 and 101, −3.54%) are novel-link candidates.

**Confidence.** Provisional — screening only, frequency not reallocated, and
the screen samples 400 origin zones.

**Interpretation.** "Unserved" here means *unreachable*, and a limited geometry
edit rarely strands a zone outright; it makes trips longer or shorter. So the
Experiment 2 comparison against the Experiment 1 frontier will mostly be a
statement about generalized cost at given coverage, and the coverage axis will
carry little signal until frequency is re-optimized (where freed vehicle-hours
*can* buy reachability).

**Falsified by.** The full evaluation tier, with frequency re-optimized,
showing material coverage movement.

---

### D8 — The novel-link running-time estimator is not biased in the exploitable direction

**Evidence.** Five-fold validation held out **by link** (so a link on several
patterns cannot sit in both sets): MAE 17.2 s, median absolute percentage error
20.5%, aggregate bias **+0.41%**, and 63% of links are *over*-predicted. Worst
route-level aggregate bias runs −2.3% to +5.0%.

**Confidence.** Strong for the direction; the spread is real and is why
`modelled_share_pct` gates which candidates may define the headline.

**Interpretation.** Systematic underestimation would let the optimizer buy
frequency with running time that does not exist. It is not doing that. The
0.9959 multiplier that would zero the aggregate bias is noise and was
deliberately **not** adopted — recalibrating on a 0.41% signal is fitting the
validation set.

**Falsified by.** Bias appearing once restricted to the link lengths and route
types that geometry edits actually produce, rather than the whole population.

---

### D9 — The peak-fleet formula the budget uses is 24% optimistic, and blocks say the balanced plan needs no more buses

**Evidence.** COTA's feed blocks all 5,435 weekday trips into 299 blocks. Read
directly, the peak requirement is **197 vehicles at pm peak** — against NTD's
reported VOMS of **198**, a 0.5% match that nothing in the pipeline was tuned
to produce. The cycle-time-over-headway formula the optimizer's budget uses
gives **150.7**: an interlining factor of **1.307**, i.e. the formula is
optimistic by a quarter, because it ignores the 19.4% of block span spent on
layover.

Applying that factor to the balanced plan (config C, λ=2): peak proxy **196.9
against a baseline 197.0** — essentially unchanged. Route 005 (+6.5 buses),
102 (+5.7) and 011 (+3.8) rise at the peak period; others fall by as much.

**Confidence.** Strong for the baseline reading, which is externally
corroborated. Moderate for the candidate proxy, which assumes a re-blocked
network would interline about as well as today's — a scheduler's judgement.

**Interpretation.** The balanced plan is not quietly buying its coverage with
capital. That was a live risk and it is now measured rather than assumed. Only
12% of blocks serve more than one route, so COTA's interlining is modest and
the assumption that a new plan could match it is not demanding.

**Falsified by.** A scheduler showing the redistributed plan cannot be blocked
at today's efficiency.

---

### D10 — What looked like a hyperpath problem is mostly a pattern-aggregation error inside the current model

**Evidence.** The combined-frequency upper bound over chosen ride legs comes to
**5.09% of generalized cost** — 2.5× the Experiment 1 effect, which would be
alarming. Split by where the alternative comes from: **84.4% of it is the same
route's own patterns**, and 19,049 of 22,984 affected legs have alternatives
that are *entirely* same-route. The genuine cross-route hyperpath bound is
**0.79%**.

Concentration: route 010 E Broad carries 23% of the bound with a median of
**4 attractive patterns** per leg; 005, 007, 001, 002 follow at 2 each.

**Confidence.** Moderate. The bound is deliberately generous; the same/cross
split is exact.

**Interpretation.** Two different problems were hiding in one number.

*Cross-route hyperpaths* — 0.79%, locally meaningful, follow-on work. Not
capable of overturning the direction of the Experiment 1 result.

*Same-route patterns* — roughly **4.3% of generalized cost**, and this one is
the current model's own error. Each ride leg is priced at its pattern's
headway (route headway × direction-trips ÷ pattern-trips). That multiplier was
added to stop a quarter-frequency pattern being priced at the route's full
frequency, which was right. But where several of a route's patterns all carry
the same stop-to-stop movement, the rider can take any of them, and charging
them one pattern's headway overcharges the wait. The fix is inside the
existing model: price the movement on the combined frequency of the patterns
that serve it.

**Why it matters to the headline.** The overcharge concentrates on
high-frequency trunk routes — exactly the ones the balanced plan proposes to
cut. Correcting it makes trunk service look better than the model currently
says, which should *reduce* the case for cutting it. So the direction of the
bias runs against the current Experiment 1 result, and the finalized frontier
has to carry that as a stated known bias until the fix is made and re-run.

**Status.** The correction is **implemented and unit-tested** as Model B,
behind a config flag, without touching the running Model A job. A pattern's
headway is `h_route * n_direction_trips / n_pattern_trips`, so summing
frequency over the patterns that actually serve the movement and inverting
gives a multiplier on the same route headway the optimizer controls:

    mult = 1 / sum_q ( n_trips(q) / n_direction_trips(q) )

With one qualifying pattern that is exactly `n_dir / n_pat`, so Model B is a
strict generalisation of Model A rather than a different model, and the only
thing that changes is how `leg_headway_mult` is computed at enumeration. A
pattern qualifies only if it serves the boarding stop, serves the alighting
stop, in that order, and runs in the period — sharing a route id is not
enough.

Legs carry **both** multipliers during enumeration: Model A's is used for the
re-pricing self-check, which has to reproduce RAPTOR's own per-pattern
arithmetic exactly, and Model B's is what gets stored. That check caught a
truncated-reconstruction bug once and was not going to be weakened to
accommodate the correction.

**Falsified by.** Running the common-lines diagnostic under Model B and
finding the same-route residual does not collapse — which would mean the
implementation is wrong, not that the defect is not there. That is the next
thing to run, and it is gated behind the Model A fixpoint finishing.

---

### D11 — Correcting valuation raises a discovery question the fixpoint cannot see

**The problem.** Model B changes how a ride leg is *priced*. It does not change
how paths are *found*: RAPTOR still searches with per-pattern headways, which is
Model A's valuation. So a route sequence can be genuinely cheap under Model B
while the search that built the candidate set never had reason to explore it,
and the corrected model would be missing a path it would itself want to use.

This is a **different failure** from the one the fixpoint addresses. The
fixpoint asks whether the candidate set contains the paths that new *headway
scenarios* make attractive. This asks whether it contains the paths the
corrected *valuation* makes attractive. A candidate set can pass one and fail
the other, and the existing adequacy check cannot detect it — that check
compares the cached set against fresh RAPTOR, and fresh RAPTOR is priced the
same wrong way.

**How it is tested, exactly rather than heuristically.** Re-run RAPTOR with
*route-level* headways: every pattern at its route's whole frequency, as if all
of it served every movement. Because a Model B multiplier is
`1 / Σ_q(n_trips(q)/n_dir_trips(q))` over a qualifying set that is a subset of
the direction, the multiplier is at least 1 and route-level pricing is a strict
**lower bound** on any Model B path cost. Where that bound does not beat the
candidate set's best Model B cost, no omission is possible and the OD pair is
cleared outright, no reconstruction needed. Where it does, reconstruct the
bound-optimal journey and price it exactly under Model B — turning "might be
omitted" into "is omitted, by this much, on this route sequence".

The bound is loose by construction, so it over-selects suspects and never
misses one. The confirmation step is what produces the number.

**Confidence.** The method is sound by construction and unit-tested on a
synthetic network built so the failure actually occurs — a trunk with two
half-frequency patterns that only wins once they combine. The *result* on COTA
is not in yet.

**Decision rule.** Committed to `ACCEPTANCE.md` as gate 11 before the
diagnostic was written: materially better means beating the set by ≥1.0
generalized minute **and** ≥1%; negligible is <1.0% of tested flow and <0.25%
of tested generalized cost; material is ≥3.0% of flow **or** ≥1.0% of cost.
Either bound alone triggers the worse case. If material, the response is
targeted candidate-generation augmentation around the affected corridors — not
replacing RAPTOR, and not compensating elsewhere in the model.

**Interpretation, whichever way it lands.** A clean result says per-pattern
discovery was tested specifically against the possibility the correction
created and found no material flow-weighted omission. A dirty one says the
correction exposed a discovery mismatch that targeted augmentation closed.
Both are useful; only silence would not be.

### D12 — The Model B correction removes the same-route residual exactly, not approximately

**Evidence.** Gate 10 re-ran the common-lines diagnostic under Model B on the
identical periods, path-assignment settings and baseline plan used for D10.

| | Model A | Model B |
|---|---|---|
| ride legs with a cheaper common-lines alternative | 22,984 | **3,778** |
| upper bound as share of generalized cost | 5.095% | **0.516%** |
| same-route component | 4.301% | **0.000%** |
| legs whose alternatives are *all* same-route | 19,049 | **0** |
| cross-route component | 0.794% | **0.516%** |

The same-route figure is `-5.3e-14` generalized minutes, which is floating-point
zero on a base of 1.77 million. That is the expected result rather than a good
one: Model B prices a ride leg on the combined frequency of every qualifying
same-route pattern, so after the correction there is no same-route common-lines
saving left for the bound to find. A residual near zero is what a correct
implementation *must* produce, and anything else would have meant the
multiplier was not being applied where the bound was looking.

The cross-route component also fell, 0.794% → 0.516%, which was not designed in
and is worth stating for that reason. It follows: Model B makes the chosen path
cheaper, so a cross-route alternative saves less against it. The direction is a
weak consistency check that the two diagnostics are measuring the same baseline.

**Confidence.** High for the collapse itself — the same/cross split is exact,
both runs share every input but the waiting model, and the block-derived fleet
figures came back bit-identical (197 peak vehicles at 17:13, interlining factor
1.30699), confirming nothing else moved between them. Moderate for the residual
0.52%, which is a generous upper bound rather than an estimate.

**Interpretation.** Gate 10 passes. Total remaining common-lines exposure is
**0.52% of generalized cost, entirely cross-route** — below the 0.79% already
accepted as non-blocking under Model A, and roughly a quarter of the ~2% effect
Experiment 1 claims. The correction did not shift the problem somewhere else;
it removed one of the two problems D10 separated and left the other slightly
smaller.

This does **not** license freezing the Model B yardstick. Gate 10 is about
valuation; gate 11 asks whether per-pattern RAPTOR can still *discover* the
paths the corrected valuation prefers, and that diagnostic is running.

**What would falsify it.** A same-route residual materially above zero under
Model B would mean the multiplier is not reaching the legs the bound prices,
and the correct response would be to find where — not to accept a smaller
number as good enough. A cross-route residual that *rose* would mean the two
runs are not scoring the same baseline.


### D13 — The corrected valuation does have a discovery gap: wide in trips, narrow in cost

**Evidence.** Gate 11, run under Model B on the top 4,000 OD pairs per period
riding the eight routes D10 named:

| | |
|---|---|
| OD pairs with a materially better omitted path | 333 |
| flow affected / tested flow | 326.1 / 6,687.7 = **4.877%** |
| generalized-cost improvement / tested cost | 1,194.6 / 645,768.4 = **0.185%** |
| median improvement | 3.58 min (3.38%) |
| p95 improvement | 9.00 min |
| omitted sequences already present in the set under other pricing | 15 of 333 |

Concentrated on 001 (90 pairs), 008 (119), 002 (111), 033, 007, 034. The
dominant sequence is `008+001`, and nearly all omissions are two-boarding
journeys — one-transfer trips whose second leg only becomes worth waiting for
once a route's patterns are counted together.

**Case C**, on the flow bound alone. The cost bound is *negligible* by the same
pre-committed table (0.185% against a 0.25% line). The rule says either bound
triggers the worse case, so Case C it is.

**Confidence.** High on the numbers — the bound clears most pairs exactly and
the survivors are priced exactly under Model B, not estimated. Moderate on
coverage: only the focus routes' top-flow pairs were tested, so this is a
lower bound on the true omission.

**Interpretation.** The two bounds disagree by a factor of 26, and that
disagreement is the finding rather than a nuisance. A lot of trips have a
slightly better path they were never offered — 3.6 minutes on journeys
averaging 74. That is far too small to move the frontier and far too widespread
to dismiss, and it is exactly the situation a rule written *after* seeing the
numbers would have been argued out of.

**Response, as pre-committed.** Targeted augmentation of candidate generation:
Model B enumeration gains a route-level-priced search scenario. Not a
valuation change, not a replacement for RAPTOR, and no compensation elsewhere.

**The rerun is a consistency check, not an independent test — and that has to
be said out loud.** The diagnostic finds suspects with route-level RAPTOR and
the augmentation adds route-level RAPTOR's optima to the candidate set. After
augmenting, the diagnostic's bound cannot beat the set for the paths it looks
at, close to by construction. A clean rerun therefore proves the augmentation
was wired in — worth knowing, given the self-check bug that made the scenario
contribute nothing on first attempt — but it does not prove discovery adequacy.

The non-circular evidence is the frontier's *sensitivity* to the augmentation:
solve Model B on both candidate sets and compare. If the wider set moves the
frontier, discovery mattered; if it does not, the omission was real, widespread,
and irrelevant to the answer — which is what the 0.185% cost share predicts. That
comparison is the one to report.

**What would falsify it.** A rerun that still shows material flow share would
mean the augmentation does not reach the sequences involved. A frontier that
moves materially on the wider set would mean the cost share understated the
omission and the whole Model B result needs the augmented set as its basis.


### D14 — The frontier is robust where the plan is not

**Evidence.** Gate 11's follow-up solved Model B at matched effort (100,000
iterations, 6 restarts, full width, seed 20260825) on both candidate sets and
scored both plans on the augmented evaluator — a superset, so neither plan
grades its own homework. Candidate paths 203,161 → 217,338 (+6.98%).

| λ | gc gap | unserved gap | route-periods changed | mean change | max change |
|---|---|---|---|---|---|
| 1 | −0.0077% | +0.0293% | 39 / 173 | 8.41 min | 40.0 min |
| 2 | +0.0127% | −0.0192% | 43 / 173 | 7.91 min | 38.6 min |
| 4 | −0.0568% | +0.0022% | 42 / 173 | 7.01 min | 20.0 min |

Committed thresholds were 0.25% generalized cost and 1.0% unserved. Every gap
comes in **one to two orders of magnitude below** them, and two of six have the
sign that favours the *un*-augmented set, which is what noise looks like.

**Confidence.** High on the non-materiality. The comparison was specified in
`ACCEPTANCE.md` before it ran, effort and seed were identical on both sets, and
the yardstick is the superset.

**Interpretation, first half — the question that was asked.** Gate 11's
discovery gap does not change the recommendation. It was real (333 OD pairs,
4.877% of tested flow) and it is irrelevant to the answer, exactly as its
0.185% cost share predicted. The flow bound and the cost bound disagreed by a
factor of 26 and the cost bound was the one that mattered. That is worth
recording precisely because the pre-committed rule sent the run down the
expensive path on the flow bound, and the expensive path was still the right
call: without it, "the omission is immaterial" would have been an assertion.

**Interpretation, second half — the finding nobody asked for.** A quarter of
the network's route-periods move by an average of **eight minutes of headway**
between two plans whose objectives differ by 0.01%. One route-period moves by
forty minutes. The two plans are, for practical purposes, the same plan in
objective space and visibly different plans in the world.

That splits the result in two, and the split has to survive into how it is
stated:

* **The aggregate claim is robust.** Roughly 6% less unserved demand at little
  generalized cost holds across candidate sets that differ by 7% in size, under
  plans that differ substantially in composition.
* **The per-route claim is not.** "Route X should go from 30 to 15 minutes" is
  not identified by this objective at this effort. Anyone acting on a specific
  headway from a specific plan would be acting on something the model does not
  actually distinguish from many alternatives.

**Which is it — a flat optimum or an under-converged search?** **Resolved by
D17: a flat optimum.** Gate 7's replicates share one candidate set and run at
the top of the effort ladder, so neither candidate-set spread nor under-search
can explain them — and the objective barely moves across seeds (Model B sd
0.064 points on a −6.65% effect, 104σ) while 19.1% of route-periods do. A search
that had not converged would scatter the *objective*; this one scatters only the
plan. The paragraph below is kept as written because it is the reasoning that
set up the test, and because the test's second job — distinguishing the two —
is the reason gate 7 reports plan disagreement at all. The two have the same
practical consequence either way. Gate 7 already requires three
seeds at λ=2 on one candidate set; that check now has a second job, because if
independent seeds also disagree on 40 route-periods the flatness is intrinsic,
and if they agree closely then the candidate set is doing more work than the
gap sizes suggest. Either answer changes what may be said about individual
routes, and neither changes the aggregate.

**What would falsify it.** Seed replicates that agree to within a handful of
route-periods would mean the plan is better identified than this comparison
suggests, and the difference here is a candidate-set effect after all — which
would make the augmentation matter for composition even though it does not
matter for score.


### D15 — The path-set method certifies the service-favouring half of the frontier and not the other half

**Evidence.** Model A's fixpoint converged (worst improvable flow 9.443% →
1.029% over four iterations) and the full-effort frontier was then re-checked
against the frozen set. It split by λ:

| λ | improvable, frozen set | improvable, after one repair step |
|---|---|---|
| 0.25 | 9.721% | **3.893%** |
| 0.5 | 1.618% | **1.792%** |
| 1.0 | 0.691% | **1.115%** |
| 2.0 | 0.678% | 0.749% |
| 4.0 | 0.656% | 0.732% |
| 8.0 | 0.688% | 0.767% |
| 16.0 | 0.988% | 0.812% |

The repair step is the fixpoint's own logic applied to the full-effort plans:
all seven go back in as enumeration scenarios, the set is rebuilt (227,791 →
233,589 paths), and every λ is re-solved on it. It fixed most of λ=0.25's gap
and **made λ=1.0 worse**, moving it from pass to fail.

**Confidence.** High. The pattern is consistent, the line was fixed in advance
and read from the loop's own last iteration, and the repair was specified
before its output was seen.

**Interpretation.** Aggregate convergence is not pointwise convergence. The
loop's exit test is the *worst* improvable share across the probe λ, and the
probe set is {0.5, 1, 2, 8}. A frontier solved at {0.25 … 16} and at higher
effort produces plans the loop never tested, and at low λ those plans are
qualitatively different rather than merely different: with almost no penalty on
unserved demand the optimizer pushes headways to the policy ceiling across much
of the network, and a candidate set enumerated around plausible headways covers
that region badly.

Re-enumerating around those plans does not converge it, because the wider set
lets the search find a *new* extreme plan, which the set covers no better. That
is the λ=1.0 regression: not noise, but the target moving. Two more repair
rounds might close λ=0.25, on its 9.7% → 3.9% trend; nothing suggests λ=0.5 or
1.0 would follow, and each round costs about five hours per model.

So the honest boundary is drawn rather than pushed: **λ ≥ 2 is certified, λ ≤ 1
is not, and the frontier is quoted from λ=2 upward.** The pre-committed
language said exactly this before the numbers arrived — quote the frontier
without the corner rather than moving the line.

**Why this costs nothing that matters.** The uncertified points are the ones
that spend less and serve fewer people: λ=0.25 gives up 13.3% of served trips.
No one proposes that. The decision-relevant region — coverage bought at small
cost — is entirely inside the certified range, and the balanced point barely
moved between the two sets (+0.531%/−6.973% frozen, +0.535%/−7.035% widened),
which is what a certified point should look like.

**What would falsify it.** λ=0.5 or 1.0 dropping below the line under further
repair rounds would mean the boundary is an artifact of stopping after one
step. A balanced point that moved materially between the frozen and widened
sets would mean λ=2's certification is worth less than it looks.


### D16 — The geometry ranking does not depend on the waiting model

**Evidence.** The 60-candidate screen was run at both ends of the bracket: Model
A's per-pattern waiting, and route-level pricing, which is a strict lower bound
on any Model B path cost. Any real Model B ranking lies between them.

| | |
|---|---|
| Spearman rank correlation | **0.8565** (keep ≥ 0.80) |
| top-10 overlap | **8 / 10** (keep ≥ 7) |
| verdict | **stable** |

Both thresholds were committed to `ACCEPTANCE.md` before the second screen ran,
and the worse of the two bounds decides, as everywhere else in this project.

The eight that hold their place are all **splices** — through-routings that
remove a forced transfer: 001+021 at PICBETS, 002+033 and 002+034 and 033+034 at
WESHIGW, 005+021 and 006+021 at NMURBEAN, 007+101 at EMO4THW, 008+035 at BOASHAN.

**Confidence.** Moderate-to-high on the ranking's model-independence; the two
ends genuinely bracket Model B, and the correlation is computed over all 60
candidates rather than the survivors.

**Interpretation.** The screen is measuring something about geometry rather than
something about how waiting is priced. That matters because the screen was run
under Model A and Model A is now known to be wrong: had the ranking moved with
the waiting model, every candidate would have needed re-screening under a model
the screen cannot express, and the shortlist would have been unusable.

That through-routings dominate both ends is itself worth noting. A splice
removes a transfer outright — a fixed penalty plus a wait — and that saving is
large under any waiting model, which is precisely why it survives a bracket that
varies the waiting model.

**One candidate the Model A screen buries.** `splice|002|011|HIGFITN` sits at
rank 53 of 60 under Model A and rank **10** under the bound: the largest single
move in the set. Under combined-frequency pricing the corridor it joins is far
more attractive than per-pattern pricing suggests. The pre-committed rule keeps
the Model A shortlist as triage and says nothing against widening it, so the two
bound-only entrants (`002|011|HIGFITN`, `005|006|NMURBEAN`) are carried into
evaluation alongside the eight. Adding candidates is the conservative error.

**Amendment, same day, after breaking the comparison down by edit kind — which
is what the original directive asked for and the first pass skipped.** The
aggregate correlation is not what it looks like:

| kind | n | Spearman *within* kind | top-10 under A | top-10 under bound |
|---|---|---|---|---|
| extend | 12 | 0.989 | 0 | 0 |
| straighten | 12 | 0.954 | 0 | 0 |
| reroute | 12 | 0.921 | 0 | 0 |
| truncate | 12 | 0.638 | 0 | 0 |
| **splice** | 12 | **0.336** | **10** | **10** |

The 0.857 overall is carried by *between*-kind separation: splices at the top
under both ends, everything else at the bottom under both. That ordering is
what the correlation is measuring. Within splices — the only kind that takes a
top-ten slot under either end — the ranking is nearly uncorrelated.

So the finding splits, and only the first half survives as stated: **the set
{splices are the good kind} is robust to the waiting model; the ordering inside
that set is not.** Eleven of the twelve splices occupy ranks 1–11 under Model A
and reshuffle freely between the ends; the twelfth sits at 53 under Model A and
10 under the bound.

The consequence is concrete. The shortlist is no longer the screen's top eight —
it is **all twelve splices**, because the screen cannot order them and the
evaluation tier can: it re-optimizes frequency and, having path sets, can
express Model B properly. Promoting eight on a within-kind correlation of 0.336
would have been promoting on noise.

**What would falsify it.** A Spearman computed on a different screening metric —
generalized cost rather than retention-adjusted unserved — coming out materially
higher within splices would mean the instability is specific to the metric
rather than to the ranking.


### D17 — The aggregate result is measured to 55 sigma; the plan behind it is not identified at all

**Evidence.** Three seeds at λ=2, full effort, **one shared candidate set** —
so seed spread and candidate-set spread cannot be confounded, which is the
confound D14 could not resolve.

| seed | gen. cost | unserved | served | cost/trip |
|---|---|---|---|---|
| 20260825 | +0.5353% | −7.0352% | +3.8062% | −3.1509% |
| 20260826 | +0.4722% | −6.8592% | +3.7109% | −3.1229% |
| 20260827 | +0.6061% | −7.1055% | +3.8442% | −3.1183% |

| quantity | mean | sd | σ |
|---|---|---|---|
| generalized cost | +0.538% | 0.067 | 8.0 |
| unserved demand | **−7.000%** | 0.127 | **55.2** |
| served trips | +3.787% | 0.069 | 55.2 |
| cost per served trip | −3.131% | 0.018 | 177.3 |

And the plans behind those numbers:

| seed pair | route-periods differing | mean move | max move |
|---|---|---|---|
| 25 vs 26 | 45 / 173 = **26.0%** | 8.11 min | 30 min |
| 25 vs 27 | 36 / 173 = 20.8% | 7.83 min | 30 min |
| 26 vs 27 | 36 / 173 = 20.8% | 6.97 min | 15 min |

Thresholds were committed before the replicates existed: 3σ on the effect, 10%
route-period disagreement on the plan.

**Confidence.** High. Three independent seeds, one set, matched effort,
thresholds fixed in advance, and the pattern is consistent across all three
pairs rather than driven by one outlier.

**Interpretation.** These two findings point in opposite directions and both
are real.

*The effect is about as well determined as anything in this project.* A 7%
reduction in unserved demand with a seed standard deviation of 0.127 points is
55 sigma. The cost figure is the noisiest of the four at 8 sigma, and 8 sigma is
still not close to a judgement call.

*The plan is not determined at all.* A quarter of the network's route-periods
move by an average of eight minutes of headway — one by thirty — between runs
that differ only in a random seed and score within 0.13 points of each other.
This settles D14: that instability was **not** a candidate-set effect, because
these replicates share a set. The optimum is flat.

**What this licenses and what it forbids.** "Redistributing service under the
existing envelope reduces unserved demand by about 7%, at a cost per trip
actually served that falls by about 3%" is supported to a degree the rest of the
model's assumptions do not deserve. "Route 010 should run every 15 minutes at
midday" is **not supported at all** — the model does not distinguish that plan
from many others that score the same. Any per-route number in a write-up or a
handoff must be labelled as one arbitrary member of a large indifference set,
and the Experiment 2 comparisons must use aggregate frontier positions rather
than plan diffs.

There is a constructive reading. A flat optimum means COTA has *freedom*: many
different concrete schedules realise essentially the same passenger benefit, so
operational constraints this model does not represent — operator bidding,
layover geography, garage assignment, political commitments — can be satisfied
almost for free. That is worth more to a planner than a single plan they would
have to take on faith.

**Confirmed on Model B, 2026-08-27 21:40 UTC**, on its own 243,257-path set:

| quantity | mean | sd | σ |
|---|---|---|---|
| unserved demand | **−6.652%** | 0.064 | **104.4** |
| served trips | +3.299% | 0.032 | 104.4 |
| cost per served trip | −2.344% | 0.011 | 214.6 |
| generalized cost | +0.878% | 0.041 | 21.5 |

Plan disagreement: worst pair **19.7%** of route-periods, mean 19.1%, average
move 6.92 min. Same verdict, same side of the line.

Model B is better conditioned than Model A on both counts — half the objective
spread (0.064 against 0.127) and a quarter less plan disagreement (19.7%
against 26.0%) — which is what a corrected valuation should do. It is nowhere
near enough to change the conclusion. Two models, two candidate sets, six
independent seeds: the effect is measured to a precision the rest of the model
does not deserve, and the plan is not identified.

**What would falsify it.** Nothing available. Both models, both sets and all six
seeds agree; a third model would have to disagree with both.


### D18 — The recommended plan needs no additional buses, measured against COTA's own blocks

**Evidence.** The block-derived fleet proxy applied to the **certified Model B
balanced plan** (λ=2, the plan behind the −6.65% headline):

| | |
|---|---|
| baseline peak proxy | 197.0 vehicles |
| balanced plan peak proxy | **197.0 vehicles** (−0.0, −0.0%) |
| peak vehicles read from blocks | 197 at 17:13 |
| NTD reported VOMS | 198 (−0.5% against blocks) |
| cycle-over-headway formula | 150.7 — 24% optimistic |

Largest per-route increases at the peak period: 005 +6.49, 102 +5.69, 032
+4.26, 025 +2.61, 011 +2.55, 021 +2.19 buses — offset elsewhere to a net zero.

**Confidence.** High on the *comparison*, which is what matters here. The proxy
is not tuned: reconstructing COTA's blocks from the feed gives 197 peak vehicles
against NTD's independently reported 198, a 0.5% match nothing was fitted to,
and the same proxy is applied to both plans. Moderate on the absolute figure,
since the interlining factor (1.307) is a system-wide constant applied per
route.

**Interpretation.** This is the constraint a planner asks about first and the
one the optimizer was never given: the vehicle-hour envelope is a budget, not a
fleet cap, and a plan can respect the hours while needing more buses at the peak
minute. It does not. The redistribution is genuinely a *redistribution* —
service moves toward the 30–120 minute tier and the routes that gain at the peak
are paid for by routes that give up peak frequency, netting to zero buses.

So the result costs no capital, no garage space and no additional operators at
the peak. That is a materially different proposition from one requiring six more
vehicles, and it is worth stating alongside the headline rather than buried in a
constraints appendix.

**A caveat that belongs with it.** Per-route figures here inherit D17: the plan
is one arbitrary member of a large indifference set, so "route 005 needs 6.5
more buses at the peak" is **not** a claim about route 005. The claim is about
the *total*, which is what the indifference set holds fixed — every plan in it
respects the same envelope.

**What would falsify it.** A block reconstruction that disagreed materially with
NTD's VOMS would undermine the proxy. A plan drawn from a different seed showing
a materially different total — rather than a different per-route split — would
mean the zero is a property of this plan rather than of the envelope.


### D19 — The screen's best candidate is one of the two that make things worse

**Evidence.** All twelve splices evaluated with frequency re-optimized inside
today's envelope on the certified Model B yardstick, at λ=2, against a noise
floor of **0.288 points** measured from three zero-edit replicates at the same
effort (unserved sd 0.096).

| candidate | screen rank | gen. cost | unserved | measurable |
|---|---|---|---|---|
| splice 033+034 WESHIGW | 2 | +0.14% | **−0.94%** | yes |
| splice 011+034 WESHIGW | 9 | +0.27% | **−0.86%** | yes |
| splice 005+006 NMURBEAN | 11 | +0.21% | **−0.68%** | yes |
| splice 011+033 WESHIGW | 4 | +0.18% | **−0.62%** | yes |
| splice 001+021 PICBETS | 7 | −0.18% | **−0.51%** | yes |
| splice 008+035 BOASHAN | 8 | −0.01% | **−0.49%** | yes |
| splice 005+021 NMURBEAN | 3 | −0.03% | −0.35% | yes |
| splice 006+021 NMURBEAN | 6 | −0.10% | −0.25% | no |
| splice 002+011 HIGFITN | 53 | −0.19% | −0.16% | no |
| splice 002+034 WESHIGW | 10 | −0.21% | −0.09% | no |
| **splice 002+033 WESHIGW** | **1** | −0.82% | **+0.98%** | yes |
| **splice 007+101 EMO4THW** | **5** | −1.04% | **+1.25%** | yes |

**Confidence.** Moderate-to-high on the ordering, which is what is claimed. The
noise floor is measured rather than assumed, every candidate is solved at
identical effort from an identically-fitted incumbent, and the two harmful
candidates miss by three to four times the floor. Low on the magnitudes: the
path sets use the reduced scenario sweep and the solver runs well below L4, so
these rank candidates and do not size them.

**Interpretation.** The screen ranked `splice|002|033|WESHIGW` first of sixty.
Evaluated properly it is the second-worst of the twelve, and the screen's
fifth-ranked candidate is the worst of all. This is not a small reordering: it
is the top of the list inverting.

The mechanism is visible in the columns. Every candidate that *helps* costs
slightly more generalized cost and serves more people; both candidates that
*hurt* save generalized cost by serving fewer. The screen holds frequency fixed,
so it cannot see the reallocation that follows an edit — it rewards an edit that
makes the network cheaper, and the cheapest edits are the ones that quietly drop
demand. A splice that looks cheap is usually cheap because it dropped someone.

That is the concrete content of "a screen ranks candidates and cannot size
them", and it turns out to be stronger than that phrasing: here the screen does
not reliably rank them either.

**It broke the ladder, which is how it was caught.** The 0/1/2/4 rungs were
composed greedily from screen order, so the first two rungs took the two harmful
candidates and the ladder ran backwards: four edits gave −2.09% generalized cost
for **+4.25%** unserved. Read naively that says geometry hurts. It says the
screen picked badly. The ladder is being recomposed from measured performance;
the screen-ordered run is preserved as `exp2_eval_screenorder.csv` because it is
the evidence, not a failed attempt.

**What would falsify it.** Re-running the two harmful candidates at full effort
and finding they clear the floor in the other direction would mean the low-effort
solve, not the screen, produced the inversion. That is the check to run before
this goes in a write-up.

**Falsification test run twice, 2026-08-29; D19 stands both times.** Both
candidates were re-solved at gate 7's own effort — 400,000 iterations, 20
restarts — alongside three zero-edit replicates *in the same run*, so the floor
is measured at the effort it is applied at rather than carried over from a
cheaper one. The first pass ran under the mislabelled Model A evaluator (D23);
the second, under Model B, is the one that counts. Both are shown, because the
agreement between them is itself the point.

| candidate | screen rank | Model B, ranking effort | **Model B, full effort** | × its floor |
|---|---|---|---|---|
| `splice\|002\|033\|WESHIGW` | **1st of 60** | +1.483% | **+2.119%** | 7.4 |
| `splice\|007\|101\|EMO4THW` | 5th of 60 | +0.153% | **+0.802%** | 2.8 |

*(Under the mislabelled Model A evaluator the same test gave +1.878% and
+0.869%. Same verdict, different model, so the inversion is not a property of
either.)*

Neither crosses zero, let alone the floor in the other direction. **Both are
worse at full effort than at ranking effort** — more search finds more of the
damage rather than recovering from it, which is what should happen if the edit
genuinely drops demand and is not merely under-optimised.

So the inversion is the screen's; it is established at the effort the rest of
the project reports at, and under the authoritative model. D19 may be quoted.

*A caveat on the floors.* Each is 3σ from three seeds, so the floor estimate is
itself noisy — Model B's is 0.130 points at ranking effort and 0.287 at full
effort, which is the opposite of the direction Model A showed. Nothing here
depends on which is larger: both candidates clear both floors by a multiple.

**What would falsify it now.** Nothing available at this effort or model. A
third candidate set, or a screen that re-optimizes frequency, would be needed —
and a screen that re-optimizes frequency is not a screen.


### D20 — Geometry edits do not compose: four individually good splices are jointly worse than none

**Evidence.** The 0/1/2/4 ladder, recomposed from *measured* single-candidate
performance rather than screen rank, each rung solved with frequency
re-optimized inside the same 2,517-vehicle-hour envelope on the certified
Model B yardstick:

| rung | edits | gen. cost vs 0 | unserved vs 0 |
|---|---|---|---|
| 0 | — | — | — |
| 1 | 033+034 WESHIGW | +0.137% | **−0.936%** |
| 2 | + 005+006 NMURBEAN | +0.164% | **−0.485%** |
| 4 | + 001+021 PICBETS, 008+035 BOASHAN | −0.192% | **+0.473%** |

*(These are Model A numbers — see the Model B rebuild below, which reaches the
same conclusion from different figures and a different set of edits.)*

Every one of those four splices, evaluated **alone**, reduces unserved demand:
−0.936%, −0.684%, −0.512%, −0.490%. Their individual effects sum to roughly
−2.6%. Together they give **+0.47%** — worse than making no change at all. Every
figure clears the 0.288-point noise floor measured from three zero-edit
replicates at the same effort.

**Confidence.** Moderate-to-high on the direction and the non-additivity, which
is the claim. Same effort, same envelope, same incumbent-fitting for every rung,
and the reversal is three to ten times the measured floor. Low on the
magnitudes: reduced scenario sweep and sub-L4 effort, so this ranks and does not
size.

**Interpretation.** This is the finding the ladder was built to look for, and it
came back the unwelcome way.

The mechanism is the shared budget. Evaluated alone, a splice gets the entire
vehicle-hour envelope reallocated to exploit it — the optimizer buys frequency
wherever the new through-routing makes it most valuable. Four splices cannot
each have the whole budget. They also *consume* it: through-routing lengthens
the merged line, so vehicle-hours that were buying frequency go into running
the longer route instead. By four edits, the reallocation each one needs is
competing with three others and the envelope is thinner than when they started.

The second edit already hurts: two edits (−0.485%) is worse than one (−0.936%).
There is no accumulation to find here, and the best geometry intervention
discovered is a **single splice**.

**What it means for how Experiment 2 gets reported.** "Which edits should COTA
make?" is not answerable by ranking candidates and taking the top N — the top N
is not the best set of N. Any recommendation is a *set*, evaluated as a set,
and this evidence supports exactly one: through-route 033 and 034 at WESHIGW,
alone. Adding the next-best measured candidate to it costs half the benefit.

**Re-run under Model B, 2026-08-30; D20 survives and gets stronger.** The
numbers in the table above were produced by the mislabelled evaluator (D23).
Both ladders were rebuilt under Model B, at the same effort, with the measured
order re-derived from the corrected single-candidate scores:

| rung | measured order | screen order |
|---|---|---|
| 1 | **−0.585%** | +1.483% |
| 2 | −0.066% | +2.454% |
| 4 | **+1.639%** | +4.201% |

Against Model B's 0.130-point floor: one edit helps, **two edits are
indistinguishable from making no change at all**, and four are worse than doing
nothing by 12.6 floors. The correction did not soften the finding — under Model
A the four-edit rung was +0.473%, under Model B it is +1.639%.

The interaction term, gate 2B-6's quantity, measured on these same rungs:

| rung | members | measured | sum of their singles | interaction |
|---|---|---|---|---|
| 1 | 011+034 | −0.585% | −0.585% | 0.000 pts |
| 2 | + 005+006 | −0.066% | −0.857% | **+0.791 pts** (6.1 × floor) |
| 4 | + 007+101, 008+035 | +1.639% | −0.448% | **+2.086 pts** (16.0 × floor) |

**And the ladder is now forced to compose harmful edits, which is itself the
argument for searching sets.** Under Model B only four of the twelve candidates
are beneficial, and the ladder must take edits on disjoint routes — so after
011+034 and 005+006 it has no beneficial candidate left that avoids routes 011,
034, 005 and 006, and reaches past them to 007+101 and 008+035, both harmful
alone. A greedy ladder cannot decline to grow. That is not a flaw in this
ladder; it is what "the top N is not the best set of N" means operationally,
and it is why Experiment 2B enumerates subsets instead of extending this.

**What would falsify it.** A joint optimization over subsets — rather than a
greedy ladder over singles — finding a two- or four-edit set that beats the
single would show the non-additivity is a property of greedy composition rather
than of the budget. That search is Experiment 2B, and it is the reason 2B
searches sets directly instead of extending this ladder: a greedy ladder can
only ever visit nested sets, and nothing here licenses the assumption that the
best pair contains the best single.


### D21 — Path-level representation buys the same coverage at a quarter of the cost

**What this is, corrected 2026-08-29.** D21 is a **Model B revalidation and
quantification of D3** — the decision-representation question — and *not* a
result of Experiment 2. Experiment 2 is the route-geometry experiment; its
findings are D16, D19, D20 and its conclusion is recorded separately. The two
were run by the same script (`exp2_treatments.py`) on a shared candidate set,
and the shared filename is the whole reason the label slipped. The numbers,
provenance and confidence below are unchanged by this correction; only the
question they answer is restated.

**Scope, and its extension.** The tables below are measured on the **unedited
(control) network**. Whether the advantage survives on edited geometry was the
open question, and it has since been answered on all twelve candidate networks
— see *Confirmed across thirteen networks* at the end of this entry.

**Evidence.** Both treatments optimize frequencies on the unedited network under
the same pinned envelope, and **both plans are then re-scored by the same frozen
Model B evaluator** — the optimizer's own objective is never compared across
treatments.

| treatment | λ | gen. cost | unserved | served | cost per served trip |
|---|---|---|---|---|---|
| route-level | 1 | +3.177% | −5.127% | +2.604% | **+0.559%** |
| route-level | **2** | **+3.071%** | **−5.877%** | **+2.985%** | **+0.084%** |
| route-level | 4 | +3.218% | −6.802% | +3.455% | −0.229% |
| path-level | 1 | −0.888% | −1.906% | +0.968% | −1.839% |
| path-level | **2** | **+0.828%** | **−5.865%** | **+2.979%** | **−2.088%** |
| path-level | 4 | +1.134% | −6.203% | +3.150% | −1.954% |

At λ=2 the two treatments deliver **the same coverage** — −5.877% versus −5.865%
unserved, +2.985% versus +2.979% served, differences well inside the seed noise
Experiment 1 measured. They do not deliver it at the same price: **+3.071%
generalized cost against +0.828%**, a factor of 3.7.

**Confidence.** Moderate. The comparison is structurally sound — one evaluator,
one envelope, identically fitted incumbents, matched effort — and the cost gap
is far larger than anything seed noise produced. Low on magnitudes: this ran at
60,000 iterations / 2 restarts / width 32, well below L4, so it ranks the
treatments rather than sizing the gap.

**Interpretation. The answer to the representation question is yes** — the
path-level representation does uncover materially better plans than the
route-level one under a common evaluator — **and the mechanism is visible in the
last column rather than the first.**

Cost per trip actually served is the column that separates them: path-level
**−2.088%**, route-level **+0.084%**. The route-level plan makes the average
rider very slightly *worse off* and buys its coverage purely by spending more;
the path-level plan makes the average rider better off and buys the same
coverage nearly for free. Both hit the same served-demand number, so an analysis
reporting only coverage would call them equivalent.

The reason is the one D3 identified and this quantifies under Model B: the
route-level optimizer cannot see passengers re-route. When it cuts a headway it
charges the full penalty to everyone on that route, so it never finds the cheap
reallocations that work precisely because riders shift to a parallel service. It
compensates by buying coverage the expensive way.

**The optimizer's own claim, recorded because its size is the finding.** The
route-level optimizer believed it had **63% less unserved demand than the
independent evaluator measures** (−60.9%, −63.2%, −64.2% at λ = 1, 2, 4). It is
not a slightly optimistic optimizer. Its objective is a different function, and
any comparison against a path-level result using that objective would be
measuring the disagreement between two yardsticks rather than the quality of two
plans. The path-level treatment's gap is 0.000% by construction: its optimizer
*is* the evaluator, which is the only reason it is safe to compare them at all —
after both are re-scored.

**Confirmed across thirteen networks, 2026-08-29.** The same script re-ran both
treatments on the control and on each of the twelve frozen geometry candidates —
one envelope, one frozen Model B evaluator, matched effort, both plans
reconstructed and independently re-scored. 72 cells.

Cost per trip actually served, the column that separates the treatments:

| λ | route-level, mean | path-level, mean | networks where path-level wins |
|---|---|---|---|
| 1 | −0.334% | **−1.624%** | **13 of 13** |
| 2 | −0.445% | **−2.257%** | **13 of 13** |
| 4 | −0.534% | **−2.125%** | **13 of 13** |

Unanimous at every λ, on every network. No p-value is attached and none should
be: the thirteen networks share one demand table, one envelope and one base
geometry, and twelve of them differ from the control by a single splice, so they
are nowhere near independent and a sign test's nominal 1-in-8192 would be a
fiction. Unanimity across thirteen dependent replications is what this is, and
it is enough — the effect is not marginal on any of them.

The optimizer's claim gap holds its size everywhere: the route-level optimizer
believes it has **63% to 73%** less unserved demand than the evaluator measures,
on all thirteen. The path-level gap is 0.000% by construction.

**An exploratory observation, flagged as such.** Route-level measured unserved
demand ranges **−1.094% to −7.454%** across the thirteen networks — a spread of
6.36 points — against path-level's **−5.110% to −6.702%**, a spread of 1.59.
Same envelope, same evaluator, same effort, so the spread belongs to the
representation and not to the networks. If it holds it says something stronger
than this entry does: that the route-level representation is not merely more
expensive but substantially less stable under a change of geometry.

It is **not a finding**. It was noticed at five of thirteen networks, with the
remaining eight already queued, and no threshold was committed in advance. The
contamination is recorded in ACCEPTANCE.md under *Pre-registration note:
representation stability across geometry*, written while it was still five. It
can be promoted only against an independent candidate set — the Experiment 2B
networks qualify, having been enumerated before it was noticed — and the
write-up must name which.

**What would falsify it.** Running both treatments at L4 and finding the cost
gap collapses would mean the route-level plans are merely under-searched rather
than structurally blind. That is the check to run before this is quoted with a
number attached; the direction is now established on thirteen networks and is
very unlikely to move, the factor of 3.7 might.



### D23 — Correcting the waiting model reorders the geometry candidates and halves the best effect

*(D22 is reserved for Experiment 2B, which is still running.)*

**How it came up.** `run_exp2_eval.py` never passed `common_lines` to
`build_setup`, so it scored every plan under Model A while its log reported the
harness's Model B (ACCEPTANCE.md, *Defect: the Experiment 2 evaluator was Model
A*). Every candidate was then re-evaluated under the corrected evaluator, at
the same effort, on the same networks, with the same seed. This entry is the
difference.

**Evidence.** All twelve candidates, λ=2, frequency re-optimized inside the same
2,517-vehicle-hour envelope, unserved demand against each model's own zero-edit
solve:

| candidate | Model A | Model B | rank A → B |
|---|---|---|---|
| `splice\|011\|034\|WESHIGW` | −0.860% | **−0.585%** | 2 → **1** |
| `splice\|033\|034\|WESHIGW` | **−0.936%** | −0.485% | **1** → 2 |
| `splice\|005\|006\|NMURBEAN` | −0.684% | −0.272% | 3 → 3 |
| `splice\|011\|033\|WESHIGW` | −0.615% | −0.233% | 4 → 4 |
| `splice\|006\|021\|NMURBEAN` | −0.247% | +0.026% | 8 → 5 |
| `splice\|002\|034\|WESHIGW` | −0.089% | +0.052% | 10 → 6 |
| `splice\|007\|101\|EMO4THW` | +1.251% | +0.153% | 12 → 7 |
| `splice\|008\|035\|BOASHAN` | −0.490% | +0.257% | 6 → 8 |
| `splice\|002\|011\|HIGFITN` | −0.155% | +0.322% | 9 → 9 |
| `splice\|001\|021\|PICBETS` | −0.512% | +0.372% | 5 → 10 |
| `splice\|005\|021\|NMURBEAN` | −0.353% | +0.395% | 7 → 11 |
| `splice\|002\|033\|WESHIGW` | +0.978% | +1.483% | 11 → 12 |

Spearman **ρ = 0.657**, Kendall **τ = 0.515**, n = 12. Largest rank move: five
places. **Six of the twelve change sign** — they reduce unserved demand under
Model A and increase it under Model B.

The measured noise floor also tightens, from **0.288** points to **0.130**, so
Model B is the better-conditioned model as well as the correct one — the same
direction D17 found on the seed replicates. Against their respective floors the
classification goes from **7 beneficial / 3 at the floor / 2 harmful** to
**4 / 2 / 6**.

**Confidence.** High on the reordering, which is the claim. Same networks, same
effort, same seed, same envelope, one variable changed, and the variable is a
documented correction to leg pricing rather than a tuning choice. Moderate on
individual magnitudes: still 60,000/2/32, which ranks rather than sizes.

**Interpretation.** Model A prices a ride leg at the chosen pattern's own
headway; Model B prices it on the combined frequency of every same-route pattern
that can carry the movement. Model A therefore undervalues frequent trunk
service, which runs the most pattern variants — and a splice is precisely an
intervention that merges two lines and changes how many patterns serve a
movement. Geometry edits are the class of change most exposed to this bias, so
it is the ranking of geometry edits that moves most.

**This overturns D16's headline and vindicates its amendment.** D16 concluded
that the geometry ranking does not depend on the waiting model, from an
aggregate Spearman of 0.857 across all edit kinds on the *screen*. Its own
amendment then found that within splices — the only kind that reaches the top
ten — the correlation was **0.336**. Every candidate here is a splice, and 0.657
on a proper evaluation sits between the two. The aggregate figure was measuring
the ease of ranking truncations and extensions, not splices. **D16's headline
should not be quoted; its amendment should.**

**What survives unchanged.** D19: the screen's first-ranked candidate of sixty,
`splice\|002\|033\|WESHIGW`, is still the worst of the twelve, and by a wider
margin under Model B (+1.483%, 11 floors). The screen's inversion is not an
artifact of the evaluator's model.

**What this costs Experiment 2's recommendation.** The claim was "through-route
33 Henderson and 34 Morse at Westview Turnaround, ≈0.9% less unserved demand".
Under the corrected evaluator that edit is worth **−0.485%**, and it is no
longer the best single: through-routing **11 Bryden/Maize and 34 Morse** at the
same turnaround is, at −0.585%. Both use only existing track
(`modelled_share_pct = 0.0`).

**The recommendation does not move, and the reason is arithmetic.** 11+34 leads
33+34 by **0.100 points** against a measured noise floor of **0.130**. The gap
is 0.77 of a floor. *The two leaders are not distinguishable.* Reordering a
recommendation on a difference smaller than the noise the same run measured
would be the D13/D17 mistake — reading a flat optimum as a ranking — committed
one level up, on candidates instead of route-periods.

Gate 9 was then run on 11+34 anyway, because a candidate that had never been
looked at could not be compared at all. It had never been inspected: the
inspection tier selects by *screen* rank, the screen scored 11+34 at −0.017%
unserved, and it fell outside the top eight. `inspect_candidates.py` now takes
`--order-from`, so the tier can be driven by measured performance instead —
which is D19's lesson applied to one more decision that was still taking the
screen's word.

What the inspection found, with 33+34 alongside:

| | `splice\|011\|034` | `splice\|033\|034` |
|---|---|---|
| measured effect | −0.585% | −0.485% |
| running-time model exposure | 0.0% (0 of 280 segments) | 0.0% (0 of 192) |
| cycle time | 61.2 → **91.5 min (+49.4%)** | 43.4 → 59.0 min (+35.9%) |
| vehicle-hours at baseline | **+1.0** | **−0.6** |
| trips per day, the two routes | 38 vs 154 (**1 : 4.1**) | 78 vs 154 (1 : 2.0) |
| stops lost, or left without service | 0 / 0 | 0 / 0 |
| mean headway today, 12 route-periods | 53.2 min | 31.8 min |

Both are clean on the things that disqualify a candidate outright: no stops
dropped, nobody left without service, and no invented track. On everything else
11+34 is the worse proposal. A **91-minute cycle** is a long line to run
reliably, and this model carries no reliability penalty — a documented
limitation, and one that is biased in exactly this direction. It *consumes* a
vehicle-hour where 33+34 releases half of one. And through-routing a 38-trip
route into a 154-trip route means most of 34 Morse still short-turns, so the
through-running benefit reaches about a quarter of its trips.

**So the recommendation stays 33 Henderson + 34 Morse, at the corrected
−0.485%.** Not because it scores better — it does not — but because the two are
inside each other's noise, and on every criterion the model does not represent,
33+34 is the more defensible line. That is a judgement about the proposal and
is labelled as one; the model does not make it.

**What would falsify it.** Re-running both candidates at full effort and finding
the gap between them inside the 0.130-point floor would mean the reordering at
the top is real but the *leader* is not identified — which would leave the
correction standing and the recommendation still open.


### D24 — At full effort no geometry edit does anything, and the half-point benefit was the search

**This retracts Experiment 2's only supportable claim.**

**Evidence.** The two leading candidates re-solved at gate 7's effort — 400,000
iterations, 20 restarts — with three zero-edit replicates *in the same run*, so
the floor is measured where it is applied.

| | ranking effort (60,000/2/32) | **full effort (400,000/20)** | floors |
|---|---|---|---|
| `splice\|011\|034\|WESHIGW` | −0.585% | **+0.060%** | 0.21 |
| `splice\|033\|034\|WESHIGW` | −0.485% | **+0.160%** | 0.56 |

Floor: **0.287 points**, from zero-edit replicates scoring 9749.1, 9748.8 and
9765.1 unserved. `splice|033|034|WESHIGW` scores **9764.8**. Re-running the
*baseline* with a different seed moves it further than the edit does.

Both candidates are inside the noise floor. Neither is beneficial. Neither is
harmful. **At full effort these edits do nothing measurable.**

**Confidence.** High. Matched effort on both networks, one evaluator, one
envelope, the floor measured in the same run at the same effort, and both
results sit inside the replicate spread rather than near its edge. This is the
comparison the project's own standing rule demands — *search effort is matched
whenever two things are compared; an effort gap is a confound, and this project
has already been burned by one* — applied to the geometry claim itself.

**Interpretation. The unedited network was the under-optimized one.** At 60,000
iterations and 2 restarts the baseline had not been solved as well as the edited
networks had, so the edits appeared to be worth about half a point. Give the
optimizer 6.7× the iterations and 10× the restarts and the baseline closes the
entire gap. The effect was never the geometry's. It was the search's, and it was
pointing the wrong way.

That is a nastier failure mode than an under-powered search producing a weak
result. Here the *comparison* was under-powered asymmetrically: both sides ran
at the same nominal effort, and the same effort was not equally sufficient for
both. Matched effort is necessary and it is not sufficient — what has to match
is convergence, and nothing was checking that.

**The asymmetry is the tell, and it is the right way round.** The harmful
candidates stay harmful at full effort — `splice|002|033|WESHIGW` at +2.119%
(7.4 floors) and `splice|007|101|EMO4THW` at +0.802% (2.8 floors). Harm survives
more search; apparent benefit does not. An edit that removes served demand keeps
removing it however well frequency is re-optimized around it, while an apparent
gain can be nothing more than one network's optimum being easier to find than
another's. Any future geometry claim should be checked against this pattern: a
benefit that shrinks with effort was probably never there.

**What Experiment 2 now says.** Twelve splice candidates, evaluated properly:
**six do measurable harm, and none does measurable good.** The best available
geometry intervention in this candidate set is *no geometry intervention*. The
claim "through-routing 33 Henderson and 34 Morse reduces unserved demand by
about 0.5%" is withdrawn — it was 0.9% under Model A, 0.5% under Model B at
ranking effort, and **0.0% under Model B at the effort the rest of the project
reports at**.

**What this does not touch.** Experiment 1. Its headline is certified at exactly
this effort with exactly this replicate design, and its −6.65% is 104σ against
its own floor. The frequency result never depended on the geometry result.

**What it means for Experiment 2B.** Stage A ranks 240 subsets at the effort
this entry shows to be unreliable for singles. That does not void the sweep —
gate 2B-5 already requires the headline to be certified at full effort, and gate
2B-7 already names the null result as permitted and expected. It sets the prior
for Stage C, and the prior is now *no measurable effect*. If a subset does clear
the floor at full effort when no single does, that is a real interaction and a
genuinely interesting result; if none does, Experiment 2 closes with a clean
negative.

**What would falsify it.** A subset in Experiment 2B clearing the full-effort
floor, or either candidate clearing it on an independent candidate set at this
effort. Not a re-run at ranking effort: that is the measurement this entry
disqualifies.


### D22 — All 240 feasible geometry subsets: nothing composes, and nothing beats one edit

**The exhaustive answer to "which combination of these edits should COTA make?"**
Not a heuristic, not a sample: every structurally feasible subset of the frozen
twelve-candidate set, 240 of them, each with frequency re-optimized inside the
same 2,517-vehicle-hour envelope and scored by the frozen Model B evaluator.

**Evidence.** Best set at each cardinality, against no edit at all:

| edits | best set | unserved vs no edit |
|---|---|---|
| 0 | — | 0.000% |
| 1 | `011+034 WESHIGW` | **−0.585%** |
| 2 | + `005+006 NMURBEAN` | −0.066% |
| 3 | + `007+101 EMO4THW` | +0.728% |
| 4 | + `008+035 BOASHAN` | +1.639% |
| 5 | + `001+021 PICBETS` | +2.629% |
| 6 | + `002+034 WESHIGW` | +3.920% |

Monotone in cardinality across the whole feasible space. Each additional edit
costs roughly a point of unserved demand.

* **Not one of the 227 multi-edit sets beats the best single.** Not by the
  0.130-point floor — *at all*. The best single is −0.585% and no set of two or
  more reaches it.
* **All 227 have a positive interaction term above the floor.** Every one is
  *substituting*: the set delivers less than its members promised separately.
  There is not a single synergistic combination in the entire feasible space.
* **Only 4 of 240 sets beat doing nothing by more than the floor**, and all four
  are singles.
* The cardinality winners are **not nested**: the best 3-set is not the best
  2-set plus one. Gate 2B-3 permitted that and it is what happened, which is why
  a greedy ladder could not have found these.

**Gate 2B-8 passes.** Three of the 240 subsets are the rungs of D20's
measured-order ladder, solved earlier by a different script through a different
code path. Stage A reproduces them to **0.0004, 0.0001 and 0.0002 points**
against a 0.130-point floor. Their expected values were committed to
ACCEPTANCE.md before Stage A reached any of them.

**Confidence.** High on the ordering and on the universality of substitution —
this is a complete enumeration, not a search, so there is no candidate ordering
to defend and no possibility that the answer is an artifact of where the search
started. Discovery-stage on the magnitudes: 60,000/2/32, which gate 12 labels as
ordering candidates rather than concluding anything about sizes.

**Interpretation.** The mechanism is one shared vehicle-hour envelope. Evaluated
alone, a splice gets the whole budget reallocated to exploit it. Two splices
cannot each have the whole budget, and through-routing also *consumes* it — the
merged line is longer, so hours that were buying frequency go into running it.
The remarkable part is not that this happens but that it happens **every time**:
227 sets, zero exceptions. Non-additivity here is not a property of particular
unlucky combinations. It is a property of the constraint.

**And the null is the answer.** Gate 2B-7 named it before any subset was solved:
*no multi-edit set beating the best single is a permitted and publishable
outcome, and D20 makes it the prior.* It is what happened. Combined with D24 —
where the best single itself lands inside the noise floor once both sides are
solved to convergence — Experiment 2's complete answer is:

> **Within this candidate space, no geometry intervention measurably helps, and
> every combination is worse than its best member.**

That is a real result and it is worth having. It says COTA's route structure, at
least along the through-routing dimension this candidate generator explores, is
not leaving passenger benefit on the table that a vehicle-hour-neutral
recombination could pick up. The budget is the binding constraint, not the
topology.

**Certified, and the certification is itself the point.** Stage C re-solved the
leader `splice|011|034|WESHIGW` and the zero-edit set at gate 7's effort —
400,000 iterations, 20 restarts — under three seeds each:

| | discovery effort | **certification effort** |
|---|---|---|
| effect vs no edit | −0.585% | **+0.007%** |
| floors | 4.5 | **0.02** |

Floor 0.287 points, from zero-edit replicates at 9749.1, 9748.8 and 9765.1.
**Verdict: NULL — inside the floor**, at two hundredths of it.

And gate 12 fired on its own: the effect moved **0.591 points** between discovery
and certification effort, more than twice the floor, so the run recorded
`gate_12_stable: false` and warned that the discovery ranking is not trustworthy
for this set. That check was written the day before, after D24 exposed the same
failure by hand. It caught it automatically this time, which is the difference
between a lesson and a control.

**What would falsify it.** A candidate generator that proposes something other
than splices — the extends, truncates, straightens and reroutes that never took
a top-ten slot and were never evaluated — or a mutation space large enough to
change route structure rather than recombine it. That is Experiment 3, and this
is the result it has to beat.

---

### D25 — The geometry null survives the budget-weight sweep, and the substitution law does not

**Stage B asked whether Experiment 2B's answer is a property of λ=2.** The whole
2B enumeration was scored at one point on the cost/coverage trade-off. If the
null were an artifact of that choice, a different λ would produce a different
winner, and the recommendation "make no geometry change" would be a
recommendation about a scalarization rather than about the network. So the 16
promoted sets were re-solved at λ ∈ {1, 2, 4}.

**The leader does not move.** `splice|011|034|WESHIGW` is the best set at every
λ tested:

| λ | best set | unserved vs no edit | best multi-edit set |
|---|---|---|---|
| 1 | `011+034 WESHIGW` | **+2.155%** | +4.396% |
| 2 | `011+034 WESHIGW` | −0.585% | −0.066% |
| 4 | `011+034 WESHIGW` | −0.510% | +0.019% |

Three conclusions hold at all three weights: the same single edit leads, no
multi-edit set beats the best single, and harm increases monotonically with
cardinality. Stage C certified that leader as null (D22), and this says the
certified thing was not a λ=2 accident.

**At λ=1 every geometry set is harmful, and by a lot.** The best of the sixteen
is +2.16% unserved; the worst is +22.1%. λ=1 prices unserved demand low enough
that the optimizer sells coverage for generalized cost — gc runs 0.9 to 2.6%
*better* than no edit while unserved blows out. That is the optimizer doing what
it was asked, and it means the geometry candidates' only measurable effect at
this weight is to make the coverage sacrifice cheaper to make.

**And the substitution law is λ≥2, not universal.** D22's strongest claim was
that all 227 multi-edit sets substitute — zero synergy in the entire feasible
space. At λ=4 that holds (all five computable sets, +0.67 to +1.36 points). At
λ=1 **the sign flips**: all five are synergistic, −1.73 to −2.63 points. The
combination is less harmful than its members promised separately.

The mechanism is the same constraint read from the other side. At λ≥2 the
optimizer spends the envelope chasing coverage, so two edits contend for one
budget and each gets less than it did alone. At λ=1 it is not chasing coverage
at all, and what the edits deliver is coverage *loss* — which saturates, because
the demand at the affected stops can only be abandoned once. Sub-additive harm,
not synergy in any useful sense. Calling it "synergistic" is what the sign
convention returns; the interpretation is saturation, and the honest statement
of D22's law is: **under a budget the optimizer is actually spending, geometry
edits substitute.**

**Confidence.** Ordering: high — the leader is stable across a 4× range of λ,
and cardinality monotonicity holds at every weight. Magnitudes at λ ∈ {1, 4}:
discovery-stage and weaker than λ=2's. Those weights ran one seed each, so no
replicate spread was measured and there is **no noise floor at λ=1 or λ=4** —
gate 2B-4 therefore permits no headline claim from them, and none is made. They
order; they do not conclude. The interaction terms at those weights are
computable only for sets whose members were all promoted, which is why five of
eight multi-edit rows carry one and three do not.

**What it changes.** Nothing about the recommendation, which is the point of
running it. It removes one of the two remaining ways the Experiment 2 null could
have been an artifact — the scalarization — and leaves the other standing: the
candidate space is splices only. That is Experiment 3's brief.

---

## Not yet earned

Geometry findings stay out of this log until they survive: frequency
re-optimization, the frozen yardstick, matched effort, a seed check, and a hand
inspection against the network. Screening evidence is for choosing what to
evaluate, not for concluding.
