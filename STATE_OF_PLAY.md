# COTA route optimization — state of play

Last updated 2026-09-07. **Experiments 1, 2, 2B and 3 are closed.** Experiment 3
is frozen at tag `exp3-final-v1`. **Experiment 4 has not launched and is not
launchable**: readiness stands at **23 MET · 1 OPEN · 1 MANUAL of 25**, and the
one open item is a missing input rather than missing code. **Experiment 5 is
built and queued behind Experiment 4.**

## The headline, in one line each

* **Experiment 1 — frequency redistribution: −6.65% ± 0.06 unserved demand at no
  additional buses.** Certified, λ≥2. Untouched by everything that follows.
* **Experiment 2 — route geometry: no supportable claim.**
* **Experiment 2B — all 240 feasible combinations: certified NULL**, surviving a
  matched-start re-test (D31).
* **Experiment 3 — eight edit kinds, 84 states: one certified route mutation,
  −0.187% unserved demand**, with a two-regime caveat that travels with it.
* **Experiment 4 — NOT LAUNCHED.** Everything the readiness pass asked for is
  now built. What blocks it is data COTA has and this project does not.
* **Experiment 5 — resource frontier: implemented, tested, BLOCKED** behind
  Experiment 4.

## D27 — the optimizer was chosen by the treatment

The single most consequential finding of the project, and it is about the
harness rather than about transit.

At discovery effort the frequency plan was snapped to a headway ladder. For some
networks the snapped incumbent was rejected as infeasible and the solver
**silently fell back to a greedy construction** — a *different optimizer*. Which
optimizer ran therefore depended on the treatment.

Nothing was deleted. Contaminated artifacts are marked **SUPERSEDED FOR
QUANTITATIVE INTERPRETATION** and remain readable, because *a superseded artifact
looks entirely legitimate from the inside*, and the record of how it looked is
part of the evidence.

### What the correction did to the answer

Stage A was re-scored across all 88 cells with treatment-independent starts. The
corrected 84-state census **reorders the kind ranking outright**:

| edit kind | n | corrected mean | best single |
|---|---|---|---|
| `add_stop` | 10 | **−0.033%** | −0.189% |
| `straighten` | 12 | −0.024% | −0.083% |
| `change_terminal` | 10 | +0.002% | −0.035% |
| `truncate` | 12 | +0.008% | −0.139% |
| `reroute` | 12 | +0.017% | −0.159% |
| `extend` | 12 | +0.028% | −0.070% |
| `split` | 4 | +0.090% | +0.031% |
| `splice` | 12 | **+0.239%** | +0.053% |

`extend` and `reroute` both changed sign. `straighten` moved from seventh to
second. **`splice` remained worst throughout, which is the internal control** —
Experiments 2 and 2B independently established splices as the harmful kind, so a
correction that leaves that standing while reordering everything above it is
behaving like a correction rather than a new error.

The census is **descriptive only**; its floor is *undefined*, not 0%.

## What D27 forced, and what it taught

* **D28 — the iteration ceiling was never binding.** Effort is bought with
  *restarts*, not iterations.
* **D30 — the fallback states were already in the winning basin.** Maximum |Δ|
  0.000000000 across eight stratified states. Mechanism real, displacement nil.
* **D31 — 2B's certified NULL survives matched starts.**
* **D32 — fixing the start policy collapsed the noise floor to zero.** Replicate
  spread had been measuring solver *variance*, not *error*.
* **D33 — the heuristic is locally optimal almost everywhere.** Max gap
  0.001837%, **not correlated with treatment**. It can veto a conclusion; it may
  never *be* a threshold.
* **D34 — the evaluator was not invariant to pattern identifier renaming.** Fixed
  by ordering patterns on content; verified end-to-end at 0.000e+00.
* **D35 — a constraint that was a label.** `Exp4Selection.pinned_off` was
  validated and hashed into `state_digest` and **reached nothing that scores**.
  Two selections differing only in it produced identical fitness under different
  digests — and `state_digest` is a declared treatment difference, so the
  firewall would have admitted the comparison and reported a zero effect for a
  treatment never applied. *A state space with a member nothing generates is a
  state space with a member nothing checks.*

D29 gates Experiment 4 separately: **an observed link is not an observed turn.**
150 of 206 candidate lines use at least one turn never observed; crosstown 40/40.

## The firewall — why this cannot recur quietly

> No treatment effect may be computed, promoted, certified, plotted, or reported
> unless the harness can prove that treatment and control differed only in
> dimensions the experiment contract explicitly permits.

