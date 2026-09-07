# EXPERIMENT 4 — BLOCKING CONTRACT

`EXP4_BLOCKING`, version 2, digest `4840070385b7bc3e`.
Implementation: `src/cota_opt/exp4_blocking.py`. Tests: `tests/test_exp4_blocking.py`.

Version 1 was preregistered on 2026-09-06. Version 2 amends its §9 and is dated
2026-09-07. **No Experiment 4 execution has occurred under either version.**

---

## 1. Two instruments, and they answer different questions

| | question | reads | frozen? |
|---|---|---|---|
| `blocks.reconstruct` | how many vehicles does COTA's **published** blocking use? | `block_id` on 2,331 real weekday trips | yes, untouched |
| `block_candidate_schedule` | what fleet do **these** trips require if feasibly reblocked? | nothing — it solves for a blocking | v2 |

The second is never called a reconstruction. It may land above or below the
published figure without either being wrong: COTA's blocking is one feasible
solution shaped by crew rules, depots and history, not the minimum.

Both count vehicles through one shared function, `blocks.block_concurrency`, so
they cannot drift into slightly different timestamp logic.

## 2. Materialisation

`materialize_timetable(network, frequency_plan, periods, first_dep_sec_by_period)`
reuses `exp4_assemble`'s reading of a headway — a period's trips begin at that
period's `first_dep_sec` and repeat every `headway` minutes while they still
start inside the window — rather than inventing a second one. Deterministic,
order-independent, content-addressed. An OFF route-period contributes no trips.

## 3. Deadhead

`DeadheadOracle.time_sec(from, to, departure_sec)` **raises** `DeadheadUnknown`.
An unknown connection is infeasible, never free. A missing deadhead silently
treated as zero lets a bus teleport, which is the same class of error as the
concurrency proxy this instrument replaces.

Barred as substitutes, each for a stated reason: pedestrian walking speed; the
NTD 12.20 mph in-service figure; `linkgraph.ObservedLink` revenue times; and the
slack between consecutive trips in published blocks — that gap proves a
connection *happened* and bounds deadhead from above by whatever the scheduler
left. It is not a travel time.

## 4. Solver

DAG minimum path cover by maximum bipartite matching (Hopcroft–Karp):

    minimum_blocks = n_trips − maximum_matching

Matching, not min-cost flow: counting buses does not need costs, and a flow
formulation invites a secondary objective nobody preregistered.

## 5. Rejection conditions

A chain set is rejected if a trip appears in zero or more than one block, a
connection is infeasible under the oracle, time runs backward, a cycle appears,
the chain count disagrees with the matching number, or a chain claims a deadhead
the oracle never supplied.

---

## §9 — production feasibility

### 9.0 ORIGINAL, PRESERVED — superseded by Amendment 1

> Production feasibility: `candidate_fleet[p] <= envelope.fleet[p]` for all six
> periods AND vehicle-hours.

It was written that way because the frozen envelope is a six-period vector, so a
six-period test looked like the faithful way to enforce it.

**What validation showed.** `candidate_fleet[p]` is the concurrency of *one*
maximum matching. Reversing adjacency order on the stripped-block baseline yields
a different maximum matching with the **same** minimum block count of 212 while
per-period concurrency moves by as much as **15 vehicles** — midday 199 → 210,
am_peak 195 → 210. The quantity is a property of one equally optimal blocking
realisation, not of the candidate timetable.

**Rejected repair.** Canonicalising the adjacency order, sorting edges, or
otherwise forcing one deterministic matching. That would make the statistic
reproducible without making it operationally meaningful, which is the worse
failure: a number that is stable and means nothing.

### 9.1 AMENDMENT 1 — 2026-09-07, before any Experiment 4 execution

> The preregistered per-period blocking arm was removed before Experiment 4
> execution because validation demonstrated that it was not invariant to the
> choice among equally optimal maximum matchings. Under the experiment's
> `OPERATIONAL_RECOURSE` assumption, fleet feasibility is instead evaluated
> using matching-independent block-count bounds and, once deadhead provenance is
> complete, minimum path-cover cardinality under the declared deadhead oracle.

The question is now **existential**: *does there exist a feasible blocking of
the candidate timetable within the allowed fleet envelope?* It is no longer
*what period-by-period profile does one arbitrary maximum matching produce?*

Per-period figures are **diagnostic only**. They are still computed and still
reported, under a field named so, and they gate nothing.

**Not permitted under this amendment:** min-cost flow or any further
optimisation layer introduced to rescue the rejected statistic; a canonical
adjacency order adopted to make it reproducible; reporting either end of the
bracket as the candidate's fleet number.

**Deferred to a separate experiment:** whether there exists a *minimum-fleet*
blocking that also satisfies additional period-specific concurrency constraints.
That is a constrained-blocking problem, not this one.

### 9.2 Three verdicts, and refusal is one of them

