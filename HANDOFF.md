# Handoff

For a transportation research team picking this repository up without the
conversation that produced it. Read `AGENTS.md` first — it is the contract the
code is written to, and the reason several results here were retracted rather
than published.

Everything below is sorted by how much you should trust it.

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

### Path-set convergence

The candidate set is enumerated in advance, which makes the optimizer
affordable and is its main structural error: an optimized plan can make
attractive a path that was never enumerated, so its cost is overstated. Measured
improvable flow share: **0.4% at baseline, 6.4% under the balanced plan, 17.6%
under the most aggressive.**

`scripts/fixpoint.py` closes this — solve, feed the plans back in as enumeration
scenarios, re-enumerate, re-solve, until the improvable share stops moving, then
solve the final frontier at full effort on the converged set and re-check. The
candidate set only grows, so each iteration is a tighter lower bound and the
loop is monotone by construction.

Raising the per-OD candidate cap from 4 to 6 added **under 1%** more paths, so
the cap was never the binding constraint — scenario coverage was.
`cota_opt.attribution` names the mechanism behind each recovered path.

---

## 2. What is provisional

* **Experiment 2 screening.** 60 candidate geometry edits, priced with full
  RAPTOR at headways scaled so the edited network spends exactly today's
  vehicle-hours. Frequency is not reallocated, so these **rank** candidates and
  do not measure them. Note also that the screen's "unserved" means
  *unreachable*, while the model's also applies the retention curve — the two
  are not the same quantity.
* **Experiment 2 evaluation tier.** Geometry with frequency re-optimized, but on
  a reduced enumeration sweep and pre-fixpoint yardstick. Exploratory.
* **Anything geometry.** `DISCOVERIES.md` deliberately excludes geometry
  findings until they survive frequency re-optimization on the frozen yardstick,
  matched effort, a seed check, and hand inspection against the network.
* **The known bias in Experiment 1's headline** — see D10 below, which is the
  first thing to fix.

---

## 3. What is limited, and how much

| Limitation | Size, where measured | Direction |
|---|---|---|
| **Commute-only demand** | LODES work trips only. 24.7% of regional commute flow is transit-accessible at all; the top 20,000 OD pairs are 64.9% of that. Scaled to 30,949 assumed weekday linked trips (NTD-derived). | Unknown. Largest unquantified error in the project; no amount of solver work touches it. |
| **Same-route pattern aggregation (D10)** | ~4.3% of generalized cost | **Against** the current Experiment 1 result — see below |
| **Cross-route hyperpath** | 0.79% of generalized cost, bounded generously | Overstates waiting; concentrated on trunk routes |
| **Novel-link running time** | MAE 17.2 s, median APE 20.5%, aggregate bias **+0.41%** out of sample | Not biased in the exploitable direction; 63% of links over-predicted |
| **Peak-fleet formula** | cycle-over-headway gives 150.7 against blocks' 197 — **24% optimistic** | The optimizer's fleet constraint is loose |
| **Scheduled ≠ actual** | not quantified | No reliability penalty in the objective |

### D10, the one to fix first

Each ride leg is priced at its **pattern's** headway (route headway ×
direction-trips ÷ pattern-trips). That multiplier stops a quarter-frequency
pattern being priced at the route's full frequency, which is right. But where
several of a route's patterns all carry the same stop-to-stop movement, a rider
can board any of them, and charging one pattern's headway overcharges the wait.

Measured: of a 5.09%-of-generalized-cost combined-frequency bound, **84.4% is
the same route's own patterns**; 19,049 of 22,984 affected legs have
alternatives that are entirely same-route. It concentrates on route 010 E Broad
(23% of the bound, median **4** attractive patterns per leg), then 005, 007,
001, 002.

Those are the high-frequency trunk routes the balanced plan proposes to cut, so
**the bias runs against the current result**. The fix is inside the existing
model — price a movement on the combined frequency of the patterns serving it —
and it is the highest-value open item.

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
