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

### D26 — Substitution is universal but its STRENGTH scales with what an edit costs

**Experiment 2B's law survives; its consequence does not.** Across all 240
feasible subsets there, every one of the 227 multi-edit sets delivered less than
the sum of its members — and, more strikingly, **not one beat the best single**.
The combination was worse than its own best member, every time.

Experiment 3's Phase A2 reproduces the first half and inverts the second.

**Evidence.** Every multi-mutation state scored so far, against the same-run
null, at 2B's discovery effort:

| k | measured | sum of members | interaction | beats best single? |
|---|---|---|---|---|
| 4 | −0.684% | −1.318% | **+0.634** | yes |
| 4 | −0.658% | −1.306% | **+0.648** | yes |
| 3 | −0.642% | −1.063% | **+0.422** | yes |
| 3 | −0.593% | −1.032% | **+0.439** | yes |
| 2 | −0.555% | −0.778% | **+0.223** | yes |
| 2 | −0.470% | −0.660% | **+0.190** | yes |

**11 of 11 substitute. 11 of 11 beat the best single (−0.404%).** In 2B that
second column was 0 of 227.

**The mechanism is the envelope, read more carefully than D22 read it.** D22
attributed non-composition to one shared vehicle-hour budget: two splices cannot
each have the whole envelope reallocated to exploit them. That is right, and it
is incomplete. What matters is *how much of the envelope an edit consumes*.

A splice is expensive. Through-routing lengthens the merged line, so the edit
spends budget merely to exist, and a second splice competes for what is left
before it can deliver anything. Substitution is then near-total: the pair
delivers less than either alone.

`add_stop` and `extend` are cheap. A stop inserted at a 400 m detour, or a route
continued a few stops further, costs a small slice of running time. Two of them
fit inside the budget with room to contribute, so they substitute *partially* —
each gets less than it would alone, but the pair still beats either.

> **Substitution is universal. Its strength is a property of the edit's cost,
> not of geometry editing as such.** 2B measured the expensive corner of that
> spectrum and generalized from it.

**Why this matters beyond bookkeeping.** D20 and D22 were the reason Experiment
3's contract forbids ranking mutations and taking the top N, and that reasoning
is untouched — everything here still substitutes, so summing member effects
still overstates, by 0.19 to 0.69 points. What changes is the expectation of
what a search should find. In 2B the correct answer was one edit or none. Here
the correct answer is plausibly a *set*, and a search that stopped at the best
single would leave roughly 40% of the available effect unclaimed.

**Confidence.** The qualitative pattern is consistent across all 11 multi-states
scored and across cardinalities 2, 3 and 4, with interaction growing
monotonically in k. The magnitudes are **discovery-stage** and gate 12 applies
with full force — D24 is precisely the case where a discovery-effort leader
evaporated at certification, and 2B's own −0.585% leader certified as +0.007%.
Nothing here is promoted on these numbers.

**What would falsify it.** Certification at 400,000/20 showing the multi-state
margins collapsing into the floor while the singles hold, which would mean the
apparent composition was search noise rather than mechanism. Or a cheap-edit
pair that substitutes totally, which would break the cost-scaling story.

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

## D27 — the optimizer was chosen by the treatment

*Found 2026-08-31, mid Experiment 3 Phase A2, by aggregating a `log.warning`
that had been printing since Experiment 1 and had never been counted.*

`optimize_frequencies` accepts an `initial` plan only if that plan, **once
snapped to the headway ladder**, still fits the envelope. `fit_incumbent`
fits in continuous headway space; the snap that follows moves roughly half the
route-periods to a *shorter* headway, which costs vehicle-hours. The
rescaled-then-snapped incumbent therefore lands back outside the envelope, the
optimizer logs `incumbent plan is infeasible under this budget`, discards it,
and runs `_greedy_build` — the build the caller disabled with
`greedy_start=False`.

**The fallback is decided by the treatment.** Over 156 Stage A solves:

| kind | fell back | | kind | fell back |
|---|---|---|---|---|
| extend | 40/40 (100%) | | truncate | 0/14 (0%) |
| reroute | 21/22 (96%) | | straighten | 0/12 (0%) |
| splice | 12/13 (92%) | | zero-edit control | 0/3 (0%) |
| add_stop | 52/63 (83%) | | every k=2, k=3 state | 46/46 (100%) |

Route-*lengthening* edits push the incumbent over the envelope; route-*shortening*
edits and the unedited control never do. Experiments 2 and 2B are the same:
`exp2_treatments_full` 72/72 solves, `exp2b_stageA_s0` 32/32, `exp2b_stageA_s1`
25/25, `exp2b_stageB` 30/32.

**And the two optimizers do not agree.** Same state, same seed, same
60000/2/32 effort, only the start set changed:

| state | incumbent start | greedy | both, best kept |
|---|---|---|---|
| zero-edit control | 2,962,743 | **2,956,121** | 2,956,121 |
| splice-011-034-WESHIGW | (fell back) 2,957,680 | 2,957,680 | 2,957,680 |

