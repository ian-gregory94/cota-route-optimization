# Experiment 3 — treatment contract

**Committed 2026-08-30, before any Experiment 3 candidate has been generated.**
Nothing in this file may be revised after the first candidate is scored except
to correct a demonstrated error, and any revision must say what it changed and
why. The purpose is not to constrain the search for its own sake. It is that
without a boundary fixed in advance, Experiment 3 becomes Experiment 4 the
moment the optimizer finds something attractive outside it, and no one can tell
afterwards whether the freedom was earned or granted retroactively.

Experiment 3 is **route mutation**, not greenfield network design. It asks
whether changing the structure of COTA's existing routes — within one operating
envelope, with frequency re-optimized — beats the best conservative result
Experiments 1, 2 and 2B could reach without changing structure.

---

## 1. What Experiment 3 is trying to beat

`pre_exp3_baseline_v1`. Every Experiment 3 number is reported against that
frozen object and against **both** of its reference points:

* the **raw baseline** — COTA's network and schedule as published; and
* the **conservative incumbent** — that network with Experiment 1's certified
  frequency redistribution and Experiment 2/2B's promoted geometry, frequencies
  re-optimized.

Beating the raw baseline is not a result. Experiments 1 and 2 already do that.
Only the margin over the conservative incumbent is Experiment 3's.

---

## 2. Legal mutations

Every permitted operation below is a value of `geometry.EDIT_KINDS` that the
code can actually construct, and `tests/test_geometry_order.py::
test_every_declared_kind_is_constructible` builds one of each and applies it.
That test exists because this table previously advertised four operations the
code could not build. **A searchable operation that does not exist is worse
than one that is absent**, because a reader budgets freedom the search never
had.

| operation | `kind` | permitted | limit |
|---|---|---|---|
| **shorten** (truncate a route at an existing stop) | `truncate` | yes | §3 removal cap |
| **straighten** (drop a deviation, keeping both ends) | `straighten` | yes | §3 removal cap |
| **extend** (continue a route to further existing stops) | `extend` | yes | §3 link rule |
| **reroute** (replace a mid-route segment with another) | `reroute` | yes | §3 link rule, removal cap |
| **splice / through-route** (merge two routes end to end) | `splice` | yes | inherently two routes; consumes both |
| **split** (cut one route into two independently scheduled routes) | `split` | yes | each half ≥ 30% of the original stop-visits; the cut may not be a terminal; both halves keep the junction stop; consumes the route |
| **add a stop to a route** | `add_stop` | yes, existing stops only | §3 stop rule; inserted at the least-detour position, deterministically |
| **change terminal** | `change_terminal` | yes | §3 terminal rule — ≤ 1,200 m, to a stop some route already serves |
| **create a crosstown or radial connection** | — | yes, expressed as `splice` or `reroute` | §3 link rule |
| **change transfer point** | — | yes, expressed as a `reroute` on one of the two routes | **narrowed 2026-08-30.** It had no operator and no distinct semantics; giving it one would let the same mutation carry two canonical identities, which breaks state identity |
| **merge two routes into one alignment** (not end-to-end) | — | **no** | not implemented, and no longer advertised |
| **constrained overlay** (a limited variant on an existing corridor) | — | **no** | §4 |
| **express / limited-stop variant** | — | **no** | §4, and gate 3-4: it is a runtime claim from skipping stops on an unchanged alignment |
| **create a new stop** | — | **no** | §3 stop rule |
| **remove a stop from the network** | — | **no** | §4 — the stop-consolidation question, whose exchange rate this feed cannot measure |
| **change frequency** | — | not a mutation | §5 — frequency is re-optimized for every network, never chosen as an edit |

Anything not listed is not permitted, and anything listed without a `kind` is
not a distinct operator — it is a way of describing one of the eight.

---

## 3. What stays fixed, and the limits

**Novel street links are permitted, and are labelled.** A mutation may use a
link COTA does not currently operate, priced by the running-time estimator
validated in `outputs/runtime_validation.json`: 5,832 links, 5-fold, MAE
**17.2 s**, aggregate bias **+0.41%** against a ±2.0% line, verdict *unbiased*.
Every candidate reports `modelled_share_pct`, the share of its segments priced
by the model rather than observed. **A candidate above 2.0% is a secondary
evidence class and may not carry a headline claim** — the same threshold
Experiment 2 used. Median absolute percentage error on a single link is 20.5%,
so a mutation whose advantage is smaller than that on a handful of modelled
links is measuring the estimator.

