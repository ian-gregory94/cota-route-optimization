# Columbus / COTA Transit Digital Twin and Optimization Harness

A research platform for one question:

> Holding COTA's approximate current operating resources constant, how much can
> passenger generalized travel cost be reduced through improved frequency
> allocation, transfer timing, stop structure, and eventually route topology?

Everything here is built from public data, calibrated where public data allows,
and explicit about the rest. It has retracted its own headline answer twice —
once for a modelling error, once for an under-powered search. Those retractions
are the most useful output so far, and both are documented rather than quietly
fixed.

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
tests/             127 deterministic tests
config/            sources, assumptions, cost weights, constraints, scenarios
scripts/           experiment runners
outputs/           reports, experiment records, per-cell checkpoints
```

## Running it

```bash
pip install -e ".[dev]"
python -m pytest                      # 127 tests

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