Greedy is **better**, by 0.224% of objective on the control — 5.7× the 0.0391%
noise floor, and larger than the mean measured effect of *any* mutation kind.
The direction is the opposite of the code comment claiming greedy "converges to
a worse optimum than the incumbent start": greedy spends the budget to 2515.1
of 2517.2 vehicle-hours, while the repaired incumbent start reaches only 2504.5
and the exchange search cannot spend the remainder back.

So the control was optimized by the weaker method and the treatments by the
stronger one — a handicap on the control, correlated with the treatment.

**What it does to the published numbers.** For 2B's own candidate:

| comparison | objective | unserved |
|---|---|---|
| published, mixed start sets | −0.1709% | **−0.5846%** |
| like for like, both states on `both` | **+0.0528%** | **+0.0931%** |

The sign flips. The −0.5846% unserved reduction — the number
`exp3_score_invariant.py` was built to reproduce, and reproduces exactly —
becomes a +0.0931% *increase*, inside the 0.130% unserved floor.

Across the A1 census the correlation between a kind's greedy-fallback rate and
its mean objective is **r = −0.711** (n = 8 kinds): the kinds that fell back
score better. The two kinds that never fell back, `truncate` and `straighten`,
are the two that were already being compared like-for-like against the control
— and they are the two that show no effect (+0.047%, −0.002%).

**What survives.** Experiment 2B certified NULL at certification effort
(400000/20/0, 3 seeds), not at discovery effort, and a finding of *no
difference* is not manufactured by handicapping the control. Nothing here says
2B's certification is wrong; it says 2B's *discovery* ranking, and all of
Experiment 3 Phase A1 and A2 so far, ranked states partly by which optimizer
each one happened to receive. `splice` also ranks near-worst *despite* getting
the better optimizer, so geometry effects are real — it is the magnitudes and
the ordering among the leaders that are not trustworthy.

**Resolved: it is a discovery-effort problem only.** The zero-edit control,
same state, same seed, both start sets, at both efforts:

| effort | incumbent start | greedy | gap | vs 0.0391% floor |
|---|---|---|---|---|
| discovery 60000/2/32 | 2,962,743 | 2,956,121 | 0.2240% | **5.7x** |
| certification 400000/20/0 | 2,956,364 | 2,956,121 | 0.0082% | **0.21x** |

Greedy is unmoved by ten times the effort (2,956,121 either way): it lands in
the right basin immediately. The incumbent start closes on it — 2,962,743 to
2,956,364, a 0.2153% climb — once it has twenty restarts instead of two. At
certification effort the residual gap is a fifth of the noise floor.

So:

* **Experiment 2B's certified NULL stands.** It was certified at 400000/20/0
  over three seeds, where the start set does not decide the answer. A null is
  not manufactured by a bias that pushes toward finding effects.
* **Experiment 3 Phase A1 and A2 are contaminated.** Both ran at discovery
  effort, where it does.
* **The Stage B and C gates are sound as written**, because they certify. Gate
  12 — convergence matched, not nominal effort — is doing exactly the job it
  was written to do.

**The remediation is small.** A state that fell back already sat in the right
basin, so `starts="both"` would change nothing for it. Only states that were
*accepted* on the incumbent start were scored in the wrong one: **40 of 115**,
every one of them cardinality 1, listed in `outputs/exp3/rescore_needed.txt`
(12 `straighten`, 12 `truncate`, 6 `add_stop`, 3 `change_terminal`, the three
null replicates and the zero-edit control, and one each of `reroute`, `splice`,
`split`). All 46 of A2's k=2 and k=3 states already used greedy. About 4.7
hours re-scores the census; A2's states need nothing but a corrected
comparison point, which is already measured.

**The fix.** `starts="both"` — repaired incumbent *and* greedy, best kept: the
only start set whose composition does not depend on the treatment, and never
worse than either alone. `repair_to_ladder` walks a snapped plan back onto the
ladder inside the envelope so the incumbent branch is genuinely available.
Default remains `"incumbent"` so no recorded number silently changes meaning.

**The lesson, which is rule 16.** A `log.warning` that fires on two thirds of
runs is not a warning, it is a code path. This one ran for three experiments.
Nothing checked how often it fired, because nothing was *counting* — the line
was visible in every log and invisible in every summary.


## D28 — the effort ladder's iteration count is not the lever

*Measured 2026-08-31 while scoping D27.*

`_exchange_search` bounds itself by total model evaluations, and the effort
ladder's first number is that bound: 60000 for discovery, 400000 for
certification. At certification effort each restart terminated after roughly
**4,000 evaluations of the 400,000 it was allowed** — the search runs out of
improving moves (`applied_this_pass == 0`) long before it runs out of budget.

So the iteration count is nominal for this problem at this size. What actually
separates discovery from certification is the **restart count**: 2 versus 20.
Greedy reached 2,956,121 at both efforts and never improved across twenty
restarts; the incumbent start needed nineteen of them to climb from 2,962,743
to 2,956,364.

Two consequences:

* A run reporting "certification effort 400000/20/0" is not doing 6.7x the
  search of a 60000/20/0 run — it is doing the same search. Effort claims
  should quote restarts, and gate 12 should read convergence off restarts.
* A certification solve is ~25s per restart here, not the hour its iteration
  count suggests. Certification is cheaper than budgeted, which is worth
  knowing before Stage B is scheduled.


