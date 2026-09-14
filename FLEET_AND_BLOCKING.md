# Fleet, blocking, and the deadhead nobody has

Written 2026-09-06. **Status section updated 2026-09-14, after Experiment 4 ran
to completion.** Supplements `claude/state-of-play.md`.

**Read the status section first if you are here because Experiment 4 finished.**
It did, and **nothing in this document changed as a result.** That is the point.

## Why this document exists

Experiment 4's resource constraint is a fleet cap. For most of this project the
number standing in for that cap was whichever fleet-like quantity was nearest to
hand, and three different quantities were in circulation at once. Two of them
were **outputs of an evaluated plan**, which means a cap was being read off the
thing the cap was supposed to constrain. This document records what the three
quantities are, which one is the cap, and what had to be built before a
*candidate* network could be measured against it at all.

## Three fleet numbers, one cap

On the identical baseline, at the identical period:

| quantity | value | what it is |
|---|---|---|
| **block-derived peak vehicles** | **197** | COTA's own vehicle blocks, reconstructed from `block_id` on 2,331 weekday trips. **This is the cap.** |
| `FitnessVector.peak_vehicles` | 176.49 | the frequency model's peak concurrency, `max_p Σ cycle/headway`. An evaluation *output*. |
| `routewise_peak` | 150.73 | the same proxy before interlining. Also an output, and further away. |

The ratio 197 / 150.73 = **1.307** is the "interlining factor". It is **evidence
of proxy error, not an exchange rate**, and nothing in the codebase is permitted
to multiply by it.

The cap is frozen in `outputs/CANONICAL_ENVELOPE.json`, digest
**`b6c647d3766338a6`**: 2,517.183333 weekday revenue vehicle-hours and the
six-period vector `{early 135, am_peak 187, midday 173, pm_peak 197, evening 178,
owl 149}`, peak 197 at 17:13 across 284 blocks. NTD-reported VOMS is 198, a
0.51% disagreement. The artifact carries a `NOT_THE_CAP` block naming each
rejected quantity and why, because the failure mode here was never ignorance of
the right number — it was that the wrong number looked equally plausible at the
point of use.

**The rule: a resource cap is read from the frozen artifact or from the
production `baseline` sentinel. Never off an evaluated plan, and never retyped
into a script.**

## The instrument problem

`blocks.reconstruct` reads `block_id` off real trips. A candidate network has no
`block_id` — its trips do not exist yet — so the instrument that produced the cap
cannot measure the thing being capped. Something else was silently supplying that
number.

So there are now **two instruments, deliberately not one**:

* `blocks.reconstruct` — "how many vehicles does COTA's **published** blocking
  use?" Semantics frozen. Reproduces the envelope exactly.
* `exp4_blocking.block_candidate_schedule` — "what fleet do **these** trips
  require if they are feasibly reblocked?" It has no blocking to read, so it
  solves for one: minimum path cover on the DAG of feasible connections, via
  maximum bipartite matching, `minimum_blocks = n_trips − maximum_matching`.

The second is never called a reconstruction. It may land above or below the
published figure without either being wrong: COTA's blocking is *one feasible
solution* shaped by crew rules, depots and history — not the minimum.

Both count vehicles through one shared function, `blocks.block_concurrency`, so
the two cannot drift into slightly different timestamp logic.

## Deadhead is the missing input, and it is bracketed rather than guessed

A vehicle can only continue onto a trip it can physically reach. That needs a
deadhead travel time between terminals, and **this project has no defensible
source for one**:

* `walk_speed_m_per_min` is a pedestrian speed;
* the NTD 12.20 mph figure is *in-service* speed, with stops and dwell;
* `linkgraph.ObservedLink` covers movements actually operated in revenue
  service, which a terminal-to-terminal deadhead generally is not;
* the slack between consecutive trips in a published block proves a connection
  *happened* and bounds deadhead from above by whatever the scheduler left. **It
  is not a travel time**, and treating it as one manufactures evidence out of a
  scheduling artifact.

`DeadheadOracle.time_sec` therefore **raises** rather than returning zero, and an
unknown connection is *infeasible, not free*. A missing deadhead silently treated
as zero lets a bus teleport — the same class of error as the concurrency proxy
this instrument exists to replace.

The missing input is bounded from both sides instead of filled in. On the real
weekday feed, 2,331 trips, terminals taken from `stop_times`:

```
180  <=  true minimum fleet  <=  212
```

The upper bound forbids **every** cross-terminal connection; the lower bound
permits all of them for free and is labelled a relaxation that certifies nothing.
**The published 197 sits inside the bracket.** That is the entire honest claim:
the historical blocking is consistent with the physics, and the instrument
neither reproduces it nor contradicts it. Closing the bracket needs a real
deadhead table — `TableDeadheadOracle` accepts one without touching the solver.

**Solver cross-check.** Under the zero-deadhead relaxation the reachability
relation is transitively closed, so Dilworth forces minimum chain cover =
maximum antichain = peak interval concurrency. The matching returns 180 and the
analytic identity returns 180 — a check of the Hopcroft–Karp implementation on
2,331 real trips that depends on no transit assumption at all.

## What COTA's own blocking needs

Every consecutive transition inside a published block, checked against the
connection rule:

