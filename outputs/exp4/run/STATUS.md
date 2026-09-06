# Experiment 4 run of 2026-09-06T18:17Z — DIAGNOSTIC, INVALID RESOURCE ENVELOPE

**Status: DIAGNOSTIC — INVALID RESOURCE ENVELOPE FOR PRODUCTION.**
**Additionally: did not complete.**

## Envelope it actually used, preserved exactly

    VEH_HOURS     = 2507.0      (canonical: 2517.183333 — 10.18 vh tighter)
    PEAK_VEHICLES = 200.0       applied UNIFORMLY to all six periods,
                                against the frequency model's peak CONCURRENCY

The canonical envelope is 2517.183333 scheduled vehicle-hours and a six-period
**block-derived** fleet vector — early 135 · am_peak 187 · midday 173 ·
pm_peak 197 · evening 178 · owl 149. Neither of the run's constants had
provenance in any artifact, and the fleet constant constrained the wrong
quantity as well as carrying the wrong number.

## What it produced

`pool.json` only: 204 of 206 pool lines assemble alone. **No proposals, no
promotions, no certifications.** The process terminated during the supernetwork
master path-set enumeration over all 204 lines and was not stopped by hand.

## Standing rules for this run

* It is never promoted to a final Experiment 4 result.
* Its objective values — of which there are none — may not be compared against
  the eventual canonical result as replicates. Different resource regimes are
  not replicate runs.
* Nothing here is rewritten or reinterpreted after the fact. The envelope it
  used is recorded above as it was.

## What it was still worth

The architecture reached real production geometry before dying: the pool
screen ran, and the per-evaluation cost of production-scale discovery was
measured on the way in — 77.9 s at 10 active lines, 176.9 s at 25, 329.1 s at
41, with full path rebuild. Those figures stand independently of the envelope
and are what established that master-path reuse is required for discovery to
be affordable at all.
