# D18 — the compute policy, decided; the gap benchmark, still not run

**2026-09-05. This is a policy decision. It is NOT D18.**

D18's frozen criterion (EXPERIMENT4_DESIGN.md §9 item 18) is:

> The gap benchmark has been run on Experiment 4 networks, its four questions
> answered in order, and question 3's answer recorded — including the branch
> where it forbids discovery-effort comparison.

That is a **measurement**. No policy sign-off closes it, this record does not
close it, and D18 remains **OPEN**. What follows decides how the measurement
will be bought, because that question was genuinely blocking and is now
answerable from measured numbers rather than estimates.

## What is newly measured

### 1. Gen1's optimization gap on a real Experiment 4 network

The Gen1→Gen2 bridge (`scripts/exp4_gen_bridge.py`) answered one real question
twice — the optimal frequency plan for a one-line assembled network under a
pinned 200 vh / 18 peak envelope, λ=2 — with the two arms differing **only** in
the solver.

| | Gen1 (exchange heuristic) | Gen2 (exhaustive enumeration) |
|---|---|---|
| objective | 3,645,587.5951 | 3,645,586.3245 |
| envelope used | 193.200 vh | 199.333 vh |
| route-periods OFF | 0 of 6 | 0 of 6 |
| seconds | 0.5 | 2,516.1 |

**Verdict: SUPERSEDED.** The exact solver found a strictly better plan.

* **optimization gap: 1.270619 absolute, 3.4854e-07 relative**
* 7,529,536 combinations enumerated, 7,529,389 feasible
* Gen1 is **5,032×** faster and leaves 6.1 vehicle-hours of the envelope unspent

This is one data point of D18's **question 1**, on one network, and it is worth
stating plainly what it is not: it is not the distribution (question 2), it says
nothing about whether the gap tracks structure (question 3), and question 3 is
the one that can forbid discovery-effort comparison outright. A single tiny gap
is the least informative possible evidence about a *structure-correlated* gap,
because a gap that is 3e-7 on simple networks and large on complex ones is
exactly the failure mode §3 was written to catch.

### 2. Exhaustive enumeration does not scale, at all

Measured: **336.6 µs per ladder combination** (30,000-combination timing on the
bridge network). The ladder has 14 rungs and a line contributes 6 route-periods:

| active lines | route-periods | combinations | wall time |
|---|---|---|---|
| 1 | 6 | 7.53e6 | 42 min (measured: 41.9) |
| 2 | 12 | 5.67e13 | ~600 years |

So **full ladder enumeration is a one-line instrument**. Any gap benchmark on
realistic Experiment 4 networks must use a **reduced neighbourhood**, which is
what D33 did and what §3 asks for ("exhaustive enumeration of a reduced
neighbourhood"). Full enumeration was never the plan; this measurement is what
makes that concrete instead of assumed.

Illustrative shape at 40 active lines (240 route-periods), **at the bridge
network's per-evaluation cost**, which is a lower bound because a full network
prices far more paths per evaluation:

* all single-key deviations: 3,120 evaluations, ~1 s
* all two-key deviations: 4.85e6 evaluations, ~27 min

The per-evaluation cost on a full-size network is **not measured** and must be
before any of this is budgeted. It is the first thing the benchmark should time.

### 3. The reason D18 got more urgent, not less

Gate 4-7 was benchmarked this session (EXPERIMENT4_MASTERPATH.md) and stays
ARMED. Its closing test is "identify the exact leader within the promotion
band", and **Experiment 4's promotion band is D18's output.** So D18 now blocks
two things rather than one: the materiality threshold §3 requires, and the
discovery approximation gate 4-7 permits. Without it, discovery pays for exact
rebuilds — about 5.3× the measured cost — and §3's own warning stands: if the
gap tracks structure, Experiment 4 cannot compare networks at discovery effort
at all.

**D18 is not an optional refinement. It is a precondition for Experiment 4
having an admissible comparison.**

## The decision

**Compute policy: sharded, checkpointed, resumable. No held container, and no
work unit whose loss costs more than its own shard.**

Concretely, binding on the D18 benchmark and on anything else at the hour scale:

1. **A work unit is a shard that writes its own result to disk on completion.**
   No shard may be sized so that losing it costs more than a few minutes of
   recompute. The filesystem survives a container recycle; background processes
   do not.
2. **A run is resumable from its shard artifacts**, and re-running a completed
   shard must be a no-op that reads its artifact rather than recomputing it.
3. **Expensive results are checkpointed the instant they exist**, before any
   formatting, aggregation or reporting can touch them. This is not
   hypothetical: the 41.9-minute exact solve above computed its answer, printed
   its verdict, and then died in `json.dumps` on a tuple key with nothing on
   disk. Forty-two minutes were lost to a formatting bug in code that ran after
   all the science was done.
4. **No foreground container hold.** Ian rejected the `sleep`-based hold and it
   is not to be reintroduced. Sessions stay alive by doing work, not by
   pretending to.
5. **The wake ladder is matched to what is actually at risk** (OPERATIONS 30):
   staggered wakes while unheld work runs, and none when nothing is running.
6. **A serializer is validated before a long run, not after it.** Round-trip a
   representative payload at startup, or write the artifact through a coercing
   helper that has its own test.

Rules 3 and 6 are new, and both are paid for by the same lost run. They belong
in OPERATIONS.

## What is deliberately NOT decided here

* **No crossover is claimed.** `EXPERIMENT4_D18_COST.md` measured Gen2 at
  0.90× exhaustive enumeration on the spaces tested — Gen2 is not yet cheaper —
  and every space tested was small enough that its move neighbourhood covers
  most of it. The crossover is certain in principle (Θ(n²) per step against
  Θ(n^k)) and **unmeasured in practice**. It stays unmeasured here. Nothing in
  this record should be read as evidence that Gen2 is cheaper than enumeration.
* **No threshold, band, or materiality floor is set.** Those are D18's outputs
  and setting one now, from one data point, would be choosing the band after
  seeing a result — the precise thing preregistration exists to prevent.
* **D18 is not closed, and its readiness verdict does not change.** It stays
  OPEN with its criterion untouched.

## Status after this record

| item | before | after |
|---|---|---|
| D18 | OPEN | **OPEN** (unchanged, by design) |
| compute policy for hour-scale work | undecided, blocking | **decided** |
| gate 4-7 | ARMED (object unbuilt) | ARMED (object built and measured, blocked on D18's band) |
