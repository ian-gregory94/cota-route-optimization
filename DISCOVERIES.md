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

## Not yet earned

Geometry findings stay out of this log until they survive: frequency
re-optimization, the frozen yardstick, matched effort, a seed check, and a hand
inspection against the network. Screening evidence is for choosing what to
evaluate, not for concluding.
