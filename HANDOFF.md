# Handoff

For a transportation research team picking this repository up without the
conversation that produced it. Read `AGENTS.md` first — it is the contract the
code is written to, and the reason several results here were retracted rather
than published.

Everything below is sorted by how much you should trust it.

**Live as of 2026-08-29 15:00 UTC.** Experiment 1 is complete and final on
Model B. Three runs are in flight, all checkpointed below the cell level and
all supervised by `scripts/supervise.sh`:

| job | what it settles | progress file |
|---|---|---|
| `exp2-frontier` | the decision-representation comparison (D21) on all twelve candidate networks, not just the unedited one | `outputs/exp2_treatments.jsonl` |
| `exp2-recheck` | D19's own falsification test: the two harmful splices at full effort against a floor measured at that effort | `outputs/exp2_recheck.log` |
| `exp2b-stageA-{0,1}` | Experiment 2B — every one of the 240 structurally feasible geometry subsets | `outputs/exp2b_subsets.shard*.jsonl` |

Nothing in sections 1–3 depends on those finishing. Section 2's Experiment 2
material is what they extend.

---

## 1. What is established

### Data and provenance

| Input | Source | How it is validated |
|---|---|---|
| GTFS static | COTA, feed `2026-MAY-04-BB_20260630` | 0 errors, 0 warnings from `validate_feed`; representative weekday 2026-05-26 (45 identical service days) |
| LEHD LODES OD | `oh_od_main_JT00_2022` | 4,640,957 block pairs → 317,706 block-group pairs → 823,915 commute trips |
| Block-group centroids | Census `CenPop2020_Mean_BG39` | population-weighted, not geometric |
| NTD 2024 profile | agency 50016, motorbus, directly operated | the parser **refuses** unless it reproduces all 18 of the profile's own printed ratios (`cota_opt.ntd`) |

`config/sources.yaml` records every URL and SHA-256. `data/` is deliberately
untracked and rebuilds from those records — the provenance rule is that inputs
are re-fetched, not committed as opaque blobs.

### Baseline validation

* Model baseline revenue vehicle-hours **identically** reproduce the GTFS
  schedule. This is asserted at run time with a 1e-9 tolerance, not checked
  afterwards, because the headway definition `h = k·T/n` makes it an identity.
* `shape_dist_traveled` is in **kilometres**, not miles — caught by comparing
  against projected geometry (the two agree to 0.155% once corrected).
* Peak vehicle requirement read from GTFS blocks: **197** at pm peak, against
  NTD's reported VOMS of **198**. Nothing was tuned to produce that match.

### Experiment 1 — frequency redistribution, geometry fixed

Decision variable is the headway of every (route, period) with weekday service
— 173 of them across 39 routes. The plan must fit inside 2,517 weekday revenue
vehicle-hours and today's peak vehicle requirement.

Assignment is path-based: RAPTOR enumerates candidate paths per OD pair,
passengers are assigned all-or-nothing to the cheapest, and a retention curve
drops travellers whose trip becomes too long. Generalized cost is in equivalent
in-vehicle minutes.

**The methodological finding is the durable one.** A route-level model — no
path assignment, so passengers cannot re-route — believes its λ=4 plan cuts
unserved demand **22.71% while saving 0.76% cost**. The same plan, scored by
path assignment: **−7.16% at +2.51%**. All seven route-level plans are strictly
dominated at matched effort, same demand, same solver, same yardstick. Any
network-redesign claim scored without path assignment inherits this error.

Two model-fidelity results that cost real effort to establish:

* **Peak expresses are a class, not a headway.** 14 of 39 routes run in a peak
  with no midday and no evening service. Treated as ordinary low-frequency
  service, the optimizer multiplies their headways twelvefold and books the
  savings. Locking them is worth 1.5–3 pp of apparent unserved reduction.
* **Crowding does not bind.** Median bus at its route-period peak load point
  carries 9% of capacity. NTD corroborates at 13.0 boardings per revenue hour.
  Model configurations with and without crowding differ in the third decimal.

### Search effort is measured, not assumed

