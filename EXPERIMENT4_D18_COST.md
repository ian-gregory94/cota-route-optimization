# D18 — measured cost of the Gen2 search, for a decision that is still Ian's

`EXPERIMENT4_DESIGN.md` §3 requires the gap benchmark to be run on Experiment 4
networks before discovery-effort comparison is permitted. That has not been run,
deliberately. What follows is the measurement the decision needs, taken from the
searches that actually executed rather than estimated.

## What it costs now

| case | lines | enumerated networks | enum s | Gen2 evaluations | Gen2 s | matched optimum |
|---|---|---|---|---|---|---|
| greedy_finds_nothing | 4 | 14 | 3.9 | 14 | 4.0 | yes |
| greedy_finds_nothing | 5 | 25 | 7.4 | 23 | 6.2 | yes |
| large_gap | 4 | 14 | 8.4 | 14 | 8.3 | yes |
| large_gap | 5 | 25 | 18.7 | 22 | 16.0 | yes |
| moderate_gap | 4 | 14 | 8.4 | 12 | 6.9 | yes |
| moderate_gap | 5 | 25 | 7.9 | 18 | 6.9 | yes |

* **0.473 s per network** at 20,000 iterations / 1 restart / width 0 on
  three-line networks — against **~380 s** for the full 111-pattern legacy
  network at 60,000/2/32. Cost tracks network size, not pool size.
* **251 MB peak RSS.** Memory is not a constraint at this scale.
* **Gen2 evaluates 0.90× as many networks as exhaustive enumeration.** It is not
  yet cheaper, and that is the honest headline: at five lines with at most three
  active, the move neighbourhood is nearly the whole space.

## How it should scale, and why that is not yet evidence

Enumeration at a cardinality cap *k* over *n* lines is Θ(n^k) — 206 lines with
40 active is not a number anyone runs. Gen2's neighbourhood is one step of
adds (n), drops (|cur|), swaps (|cur|·n) and paired adds (n²/2), so Θ(n²) per
step with few steps. The crossover is therefore certain in principle and
**unmeasured in practice**: every space tested here is small enough that the
neighbourhood covers most of it.

Measuring the crossover needs spaces of 10–20 lines, which is 10³–10⁴ networks
at 0.5 s, i.e. one to two hours per space — and that is the compute-policy
question, not an answer to it.

## What is still missing before D18 can be decided

* the crossover measurement above;
* the §3 gap benchmark itself, which is a *different* question — how far the
  delivered plan sits from an exact one on Experiment 4 networks — and which
  §3 says may **forbid discovery-effort comparison outright** if the gap tracks
  network structure;
* a decision on the container hold, since anything at the hour scale meets the
  same reclaim problem that ended Phase 5b.

Nothing here proposes a policy. The brief was to measure first.