**A terminal may move up to 1,200 m**, and only to a stop already served by
some route in the feed. 1,200 m is two access radii (the zone-to-stop radius is
600 m), so a terminal move cannot silently strand a catchment that the model
would then have to re-house. Moving further is a different route, not a mutated
one.

**A route may lose at most 40% of its baseline stop-visits.** Past that it is
not the route any more, and the demand attributed to it stops being a fair
comparison. The cap is on stop-visits rather than distance because the demand
model reaches the network through stops.

**No stop is created and none is removed from the network.** A mutation may
change which routes serve a stop; it may not change which stops exist. Creating
one would require ridership at a place that has never had service, which this
demand proxy cannot supply. Removing one belongs to the stop-consolidation
question, whose exchange rate this feed cannot measure (D-series stop-price
diagnostic; `outputs/exp3_stopprice_diagnosis.json`).

**Network edit distance ≤ 15%**, defined as

> (stop-visits added + stop-visits removed, summed over all routes) ÷ (total
> baseline stop-visits)

A candidate above 15% is **Experiment 4** and is out of scope here, however well
it scores. This is the line that stops Experiment 3 drifting; it is a single
number precisely so that it cannot be argued with case by case.

**One atomic mutation touches one route**, except splice, split and merge,
which inherently touch two and count as one mutation.

**Two mutations are structurally incompatible if** they name a common route, or
if one removes a stop the other uses as a terminal or transfer point.
Incompatible pairs are never generated, and the check is on structure, never on
measured performance.

**Corrected 2026-08-30.** This clause used to say the rule was "the one
`geometry.apply_edits` already enforces". It was not. Only splices consumed
their routes; two truncations of the same line composed in application order and
`apply_edits` accepted them. The gap mattered more than it looks: **a state
whose meaning depends on the order its mutations were applied has no
permutation-invariant digest**, so two searches reaching the same set of
mutations by different paths would cache, compare and de-duplicate as different
states. `apply_edits` now enforces one mutation per route by default, and
`tests/test_geometry_order.py` applies a state's mutations in every order and
demands the same network back. The historical complexity-ladder behaviour stays
reachable behind `require_disjoint_routes=False` so Experiment 2's runs remain
reproducible; nothing in Experiment 3 may use it.

---

## 4. What Experiment 3 may not claim

**No advantage may rest on serving fewer stops on the same path.** The natural
experiment in COTA's own schedule returns −157 s per additional stop — patterns
serving more stops are scheduled *faster* — because all eleven available
comparisons differ by a terminal bay or an intersection corner rather than a
wayside stop, and relaxing every filter threshold produces zero wayside
comparisons. So:

* running time on **existing links** is inherited from the observed schedule;
* running time on **novel links** uses the validated estimator, within §3;
* **straightening** that removes distance is credited with the reduced modelled
  running time, because the saving is distance, not stops;
* a mutation whose only claimed gain is fewer stops on the same alignment is
  credited **zero**, or declared outside the supported experiment.

This is revisitable if operational data — AVL, APC, observed dwell — ever
arrives. It is not revisitable by assuming a dwell figure.

---

## 5. How frequency optimization nests

Every serious candidate is scored as

> mutate geometry → rebuild path sets and check adequacy → **re-optimize
> frequency under the same envelope** → evaluate under the frozen Model B
> evaluator

and never as *mutate → keep the old headways → compare*. Experiment 1
established that the aggregate optimum is identified while individual
route-period allocations are not, so scoring a mutation against one arbitrary
headway plan measures that plan's accidents. Experiment 2 showed the cost of
the shortcut directly: the fixed-frequency screen ranked the worst candidate of
twelve first out of sixty.

A fixed-frequency screen may still be used **for discovery only**, to bound a
pool that is too large to evaluate. Its output is labelled as a screen, never
as a ranking, and no candidate is promoted or discarded on it alone.

---

## 5a. What "beats the incumbent" means, fixed before any result exists