`production_feasible` returns `FEASIBLE`, `INFEASIBLE`, or `UNDECIDABLE`.

**INFEASIBLE** requires a matching-independent violation, so a refutation can
never be an artifact of which matching turned up:

* revenue vehicle-hours over the envelope — a property of the timetable, not of
  the blocking;
* `period_lower_bounds` over the envelope — a vehicle is unavailable over
  `[departure, arrival + min_layover)` however the trips are chained, because
  deadhead is non-negative;
* block count above the baseline's *under the same instrument*;
* a bracket that cannot be reconciled: the candidate needs more with every
  deadhead free than the baseline needs with no interlining at all.

**FEASIBLE** requires an oracle whose provenance satisfies the certification
contract — currently unreachable, and correctly so.

**UNDECIDABLE** everywhere else, and *every* blocker is reported, not the first
one found; a blocker list that reveals itself one item per run is a queue.

A bracket containing the answer never upgrades `UNDECIDABLE`. The baseline
returning `UNDECIDABLE` under current provenance is correct behaviour.

---

## 6. The bracket, and what it is not

    180  ≤  true minimum fleet  ≤  212        (2,331 baseline trips)

Upper: `SameTerminalOracle` forbids every cross-terminal connection. Lower:
`ZeroDeadheadRelaxation` grants them all free and is labelled as certifying
nothing. Any real deadhead model lands between. The published **197 sits
inside**.

`CandidateFleetBound` carries both ends as one object and raises on
`certified_value()`, because neither end is the candidate's fleet requirement.

**Solver cross-check.** Under the relaxation the reachability relation is
transitively closed, so Dilworth forces minimum chain cover = maximum antichain =
peak interval concurrency. Matching returns 180; the analytic identity returns
180. That validates Hopcroft–Karp on 2,331 real trips independently of any
transit assumption.

## 7. Four fleet numbers that are not one number

`FleetQuantity` refuses `float()`, refuses ordering, and refuses comparison
across kinds. Reading requires naming a purpose; the legacy proxy refuses any
purpose containing "certif".

| kind | value | instrument |
|---|---|---|
| `PUBLISHED_BLOCK_PEAK` | 197 @ 17:13 | `blocks.reconstruct` |
| `CANDIDATE_BLOCK_BOUND` | 180–212 | path cover, deadhead OPEN |
| `LEGACY_CONCURRENCY_PROXY` | 176.132352 | `FitnessVector.peak_vehicles` — **barred from certification** |
| `CERTIFIED_MINIMUM_BLOCKS` | — | does not exist yet |

Neither the cap nor the proxy is defaulted anywhere in source: a resource cap is
read from `outputs/CANONICAL_ENVELOPE.json` or the production `baseline`
sentinel, never retyped.

## 8. Audit of COTA's own blocking

| | count |
|---|---|
| transitions examined | 2,047 |
| same terminal, feasible | 2,007 |
| same terminal, under the 300 s minimum layover | 7 |
| cross-terminal (deadhead unknown) | 33 |

98.4% of the published blocking needs no deadhead data at all. The 7 short
layovers measure the 300 s **assumption**, not a defect in COTA's schedule, and
are not to be reinterpreted as evidence about COTA's layover policy.

## 9. Terminal identity — a second open input

Found by running the gate on a real candidate rather than by reasoning about it.

GTFS `parent_station` is **empty in all 2,949 stop rows**, so nothing states
which stop_ids are one physical terminal. On the published feed this barely
matters: 9 of 2,331 trips (0.4%) end where nothing starts. On a synthesised pool
candidate it dominates — an outbound ends at `HIGHALS` while its own inbound
starts at `HIGHALN`, and **240 of 288 trips (83.3%)** are stranded, so the
same-terminal upper bound is one block per trip almost by construction.

Barred substitutes: grouping stops within some distance (the threshold would be
invented and the answer would move with it); grouping by `stop_name` prefix or a
`BAY` suffix (that infers geography from a label); assuming a route's two
directions share a terminal because they are the same route.

`terminal_identity()` measures it, and `production_feasible` **withholds every
terminal-dependent comparison** on a degenerate timetable — in both directions,
so it neither refutes nor approves on an artifact. Terminal-free lower bounds
still bite. Readiness item **D24**.

## 10. Operational recourse

`OPERATIONAL_RECOURSE`, digest `44a81590ff1b1e81`. Reblocking is permitted; no
additional fleet beyond the frozen per-period envelope, and no change to the
network, frequency plan, deadhead assumptions or layover assumptions alongside
it.

## 11. Status

**EXP 4 BLOCKED — CANDIDATE BLOCKER IMPLEMENTED, DEADHEAD PROVENANCE OPEN,
TERMINAL IDENTITY PROVENANCE OPEN.**

Both missing inputs would be closed by the same artifact: an operator-supplied
terminal/garage table. Neither is replaced with a convenient assumption.