A convergence study at λ=1 gives objective improvement by search level:
**L0 −0.66% / L1 −1.40% / L2 −1.75% / L3 −1.83% / L4 −1.87%.** This exists
because an earlier ablation was run at L0 while Experiment 1 ran at L4 — a 20×
effort gap that biased the comparison toward its own conclusion. Everything
comparative is now run at matched effort against this ladder. **If you change
one thing about how you use this repo, keep that discipline.**

### The Experiment 1 result

Corrected waiting model (Model B), full search effort, on a candidate set that
converged and was then independently certified. Three seeds:

> **−6.65% ± 0.06 unserved demand · +3.30% ± 0.03 trips served ·
> +0.88% ± 0.04 generalized cost · −2.34% ± 0.01 cost per trip actually served**,
> at 2,516.5 of 2,517.2 weekday revenue vehicle-hours.

Read the cost column carefully. Total generalized cost **rises**, because the
plan serves 3.3% more people; cost per person actually served **falls**. It is
not a free lunch and the +0.88% is 21 standard deviations from zero — there is
no version of this where the cost is "not measurable".

**It needs no additional buses.** The block-derived fleet proxy puts the
balanced plan at **197.0 peak vehicles against a 197.0 baseline**. The proxy is
not tuned: reconstructing COTA's blocks from the feed gives 197 peak vehicles
against NTD's independently reported VOMS of 198. The optimizer was given a
vehicle-hour budget, not a fleet cap, and hours are not buses — a plan can
respect the hours and still need more vehicles at the peak minute. This one
does not.

**The plan behind the number is not identified.** Independent seeds on one
shared candidate set produce plans differing on **20–26% of route-periods** at
an average of seven minutes of headway, while scoring within 0.13 points of each
other. The aggregate is measured to a precision the rest of the model's
assumptions do not deserve; no individual route headway is supported at all.
Quote the total, label any specific plan as one arbitrary member of a large
indifference set, and read D17 before writing a sentence with a route number in
it.

There is a constructive reading, and it is the better one for a planner: a flat
optimum means COTA has *freedom*. Many concrete schedules realise the same
passenger benefit, so constraints this model cannot see — operator bidding,
layover geography, garage assignment, the politics of cutting a named route —
can be satisfied almost for free.

### Path-set convergence, and where it stops working

The candidate set is enumerated in advance, which makes the optimizer
affordable and is its main structural error: an optimized plan can make
attractive a path that was never enumerated, so its cost is overstated. Measured
improvable flow share: **0.4% at baseline, 6.4% under the balanced plan, 17.6%
under the most aggressive.**

`scripts/fixpoint.py` closes this — solve, feed the plans back in as enumeration
scenarios, re-enumerate, re-solve, until the improvable share stops moving, then
solve the final frontier at full effort on the converged set and re-check. The
candidate set only grows, so each iteration is a tighter lower bound and the
loop is monotone by construction. Both models converged on the tolerance test
rather than an iteration cap:

| iteration | 0 | 1 | 2 | 3 | converged set |
|---|---|---|---|---|---|
| Model A | 9.443% | 4.524% | 1.138% | 1.029% | 227,791 paths |
| Model B | 5.302% | 2.406% | 0.732% | 0.671% | 240,965 paths |

**But convergence in aggregate is not convergence at every λ**, and this is the
limitation to carry forward. The loop probes at λ ∈ {0.5, 1, 2, 8} and exits on
the worst improvable share across them; the frontier is then solved at
{0.25 … 16} and at higher effort. Re-checking the full-effort plans against the
frozen set, **λ ≥ 2 passes on both models and λ ≤ 1 fails on both** — at
different thresholds, on candidate sets 4% apart. A repair step (feed the
full-effort plans back, rebuild, re-solve every λ) closed most of the λ=0.25 gap
and made λ=1 *worse*, because a wider set lets the search find a new extreme
plan the set covers no better. **Both frontiers are quoted from λ = 2 upward and
the cost-favouring corner is reported as uncertified.** See D15.

Raising the per-OD candidate cap from 4 to 6 added **under 1%** more paths, so
the cap was never the binding constraint — scenario coverage was.
`cota_opt.attribution` names the mechanism behind each recovered path.