**Whitelist, not blacklist.** Every field carries a `Sem` classification
(IDENTITY / OPPORTUNITY / OUTCOME / NONE); permitted differences are declared per
event type with written justifications; observations are content-addressed.

**D35 marks its limit.** The firewall proves two arms differed only where
permitted. It cannot prove a permitted difference was actually *applied*.

## Experiment 3 — complete, and it is not the null

Stage B preregistered and frozen before any cell ran. 200 cells, 0 firewall
refusals, evaluation-path digest identical at first and last cell.

> **`add_stop-010#22c4c35ac5b2`: −0.1866% unserved demand, |mean Δ| / SD(Δ) =
> 78.6**, certified against control *and* distinguishable from all 28 other
> certified candidates.

**29 of 39 certified.** The effects did **not** shrink under more search — the
opposite of the Experiment 2 pattern, where two geometry leaders moved 0.645
points and both crossed zero across the identical effort transition.

Two caveats travel with the number: nine of the 39 are seed-invariant, so their
paired SD inherits the control's variance entirely; and two analysis-code fixes
were made after the numbers were visible, each bounded by demonstration (payload
byte-identical, stdout delta one line) and disclosed in full.

**The two-regime split is the result's weakest point and it stands.** §6
escalates what is unresolved or failing, which is by construction the smaller
margins — so the leader has never been solved above 20 restarts, all 28 of its
pairwise comparisons are at 20 restarts, and the best margin confirmed at 40 is
2.33× smaller. Final split: 23 of 29 certified carry 40-restart verdicts; 6 —
the leader among them — carry 20-restart verdicts. Phase 5b would have closed
this and was **abandoned with zero cells completed**, for operational reasons
only, verified against the observation store. Anyone quoting −0.187% should
quote the regime split with it.

**Certified means distinguishable from solver variance at this effort, and
nothing more.**

---

# Experiment 4 — everything is built; the missing pieces are data

Readiness **23 MET · 1 OPEN · 1 MANUAL of 25**. Gates 15: 11 MET, 4 ARMED, 0
OPEN. **No search has run.** The only run that ever started is preserved at
`outputs/exp4/run/STATUS.md` as **DIAGNOSTIC — INVALID RESOURCE ENVELOPE**.

## D18 — MET, and Experiment 4 is blocked by its answer

The gap benchmark ran on 36 cells over 4 network structures by exhaustive
enumeration of a reduced neighbourhood under the production objective. Median
gap +0.297432%, max +0.645892%.

**Q3's answer: the gap TRACKS network structure.** Largest structure-paired
differential 0.381749 pp against a median absolute gap of 0.297432 pp — ratio
**1.283** against a limit of **0.5** declared before any number existed. §3's
**forbidding branch** was taken: `discovery_effort_comparison_permitted = False`,
**no promotion band emitted**.

D18 is MET and Experiment 4 is blocked *by its answer*, which is a different
thing. This is **D27 one level up**: D27 was the optimizer being *chosen* by the
treatment; this is the optimizer's *answer quality* being correlated with it. The
firewall catches the first and structurally cannot catch the second, because both
arms genuinely run the same optimizer under the same contract.

The remedy is an architecture, not a firewall rule:

> **Discovery proposes. Exact optimization decides.**

`ProposalScore` holds a discovery objective and refuses to be compared, ordered,
or converted to a float. The only way to read it is `for_promotion_only()`, whose
name is the audit trail.

## C9 — MET, after the proposal generator was revised

C9 asks whether the discovery approximation identifies the exact leader. Revision
1 failed on a single steepest-descent trajectory from one start. Revision 2 — the
full preregistered multi-start family — passes **6/6 with 100% frontier recall**,
under the exact master-path reuse configuration the production run uses.

Gate 4-7 was corrected to one factor, measured, and then **disposed of by the
architecture** rather than closed: reuse output is a `ProposalScore` that cannot
decide anything, and every promoted candidate is re-certified by `solve_exact`
with no path cache at all. The measured residual is enumeration richness, not
filtering — at survival fraction 1.000, where filtering is the identity, the
reuse arm still differs and is *better* in 4 of 5 cases.

## The envelope: three fleet numbers, one cap

A cap was being read off evaluated plans. Twice. Then invented outright.

| quantity | value | what it is |
|---|---|---|
| **block-derived peak vehicles** | **197 @ 17:13, 284 blocks** | COTA's own blocks, reconstructed from the feed. **This is the cap.** |
| `FitnessVector.peak_vehicles` | 176.132352 | the frequency model's peak concurrency. An evaluation **output**. |
| `routewise_peak` | 150.73 | the same proxy before interlining. |

