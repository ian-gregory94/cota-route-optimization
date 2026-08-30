# Columbus / COTA Transit Digital Twin and Optimization Harness

A research platform for one question:

> Holding COTA's approximate current operating resources constant, how much can
> passenger generalized travel cost be reduced through improved frequency
> allocation, transfer timing, stop structure, and eventually route topology?

Everything here is built from public data, calibrated where public data allows,
and explicit about the rest. It has retracted its own headline answer **four
times** — for a modelling error, an under-powered search, an evaluator that was
silently the wrong model, and a benefit that turned out to be the search rather
than the intervention. Those retractions are the most useful output so far, and
all four are documented rather than quietly fixed.

## What we currently believe

**Experiment 1 — frequency redistribution, closed and certified.**

> Redistributing service inside COTA's existing routes and existing
> 2,517 weekday revenue vehicle-hours reduces unserved demand by
> **6.65% ± 0.06**, serves **3.30% ± 0.03** more trips, raises total
> generalized cost by **0.88% ± 0.04** and lowers cost per trip actually served
> by **2.34% ± 0.01** — with **no additional buses** (197.0 peak vehicles
> against 197.0).

Total cost rises because the plan serves 3.3% more people; cost per person
served falls. Three seeds at full effort on one shared candidate set.

Two things travel with that number and may not be dropped:

* **The claim is the aggregate, not any one timetable.** Independent seeds
  produce plans differing on **19% of route-periods** by an average of seven
  minutes while scoring within 0.064 points of each other. The optimum is flat.
  No individual route headway is a recommendation. The constructive reading is
  the better one: many concrete schedules realise the same benefit, so
  constraints this model cannot see — operator bidding, layover geography,
  garage assignment, politics — can be satisfied almost for free.
* **The certified frontier begins at λ = 2.** The cost-favouring λ ≤ 1 corner
  fails path-set adequacy on both models and is reported as uncertified.

**Experiment 2 — route geometry, no supportable claim.**

> Twelve splice candidates. **Six do measurable harm. None does measurable
> good.** The best available geometry intervention in this candidate set is no
> geometry intervention.

At the ranking effort used to order candidates, the two leaders looked worth
about half a point each. Re-solved at the effort Experiment 1 is certified at —
400,000 iterations, 20 restarts, with three zero-edit replicates in the same run
— both land inside the 0.287-point noise floor. The replicates score 9749.1,
9748.8 and 9765.1 unserved; the leading candidate scores 9764.8. Re-running the
*baseline* with a different seed moves it further than the edit does.

The unedited network was the under-optimized one: at low effort the baseline had
not been solved as well as the edited networks had. Both sides ran at the same
*nominal* effort, which is what the standing rule requires — the same effort was
simply not equally sufficient for both. **Matched effort is necessary and not
sufficient; what has to match is convergence.**

The harmful candidates stay harmful at full effort. Harm survives more search
and apparent benefit does not, which is the right way round — and a useful
heuristic: a benefit that shrinks with effort probably was never there.

**Experiment 2B — the joint subset search** over all 240 structurally feasible
combinations is **closed, and its answer is the null.** Because edits do not
compose, *it*, not the single-candidate ranking, answers "which combination
should COTA make" — and the answer is none of them. Not one of the 227
multi-edit sets beats the best single, harm rises monotonically with every
edit added, and at λ≥2 every combination *substitutes*: it delivers less than
its members promised separately, with zero exceptions in the entire feasible
space. The leader was then re-solved at certification effort under three seeds
and scores +0.007% — two hundredths of a noise floor.

The same leader wins at λ ∈ {1, 2, 4}, so this is a result about the network
rather than about one point on the cost/coverage trade-off. Full account in
`EXPERIMENT2_CLOSEOUT.md`.

**Experiment 3 — route mutation** has not started. Its rules are committed in
`EXPERIMENT3_CONTRACT.md` before any candidate exists.

## The Model A → Model B correction

A ride leg's waiting time can be priced two ways. **Model A** charges the
chosen pattern's own headway. **Model B** charges the combined frequency of
every same-route pattern that serves the boarding stop, the alighting stop, and
in that order — because a passenger boards whichever comes first. Model A is
the special case where one pattern qualifies.

Model A systematically undervalues frequent trunk service, which runs the most
pattern variants, so it is biased against exactly the routes a frequency
optimizer proposes to cut. Model B is the sole authoritative evaluator.

**And for three days the Experiment 2 evaluator was Model A while reporting
Model B.** The script built its evaluator without specifying the model and got
the config default; the run's log reported the *harness's* setting, which was a
different object. Correcting it changed six of twelve candidates' signs and
halved the headline geometry claim. Every experiment artifact now records the
model the evaluator actually used, and a run that cannot state it produces no
artifact. See `outputs/CANONICAL_RESULTS.json` for which artifacts are current
and which are superseded — nothing was deleted, and a superseded artifact looks
entirely legitimate from the inside.

## Current limitations, with sizes