---

## 2. What is provisional

### Experiment 2 — geometry, and the one claim it supports

The supportable claim is a single sentence:

> Through-routing **33 Henderson** and **34 Morse** at Westview Turnaround
> reduces unserved demand by about **0.5%** at roughly neutral generalized cost,
> using only track COTA already runs — and adding further edits from the same
> shortlist gives all of it back.

**That number was 0.9% until 2026-08-30 and the change is not a refinement.**
The evaluation script scored every plan under Model A while reporting Model B
(ACCEPTANCE.md, *Defect: the Experiment 2 evaluator was Model A*). Re-run under
the corrected evaluator, six of the twelve candidates change sign, the
classification goes from 7 beneficial / 3 at the floor / 2 harmful to **4 / 2 /
6**, and this edit's effect roughly halves. See D23.

It is also no longer the best-scoring single: `splice|011|034|WESHIGW` measures
−0.585% against its −0.485%. **The recommendation stays where it is anyway**,
because the gap is 0.100 points against a 0.130-point noise floor — 0.77 of a
floor, not a distinguishable difference — and on the criteria the model does not
represent, 11+34 is the weaker proposal: a 91-minute cycle against 59, +1.0
vehicle-hours where 33+34 releases 0.6, and a 1 : 4.1 trip asymmetry that leaves
most of 34 Morse short-turning. That is a judgement about the proposal, and it
is labelled as one.

Four things had to be established to get here, and each is a warning to anyone
tempted to shortcut the funnel.

**The screen ranks candidates and does not reliably rank them.** Its
first-ranked candidate of 60, `splice|002|033|WESHIGW`, is second-worst of the
twelve when evaluated with frequency re-optimized: **+0.98% unserved** against a
measured 0.288-point noise floor. Its fifth-ranked is the worst. The mechanism
is visible in the columns — every candidate that helps costs slightly more
generalized cost and serves more people, and both that hurt *save* generalized
cost by serving fewer. The screen holds frequency fixed, so it cannot see the
reallocation an edit triggers; it rewards edits that make the network cheaper,
and the cheapest edits are the ones that quietly drop demand. See D19.

**Edits do not compose.** Composed best-first from measured performance, one
edit gives −0.585%, two give −0.066% — inside the 0.130-point noise floor, so
indistinguishable from making no change — and four give **+1.639%**, worse than
doing nothing by 12.6 floors. They compete for one vehicle-hour envelope, and
through-routing consumes it: the merged line is longer, so hours that were
buying frequency go into running it. The interaction term — measured effect
minus the sum of the members' own effects — is +0.791 points at two edits and
+2.086 at four. "Which edits should COTA make" is therefore not answerable by
taking the top N: the top N is not the best set of N. Any recommendation is a
set, evaluated as a set. See D20.

Under Model B the greedy ladder is also *forced* to compose harmful edits. Only
four candidates are beneficial, rungs must use disjoint routes, and after the
first two there is no beneficial candidate left that avoids the routes already
used — so it reaches past them. A greedy ladder cannot decline to grow, which
is why Experiment 2B enumerates subsets instead.

**Screen numbers were bracketed, not rescored.** Model B cannot be run in the
screen — its multiplier depends on the boarding stop, the alighting stop and
their order, so it is a property of a leg, and the screen prices straight out of
RAPTOR's labels where waiting is fixed per pattern before the alighting stop is
known. Running it with a Model B flag would have produced Model A numbers under
a Model B label. It was bracketed between Model A and route-level pricing (a
strict lower bound on any Model B cost) instead. Aggregate Spearman 0.857 — but
**within splices, the only kind that takes a top-ten slot, 0.336.** The set
{splices are the good kind} is robust; the ordering inside it is not, which is
why all twelve were evaluated rather than the top eight. See D16.

**And the waiting model does move the ranking, which D16's headline denied.**
With all twelve evaluated under both models properly — same networks, same
effort, same seed — Spearman is **0.657** and six of the twelve change sign.
D16's aggregate 0.857 was measuring how easy truncations and extensions are to
rank, not splices; its own amendment, at 0.336, was closer. Quote the amendment,
not the headline. See D23.

