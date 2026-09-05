# Gate 4-7 — the frozen supernetwork master path set, built and measured

**2026-09-05. Verdict: ARMED, on a measurement rather than on an absence.**

Gate 4-7 was previously ARMED because its object did not exist. It now exists,
it has been benchmarked on a preregistered sample, and it does not close. This
document is the receipt for that, and the reason is not the one anyone expected.

## What was built

`src/cota_opt/exp4_masterpath.py`. Paths are enumerated **once** on the
supernetwork — every pool line in the space active together, under multiple
service/frequency scenarios — and then **filtered** per candidate:

* a master path survives in a candidate iff **every** ride leg it uses belongs
  to a route the candidate actually runs;
* surviving legs are **remapped** onto the candidate's own route-period vector;
* a surviving path that still carries an unmappable leg raises, rather than
  being priced against a route the candidate does not operate.

This is a **restriction of the choice set, not an approximation of it**. Every
path the candidate is scored on is a real path in that candidate, priced
identically to how the exact rebuild would price it.

It is emphatically not what was measured before. `exp4_pathreuse.py` shared one
`pathset_cache` across successive candidates; the cache is keyed by **period
alone**, so every candidate after the first was scored against the *previous
candidate's* paths. That is the incumbent-path reuse gate 4-7 explicitly
forbids, and it measured worst 1.307 relative error on revenue vehicle-hours.
The master path set is roughly **a thousand times better** — worst 5.7e-3 on
the objective. It still does not close the gate.

## The preregistered sample

Declared as a rule, not a list, so it cannot be curated after the fact. For each
of the five frozen C10 deception spaces — which is why the sample already
contains deceptive geometry rather than a benign sample chosen for it:

1. every subset of the case's pool within its cardinality bounds (this supplies
   sparse networks, dense networks, one-route-different pairs and swaps
   exhaustively rather than by selection);
2. the supernetwork itself — the one candidate where filtering must be the
   identity;
3. one PINNED_OFF variant, pinning every period of one line — a fate no subset
   can express;
4. CHOSEN_OFF arises inside any of the above, because `allow_off=True` lets the
   frequency solver switch an active line off on its own.

The envelopes are the cases' own binding budgets, so every candidate sits near
the resource boundary by construction. **80 candidates, 600 ranking pairs.**

A pool line the assembler refuses (one has a one-stop direction) is dropped from
the supernetwork — but only after being retested **alone** and refused there
too, which is what establishes that the refusal is a property of the line and
not of the selection. If every line assembled alone but their union did not, the
subset property the whole filter relies on would fail, and the script raises
instead of quietly shrinking the supernetwork.

## What gate 4-7 requires, and what was measured

> On a preregistered sample the approximation is compared against exact rebuilds
> for objective gap, unserved gap, ranking stability, omitted and improvable
> flow, and whether the promoted set changes; if it cannot identify the exact
> leader within the promotion band, it is widened or abandoned.

| quantity | measured |
|---|---|
| worst objective relative gap | 5.745e-03 |
| worst unserved gap | 220.1 trips |
| total omitted flow | 972.4 trips |
| worst improvable flow (relative) | 8.082 |
| worst field relative difference | 8.082 |
| ranking inversions | **120 of 600 pairs (20.0%)** |
| exact leader identified | **2 of 5 cases** |
| promoted set unchanged | **1 of 5 cases** |
| median speedup | 5.30× (range 2.36–9.66×) |

## The finding that matters

**The residual is not caused by filtering.**

The supernetwork candidate has survival fraction 1.000 — every master path
survives, the filter is the identity — and it *still* differs from the exact
arm, by 4.6e-4 to 3.7e-3. In **four of five cases the reuse arm scores better**,
not worse.

That is not an approximation error. It is an **enumeration richness** difference:
the master is built with extra service/frequency scenarios, as the contract
requires ("a rich master path set under multiple service/frequency scenarios"),
while the exact arm enumerates at production defaults. The master finds paths
the exact rebuild never proposes, and prices them honestly.