## D29 — an observed link is not an observed turn

*Measured 2026-08-31 on the frozen Experiment 4 route pool.*

The Experiment 4 pool reports **`modelled_share = 0.0` for all 206 lines**:
every directed link in every proposed line is one COTA already drives. That
number is correct and it was over-read. It says nothing about the *turns*.

A line stitched from two observed corridors meets at a junction. `A→B` observed
and `B→C` observed does not make `A→B→C` observed — the movement through B may
be one no bus has ever made. Checking both directions of each line against the
2,952 observed links and the consecutive edge-pairs behind them:

| evidence class | lines | share |
|---|---|---|
| 0 — legacy sequence (operated today) | 41 | 19.9% |
| 1 — observed-turn synthesis (new line, every link *and* turn observed) | 15 | 7.3% |
| 2 — observed-edge synthesis (every link observed, ≥1 novel turn) | **150** | **72.8%** |
| 3 — modelled geometry (≥1 unobserved link) | 0 | 0.0% |

**150 of 206 lines ask for at least one turn COTA has never operated**, and the
generator breakdown is exactly where it would be expected:

| generator | lines | with novel turns |
|---|---|---|
| crosstown | 40 | **40 (100%)** |
| od | 60 | 59 |
| terminal | 40 | 30 |
| trunk | 25 | 21 |
| legacy | 41 | 0 |

Crosstown generation is the whole point of recombination and it is also, by
construction, the operation that invents turns: joining two radial corridors at
a junction is a novel movement through that junction unless some route already
makes it.

Within a line the novel turns are a minority — the worst offenders sit at
82–96% observed turns — so this is not "these routes are fictional". It is that
the evidence is *weaker than the modelled share implies*, and the difference
was invisible because nothing measured it.

**Class 2 is reported, not rejected.** An unobserved turn between two observed
corridors is weaker evidence, not proof of impossibility; a bus that can drive
`A→B` and `B→C` can usually drive `A→B→C`, and where it cannot, the reason is a
banned left or a physical island that a turn-level flag is the right way to
surface. A gate invented after seeing these numbers would not be a gate.

**The wording this replaces.** "Every route is priced entirely on links COTA
already drives" becomes: *every route uses directed links observed in current
COTA service; transition-level support is tracked separately, because novel
combinations of observed links may still imply unobserved turns.*


## D30 — the fallback states were already in the winning basin

*Measured 2026-08-31, before the Experiment 3 remediation ran, because the
40-state remediation set was an inference and not yet a demonstrated
invariant.*

A state whose incumbent was rejected ran `_greedy_build` alone. Under
`starts="both"` it gets greedy **and** a repaired incumbent, best kept — so
`both` cannot make such a state worse. Nothing showed it could not make one
*better*, and if it could, the 40-state list was incomplete.

Eight previously-fallback states, stratified across cardinality and mutation
kind, each run at the original discovery effort under `starts="greedy"` and
`starts="both"` with everything else identical:

| state | k | greedy | both | Δ |
|---|---|---|---|---|
| A2 leader | 4 | 2,943,013.3307 | 2,943,013.3307 | 0 |
| k=2 | 2 | 2,946,056.4606 | 2,946,056.4606 | 0 |
| k=3 | 3 | 2,943,490.7558 | 2,943,490.7558 | 0 |
| k=4 | 4 | 2,943,287.3456 | 2,943,287.3456 | 0 |
| add_stop single | 1 | 2,950,538.0418 | 2,950,538.0418 | 0 |
| extend single | 1 | 2,954,048.7671 | 2,954,048.7671 | 0 |
| reroute single | 1 | 2,951,408.5162 | 2,951,408.5162 | 0 |
| splice single | 1 | 2,957,680.4901 | 2,957,680.4901 | 0 |

**Maximum |Δ| across all eight: 0.000000000.** Not "within tolerance" —
bit-identical, with **identical frequency-plan hashes 8/8**, and `both`
selecting the greedy arm **8/8**. The repaired incumbent never won, on any
state, at any cardinality.

Each `greedy` arm also reproduced its recorded Phase A1/A2 objective to
**0.000000000**, so a difference under `both` could not have been blamed on
drift somewhere else in the chain.

**Therefore the remediation set is exactly the states *accepted* on the
incumbent start** — 40 of 115, all cardinality 1, in
`outputs/exp3/rescore_needed.txt`. The 75 fallback states, and every one of
A2's k≥2 states, were already scored in the basin `both` selects, and
re-scoring them would return the same numbers at a cost of about nine hours.

This is what the invariant is worth: it converts "we think only 40 need
redoing" into "we measured that the other 75 cannot move", and it cost eight
states of compute to buy.

*Scope note.* The measurement covers this remediation, at discovery effort, on
this pool. It is not a general claim that a repaired incumbent never beats
greedy — D27 measured the reverse relationship at certification effort, where
the incumbent start climbs to meet greedy. The claim is bounded to the states
being re-scored and the effort they are re-scored at.


## D31 — Experiment 2B's certified NULL survives matched starts

*Retested 2026-08-31, corrective plan section 5.*