**Still provisional in Experiment 2:**

* Magnitudes. Candidate path sets use the reduced scenario sweep and the solver
  runs below L4, so the evaluation ranks candidates against a measured noise
  floor and does not size them. *(The two harmful candidates have since been
  re-run at full effort, twice, under both models. D19 may be quoted.)*
* Everything that is not a splice. Extends, truncates, straightens and reroutes
  take no top-ten slot at either end of the bracket and were never evaluated.
* A joint search over subsets. The ladder is greedy over singles; D20's
  non-additivity might be a property of greedy composition rather than of the
  budget, and nothing here distinguishes them. **Experiment 2B is that search
  and is running** — all 240 structurally feasible subsets, exhaustively.

**Model A's headline.** Preserved as the control and never overwritten, but it
carries the same-route waiting bias D10 identified. Quote Model B.

---

### Experiment 2B — the joint subset search, and why it is not a bigger ladder

D20 rules out the obvious way to answer "which edits should COTA make?".
Ranking candidates and taking the top N does not give the best set of N,
because the effect of a set is not the sum of its members'. Re-ordering the
ladder by *measured* rather than screened performance improves every rung by
1.9 to 3.8 points and still cannot make composition pay — one edit −0.94%, two
−0.49%, four +0.47% — so the failure is not the screen's, and a longer or
better-ordered ladder will not fix it. A greedy ladder can only ever visit
nested sets, and nothing licenses the assumption that the best pair contains
the best single.

So 2B enumerates instead. The twelve candidates admit exactly **240
structurally feasible subsets**, maximum cardinality 6, because
`geometry.apply_edits` removes both of a splice's routes from its live set and
raises if a later edit names one — any two splices sharing a route cannot
coexist. That is a much better position than heuristic search: no candidate
ordering to defend, no greedy path to justify, and no way for the answer to be
an artifact of where the search started.

**All twelve are eligible, including the two that are harmful alone.** Nothing
is excluded on performance. Removing a member because it scores badly by itself
would assume exactly the composability the experiment exists to test — a
candidate that hurts alone can substitute for one that helps, and the search
cannot discover that if the candidate is not in it. The classification (7
beneficial, 3 inside the noise floor, 2 harmful, in
`outputs/exp2_candidate_classes.json`) is evidence about singles and is not a
filter on sets.

The comparison every set is ranked on is against the **unedited** network's
optimized outcome, not against its own network with baseline frequencies. The
second is easy to compute and answers a different question — how much frequency
re-optimization gains on that geometry — and ranking on it would have produced
a clean, defensible, irrelevant answer.

Gate 2B-6 requires the interaction term for **every** set, not for the ones
that look interesting: measured effect minus the sum of its members' measured
single effects, classified against the same 0.288-point floor. Unserved demand
is a cost, so a positive term means the set delivered less than its members
promised — "substituting", which is D20's pattern — and a negative term is real
synergy. Gate 2B-7 makes the null result publishable and names it the prior:
**no multi-edit set beating the single splice is a permitted outcome.**

The seven 2B gates were committed to `ACCEPTANCE.md` before any subset was
solved.

## 3. What is limited, and how much

| Limitation | Size, where measured | Direction |
|---|---|---|
| **Commute-only demand** | LODES work trips only. 24.7% of regional commute flow is transit-accessible at all; the top 20,000 OD pairs are 64.9% of that. Scaled to 30,949 assumed weekday linked trips (NTD-derived). | Unknown. Largest unquantified error in the project; no amount of solver work touches it. |
| **Same-route pattern aggregation (D10)** | was ~4.3% of generalized cost; **0.000% under Model B** | Corrected. Ran against the Model A result — see below |
| **Cross-route hyperpath** | 0.79% under Model A, **0.516% under Model B**, bounded generously | Overstates waiting; concentrated on trunk routes. Deferred, not corrected |
| **Per-route headways are not identified** | plans differing on ~25% of route-periods (mean 8 min) score within 0.01% | Aggregate result unaffected; no individual route headway may be quoted as a recommendation |
| **Stop cost cannot be measured from this feed** | 11 natural experiments, 3 routes, pooled **−157 s per extra stop** (inverted sign) | Blocks any Experiment 3 consolidation claim resting on runtime savings; handled as a break-even threshold instead |
| **Novel-link running time** | MAE 17.2 s, median APE 20.5%, aggregate bias **+0.41%** out of sample | Not biased in the exploitable direction; 63% of links over-predicted |
| **Peak-fleet formula** | cycle-over-headway gives 150.7 against blocks' 197 — **24% optimistic** | The optimizer's fleet constraint is loose |
| **Scheduled ≠ actual** | not quantified | No reliability penalty in the objective |