| limitation | size | direction |
|---|---|---|
| commute-only LODES demand | 24.7% of regional flow is transit-accessible; the top 20k pairs are 64.9% of that | unknown; the largest unquantified error |
| frontier below λ = 2 | uncertified on both models | quoted from λ = 2 upward |
| per-route headways | 19–26% seed disagreement | aggregate unaffected; no route-level recommendation |
| cross-route common lines | 0.516% of generalized cost under Model B | overstates waiting on trunk routes; deferred |
| stop-service penalty | unmeasurable from this feed (−157 s/stop, inverted) | blocks any consolidation claim resting on runtime savings |
| novel-link running time | MAE 17.2 s, aggregate bias +0.41% | unbiased, but 20.5% median APE on a single link |
| scheduled ≠ actual | unquantified | no reliability penalty anywhere |

## What it does

- **Provenance-first ingestion.** Every external dataset enters through an
  immutable raw store with SHA-256 checksums, retrieval timestamps and a source
  record in `config/sources.yaml`. Unknown data is marked `UNKNOWN`, never
  invented.
- **GTFS parse and validation.** Structural validation that reports malformed
  records rather than silently discarding them. COTA's current feed passes with
  zero errors.
- **Scheduled baseline.** Route/stop/trip counts, headway distributions, service
  spans, runtimes, revenue vehicle-hours and miles, peak vehicle counts, stop
  spacing — all labelled as *scheduled estimates*, not reported operating
  statistics.
- **RAPTOR routing.** Both a timetabled earliest-arrival router (ground truth
  against the published schedule) and a frequency-based generalized-cost router
  that composes with a `FrequencyPlan`, so passengers re-route when service
  changes.
- **Real OD demand.** LEHD LODES block-to-block commute flows aggregated to
  block groups, mapped to stop access, scaled to an NTD-anchored weekday
  linked-trip total.
- **NTD reconciliation.** The FTA agency profile is parsed deterministically and
  *rejected* unless it reproduces the profile's own 18 printed efficiency
  ratios.
- **Frequency optimization.** Marginal-exchange search over a headway ladder
  under a fixed vehicle-hour and peak-fleet envelope, with a measured
  convergence curve rather than an assumed search budget.

## Layout

```
src/cota_opt/      production logic (typed, tested)
  registry.py      immutable raw store + provenance
  gtfs.py          parsing and structural validation
  baseline.py      scheduled-service baseline tables
  raptor.py        timetabled + frequency-based routing
  odmatrix.py      LODES OD, gravity fallback, zone system
  pathset.py       candidate path enumeration and fast re-costing
  frequency.py     FrequencyPlan / ResourceBudget / solver
  crowding.py      link loads and peak-load-point crowding
  routeclass.py    service-pattern route classification
  ntd.py           ratio-verified NTD profile parsing
  harness.py       one cached entry point for the whole build chain
  cache.py         content-addressed cache + checkpointed result store
tests/             354 deterministic tests
config/            sources, assumptions, cost weights, constraints, scenarios
scripts/           experiment runners
outputs/           reports, experiment records, per-cell checkpoints
```

## Running it

```bash
pip install -e ".[dev]"
python -m pytest                      # 354 tests

python -m cota_opt.cli sources        # what data is registered
python -m cota_opt.cli ingest-gtfs path/to/cota.gtfs.zip
python -m cota_opt.cli validate
python -m cota_opt.cli baseline
python -m cota_opt.cli report

python scripts/convergence.py         # how much search this problem needs
python scripts/run_matrix.py --iterations 150000 --restarts 5 --width 48
```

The first build takes ~12 minutes; after that `data/cache/` makes it 0.2
seconds. Long runs checkpoint per cell and resume rather than restart.

## Data sources

COTA GTFS static and GTFS-Realtime; FTA National Transit Database (agency
50016); LEHD LODES8 origin-destination, residence-area and workplace-area
characteristics; 2020 Census block-group population centroids. URLs, licences
and retrieval status are in `config/sources.yaml`.

Some hosts are unreachable from a sandboxed environment; those files are
retrieved externally and registered through the same provenance path, so the
resulting artifact is identical either way.

## Standing caveats

Demand is LODES **commute** flow — non-work travel is absent, which matters most
at midday. Period demand shares are assumed, because LODES has no time
dimension. Stop-level boardings (APC) are not public and are the binding
constraint on everything downstream. Nothing here is a recommendation to COTA.

## Governing contract

`AGENTS.md` is the development and research contract: evidence standards,
provenance rules, CRS discipline, the scheduled-vs-actual distinction, and the
skeptic protocol for surprising results.

`ACCEPTANCE.md` holds the gates, each committed before the run it judges.
`EXPERIMENT3_CONTRACT.md` fixes what Experiment 3 may mutate, before any
candidate exists. `DISCOVERIES.md` is the research diary and keeps every path
taken, including the wrong ones; this README describes what we currently
believe, which is a much shorter list.