2B certified `splice|011|034|WESHIGW` as NULL at 400000/20/0 over three seeds —
with `starts="incumbent"`, under which the control kept its incumbent start and
the candidate silently ran a greedy build instead (D27). The verdict had to be
re-established with a start policy the treatment does not choose.

Control and candidate, the same three seeds, the same effort, `starts="both"`
for every cell, through the comparison firewall:

| seed | objective | unserved |
|---|---|---|
| 20260825 | +0.0528% | +0.0931% |
| 20260826 | +0.0528% | +0.0931% |
| 20260827 | +0.0566% | +0.0843% |
| **mean** | **+0.0540%** | **+0.0902%** |

Against 2B's own 0.287-point unserved floor that is **0.31 of one floor**.

| | unserved effect | floors | verdict |
|---|---|---|---|
| 2B as recorded, mixed starts | +0.0065% | 0.02 | NULL |
| this retest, matched starts | +0.0902% | 0.31 | **NULL** |

**The conclusion holds, and its sign never wavers.** The effect is roughly
fourteen times larger under matched starts and still less than a third of the
floor — and it is *positive at every seed on both quantities*, meaning the
through-routing is worse than doing nothing, not better. The direction is the
same one 2B reported; only the magnitude moved, and it moved further from the
claim rather than towards it.

Two things worth keeping from this:

* **Discovery said −0.5846%. Certification with matched starts says +0.0902%.**
  The discovery number was wrong in sign as well as size, and both errors —
  the optimizer asymmetry and the effort shortfall — pushed the same way.
* **2B had already seen the effect vanish.** Its own record carries
  `discovery_effort_pct −0.5846` against `effect_pct +0.0065` and
  `gate_12_stable false`. It attributed that to effort and was half right; D27
  supplies the other half. The record and the mechanism now agree.

The original certification artifact is preserved as
`outputs/exp2b_certification.superseded.json`, stamped SUPERSEDED FOR
QUANTITATIVE INTERPRETATION. The verdict itself is marked confirmed, not
replaced.


## D32 — fixing the start policy collapsed the noise floor to zero

*Found 2026-08-31, in the first four cells of the corrected re-score.*

The corrected zero-edit control and its three replicates returned **bit-identical
objectives**: 2,956,120.583955 at every seed. 3σ of that spread is exactly
**0.00000%**.

This project has been here before, by a different route. The note in
`exp3_score_invariant.py` reads: *"Without refitting the incumbent, every solve
reported `exchanges=0` and three seeds returned BYTE-IDENTICAL results — a zero
noise floor, which licenses every margin that is not precisely nil."* Fixing
D27 reproduced the symptom the D27 fix was partly written to cure.

**Mechanism.** `_greedy_build` takes no RNG; it is fully deterministic. The
perturbation restarts *are* seeded, but at two restarts they never escape
greedy's basin, so the seed never reaches the answer. Since `starts="both"`
selects greedy on every state measured — 8 of 8 in D30, 4 of 4 here — the whole
discovery pipeline is deterministic.

At certification effort it is not, because twenty restarts occasionally escapes:

| effort | starts | seed spread | 3σ as % of mean |
|---|---|---|---|
| discovery 60000/2/32 | both | 0 | **0.00000%** |
| certification 400000/20/0 | both | 112.06 | 0.00657% |
| discovery 60000/2/32 | incumbent *(the contaminated census)* | — | 0.039% |

**Why this is not cosmetic.** Determinism is not accuracy. A deterministic
heuristic sitting 0.5% from optimum on one geometry and 0.1% on another produces
a 0.4% "effect" that is pure solver artifact and reproduces perfectly every
time. Replicate spread bounds solver *variance*; it never bounded solver
*error*, and with the variance at zero there is nothing left for it to bound.

**Consequence.** The corrected A1 census can rank states and report magnitudes.
It cannot carry a "clears the floor" column, because under the corrected
pipeline that column would mark every nonzero difference as material. The
materiality threshold has to come from a measurement of optimization *error* —
which is what an exact or bounded frequency benchmark measures, and the reason
that benchmark is the next piece of work rather than a later one.

The floor quoted in the superseded A1 census (0.039%) was itself measured on the
contaminated path, where the seed reached the answer only because the incumbent
start did. It should not be carried forward either.


## D33 — the Gen1 frequency heuristic is locally optimal almost everywhere, and its error is not treatment-correlated

*Measured 2026-08-31. 75 cells: 5 networks × 5 strata × 3 neighbourhood sizes.*

The corrected census has no materiality threshold because replicate spread
measures solver *variance* and the corrected pipeline is deterministic (D32).
This measures solver *error* instead.

**Method.** All but *N* route-periods of 173 are pinned to a one-rung ladder;
the free ones keep three rungs centred on the plan Gen1 actually delivered on
the full problem. Every one of the 3^N combinations is priced with the real
evaluator, so the benchmark objective and the production objective are
*identical* — the reduction is in the decision space, not the objective. That
matters: the Gen1 objective does not separate, because a path's waiting cost
depends on the combined frequency of every same-route pattern serving its
boarding stop then its alighting stop, so a MILP would have to linearize or drop
that coupling and would then be benchmarking something else.

### Q1/Q2 — the gap and its distribution