### D10, and what fixing it cost

Each ride leg used to be priced at its **pattern's** headway (route headway ×
direction-trips ÷ pattern-trips). That multiplier stops a quarter-frequency
pattern being priced at the route's full frequency, which is right. But where
several of a route's patterns all carry the same stop-to-stop movement, a rider
can board any of them, and charging one pattern's headway overcharges the wait.

Measured under **Model A**: of a 5.09%-of-generalized-cost combined-frequency
bound, **84.4% was the same route's own patterns**; 19,049 of 22,984 affected
legs had alternatives that were entirely same-route. It concentrated on route
010 E Broad (23% of the bound, median **4** attractive patterns per leg), then
005, 007, 001, 002 — the high-frequency trunk routes the balanced plan proposes
to cut, so the bias ran **against** the result.

**Model B** prices a movement on the combined frequency of every same-route
pattern that serves the boarding stop, the alighting stop, and in that order:

    mult = 1 / Σ_q ( n_trips(q) / n_direction_trips(q) )

Model A is the one-qualifying-pattern case, so B is a strict generalisation and
nothing about the path representation, the objective or the optimizer changes.

Two gates had to pass before it could be trusted, and both are recorded in
`ACCEPTANCE.md` with thresholds committed before the diagnostics were written.

**Gate 10 — valuation.** Re-running the common-lines diagnostic under Model B:
same-route component **4.301% → 0.000%** (−5.3e-14 minutes on a base of 1.77
million); legs whose alternatives are all same-route **19,049 → 0**; total bound
**5.095% → 0.516%**, now entirely cross-route and *below* the 0.79% already
accepted as non-blocking. Zero is what a correct implementation must produce,
not a good outcome — anything else would have meant the multiplier was not
reaching the legs the bound prices. Block-derived fleet figures came back
bit-identical across the two runs (197 peak at 17:13, interlining 1.30699),
confirming nothing else moved.

**Gate 11 — discovery.** Correct valuation is not sufficient if the corrected
model cannot *find* the paths it prefers: RAPTOR searches with per-pattern
headways, which is Model A's valuation. First pass returned **Case C** — 4.877%
of tested flow (material) had a materially cheaper Model B path outside the
candidate set, on 0.185% of tested cost (negligible). The two bounds disagreed
by a factor of 26 and the pre-committed rule sends either one to the worse case,
so candidate generation was augmented with a route-level-priced search scenario
(a strict lower bound on Model B path cost, so the search explores what only
wins once patterns combine). Not a valuation change; Model A's candidate set is
byte-for-byte unmoved.

The rerun returned Case A, zero omissions — flagged in advance as a consistency
check rather than evidence, because the diagnostic and the augmentation use the
same bound. The evidence that counts is the **sensitivity comparison**: solve
Model B at matched effort on both candidate sets, score both plans on the
augmented evaluator (a superset, so neither grades its own homework). Gaps came
in at **≤0.057% generalized cost and ≤0.03% unserved** against 0.25%/1.0% lines,
at every λ, with two of six favouring the un-augmented set. The omission is real
and does not change the recommendation.

### The result splits: robust in aggregate, not per route

That comparison produced the caveat this handoff most needs to carry. The two
plans scoring within **0.01%** of each other differ on **39–43 of 173
route-periods**, by a mean of **8 minutes of headway**, one by forty.