| | count |
|---|---|
| transitions examined | 2,047 |
| same terminal, feasible | 2,007 |
| same terminal, under the 300 s minimum layover | 7 |
| cross-terminal (deadhead unknown) | 33 |

**98.4% of the published blocking needs no deadhead data at all.** The missing
input is real but small. The 7 short layovers measure the 300 s *assumption*, not
a defect in COTA's schedule.

## The finding that changed the acceptance test

The production-feasibility test was specified as `candidate_fleet[p] <=
envelope.fleet[p]` for all six periods, plus vehicle-hours.

**The per-period arm of that test is not a well-posed question.** A maximum
matching is not unique. Reversing the adjacency order yields an *equally maximum*
matching — same `minimum_blocks`, 212 — whose per-period concurrency differs by
up to 15 vehicles (midday 199 → 210, am_peak 195 → 210). Longer chains hold a
vehicle nominally in service across an idle midday it never worked, and which
chains you get is an artifact of list order.

So `production_feasible` returns **three** verdicts, and refusal is one of them:

* **INFEASIBLE** is claimable. `period_lower_bounds` is matching-independent and
  no blocking can beat it; vehicle-hours is a property of the timetable, not of
  the blocking; `minimum_blocks` is a graph invariant comparable to the baseline
  measured with the same instrument.
* **FEASIBLE** is not claimable while the per-period figure moves with list
  order — the function returns **UNDECIDABLE** rather than whichever verdict the
  current tie-break happens to produce.

*The instrument can refute a plan. It cannot yet approve one, and it says so.*

This is the same shape as D35 and OPERATIONS 24/27/31: **a test that appears to
be checked is not evidence that it checks anything.** Here the test would have
returned a verdict on every run, and the verdict would have been a property of
the solver's tie-break.

## Status — updated 2026-09-14

**EXPERIMENT 4 HAS RUN AND COMPLETED. THE FLEET POSITION IS UNCHANGED:
DEADHEAD PROVENANCE OPEN, TERMINAL IDENTITY OPEN, EVERY CANDIDATE UNDECIDABLE.**

Experiment 4 certified 200 of 200 promoted candidates on 2026-09-14 and
established an exact leader (`...ecb2ffc4bcce`, objective 3,511,184.5658). It ran
under `READINESS_FROZEN` (authorised by Ian, 2026-09-07), which reclassified the
fleet question rather than resolving it:

> Fleet uncertainty must be reported but must not prevent execution or ranking.
> Only an error that makes candidate construction or objective comparison
> invalid may stop the run.

So the run proceeded with **fleet REPORTED, NOT GATED**. Concretely:

* `production_feasible` returned **`UNDECIDABLE` for every one of the 200
  candidates, including the leader.** No candidate was refuted and none was
  approved.
* **No fleet verdict filtered, ranked or rejected anything.** Ranking was on
  `objective_EXACT` alone, under the frozen tie-break `0297e180cf30369d`.
* D24 (terminal identity) moved from **launch gate** to **post-result
  operational validation**. It is **not closed**; its status is unchanged.

**Certification finishing did not advance the fleet question by one step.** The
leader is the best certified objective under the canonical vehicle-hours
envelope and nothing more. There is no fleet requirement for it, and the
180–212 figure is a `CANDIDATE_BLOCK_BOUND` on the *published baseline* —
**neither end may be reported as the leader's fleet number**, or as anyone's.

The leader's own bracket makes the point harder than the baseline's does:

```
leader ...ecb2ffc4bcce, 476 trips:   71  <=  minimum fleet  <=  373
```

A width of 302 vehicles on a 476-trip timetable. That is not a loose estimate,
it is the absence of an estimate — the lower end is the zero-deadhead Dilworth
relaxation and the upper end is one block per trip where no same-terminal
continuation exists, which on a synthesised candidate is nearly everywhere
(D24: 83.3% of candidate trips stranded). Quoting either end as a fleet figure
would be quoting an artifact of a missing input.

Anyone reading the Experiment 4 result as a deployable plan is reading it wrong.
The deadhead oracle it would need still does not exist, and a convenient
assumption is still not a substitute for a missing input.

**Both open inputs would be closed by the same artifact: an operator-supplied
terminal/garage table.** That is the single thing that would move this document.

### D23 — resolved before launch

The earlier version of this section recorded D23 as the single open readiness
item, failing because `scripts/exp4_launch.py` carried a hardcoded `2507.0`
hours and a scalar peak. **Both were removed on 2026-09-07**; the launcher reads
the frozen artifact, and D23's ten assertions were MET at launch. Readiness stood
at 23 MET · 1 OPEN · 1 MANUAL of 25 when the run started, the one OPEN being the
missing deadhead/terminal input rather than missing code.

## Where it lives

`src/cota_opt/exp4_blocking.py` · `src/cota_opt/blocks.py`
(`block_concurrency`) · `tests/test_exp4_blocking.py` (56 tests) ·
`scripts/exp4_blocking_validate.py` · `outputs/exp4/blocking_validation.json` ·
`outputs/CANONICAL_ENVELOPE.json` · `scripts/exp4_freeze_envelope.py`.
Per-candidate fleet verdicts from the completed run are in
`outputs/exp4/run/status.json` under `fleet_feasibility`.