| | |
|---|---|
| cells with any gap at all | **9 of 75** |
| median | +0.000000% |
| mean | +0.000149% |
| 95th percentile | +0.001440% |
| maximum | **+0.001837%** |

By stratum, and the pattern is structural rather than random:

| stratum | mean | max | cells with a gap |
|---|---|---|---|
| `peak` | +0.000655% | +0.001837% | **6 of 15** |
| `common_lines` | +0.000082% | +0.000617% | 2 of 15 |
| `offpeak` | +0.000009% | +0.000129% | 1 of 15 |
| `weak_interaction` | 0 | 0 | 0 of 15 |
| `seeded_random` | 0 | 0 | 0 of 15 |

The heuristic's suboptimality sits almost entirely in the **peak** route-periods
and secondarily in the **common-lines** ones — exactly where demand is heaviest
and where Model B's waiting term couples route-periods together. Where the
problem separates, the heuristic is exactly optimal in every cell tested.

### Q3 — does the error move with the treatment?

| network | mean gap | max | cells with a gap |
|---|---|---|---|
| control | +0.000367% | +0.001837% | 3 |
| `lengthen_add_stop` | 0 | 0 | 0 |
| `lengthen_extend` | +0.000288% | +0.001440% | 3 |
| `shorten_truncate` | +0.000091% | +0.000617% | 3 |
| `shorten_straighten` | 0 | 0 | 0 |

Paired on identical subproblem shape (same stratum, same size), the largest
control-minus-treatment difference is **0.001837 percentage points**. There is
no sign of the lengthening/shortening split that D27 found in the *start
policy*: two of the four treatments show no gap at all, and the two that do
straddle the control rather than sitting to one side of it.

### Q4 — what this licenses, and what it does not

**0.0018 percentage points** is the largest differential error observed.
Measured effects in the corrected census run two to three orders of magnitude
larger.

**What this is.** A local optimality check. Each cell varies at most 10
route-periods of 173, across three ladder rungs centred on the delivered plan,
and establishes exactly — under the production objective — whether the delivered
answer is optimal within that neighbourhood.

**What this is not.** It is not the heuristic's distance from the global
optimum, and the figure must never be quoted as though it were. A plan can be
optimal in every neighbourhood sampled here and still sit far from the best plan
reachable by moving twenty route-periods at once, or any of them more than one
rung. **Local optimality is necessary for global optimality and nowhere near
sufficient.** Notice also that N=6, N=8 and N=10 find almost the same thing:
widening the neighbourhood barely helped, which is consistent with a genuinely
local optimum and equally consistent with the enumeration being too narrow to
reach whatever else is out there.

**How to use it.** As a *lower* bound on the differential-error bound; the
full-problem differential can only be larger. A census margin below 0.0018
points is not distinguishable from treatment-correlated solver error. A margin
above it is **not** thereby established — it is only not excluded by this
measurement, which is a much weaker statement and must be written as such
wherever the census is reported.

## D33-B — at Stage B effort the optimization gap did not shrink, and it moved into the control

*Measured 2026-09-02. 375 cells: 5 networks × 5 Stage B seeds × 5 strata × 3
neighbourhood sizes, anchored on plans whose digests were verified against the
Stage B receipts.*

D33 was measured at discovery effort and preregistration §7 forbids that figure
from transferring. This is the re-measurement, designed in
`EXPERIMENT3_D33_STAGEB_DESIGN.md` before any gap here was computed. Only the
anchor changed: the delivered plan now comes from the frozen Stage B
configuration on each of the five predeclared seeds. The exact reference is
exhaustive enumeration and has no effort parameter.

**The design predicted the gap would shrink with more search. It did not.**

| | discovery effort | Stage B effort |
|---|---|---|
| max gap | 0.0018370% | **0.0018970%** |
| cells with any gap | 9 of 75 | 17 of 375 |

That prediction was written down in advance precisely so that being wrong would
be a result rather than something to explain away. Ten times the restarts bought
no reduction in the worst neighbourhood gap.

### Where the gap went is the finding

| network | max gap | cells with a gap |
|---|---|---|
| **control** | **0.0018970%** | **9 of 75** |
| `extend-025` | 0.0009392% | 3 of 75 |
| `truncate-035` | 0.0003614% | 5 of 75 |
| `add_stop-010` (the leader) | **0** | **0 of 75** |
| `straighten-021` | **0** | **0 of 75** |

At discovery effort the gap straddled the control. At Stage B effort it sits
**almost entirely in the control arm**, and two treatments — including the
leader — are locally optimal in every one of their 75 cells. The paired
differential is therefore positive throughout (mean +0.00022%): the control is
solved *less* well than the treatment it is being compared against.

**That is the shape of the Experiment 2 artifact** — D24's "the unedited network
was the under-optimized one", which inflated an apparent geometry benefit until
gate 12 exposed it. The same asymmetry is present here, in the same direction,
and would inflate every measured treatment effect.

**It is three orders of magnitude too small to matter.** The largest
differential is 0.0018970%, against a leader margin of 0.18657% — a ratio of
**98×**. The smallest certified margin, `straighten-021` at 0.00780%, is 4.1×
the bound, and that candidate was measured directly with a gap of exactly zero.

**Verdict: PASS. 0 of 30 certified candidates vetoed.**