* The **aggregate claim is robust** — roughly 6% less unserved demand at little
  generalized cost, holding across candidate sets differing by 7% in size and
  plans differing substantially in composition.
* The **per-route claim is not**. "Route X should go from 30 to 15 minutes" is
  not identified by this objective at this effort. Acting on a specific headway
  from a specific plan means acting on something the model does not distinguish
  from many alternatives.

Flat optimum or under-converged search is **resolved: a flat optimum** (D17).
Gate 7's replicates share one candidate set and run at full effort, so the
19.1% mean route-period disagreement (Model B; 26.0% Model A) cannot be a
candidate-set effect or under-search — and the objective's own spread across
those same seeds is 0.064 points on a −6.65% effect. The search scatters the
plan and not the score, which is what a flat optimum means. The practical
consequence is unchanged: read the route-period disagreement number before
quoting any individual route, and quote none.

---

## 4. What an expert should attack next

Roughly in order of how much they would change the answer:

1. **Richer OD demand.** All-purpose travel, not commute. Everything else is
   downstream of this.
2. **The D10 fix**, then re-run Experiment 1's frontier with and without it.
3. **Formal transit assignment** — the current model is all-or-nothing onto the
   cheapest enumerated path with a retention curve. Frequency-based equilibrium
   assignment with capacity effects is the standard alternative.
4. **Optimal-strategy (hyperpath) assignment**, once D10 is separated out. The
   residual cross-route effect is 0.79% and bounded generously.
5. **Observed reliability** — GTFS-RT collection exists (`cota_opt.realtime`)
   but nothing in the objective uses it. Scheduled service is modelled.
6. **Ridership validation.** Nothing here is calibrated against observed
   boardings; the demand proxy is a proxy.
7. **Equity and demographic incidence.** Who pays for the redistribution is not
   modelled at all, and the balanced plan cuts real trunk corridors.
8. **Proper vehicle blocking** for candidate plans, rather than the interlining
   factor proxy (`cota_opt.blocks`).
9. **Elastic demand.** The retention curve is a crude stand-in for people
   declining a trip that became too long.
10. **Service standards and political constraints** — see §6.

---

## 5. Reproducing the main experiments

```bash
pip install -e .
python -m pytest tests -q                     # ~190 tests

python scripts/fetch_gtfs.py                  # inputs, per config/sources.yaml
# LODES and the NTD profile are large/blocked from some networks; sources.yaml
# has their URLs and hashes.

python scripts/run_exp1.py                    # route-level frequency (the naive model)
python scripts/run_exp2.py                    # path-based frequency
python scripts/convergence.py                 # the search-effort ladder — run this first
python scripts/run_matrix.py                  # the controlled R/A/B/C comparison
python scripts/fixpoint.py                    # path-set convergence + final frontier
python scripts/validate_runtime.py            # held-out running-time estimator check
python scripts/run_diagnostics.py             # peak fleet from blocks; hyperpath bound
python scripts/run_exp2_screen.py             # geometry candidate screening
python scripts/run_exp2_eval.py               # geometry + frequency re-optimization
python scripts/make_figures.py                # every figure that has its inputs
```

Long runs checkpoint per cell to JSONL in `outputs/` and **resume rather than
restart**. `data/cache/` is a content-addressed store keyed on the inputs that
actually affect each artifact, so a stale entry cannot be silently reused.

Two operational notes: the harness needs roughly 2 GB, so do not run two of
these concurrently on a small machine (that OOM-killed both runs here once);
and `scripts/supervise.sh` restarts a long job that dies.

---

## 6. A framing worth keeping

Once the technical frontier is stable, the useful question stops being *why
doesn't COTA implement the optimum* and becomes *what is the measurable
systemwide cost of each service-policy constraint* — a minimum trunk frequency,
a coverage floor, protection for a specific corridor, the peak-express
timetable. Each can be imposed as a constraint and the frontier re-measured.
That number is arguably more useful to an agency than the unconstrained
optimum, which no one is going to adopt.

The model does not say what COTA should do. It says what the current geometry
and budget make possible, and — via the route-level-versus-path-assignment
result — how badly a coarser model would mislead anyone asking.
