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

| operation | permitted | limit |
|---|---|---|
| **shorten** (truncate a route at an existing stop) | yes | §3 removal cap |
| **extend** (continue a route along stops another route already serves) | yes | §3 link rule |
| **reroute** (replace a mid-route segment with another) | yes | §3 link rule, removal cap |
| **straighten** (drop a deviation, keeping both ends) | yes | §3 removal cap |
| **change terminal** | yes | §3 terminal rule |
| **change transfer point** | yes | must be an existing stop served by both routes |
| **splice / through-route** (merge two routes end to end) | yes | inherently two routes |
| **split** (cut one route into two independently scheduled routes) | yes | each half must retain ≥ 30% of the original stop-visits |
| **create a crosstown or radial connection** | yes, as a splice or reroute over existing links | §3 link rule |
| **constrained overlay** (a limited variant on an existing corridor) | **no** | §4 |
| **add a stop to a route** | yes, existing stops only | §3 stop rule |
| **create a new stop** | **no** | §3 stop rule |
| **remove a stop from the network** | **no** | §4 — that is the stop-consolidation question, and its exchange rate is unmeasurable from this feed |
| **express / limited-stop variant** | **no** | §4 |
| **change frequency** | not a mutation | §5 — frequency is re-optimized for every network, never chosen as an edit |

Anything not listed is not permitted.

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

**Two mutations are structurally incompatible if** they name a common route
(the rule `geometry.apply_edits` already enforces — a splice consumes both its
routes), or if one removes a stop the other uses as a terminal or transfer
point. Incompatible pairs are never generated, and the check is on structure,
never on measured performance.

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

## 6. Search design: interactions are assumed from the start

Experiment 2 gave direct evidence that geometry interventions are non-additive
— individually beneficial edits become harmful in combination, and the
interaction term reaches 16 times the noise floor at four edits. Experiment 3
therefore searches over **network states**, not over independent edit values.

`score each mutation → rank → take the top N` is forbidden as a search
procedure. It is permitted only as an explicit object of study, stated as such,
whose expected failure is already on record.

Exhaustive enumeration will not be affordable here as it was in 2B, so a
heuristic is expected — beam search, evolutionary search, MCTS, neighbourhood
search. **Whichever is chosen must first be benchmarked on a subspace small
enough to enumerate exhaustively**, and must recover the known optimum there
before it is trusted anywhere larger. A search that cannot find the answer where
the answer is known is not evidence about a space where it is not.

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

---

## 8. Gates

Experiment 3 inherits gates 3-1 through 3-9 as committed in `ACCEPTANCE.md`
(no measured stop penalty; recommendations must survive the whole plausible
assumption range; conservative break-even; the schedule relationship is not
causal; sole-access stops excluded; Model B asserted; the screen does not
select; sets not sums; the noise floor measured in the same run at the same
effort), and adds one that matters only here:

**Gate 12 (convergence, not just effort) applies to every Experiment 3
comparison.** A mutated network and the incumbent it is compared against must
both be shown converged — two effort levels, replicates on both sides, or a
convergence trace — before any margin between them is quoted. D24 is the reason:
an apparent half-point geometry gain was the unedited network being the harder
of the two to solve well, at an effort that was nominally matched and materially
was not.

**Gate 3-10 — mutation identity stability.** If independent seeds at matched
effort produce structurally different networks that score within the noise
floor of each other, the **structure is not identified** and must be reported
that way — exactly as Experiment 1 reports its headways. Structural
disagreement is measured and published alongside the effect, as gate 7 does for
route-periods. No map is promoted because it came from seed 1.

---

## 9. Definition of ready

Experiment 3 does not begin until each of these has an exact artifact reference:

1. **The best defensible performance without changing route structure** —
   `outputs/canonical/exp1_final.json` plus the Experiment 2/2B incumbent.
2. **The object Experiment 3 must beat** — `pre_exp3_baseline_v1`.
3. **The assumptions and evaluator producing that score** — the `evaluator`
   block in each canonical artifact, and the config snapshots hashed inside it.
4. **What Experiment 3 may mutate** — this file.
5. **What would cause an exciting result to be rejected** — gates 3-1 to 3-10.