**The primary criterion is the λ=2 path-level scalarized objective:**

```
objective(plan) = generalized_cost + λ · w_unserved · unserved_demand
```

with **λ = 2** and `w_unserved` read at runtime from
`config/cost_weights.yaml` (`weights.unserved`, currently 60.0 minutes-
equivalent per unserved trip). The weight is **read, never hardcoded** — a
constant copied into the search would silently diverge the moment the config
changed, and the objective would then be a different objective wearing the same
name. `exp3.objective()` is the single implementation; nothing else computes it.

This is one number, and one number is what a search can be run against. It is
also not enough on its own to describe a plan, so **every result reports all six
of these separately, always, at every stage**:

| metric | why it is not optional |
|---|---|
| generalized cost | rises when a plan serves more people; the scalarized objective hides that |
| unserved demand | Experiments 1 and 2's headline quantity, and the one every prior floor was measured on |
| served demand | the direction the project actually cares about |
| generalized cost per served trip | the only one of these that fell in Experiment 1 |
| weekday revenue vehicle-hours | the binding constraint |
| peak vehicles | hours are not buses; a plan can respect the budget and still need a bigger fleet |

A table showing the objective without the components is not a result.

**The comparison object.** The conservative incumbent is COTA's **unchanged**
geometry with frequency re-optimized inside the same envelope under the same
Model B evaluator. It has no geometry component, because Experiment 2 promoted
nothing and Experiment 2B certified the null across all 240 feasible subsets.

`outputs/canonical/exp1_final.json` is the **reference** result — the frozen
number a reader can check against. It is *not* the thing a margin is computed
from. **Every promoted comparison re-solves the unchanged network itself, at
matched effort, in the same run, with replicates.** D24 is why: the frozen
number was produced by a different run at a different effort, and the entire
Experiment 2 geometry claim came from comparing a well-solved edited network
against a badly-solved unedited one at nominally identical effort. Quoting a
margin against a stored number reintroduces that failure with no way to detect
it.

Beating the **raw published schedule** is context, reported as context. It is
not an Experiment 3 result: Experiments 1 and 2 already beat it, and reporting
it again counts the same gain twice.

**Noise floors are measured for the quantity being compared.** The 0.130-point
and 0.287-point floors in this project are floors on *unserved demand* at two
efforts. They may not be applied to the scalarized objective, which has
different units and a different variance. Every stage that quotes a margin
measures, in the same run and at the same effort, a floor for the objective
**and** a floor for each of the six reported components — from zero-edit
replicates, 3σ, as everywhere else.

---

## 6. Search design: interactions are assumed from the start

Experiment 2 gave direct evidence that geometry interventions are non-additive
— individually beneficial edits become harmful in combination, and the
interaction term reaches 16 times the noise floor at four edits. Experiment 3
therefore searches over **network states**, not over independent edit values.

`score each mutation → rank → take the top N` is forbidden as a search
procedure. It is permitted only as an explicit object of study, stated as such,
whose expected failure is already on record.

Exhaustive enumeration is not affordable here as it was in 2B: 84 mutations
admit far more feasible states than could ever be scored. **The heuristic must
first be benchmarked on a subspace small enough to enumerate exhaustively**, and
must recover the known optimum there before it is trusted anywhere larger. A
search that cannot find the answer where the answer is known is not evidence
about a space where it is not.

**Chosen and benchmarked.** Neighbourhood search over states with restarts:
each step adds one compatible mutation, drops one, or **swaps** one for another.
Swap is not redundant with add-then-drop — 2B found cardinality winners are not
nested, so the best 3-set is not the best 2-set plus one, and reaching the
better state means passing through a worse one, which an add-only search will
not do.

**Benchmark result** (`outputs/exp3/search_benchmark.json`): on 2B's 240
exhaustively enumerated states the search recovers `splice|011|034|WESHIGW` from
all **eight** declared seeds independently, evaluating 57 states of 240, and a
resumed run does zero work and returns the same answer.

Two things about that result are stated rather than left implicit:

* **It is necessary, not sufficient.** That optimum is a single mutation
  adjacent to the null, so a greedy add-only search finds it trivially. Passing
  shows the plumbing works — state hashing, incompatibility, checkpointing,
  resume — and little about the move set. `tests/test_statesearch.py` supplies
  what it cannot: a non-nested optimum only a swap reaches, a deceptive single
  that traps add-only search, a space whose answer is the null, and a benchmark
  harness proven able to fail.
* **The recovered optimum later certified as NULL** (D22). The benchmark
  validates search recovery, not the intervention. Conflating those is the exact
  error gate 12 exists to prevent.

---

## 7. Staged effort, and never mixed in one table

| stage | what it is | what it may support |
|---|---|---|
| **A. discovery** | cheap search over many networks | which candidates to look at. Nothing else. |
| **B. promotion** | full re-optimization and evaluation of a small frontier | comparisons between promoted candidates |
| **C. certification** | full effort, multiple seeds, adequacy, fleet and resource checks, robustness | a headline claim |
| **D. planner inspection** | hand inspection against the network | whether a certified result is implementable |

Every output records the stage that produced it. A discovery score and a
certified score never appear in the same table without the column that
distinguishes them. Stage D runs **after** the numbers exist, never before —
inspecting first is how a pretty map acquires a score.

### Stage A — discovery

* Search many valid network states at **60,000/2/32**, the same discovery effort
  2B ranked at, so the two are comparable.
* **Path sets are rebuilt for every state.** A mutated network's competitive
  paths are not the baseline's, and reusing them would score the mutation on a
  candidate set chosen for a different network.
* **Frequency is re-optimized on every state.** Never scored against one frozen
  headway plan; §5 is the argument.
* Scores are **discovery signals only**. Their magnitudes are not findings.
* The noise floor is measured from zero-edit replicates **before the search
  runs**, so no state can be promoted against a floor that does not exist yet.
* **Checkpointing is below the network-state level** — append-only JSONL keyed
  on the full cache key — and resume is exact: a run that dies loses the state
  in flight and nothing else.
* A state the contract refuses is recorded and priced out of the search, never
  allowed to kill a sweep hundreds of states in. 2B had a worker die on one bad
  subset and get restarted onto it forever.

**Promotion is a band, not a top N.** At discovery effort every state within a
floor of the leader is a tie, and taking the top N discards the true winner
whenever the ranking is off by one floor — which in this project it has been
(D24). Promoted:

* everything within **2.0 floors** of the leader;
* the best **2 states featuring each mutation kind**, so a kind cannot be
  eliminated by the leader's neighbourhood rather than on its merits;
* the best state at **each cardinality**, not required to be nested.

### Stage B — promotion

For every promoted state:

* rebuild path sets and **check adequacy**;
* solve the mutated network **and the unchanged incumbent** at matched effort,
  in the same run;
* use **at least two effort levels**, or a convergence trace, on both sides;
* include **replicated unchanged-network controls in the same run** — not the
  frozen Experiment 1 number, which was produced by a different run at a
  different effort;
* **reject an apparent benefit that shrinks materially as effort rises.** That
  is D24 exactly, and gate 12 makes it automatic;
* report the scalarized objective **and all six component metrics**.

### Stage C — certification

At least Experiment 1's certification effort: **400,000 iterations, 20 restarts,
full width**, and three predeclared seeds — **20260825, 20260826, 20260827**,
the same three Experiments 1 and 2B certified on. Required:

* matched **convergence** on candidate and incumbent, not merely matched effort;
* **same-run noise floors**, for the objective and every reported component;
* path-set **adequacy**;
* **vehicle-hour** compliance;
* **peak-fleet** check against the 197.0 baseline;
* **Model B provenance in the scoring artifact**, read from the setup that
  scored rather than from what the run requested;
* **robustness across the supported λ≥2 range**;
* **mutation identity stability** (gate 3-10).

If different seeds produce structurally different networks within the noise
floor, the aggregate benefit is reported as identified and **the specific map as
unidentified** — exactly as Experiment 1 reports its headways. The prettiest
seed is not selected.

### Stage D — planner inspection

Maps, cycle times, route lengths, transfer logic, reliability exposure, trip
asymmetry, layover plausibility, operator legibility — inspected **only after
numerical certification**. A plausible-looking map does not rescue a failed
numerical gate, and an ugly map is not discarded before it is measured. Gate 9
caught `extend|102` on legibility where no metric did; the order still matters.