197 / 150.73 = **1.307**, the "interlining factor". It is **evidence of proxy
error, not an exchange rate**, and nothing may multiply by it.

Frozen in `outputs/CANONICAL_ENVELOPE.json`, digest **`b6c647d3766338a6`**:
2,517.183333 weekday revenue vehicle-hours and `{early 135, am_peak 187,
midday 173, pm_peak 197, evening 178, owl 149}`. NTD VOMS is 198 — 0.51% apart.
The artifact carries a `NOT_THE_CAP` block naming each rejected quantity, because
the failure was never ignorance of the right number: the wrong one looked equally
plausible at the point of use.

**A resource cap is read from that artifact or from the production `baseline`
sentinel. Never off an evaluated plan, and never retyped into a script.**
`scripts/exp4_launch.py` carried `2507.0` hours and a scalar `200.0` peak until
2026-09-07; both are gone, and the launcher now reads the artifact.

## Two blocking instruments, because they answer different questions

`blocks.reconstruct` reads `block_id` off real trips. **A candidate network has
no `block_id`** — its trips do not exist yet — so the instrument that produced
the cap cannot measure the thing being capped. Something else was silently
supplying that number.

* `blocks.reconstruct` — "how many vehicles does COTA's **published** blocking
  use?" Semantics frozen; reproduces the envelope exactly.
* `exp4_blocking.block_candidate_schedule` — "what fleet do **these** trips
  require if feasibly reblocked?" No blocking to read, so it solves for one:
  **DAG minimum path cover by maximum bipartite matching**,
  `minimum_blocks = n_trips − maximum_matching`. Hopcroft–Karp; no min-cost
  flow, because counting buses does not need costs.

Both count vehicles through one shared `blocks.block_concurrency`, so they cannot
drift into slightly different timestamp logic.

`materialize_timetable` turns a frequency plan into concrete trips, reusing
`exp4_assemble`'s reading of a headway rather than inventing a second one.
Deterministic, order-independent, content-addressed.

### Test A — published-block reconstruction

`[135, 187, 173, 197, 178, 149]`, system peak **197 @ 17:13**, 284 blocks.
Exact. It is the provenance test and it guards the shared-counter refactor.

### Test B — the bracket

    180  ≤  true minimum fleet  ≤  212        (2,331 stripped-block trips)

Upper: every cross-terminal connection forbidden. Lower: all of them free, and
labelled a relaxation that certifies nothing. **The published 197 sits inside.**
That is the entire honest claim — the historical blocking is consistent with the
physics, and the instrument neither reproduces it nor contradicts it.

**Dilworth cross-check.** Under the relaxation the reachability relation is
transitively closed, so minimum chain cover = maximum antichain = peak interval
concurrency. Solver 180, analytic 180. That validates Hopcroft–Karp on 2,331 real
trips independently of any transit assumption.

### The audit of COTA's own blocking

2,047 transitions: **2,007** same-terminal feasible, **7** under the 300 s
layover (which measures the *assumption*, not COTA), **33** cross-terminal.
**98.4% of the published blocking needs no deadhead data at all.**

## §9 — amended before execution, with the original preserved

The preregistered arm was `candidate_fleet[p] <= envelope.fleet[p]` for all six
periods, plus vehicle-hours. **That question is not well posed.**

A maximum matching is not unique. Reversing the adjacency order yields an
*equally maximum* matching — same 212 blocks — whose per-period concurrency moves
by up to **15 vehicles** (midday 199 → 210, am_peak 195 → 210). Longer chains
hold a vehicle nominally in service across an idle midday it never worked, and
which chains you get is an artifact of list order.

**AMENDMENT 1** (2026-09-07, before any execution) removes the per-period arm as
a gate. The question is now **existential** — *does there exist a feasible
blocking of the candidate timetable within the envelope?* — and the invariant
quantity is `minimum_blocks`. Per-period figures survive as **diagnostics**.

Deliberately **not** done: canonicalising the adjacency order to make the
statistic reproducible. That would make it stable without making it mean
anything, which is the worse failure. Nor was min-cost flow added to rescue it —
that answers a different question, and belongs to a separate constrained-blocking
experiment if anyone wants it.

The original §9 text is preserved verbatim in `FLEET_ARM_ORIGINAL`, in
`EXPERIMENT4_BLOCKING_CONTRACT.md` under "ORIGINAL, PRESERVED", and in tests that
fail if either is quietly rewritten.

## Three verdicts, and refusal is one of them