This inverts the obvious remedy. Gate 4-7 says the approximation is "widened or
abandoned", and widening was tried first: 3× the scenarios and 2× the per-OD
path cap moved the master from 377 to 404 paths per period and changed the
verdict not at all — same leader missed, same 1-of-10 inversions, same worst
field difference to four digits. **Widening makes the master more different from
the exact arm, not less.** It cannot close a gap that is partly the difference
between the two enumerations.

The second half of the residual is structural, and scales cleanly with how far
the candidate sits from the supernetwork:

| active lines | candidates | median survival |
|---|---|---|
| 1 | 23 | 0.097 |
| 2 | 39 | 0.241 |
| 3 | 8 | 0.712 |
| 4 | 4 | 1.000 |
| 5 | 6 | 1.000 |

A single-line candidate keeps under 10% of the master's paths, and one case
reached survival 0.000 — no master path survived at all. The reason is not
truncation: a route that is only worth taking once other lines are absent is
*dominated* in the supernetwork, so it never enters the supernetwork's top-k for
that OD however large k is made. Raising `max_paths_per_od` does not reach it.

**This is directly relevant at Experiment 4 scale, not an artifact of a small
sample.** The real pool is 206 lines with roughly 40 active, so a candidate is
about as far from its supernetwork, proportionally, as a 1-of-4 candidate is
here — the regime with 9.7% survival.

## Why the gate does not close, and what would close it

Gate 4-7's closing condition is not a numeric epsilon. It is whether the
approximation **identifies the exact leader within the promotion band**.
Experiment 4's band is the output of D18's gap benchmark, which has not been
run. So exactly two closures are available:

* **band-independent** — same leader in every case, zero ranking inversions,
  unchanged promoted set. That identifies the leader within *any* band however
  narrow, and closes the gate on the measurement alone. **Not met:** 2 of 5
  leaders, 20% of pairs inverted, promoted set changes in 4 of 5 cases.
* **band-dependent** — the residual is inside a band that does not yet exist.
  **Blocked on D18.**

A 5.7e-3 objective gap may well be immaterial. Nobody may say so yet, because
saying so is what the promotion band is for, and the whole point of setting a
band before the search is that it cannot then be chosen to fit a result.

So gate 4-7 stays **ARMED**, and its blocker has changed from *"the object does
not exist"* to *"the object exists, is measured, and needs D18's band or a
different discovery design."*

## What this costs the Experiment 4 plan

The gate exists because rebuilds dominate: 311 of every 413 seconds. The
measured speedup is **5.3× median**, real but well short of what the greenfield
search was budgeted against — and it currently buys a 20% ranking inversion
rate. Three options remain, and none is this document's to choose:

1. run D18, get the band, and see whether 5.7e-3 is inside it;
2. build the master at **production enumeration settings**, which removes the
   richness half of the residual and makes the comparison measure filtering
   alone. This is a different object from the one the contract describes and
   would need that text changed — a methodology decision, not a benchmark
   parameter;
3. abandon reuse for discovery and pay for exact rebuilds, which is the
   conservative option gate 4-7 already names.

## Incidental, and not incidental at all

This benchmark is what found **D35** — `PINNED_OFF` was a label on the state
digest and not a constraint on the score. Its `pinned_off` rows came back
byte-identical to its supernetwork rows in all five cases. The sample contained
a `pinned_off` variant only because the preregistered sample said to include a
fate the subsets cannot express, which is the argument for declaring a sample by
rule rather than by convenience.

## Artifacts

* `src/cota_opt/exp4_masterpath.py` — the object
* `scripts/exp4_masterpath_benchmark.py` — the benchmark
* `outputs/exp4/masterpath_benchmark.json` — 80 candidates, per-field, per-case
* `outputs/exp4/pathreuse_benchmark.json` — the naive result this replaces