By stratum the concentration also moved: `peak` 12 of 75 and `offpeak` 5 of 75,
with `common_lines`, `weak_interaction` and `seeded_random` at exactly zero —
where at discovery effort the secondary concentration was in `common_lines`.

### What this still does not license

Unchanged from D33's Q4, and it must travel with the figure: this is a **local**
optimality check over at most 10 of 173 route-periods across three ladder rungs.
It is a *lower* bound on the differential-error bound; the full-problem
differential can only be larger. A margin above it is **not thereby
established** — it is only *not excluded* by this measurement.

## D34 — the evaluator is not invariant to pattern identifier renaming

**Found by the Experiment 4 substrate's equivalence test**, which is exactly the
check `EXPERIMENT4_CONTRACT.md` calls "the one most likely to fail quietly": do
not trust a new representation until it reproduces a number the old one already
produced.

The same network, scored twice through the same `solve_on_network`, differs when
its patterns are renamed and re-sorted:

| field | ids+order preserved | ids renamed, sorted |
|---|---|---|
| `generalized_cost` | 0.000e+00 | 9.410e-05 |
| `unserved_demand` | 0.000e+00 | 5.878e-04 |
| `served_demand` | 0.000e+00 | 2.729e-04 |
| `revenue_veh_hours` | 0.000e+00 | 4.099e-04 |
| **`peak_vehicles`** | 0.000e+00 | **8.568e-04** |
| `gc_per_served_trip` | 0.000e+00 | 3.669e-04 |

Exact on every field when order is preserved; **worst 8.568e-04, on peak
vehicles**, when it is not.

The geometry, segment times, stop set, trip stats and pattern count are
identical in both. 2,949 stops, 111 patterns and 2,331 trip-stat rows either
way, and no stop is dropped. Only the identifiers differ.

**Mechanism.** `raptor.build_raptor_network` builds its pattern index from dict
iteration order:

```python
pattern_ids = [p for p in net.patterns if all(s in stop_index for s in ...)]
```

That is insertion order. Pattern index order sets RAPTOR's scan order, which
breaks ties between equal-cost boardings, and with `max_paths_per_od = 4` a
different enumeration order retains a different subset of near-equal paths. The
retained set is what gets repriced under every headway vector, so the difference
propagates into generalized cost and unserved demand.

**Size.** Worst 8.568e-04 relative, on peak vehicles — 176.132 against 176.283,
a sixth of a bus. Unserved demand moves 5.878e-04, about 0.06%. Small but not
nothing: Experiment 3's certified leader is 0.187%, so the unserved figure is a
third of that margin and larger than several certified Experiment 3 effects.
Peak vehicles matters separately because it is a **constraint** rather than just
a reported quantity: a network sitting at 197.0 of 197.0 peak vehicles could
cross its cap on renaming alone.

**What it does and does not threaten.**

* It does **not** invalidate any Gen1 result. Every Gen1 comparison scored both
  arms with the same network object and therefore the same pattern order, so the
  effect cancels. Experiment 3's receipts are unaffected and its closure and
  integrity suites still pass.
* It **does** mean a score is a property of *(network, pattern order)* rather
  than of the network alone, and that two representations of one network can
  disagree by ~6e-4. Any future comparison across differently-constructed
  networks must fix the order or absorb this as a floor.

**What was done.** `exp4_assemble.assemble` iterates `sorted(selection.lines)`
and derives pattern ids from content, so an Experiment 4 network is
deterministic: the same selection always assembles to the same order and scores
identically. That makes Experiment 4 internally consistent. It does not make an
Experiment 4 network comparable to a legacy-ordered one at finer than ~6e-4, and
that limit is recorded here rather than discovered later.

**FIXED 2026-09-05.** `raptor._canonical_pattern_order` orders patterns by
transit content — `(route_id, direction_id, stops, segment run times, n_trips)`
— and `pattern_id` is deliberately absent from the key, since including an
arbitrary label would reintroduce the dependence being removed. Stop order was
already `sorted`, so patterns were the only gap.

Verified end to end by re-running the same comparison that produced the table
above: the renamed, re-sorted network now agrees with the legacy one at
**0.000e+00 on all seven fields**, peak vehicles included
(`outputs/exp4/equivalence_d34fixed.json`). Seven unit tests exercise every
insertion permutation of a five-pattern network, five id prefixes, 200
randomised permutation+rename combinations, reconstruction into a fresh object,
and a peak-vehicle stress case sized to sit at the real 197-vehicle cap.

**Class-B under `METHODOLOGY.md`**: same problem, same objective, same feasible
set — what changed is that the evaluator now computes a function of the network
alone. Gen1's stored results are untouched, and Experiment 3's closure and
integrity suites, the Gen1 freeze and the baseline all still verify, because
every Gen1 comparison scored both arms from one network object in one order and
the effect cancelled. A Gen1 *re-run* may move by up to the figures above.

## D35 — PINNED_OFF was a label on the state digest, not a constraint on the score

**2026-09-05, found by the gate 4-7 master-path benchmark.**

`Exp4Selection.pinned_off` is validated at construction, refuses anything that
is not a `(line, period)` pair, and is hashed into `state_digest`. It reached
nothing that scores:

