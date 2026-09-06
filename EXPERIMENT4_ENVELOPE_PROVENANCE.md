# Resource envelope provenance — three fleet numbers, one cap

**2026-09-06.** Written because a production run launched on an envelope with no
provenance, and the mistake was the one this codebase had already written down.

## Verdict

| number | what it actually is | source | cap? |
|---|---|---|---|
| **2517.183333** | GTFS **scheduled** weekday revenue vehicle-hours | `exp1_*/experiment.json` → `gtfs_scheduled_revenue_veh_hours`; `exp2.build_setup` **raises** unless the model reproduces it to <1e-9 | **YES** |
| **197.0** | **block-derived** peak vehicles at pm_peak, 17:13, from reconstructing COTA's 284 vehicle blocks out of the feed | `outputs/fleet_check_modelB.json` | **YES** |
| 198 | NTD reported VOMS | `config/assumptions.yaml: ntd_voms` | no — external validation, −0.51% against 197, nothing fitted to it |
| 176.49 | frequency model **peak concurrency**, pm_peak | `FitnessVector.peak_vehicles = peak_arr.max()` — an evaluation **output** | **no** |
| 150.73 | `routewise_peak`, the same proxy **before** interlining | `fleet_check_modelB.json` | **no** |
| 2507.763673 | an **optimized plan's realised** vehicle-hours — 99.63% of the 2517.183 cap | `exp4_equivalence.py` output | **no** |
| 2507.0 | invented | `exp4_launch.py` — me | **no** |
| 200.0 uniform | invented | `exp4_launch.py` — me | **no** |

Canonical per-period block-derived fleet:
`early 135 · am_peak 187 · midday 173 · pm_peak 197 · evening 178 · owl 149`

Frozen at `outputs/CANONICAL_ENVELOPE.json`, digest `b6c647d3766338a6`,
cross-checked against EXPERIMENT4_CONTRACT §3 and refusing to write on
disagreement.

## The trap, which the codebase had already documented

`src/cota_opt/contract.py`, written long before this run:

> The fleet half of gate 3-8 needs the BLOCK-DERIVED peak, the proxy Experiment
> 1 validated against NTD's VOMS of 198. The frequency model's own
> `peak_vehicles` is peak concurrency, a different and systematically smaller
> quantity — **on the unedited network it reads 176 against the block-derived
> 197**. Comparing concurrency to a block-derived budget would pass every plan
> while appearing to check something, so the check records that it did NOT run
> rather than running wrong.

Measured here: concurrency 176.49 against block-derived 197 **at the same
period**, a 10.4% understatement, because concurrency does not model interlining
(measured factor 1.307). The two numbers are not the same quantity in different
units. They are different quantities.

`peak_vehicles = max over periods of Σ (2·runtime·(1+layover) / headway)` — a
continuous, fractional, interlining-blind concurrency. It is what `_feasible`
compares against `ResourceBudget.peak_vehicles_by_period`, so the optimizer's
internal fleet constraint is **concurrency vs concurrency** and is internally
consistent — but it is **not** the 197-bus envelope the contract freezes, and
the block-derived check is currently recorded as `NOT RUN`.

## How the error happened

I read `revenue_veh_hours 2507.763673` and `peak_vehicles 176.132352` out of the
equivalence receipt and treated them as the envelope. Both are **outputs of
evaluating a plan**. The hours figure is an optimized plan spending 99.63% of
its budget; the fleet figure is concurrency. I then rounded one down to 2507.0
and replaced the other with 200.0 — a number with no source at all, and one that
is *looser* than every canonical per-period cap.

Two errors, one class: **a cap inferred from a plan's usage.**

## Consequences for the running Experiment 4

The run (pid 2690, launched 18:17Z, still running and untouched) uses:

* **2507.0 vh** — 10.18 vh **tighter** than canonical (−0.40%);
* **200.0 peak, uniform across all six periods** — **looser** than every
  canonical per-period cap, by +1.5% at pm_peak and +48% at owl, and applied as
  concurrency rather than block-derived fleet.

**It cannot be the final constant-resource Experiment 4 result.** It may finish
as a diagnostic/exploratory run — the architecture, the proposal generator and
the certification instrument are all exercised on real geometry, which is worth
having — but its envelope is not COTA's, so no resource-constrained claim can
rest on it. The production search and certification must be rerun under the
frozen cap.

Nothing has been rewritten or reinterpreted after the fact. The run's own
`status.json` records the envelope it actually used, and this document records
that the envelope was wrong.

## The new invariant

**Readiness D23 — "Production resource envelope equals the frozen canonical
one."** It reads `outputs/CANONICAL_ENVELOPE.json` and the launcher's declared
constants and refuses when they differ, naming the concurrency-vs-block trap in
its own failure text. It is **OPEN** right now, which is correct: the running
launcher does not satisfy it.

D23 also rejects a *scalar* peak constant outright, whatever its value. The
canonical fleet envelope is per-period, and a uniform scalar is a different
constraint even when the number is right.

## What Experiment 5 must inherit

§4 of the Experiment 5 brief says to use the canonical constants rather than
retyping approximations. `exp5_resource.ResourceEnvelope.canonical()` takes them
as arguments and never hard-codes; the frontier percentages will be applied to
`CANONICAL_ENVELOPE.json`, not to whatever the Experiment 4 winner consumes.

One unresolved question Experiment 5 will have to answer explicitly, because it
changes what the fleet axis means: the production optimizer constrains
**concurrency**, while the contract's envelope is **block-derived fleet**.
Scaling the concurrency caps by 75%…150% scales a proxy; scaling the
block-derived caps scales the thing the contract froze. These are not the same
experiment, and E5-8's resource accounting has to say which instrument it is
enforcing. That decision is yours and is recorded here rather than made
silently.
