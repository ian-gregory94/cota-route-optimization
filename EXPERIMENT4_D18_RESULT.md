# D18 — the gap benchmark has run, and it took the forbidding branch

**2026-09-06. D18: MET. Experiment 4: blocked by D18's answer.**

Those are two different statements and the difference is the whole document.
D18's criterion is that the benchmark **has been run** and question 3's answer
**recorded** — "including the branch where it forbids discovery-effort
comparison." That branch was taken. The item is met. The experiment is not
runnable as designed.

`outputs/exp4/gap_benchmark.json` · design digest `69be98f915d60492`

## Method

D33's, ported to Experiment 4 networks exactly as EXPERIMENT4_DESIGN §3
requires — and §3 is explicit that D33's *number* does not transfer, so this
measured its own.

All but *N* route-periods are frozen at the **delivered Gen1 plan** by a
one-rung ladder; the free ones keep *K* = 3 rungs around theirs; every one of
the K^N combinations is priced by the real evaluator and the best feasible one
is the exact optimum **of that reduced problem, under the production
objective**. Benchmark objective and production objective are the same function.
The approximation is confined entirely to the size of the decision space, which
is stated rather than hidden.

The enumerator is the existing one — `gen2_frequency.solve_exact`, driven
through `solve_on_network(solver="exact", ladder_override=…)` — so the exact
reference and the heuristic answer come from the same setup, the same evaluator,
the same feasibility predicate and the same scalarization. Nothing about the
comparison is reimplemented.

Full ladder enumeration was never an alternative, and that is measured rather
than assumed: at 336.6 µs per combination one line is 7.53e6 combinations and 42
minutes, and two lines is 5.67e13 — roughly 600 years. The reduced neighbourhood
at K=3, N=10 is 59,049.

**36 cells**: four network structures × three free-route-period strata (peak,
offpeak, seeded random) × three sizes (N = 6, 8, 10). Anchored on the delivered
plan, λ = 2, seed 20260825.

## Q1 / Q2 — the gap and how it distributes

Median **+0.297432%**, mean +0.259385%, max +0.645892%. Nonzero in **34 of 36**
cells — the heuristic is genuinely not at the optimum of its own neighbourhood.

| structure | n | mean gap | max gap |
|---|---|---|---|
| dense (high-branching) | 9 | **+0.164698%** | +0.381521% |
| many_off | 9 | **+0.135827%** | +0.401451% |
| other_pool | 9 | **+0.363733%** | +0.645892% |
| sparse | 9 | **+0.373284%** | +0.583427% |

Sparse networks sit **2.27×** further from optimal than dense ones.

## Q3 — does the gap move systematically with network structure?

Paired on (stratum, N), so the same subproblem *shape* is compared in two
different network structures. Reference: `dense`.

| structure | n | mean differential | max abs |
|---|---|---|---|
| many_off | 9 | −0.028871 pp | 0.142864 pp |
| other_pool | 9 | +0.199035 pp | 0.377991 pp |
| **sparse** | 9 | **+0.208586 pp** | **0.381749 pp** |

```
largest paired |differential| : 0.381749 pp
median absolute gap           : 0.297432 pp
ratio                         : 1.283   (declared limit 0.5)
```

**Q3 ANSWER: the gap TRACKS network structure.**

The threshold was declared in the source before any number existed and is
committed. But the conclusion does not lean on it: a ratio of 1.283 means the
structure-correlated differential is **larger than the median gap itself**. To
avoid forbidding, one would have to accept a limit above 1.283 — i.e. accept
that the between-structure component may exceed the thing being measured.

Nor does it lean on the weakest stratum. `other_pool` changes both the pool and
the structure and is therefore a confounded contrast — but it is not what drives
the result. The largest differential, **0.381749 pp, comes from `sparse`**: same
pool, same envelope, same subproblem shapes, differing only in how many lines
are active. That is the clean contrast, and it is the binding one.

`many_off` behaves like `dense` (−0.029 pp), which is the right sanity check —
it *is* dense with one line pinned off, and the pin does not change the
optimizer's difficulty the way thinning the network does.

## Q4 — what this licenses

**No band is emitted.**

§3's branch, verbatim: *"If (3) says the gap tracks structure, Experiment 4
cannot compare networks at discovery effort at all, and the search must select
on something else — rank stability across efforts, or certification of a wider
frontier."*

`discovery_effort_comparison_permitted: false`.

A generic mean or maximum gap is not an effect floor and none is offered. Only
the differential bounds anything, and the differential is what forbids.

## What it means

The optimizer's **distance from optimal depends on the treatment dimension
itself.** Experiment 4's treatment is which lines are active; the gap is 2.27×
larger on sparse networks than dense ones. So a discovery-effort comparison
between a sparse network and a dense one is partly a comparison of how well the
solver happened to do on each — with a structure-correlated artifact of up to
0.38 percentage points available, against effects the project has been reporting
at 0.19%.

This is **D27's shape one level up**. D27 was the optimizer being *chosen* by the
treatment. This is the optimizer's *answer quality* being correlated with the
treatment. The firewall catches the first; nothing catches the second, because
both arms genuinely ran the same optimizer under the same contract.

§3 wrote this possibility down before the search precisely so that meeting it
would not be a crisis. It has been met, on a preregistered criterion, with the
threshold fixed in advance and the result deterministic on an independent rerun
(byte-identical: every one of the 36 gaps, the design digest, the ratio).

## Consequence for gate 4-7

Gate 4-7 governs a **discovery-effort approximation**. Discovery-effort
comparison is now forbidden, so the gate cannot close on a comparison that may
not be made. `scripts/exp4_gate47_adjudicate.py` refuses on exactly that ground
and records it.

There is an uncomfortable convergence worth naming. Gate 4-7's own measurement
found that master-path reuse **also** penalises sparse networks — median +267 /
+355 / +257 objective units at 1 / 2 / 3 active lines, exactly 0.00 at full
survival. Two independent mechanisms, both biasing against sparse networks, both
in the same direction. A greenfield search would compound them, and both push
toward activating more lines.

## The two paths §3 names

Neither is chosen here.

1. **Rank stability across efforts.** Select on whether a network's rank holds
   as effort increases, rather than on its discovery-effort score. Costs at
   least a second effort level for every candidate the search keeps.
2. **Certification of a wider frontier.** Let discovery propose generously and
   move the decision entirely into exact certification, where the gap is not a
   confound because every promoted network is rebuilt exactly. D28 already bought
   the headroom for this: a certification solve costs about eight minutes rather
   than the hour its iteration count implies, and §4 says that freedom "should be
   spent."

Option 2 is the better fit for what has been measured, because it also disposes
of gate 4-7: if discovery buys no conclusions at all and every decision is made
on exact rebuilds, the reuse approximation's bias stops mattering. It is a change
to how Experiment 4 selects, which is a methodology decision and not one to make
inside a benchmark receipt.

## Status

| item | before | after |
|---|---|---|
| D18 | OPEN | **MET** — run, Q3 recorded, forbidding branch taken |
| gate 4-7 / C9 | ARMED, blocked on the band | **ARMED, blocked by D18's answer** |
| Experiment 4 search | not started | **not started, and not licensed as designed** |

Readiness 21 MET · 1 OPEN (C9) · 1 MANUAL (C15). Gates 10 MET · 5 ARMED · 0 OPEN.