`production_feasible` returns `FEASIBLE`, `INFEASIBLE`, or `UNDECIDABLE`.

**INFEASIBLE** always runs through a matching-independent quantity, so a
refutation can never be an artifact of which matching turned up: vehicle-hours
over the envelope; `period_lower_bounds` over the envelope; block count above the
baseline's *under the same instrument*; or a bracket that cannot be reconciled.

**FEASIBLE** requires an oracle whose provenance satisfies the certification
contract. Currently unreachable, and correctly so.

**UNDECIDABLE** everywhere else — and *every* blocker is reported, not the first
found, because a blocker list revealed one item per run is a queue.

*The instrument can refute a plan. It cannot yet approve one, and it says so.*
**The baseline returns UNDECIDABLE, which is correct behaviour.**

## Four fleet numbers are now four types

`FleetQuantity` refuses `float()`, refuses ordering, refuses comparison across
kinds, and requires a named purpose to read; the legacy proxy refuses any purpose
containing "certif". `CandidateFleetBound` carries both ends of the bracket as
one object and raises on `certified_value()`. Neither the cap nor the proxy is
defaulted anywhere in source — a test asserts it, because a correct constant is
still a constant.

## Deadhead provenance — OPEN

A vehicle can only continue onto a trip it can reach, and this project has no
defensible source for terminal-to-terminal deadhead time:

* `walk_speed_m_per_min` is pedestrian;
* NTD's 12.20 mph is *in-service* speed, with stops and dwell;
* `linkgraph.ObservedLink` covers movements operated in revenue service, which a
  deadhead generally is not;
* the slack between consecutive trips in a published block proves a connection
  *happened* and bounds deadhead from above by whatever the scheduler left. **It
  is not a travel time**, and calling it one manufactures evidence out of a
  scheduling artifact.

`DeadheadOracle.time_sec` **raises** rather than returning zero. An unknown
connection is infeasible, never free. `TableDeadheadOracle` accepts a real table
without touching the solver.

## Terminal identity — OPEN, and found by running the thing (D24)

`--stage preflight` executes the whole fleet path on a real 6-line candidate
without starting a search. D23 checks the launcher's *text*; something had to
check that the text *runs*. It ran, and it found a second missing input.

GTFS `parent_station` is **empty in all 2,949 stop rows**, so nothing states
which stop_ids are one physical terminal. On the published feed this barely
matters — 9 of 2,331 trips (0.4%) end where nothing starts. On a synthesised pool
candidate it dominates: an outbound ends at `HIGHALS` while its own inbound
starts at `HIGHALN`, and **240 of 288 trips (83.3%)** are stranded, so the
same-terminal upper bound is one block per trip almost by construction.

Barred substitutes, each for the same reason estimating deadhead from block slack
is barred: a distance threshold (invented, and the answer moves with it); a
`stop_name` prefix or `BAY` suffix (infers geography from a label); assuming a
route's two directions share a terminal because they are the same route.

`terminal_identity()` measures it, and `production_feasible` **withholds every
terminal-dependent comparison** on a degenerate timetable — in both directions,
so it neither refutes nor approves on an artifact. Terminal-free lower bounds
still bite.

**Both open inputs would be closed by the same artifact: an operator-supplied
terminal/garage table.** Neither is replaced with a convenient assumption.

## D23 — ten assertions, MET

A production run's envelope must equal the canonical one **and constrain the
right quantity**. Nine assertions can pass while the run still constrains the
wrong thing: right numbers, wrong variable. The ten check that hours and the
fleet vector are *read from the frozen artifact rather than typed*; that no
scalar peak stands in for a six-period vector; that `peak_vehicle_budget` is not
set to a number `contract.py` can only record as `NOT RUN`; that the envelope
digest is propagated; that no concurrency-to-fleet conversion appears; that the
candidate solver is actually called; that a bound-only oracle's verdict routes
through `production_feasible` and its provenance status is propagated; that
`fleet_by_period` is not read as a gate; and that `BLOCKING_CONTRACT_DIGEST` and
`OPERATIONAL_RECOURSE` are carried.

`OPERATIONAL_RECOURSE` (digest `44a81590ff1b1e81`): reblocking is permitted; no
additional fleet beyond the frozen envelope, and no change to the network,
frequency plan, deadhead assumptions or layover assumptions alongside it.

## Exhaustive enumeration is a one-line instrument

**336.6 µs per ladder combination.** One line is 7.53e6 combinations and 42
minutes; two lines is 5.67e13 and roughly 600 years. Any gap benchmark on
realistic networks must use a reduced neighbourhood, as D33 did. No crossover is
claimed — Gen2 remains at 0.90× exhaustive enumeration on the spaces tested.

