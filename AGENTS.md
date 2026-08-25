# AGENTS.md — Governing Development & Research Contract

Columbus/COTA Transit Digital Twin and Optimization Harness.

## Mission

Holding COTA's approximate current operating resources constant, quantify how much
passenger generalized travel cost can be reduced through improved frequency
allocation, transfer timing, stop structure, and eventually route topology.

## Non-negotiable rules

1. **Evidence standard.** Nothing is "complete" until it has been executed and its
   outputs inspected. Import success is not evidence.
2. **Provenance.** Every external dataset enters through the registry
   (`cota_opt.registry`): immutable raw file, SHA-256 checksum, retrieval
   timestamp, source record in `config/sources.yaml`. Unknown data is marked
   `UNKNOWN`, never invented.
3. **No silent data loss.** GTFS validation reports malformed records; it does not
   discard them silently.
4. **CRS discipline.** Never compute planar distances on raw WGS84 lon/lat. All
   metric geometry runs in a projected CRS (Ohio South ft or UTM 17N m; this repo
   uses EPSG:32617, meters).
5. **Assumptions are config, not code.** Cost weights, service periods, layover
   ratios, demand-proxy parameters live in `config/*.yaml`.
6. **Scheduled ≠ actual.** Metrics derived from GTFS are *scheduled estimates*.
   They are never presented as COTA's reported operating statistics unless
   verified against an authoritative source (e.g. NTD).
7. **Honest results only.** Optimization results computed with proxy demand are
   labeled as such. No claim of "a real COTA frequency optimization result"
   unless demand and baseline calibration are mature.
8. **Determinism.** Experiments persist id, timestamp, git commit, input
   checksums, config snapshot, and random seed; reruns with the same inputs
   reproduce the same outputs.
9. **Skeptic pass.** Surprising results get: data check, unit check, CRS check,
   filter check, independent recomputation, before being reported.

## Layout

- `src/cota_opt/` — production logic (typed, tested).
- `tests/` — pytest, deterministic, synthetic fixtures.
- `config/` — sources, assumptions, cost weights, constraints, scenarios.
- `data/raw` (immutable), `data/interim`, `data/processed` — gitignored.
- `outputs/` — reports and experiment artifacts, machine-readable + prose.

## Environment constraints (recorded 2026-08-25)

- Cloud sandbox egress is limited to package registries; cota.com/census.gov are
  unreachable from code. Raw data arrives via the user's machine (staged into
  `data/raw/`). Downloader code still exists and is the canonical path when run
  in an unrestricted environment.
