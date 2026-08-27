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

**Confidence.** Moderate, pending the converged-path-set rerun.

**Interpretation.** There is a ceiling near 7% on what redistributing frequency
inside this geometry and this budget can reach.

**Falsified by.** The converged path set moving the aggressive end of the
frontier enough to un-flatten it — plausible, since that end is exactly where
path-set inadequacy was worst (17.6% of flow improvable).

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

**Which is it — a flat optimum or an under-converged search?** Not yet known,
and the two have the same practical consequence. Gate 7 already requires three
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


---

## Not yet earned

Geometry findings stay out of this log until they survive: frequency
re-optimization, the frozen yardstick, matched effort, a seed check, and a hand
inspection against the network. Screening evidence is for choosing what to
evaluate, not for concluding.