* `exp4_assemble.assemble` copied it into `AssemblyReport.pinned_off` and
  otherwise ignored it — the route-periods kept their service;
* `exp4_score.score_exp4_network` never forwarded `selection.pinned_off`;
* `exp3_score.solve_on_network` accepted a `pinned_off` argument and forwarded
  it on the `"exact"` solver branch **only**, so Generation 1's
  `optimize_frequencies` never saw it.

So two selections differing *only* in `pinned_off` produced **identical
fitness under different state digests**. That is worse than a wrong number.
`state_digest` is a declared treatment difference in the Experiment 4 contract,
so the firewall would have admitted the comparison and reported a zero effect —
for a treatment that was never applied. A null result from an unapplied
treatment is indistinguishable, in the receipt, from a null result from a real
one.

**How it surfaced.** Not from a test. The master-path benchmark scores a
`pinned_off` variant alongside the supernetwork, and its rows came back
byte-identical in all five cases:

| case | supernetwork objective | pinned_off objective |
|---|---|---|
| greedy_finds_nothing | 3.628658e+06 | 3.628658e+06 |
| large_gap | 3.614702e+06 | 3.614702e+06 |
| moderate_gap | 3.632465e+06 | 3.632465e+06 |
| greedy_overbuilds | 3.639134e+06 | 3.639134e+06 |
| weak_junction | 3.620184e+06 | 3.620184e+06 |

Two candidates that differ are allowed to score the same. Ten values agreeing
to every digit are not a coincidence, and the sample only contained a
`pinned_off` variant because the preregistered sample said to include a fate
the subsets cannot express.

**The fix.** Pin the **setup**, not a solver. A route-period with a single-rung
ladder cannot be moved by any optimizer, which is the mechanism `locked`
already uses, so applying it above the solver switch binds Gen1 and Gen2
alike — rather than each solver being trusted separately to honour a flag.

The baseline plan is pinned too, and that is not belt-and-braces:
`snap_to_ladder` **refuses** a finite headway against an OFF-only ladder
("ladder offers no service at all"), so pinning the ladder alone would raise
rather than pin. The result is then asserted — a plan that comes back with
service on a pinned route-period is an `AssertionError`, because a constraint
enforced only by construction is a constraint nobody has ever watched fail, and
this one was a no-op for as long as it existed.

Measured after the fix, three lines with one pinned off across all six periods:

```
free      objective 3.642440e+06  digest 0ccd940f1232
pinned    objective 3.644617e+06  digest db07b4f83411
pinned line has service in the returned plan: no -- all OFF
```

The pinned network is *worse*, which is the right direction: removing service
cannot improve the objective. Before the fix these two numbers were equal.

**What it says about the method.** The three Fates that the search can *choose*
— ABSENT, CHOSEN_OFF, ACTIVE — were all exercised by ordinary candidates and
all worked. PINNED_OFF is the one fate an input imposes, so no search path
produced it and nothing tested it. A state space with a member nothing
generates is a state space with a member nothing checks.

Regression cover in `tests/test_exp4_substrate.py` pins the wiring rather than
the numbers: the passthrough exists, the pin is applied *before* the solver
switch, the baseline plan is pinned as well as the ladder, the result is
asserted, a pin naming an absent route-period is refused, and
`snap_to_ladder(20.0, [OFF])` still raises.

## D36 — discovery's ordering is inverted, and the promotion cap came within four ranks of excluding the winner

**2026-09-14, found by the reserved question at the close of Experiment 4.**

The question was reserved in `36c46ddf` and deliberately not attempted until
all 200 candidates were certified: does certified rank correlate with discovery
rank? D18 predicted a weak correlation. It is not weak. It is **negative**.

```
spearman(discovery rank, certified rank), n=200      -0.3361
```

The certified winner, `...ecb2ffc4bcce`, was **discovery rank 196 of 200**.
Promotion takes the top 200 of 2000 proposals by discovery score. The winner
sat **four slots above the cut**, separated from the 201st proposal by 12.02 on
a score of 3.62 million. Rank 200 and rank 201 differ by 5.57 — **0.000154%**.

The CAP BOUND recall risk has been carried in `promotion.json` since promotion
as a stated hazard. It was not hypothetical. It came within four ranks — drawn
through a region where discovery scores differ in the sixth decimal place — of
excluding the certified winner from the experiment entirely.

**The mechanism, in one number.** Discovery always overstates the exact
objective, by between 0.9116% and 3.2279%. That overstatement is anti-correlated
with the true objective at

```
spearman(exact objective, overstatement)             -0.9930
```

— the better the candidate, the more discovery overstates it. The leader
carries the **largest overstatement in the field**, 3.2279%, the maximum
observed. A near-perfect negative correlation of that shape has one cause: the
discovery score is very nearly *constant* across the field, so its residual
simply tracks `−exact`.

Across the same 200 candidates:

| quantity | spread |
|---|---|
| exact objective | 2.2788% |
| discovery score | 0.1589% |
| **ratio** | **exact varies 14× more** |

| quantity | value |
|---|---|
| stdev of exact objective, % of mean | 0.4361% |
| stdev of discovery overstatement | 0.4638 pts |
| **ratio** | **error exceeds signal, 1.06×** |