**Gen1 is frozen** (`gen1-frozen-v1`) and the bridge has run: verdict
**SUPERSEDED**, Gen1's optimization gap 1.270619 (3.49e-07 relative) over
7,529,536 combinations, leaving 6.1 vehicle-hours of the envelope unspent, at
5,032× the speed.

---

# Experiment 5 — resource frontier: built, tested, BLOCKED

`src/cota_opt/exp5_resource.py` and `exp5_frontier.py`, 32 tests. Blocked behind
Experiment 4; nothing has been run.

The envelope is the same frozen artifact, and the type system enforces it:
`ResourceEnvelope` holds fleet **per period as integers** and **rejects a
one-entry mapping outright** — `{"all": 197}` is a scalar cap in a dict costume,
and a test caught it accepting one. `Exp5Feasibility` refuses a non-block
`fleet_source`. `FLEET_ROUNDING = "floor"`; the superseded continuous proxy is
recorded as `"none_continuous_proxy"` rather than deleted.

`exp5_frontier` supplies treatment isolation, monotonicity, feasibility,
traversal invariance, marginals, diminishing returns and transition matrices.

---

## Operations — 32 rules, each bought with lost work

`OPERATIONS.md`. The costly ones:

* **24 — a batch in flight freezes the code that can change its numbers.** Cost:
  one certification batch and five census states.
* **25 — use a pidfile, never a process-name pattern.**
* **26 — shard the whole list, not the remaining one.**
* **27 — a keeper you never checked is not a keeper.** An hourly trigger had been
  failing at startup on *every* firing while reporting `enabled: true` and a
  healthy `next_run_at`. Nine hours lost to a dead watchdog.
* **28 — this container dies of SESSION idleness, not process idleness.**
* **29 — a wake chain does not survive a foreground hold.**
* **30 — match the wake ladder to what is actually at risk.**
* **31 — checkpoint an expensive result the instant it exists.** An exact
  enumeration ran 41.9 minutes, computed its answer, printed its verdict, and
  died in `json.dumps` on a tuple key with nothing on disk.
* **32 — validate a serializer before the long run, not after it.**

The recurring shape across 24, 26, 27, 29, 31 and D35: *a mechanism that looks
like it is working is not evidence that it ran.* The §9 amendment is the same
shape once more — a per-period test that would have returned a verdict on every
run, where the verdict was a property of the solver's tie-break.

## Repository

`github.com/ian-gregory94/cota-route-optimization`.

The Experiment 3 history was collapsed from 2,875 commits to 328 with a
**byte-identical tree**; `HISTORY_NOTE.md` and `EXP3_HISTORY_MAP.json` record it.

The sandbox holds no git credential and neither does the VM behind the folder
bridge. **GitHub Desktop has its own token and can push.** The loop: sandbox
bundles → `Downloads` → the clone at
`C:\Users\ianjg\source\repos\cota-route-optimization` fetches → Desktop pushes.
`PUSH_TO_GITHUB.md` documents the traps.

The 23 files the clone reports as modified are **pure CRLF noise** — zero changed
lines under `--ignore-cr-at-eol`. Do not commit them.

## Known limitations, with sizes

| Limitation | Size | Direction |
|---|---|---|
| Commute-only LODES demand | 24.7% of regional flow transit-accessible | unknown; largest unquantified error |
| **Deadhead travel time** | **unavailable; bracket width 180–212 (18%)** | **blocks Exp 4 fleet certification** |
| **Terminal identity** | **`parent_station` empty in 2,949/2,949 stops; 83.3% of candidate trips stranded** | **blocks Exp 4 fleet certification (D24)** |
| Frontier below λ = 2 | uncertified on both models | quoted from λ = 2 upward |
| Per-route headways | 19–26% seed disagreement | aggregate unaffected; no route-level recommendation |
| Cross-route hyperpath | 0.516% of generalized cost | overstates waiting on trunk routes; deferred |
| Stop cost | unmeasurable from this feed (−157 s/stop, inverted) | blocks any consolidation claim resting on runtime savings |
| Novel-link running time | MAE 17.2 s, bias +0.41% | not exploitable |
| Novel *turns* (D29) | 150/206 candidate lines; crosstown 40/40 | gates Experiment 4 |
| Scheduled ≠ actual | unquantified | no reliability penalty |
| Gen1 frequency optimality | gap 1.270619 (3.49e-07) on the one network measured exactly | leaves envelope unspent; unmeasured at scale |