---

## 8. Gates

Experiment 3 runs under gates **3-1 through 3-10** as committed in
`ACCEPTANCE.md`, plus gate 12. Those gates were **renumbered on 2026-08-30**,
and the renumbering matters: the gates that used to carry these numbers were
written for stop consolidation — walking traded against vehicle running time —
which is not what this experiment does. They are preserved under the `SC-`
prefix and marked deferred. An Experiment 3 governed by gates about a quantity
it never measures would have been an experiment governed by nothing, and worse,
the deferred consolidation question could have re-entered under Experiment 3's
name because the gates still permitted it.

The operative ten, in one line each:

| gate | what it forbids |
|---|---|
| 3-1 | scoring under an evaluator that cannot state its own waiting model |
| 3-2 | letting a fixed-frequency screen decide what gets evaluated |
| 3-3 | comparing against a floor measured for a different quantity or at a different effort |
| 3-4 | crediting a runtime saving to skipping stops on an unchanged alignment |
| 3-5 | leaving a sole-access stop unserved |
| 3-6 | ranking mutations individually and taking the top N |
| 3-7 | quoting a margin over anything but the incumbent re-solved in the same run |
| 3-8 | exceeding the vehicle-hour budget or the 197.0 peak-vehicle baseline |
| 3-9 | letting a high modelled-link exposure carry a headline |
| 3-10 | promoting one map when the seeds disagree structurally inside the floor |
| 12 | matching nominal effort and calling it matched convergence |

**Gate 12 (convergence, not just effort) applies to every Experiment 3
comparison.** A mutated network and the incumbent it is compared against must
both be shown converged — two effort levels, replicates on both sides, or a
convergence trace — before any margin between them is quoted. D24 is the reason:
an apparent half-point geometry gain was the unedited network being the harder
of the two to solve well, at an effort that was nominally matched and materially
was not.

---

## 9. Definition of ready

Experiment 3 does not begin until each of these has an exact artifact reference:

1. **The best defensible performance without changing route structure** —
   `outputs/canonical/exp1_final.json`. There is no geometry component:
   Experiment 2 promoted nothing and Experiment 2B certified the null, so the
   incumbent is that frequency plan on COTA's unchanged geometry.
2. **The object Experiment 3 must beat** — `pre_exp3_baseline_v2`
   (`outputs/canonical/pre_exp3_baseline_v2.json`). v1 is preserved unchanged
   under the `pre-exp3-v1` tag; it was written while 2B stage C was still
   running and recorded the geometry incumbent as pending.
3. **The assumptions and evaluator producing that score** — the `evaluator`
   block in each canonical artifact, and the config snapshots hashed inside it.
4. **What Experiment 3 may mutate** — this file.
5. **What would cause an exciting result to be rejected** — gates 3-1 to 3-10
   and gate 12. Concretely, an Experiment 3 finding is rejected if **any** of
   these is true, however good the headline looks:

   * its margin over the conservative incumbent is inside the noise floor
     measured **in the same run, at the same effort, for the same quantity** —
     the objective's own floor, not unserved demand's;
   * the margin shrinks when both sides are solved at a higher effort — D24's
     failure, and the reason gate 12 exists;
   * its advantage rests on serving fewer stops along the same alignment;
   * it exceeds 15% network edit distance, in which case it is a real result
     about a different experiment;
   * its `modelled_share_pct` exceeds 2.0% and the margin is not large against
     the estimator's 20.5% median single-link error;
   * independent seeds at matched effort produce structurally different
     networks scoring within the floor of each other — the structure is then
     not identified, and no single map may be shown as the answer;
   * it was ranked by a fixed-frequency screen and never re-optimized;
   * it beats the raw baseline but not the conservative incumbent, which is
     Experiments 1 and 2's result being reported twice;
   * the incumbent it beat was the frozen Experiment 1 record rather than the
     unchanged network re-solved at matched effort in the same run;
   * it needs more than 197.0 peak vehicles, however well it respects the
     vehicle-hour budget;
   * the evaluator that produced it cannot state its own waiting model.

   The list is deliberately blunt. Every entry on it has already happened once
   in this project, except the last two, which were caught before they could.