Discovery's approximation error is *larger* than the true variation it is
ranking. Any ordering it produces in this band is dominated by its own
residual, and that residual points the wrong way.

**Supporting counts.** Of the certified top 20, only **four** were inside
discovery's own top 100. Their discovery ranks: 33, 73, 90, 97, 106, 109, 110,
117, 122, 133, 135, 139, 142, 143, 155, 158, 195, 196, 198, 199. Of the
certified top 50, thirteen were in discovery's top 100 — and thirteen were in
its **bottom fifty**. Discovery's own top ten certified at ranks 196, 198, 135,
133, 166, 167, 164, 102, 170, 157: every one in the bottom half.

**It is not the shallow-basin effect in disguise.** `spearman(discovery rank,
rounds) = −0.0202` — no relationship at all. The overstatement rises gently
with rounds (1.72% at 3 rounds to 2.57% at 14), but discovery's *ordering*
carries no rounds signal. D36 and D37 are independent.

**What this is.** D18 in its sharpest form. The gap is not noise around the
truth; it is a structured quantity that grows with candidate quality, so
ranking by approximate objective ranks by structure-induced error. The
architecture's rule — discovery proposes, exact optimisation decides,
`ProposalScore` refuses ordering and float conversion — is not a stylistic
preference. Measured, the proposing half would have inverted the answer.

**The band caveat travels with this finding.** It is measured *inside* the
promoted 200, whose discovery scores span 0.159%. Extrapolating a
restricted-range correlation outward is precisely the error this project keeps
refusing to make. What proposals 201–2000 contain is unknown; certifying them
is ~326 hours at 652 s a candidate. What the finding does say is that the
*argument* for the cap — that discovery ordering concentrates the good
candidates at the top — is measurably false inside the band where it was
applied.

Artifact: `outputs/exp4/run/discovery_vs_certified.json`. Nothing here changes
the result: `rank_certified` ordered the complete set on `objective_EXACT`
alone under the frozen tie-break `0297e180cf30369d`.

## D37 — fast convergence excludes a candidate from contention, and says nothing else

**2026-09-14, from the complete Experiment 4 certified set.**

Computed on all 200:

```
best rank among rounds <=  8 :  80 of 200   (13 such candidates)
best rank among rounds <= 10 :  70 of 200   (28 such candidates)
```

The top **69** is entirely 11+ rounds. The boundary widened monotonically as
the field filled in — 60th at n=180, 66th at n=191, 70th at n=200 — so more
data strengthened the claim rather than eroding it. The preregistered falsifier
(a candidate inside the top fifty converging in ten rounds or fewer) did not
occur in 200.

This is consistent with the `(N,K)`-block-local contract rather than a
discovery about it. With `N_KEYS=8, K_RUNGS=3`, a plan with no improving 8-key
block within 3 ladder rungs stops early because it sits in a shallow basin, and
a shallow basin is a bad plan.

**The claim is about certified rank, not about truth.** Those same fast
candidates are the ones whose certified objective is *least* trustworthy as a
bound on the global optimum — the block-local residual is unmeasured and
structurally widest exactly where convergence is fastest. D37 says the
certification procedure ranks them low, not that they are bad.

**What it does not say.** Nothing about where in the remaining field a fast
candidate lands: the 28 candidates at ≤10 rounds run from 70th to 199th.
Nothing about which of the slow buckets wins — the leader converged in 12
rounds, two short of the deepest in the field, from a bucket of 13.

**Three things this claim used to say and no longer does.** They are recorded
because the checkpoint commits are the project's running record:

1. *"Every candidate converging in ≤8 rounds lands in the bottom half"* —
   FALSE, and false since candidate 147. `...b2b43dbb7034` (8 rounds) entered
   at rank 58 of 147 and finished 80th of 200. Restated as holding at the 150,
   160 and 170 checkpoints; corrected at 180 (`4a0077bc`). Cause: numbers were
   recomputed each checkpoint, *claims* were not.
2. *The enrichment tables*, all of them before the 190 checkpoint. At 180 the
   12-round bucket read 0.00×/0.33× — the most depleted non-empty row — and ten
   candidates later it held first place outright. A 13-member bucket moves
   eight percentage points on one result. Final table below; no row with fewer
   than ~20 members will support a claim, which is six of the ten rows.
3. *Spearman(rounds, certified)* as evidence. Nine checkpoints: −0.299, −0.319,
   −0.312, −0.302, −0.262, −0.265, −0.264, −0.271, −0.2653 final. It wandered
   without direction for the whole run. With 56% of the field (112 of 200) in
   the 13-round bucket it mostly measures intra-bucket scatter. Recorded, not
   argued.

| rounds | field | top 20 | enrich | top 50 | enrich |
|---|---|---|---|---|---|
| 3–10 | 28 | 0 | 0.00× | 0 | 0.00× |
| 11 | 29 | 2 | 0.69× | 4 | 0.55× |
| 12 | 13 | 1 | 0.77× | 2 | 0.62× |
| 13 | 112 | 14 | 1.25× | 38 | 1.36× |
| 14 | 18 | 3 | 1.67× | 6 | 1.33× |
