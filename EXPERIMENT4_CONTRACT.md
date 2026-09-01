# Experiment 4 — greenfield network generation: treatment contract

**Committed 2026-08-31, before any synthetic route exists.**

## The question

> If COTA were not required to preserve the structure or identity of its
> existing local bus routes, what network would best serve the same modeled
> demand inside the same operating-resource envelope?

Experiment 4 releases **route structure**. It does not release the resource
envelope — that is Experiment 5 — and it does not impose political, equity,
neighborhood-preservation or one-seat-ride constraints beyond those already
inherent in the passenger objective, which are Experiments 6 and 7.

So the counterfactual is deliberately narrow: *with today's resources and
today's physical transit footprint, how much performance is lost solely because
the network is organized into the routes it currently has?*

---

## 1. The incumbent

**Do not define it until Experiment 3 closes.** At Exp 3 closeout, create
`pre_exp4_baseline_v1`.

The hierarchy is explicit and each step must be beaten in turn:

> published COTA schedule → Exp 1 frequency optimum → Exp 3 constrained
> route-mutation optimum → Exp 4 greenfield optimum

Experiment 2/2B contributes **no incumbent geometry**: it certified the null.

**If Experiment 3 certifies several structurally different networks inside one
noise floor, seed 1 is not "the Exp 3 network."** `pre_exp4_baseline_v1` carries
the entire certified tied set, and Exp 4 must beat the best matched-effort
member of it.

Every promoted Exp 4 network is compared against that incumbent **re-solved in
the same run at matched convergence**. A stored score is a reference, never a
denominator. D24 is why.

## 2. What is released

Route identity has no privileged status. Released: route identities, route
count, route combinations, termini, transfer architecture, which corridors get a
one-seat ride, which existing stops each route serves, route-period service
activation, and **essentially all network edit distance**. There is no 15% limit.

A valid Exp 4 network may bear no recognizable resemblance to today's map. That
is not a legibility failure. **It is the treatment.**

## 3. What stays fixed

Weekday demand model and scaling · six service periods · passenger cost weights
· λ=2 primary objective · Model B path assignment at minimum · waiting and
retention assumptions · walking radius and speed · **the existing stop
universe** · **2,517.183 weekday revenue vehicle-hours** · **197 peak vehicles**
· minimum layover · the headway ladder while a route is active · no new fleet ·
no extra operating hours.

Experiment 5 moves the resource constraints. The separation is the point: if
Exp 4 got extra buses at the same time as new routes, no result could say
whether the gain came from design or from more service.

## 4. The peak-express system is held fixed

Experiment 1 established that the 14 peak-oriented express routes are not
ordinary low-frequency service, and that treating them as frequency service
manufactured **1.5–3 percentage points of fake improvement** — the optimizer
stretched a designed timetable as though it were random-arrival service.

So Exp 4 **does not redesign them**. The peak-express class and its service
pattern are frozen as an external layer, and the greenfield local network is
designed around it. Redesigning the express system needs a timetable-aware
model, which is a different experiment.

Being "more greenfield" is not a reason to quietly reintroduce an
already-discovered modeling error.

## 5. Greenfield topology, not greenfield running times

**The primary network domain is the observed-link graph.** Each directed edge is
a consecutive stop-to-stop movement operated by *some* COTA route in the GTFS,
carrying that movement's observed median scheduled running time.

Synthetic routes concatenate those edges in combinations no existing route uses.
A synthetic line may take pieces of routes 1, 8, 31 and 34 and become one new
line — far more radical than Exp 3 — while **every individual segment is a road
COTA already operates with an observed running time.**

> Greenfield route topology without greenfield runtime assumptions.

That is the **primary evidence class**.

The novel-link estimator is good enough for small exposure — 5,832 validation
links, MAE 17.2 s, aggregate bias +0.41% — but its **median absolute error on a
single link is 20.5%**. A greenfield network built from arbitrary straight lines
could be 50–100% modelled, at which point the optimizer is mostly optimizing our
estimator. Genuinely novel links are permitted only as a **secondary,
exploratory** class, and a high-modelled-share network may not displace the
observed-link winner as the headline without a new runtime-validation argument.

## 6. The stop universe is fixed

Exp 4 may serve an existing stop, stop serving one, or connect existing stops in
completely different structures. It may **not** invent a stop, move one to an
arbitrary location, or claim a runtime saving for skipping stops along an
unchanged alignment.

A generated route on the observed-link graph **serves the nodes it traverses**.
The generator may not traverse an observed chain and silently declare
intermediate stops skipped to manufacture speed. Stop-location optimization
remains a separate question needing better evidence.

## 7. Gate 3-5 does NOT carry into the primary objective

Experiment 3 protects the 13 sole-access stops because it asks for a
recognizable modification of COTA. Experiment 4 asks something else, and forcing
the unconstrained optimum to preserve every current catchment would destroy the
baseline Experiment 6 is supposed to measure against.

If the optimizer abandons coverage because the objective says service is worth
more elsewhere, **that is information we want**. It is reported, not forbidden:
stops losing service, demand losing access, neighborhoods affected, one-seat
rides lost, transfer burden created.

## 8. A genuine synthetic representation

An Exp 4 route is **not** "route 8 with 73% of its stops changed." Route identity
is gone.

`SyntheticRoute` carries at minimum: canonical id · outbound stop sequence ·
inbound stop sequence · observed/modelled edge provenance · one-way runtime by
direction · terminals · distance · stop count · modelled-link share ·
generation provenance.

`SyntheticNetwork` is an **unordered set** of those lines plus service-period
activation. Canonical identity is based on actual geometry and stop sequence,
never on the order a search discovered the routes. **The same network reached by
two search paths must hash identically.**

## 9. Service activation becomes a decision variable

The existing optimizer assumes a `(route, period)` service already exists in the
baseline GTFS and must therefore retain service. That is meaningless for a route
that did not exist yesterday.

Frequency options for a synthetic route-period become:

> **OFF**, 60, 45, 40, 30, 24, 20, 15, 12, 10, 7.5, 6, 5

subject to the envelope. **OFF consumes zero vehicle-hours and zero peak
vehicles and contributes no frequency.** This may not be faked by giving every
synthetic route a copied "baseline headway" — there is no baseline headway.

## 10. A frozen, finite route pool

Every stop sequence over 2,949 stops is not a search space. Generate a broad but
finite line pool from the observed-link graph, using **several independent
generators** so no single heuristic defines the answer:

* **Legacy inclusion — mandatory.** Every supported current local route, exactly,
  plus Experiment 3's promoted routes where representable. *The current network
  must be inside the search space*, or an inferior Exp 4 answer could just mean
  the generator failed to propose what COTA already runs.
* **OD-driven** — direct or near-direct paths between high-flow access nodes.
* **Terminal-to-terminal** — paths among existing turnarounds through the graph.
* **Transfer-removal** — direct lines for major movements that currently transfer.
* **Crosstown** — explicit non-downtown movements, so a radial legacy network
  does not define every seed.
* **Trunk candidates** — high-demand corridor spines able to carry several
  current movements.

Use K-shortest / near-shortest paths per endpoint pair so one shortest-path
algorithm does not silently define the design space. Deduplicate by canonical
geometry. **Freeze the pool before scoring.**

## 11. Generation constraints are physical, not political

Candidates must have serviceable paths through the link graph, no gratuitous
stop repetition, paired direction geometry where appropriate, finite cycle time,
feasible turnaround logic, and lengths whose reliability we can model.

Today's local routes run roughly 21–99 minutes one way (5th–95th percentile
about 27–95). The search bound is deliberately broader:

> **10–120 minutes one way** — a search bound, not a claim about ideal length.

**Test whether the winner touches the bound.** If the best network is full of
120-minute routes the bound is active and must be raised, or the result is
censored. Same rule for any route-count cap: set a generous limit and prove the
solution does not live on it.

## 12. Discovery cannot rebuild exact paths per state

The Experiment 3 measurement: a state costs **413 s, of which 311 s is the path
rebuild**, and changing frequency-solver effort barely matters. A greenfield
search may need thousands of evaluations, so exact rebuild per discovery state
makes Exp 4 computationally impossible.

**It may not be solved by reusing the incumbent's paths.** That would invalidate
the experiment.

Instead: once the route pool is frozen, build a **supernetwork** containing all
candidate lines and enumerate a rich **master path set** under multiple
service/frequency scenarios. A candidate network activates a subset of routes;
paths using absent routes become unavailable; frequency is optimized over the
active network. Enumeration is reusable because the route universe is frozen.

**It is an approximation, so it is benchmarked.** On a preregistered sample of
candidate networks, compare master-path scoring against exact state-specific
rebuild and measure: objective gap · unserved gap · ranking stability · omitted
and improvable flow · whether the promoted set changes. If the approximation
cannot identify the exact leader within the noise/promotion band, widen the
master set or abandon it.

**Certification remains exact**: every promoted network gets an exact rebuild,
adequacy test, frequency re-optimization and evaluation. The approximation buys
discovery speed. It does not buy conclusions.

## 13. Path-model adequacy must be revalidated

Assumptions safe on today's map were measured *on today's map*.

* **Transfer depth.** RAPTOR currently allows two transfers. A trunk/feeder
  network may deliberately create more. Promoted networks are rerun with a
  deeper limit; if `max_rounds` materially changes the winner or its score, the
  path model is inadequate.
* **Paths per OD.** The 4→6 candidate-cap result was measured on the existing
  network and does not carry to an alien one with many overlapping alternatives.
  Redo the sensitivity.
* **OD truncation.** The top 20,000 pairs are about **65%** of transit-accessible
  commute flow. At certification, evaluate promoted networks on a materially
  wider OD set and test whether ordering or headline direction changes. The
  optimizer does not get to redesign Columbus around the computationally
  convenient top of the OD table.

## 14. Common-lines waiting must be rechecked

Model B fixed the large error from overlapping patterns of the *same* route. Its
remaining approximation is overlapping *different* routes — about **0.516%** of
generalized cost on today's network. A generated trunk network may create far
more cross-route overlap.

Every promoted network reruns the hyperpath/common-lines diagnostic. If exposure
stays small, fine. If it balloons, either implement the general waiting model or
classify the result as model-dependent and do not headline a margin of
comparable size. Today's residual is not assumed to survive a network the
optimizer designed itself.

## 15. Crowding must be rechecked

Crowding did not bind on the existing network. A greenfield optimizer may
concentrate passengers onto a few strong trunks. Every promoted network gets
segment load profiles, peak load factors, overloaded segments, and a
crowding-enabled sensitivity if exposure becomes meaningful.

*"Crowding didn't matter in Experiment 1"* is not evidence about a different
network.

## 16. The search is over whole networks

Experiment 2B settled that route interventions are not additive: across all 240
feasible subsets, every multi-edit set delivered less than the sum of its
members. So there is **no** procedure of *score 500 routes → take the best 30*.
A route has no value independent of the network around it.

State = a set of synthetic routes plus service activation. Moves: add route ·
drop route · swap route · change service span · replace a route with an
alternative corridor candidate. Start families: the Exp 3 incumbent ·
demand-derived constructions · seeded random feasible networks · sparse
trunk-heavy networks. **No family gets exclusive rights to the search.**

## 17. The search is benchmarked on a harder space

As in Experiment 3, but harder. Construct a tractable route pool, enumerate
every feasible network within a small size envelope, and require recovery of the
true optimum from incumbent, random and **deliberately deceptive** starts.

The benchmark must include cases where the optimum requires **dropping a locally
good route**, where the optimum is **not nested**, where a **swap is required**,
and where the **incumbent is actually optimal**.

Passing the 2B benchmark is not sufficient — its winner is a singleton adjacent
to the null, and the Experiment 3 contract already concedes it barely exercises
the move set.

## 18. Stages

**A — greenfield discovery.** Validated approximation, broad search. Ordering
signals only. Promotion is a **band**: everything within a preregistered number
of discovery floors of the leader, plus the best network from each
generator/start family, structurally distinct networks inside the band, the
incumbent always, and networks from different route-count/service-structure
regimes. One neighborhood of one solution may not consume the promotion set.

**B — exact promotion.** Exact rebuild · adequacy · frequency re-optimization ·
the Exp 3 incumbent re-solved in the same run · same-run floors · at least two
effort levels · gate 12 · all component metrics · transfer-depth and path-cap
checks. A discovery benefit that disappears under exact rebuilding is a
discovery false positive.

**C — certification.** At least 400,000 / 20 / full width / three predeclared
seeds. Required: matched convergence · same-run objective and component floors ·
path adequacy · expanded-OD robustness · Model B provenance · common-lines
diagnostic · transfer-depth sensitivity · candidate-cap sensitivity ·
vehicle-hour compliance · peak-fleet compliance · crowding check · λ≥2
robustness · demand robustness · structural identity stability.

**D — physical inspection.** Terminals · turnarounds · cycle times · extreme
length · duplicated corridors · reliability exposure · transfer structure ·
service span · asymmetry · operational legibility.

Stage D distinguishes **physically incoherent** from **politically insane**.
Only the first is a failure here; the second is Experiment 7.

## 19. Demand robustness is mandatory

The demand model is this project's largest external-validity limitation, and
structural freedom gives the optimizer many more ways to exploit artifacts in
the LODES proxy. Every certified candidate is tested against commute LODES ·
altered period shares · demand scaling · the implemented noncommute stress
direction · reasonable blends · preferably an OD holdout or widened universe.

The claim we want is **not** "this exact network is 14.382% better." It is:

> Substantial additional benefit from greenfield restructuring survives
> materially different demand shapes.

or, equally valuable:

> The apparent greenfield gain disappears when commute geometry is perturbed.

Both are legitimate results.

## 20. Structural stability needs a new metric

Exp 4 route ids are synthetic, so route-id disagreement is meaningless. Network
structural distance is defined from **actual service geometry**: directed
stop-to-stop edge overlap · stop-route incidence · service-weighted edge overlap
· OD direct-connectivity overlap.

Then: among independently optimized networks scoring within the certification
floor, how different are the maps? If seeds find wildly different maps with
identical outcomes, the conclusion is

> the value of greenfield redesign is identified; the exact greenfield network
> is not

— the direct analogue of Experiment 1's flat headway optimum, and the expected
outcome.

## 21. What gets reported

The six required metrics carry forward: generalized cost · unserved demand ·
served demand · cost per served trip · vehicle-hours · peak vehicles.

Experiment 4 adds: active local routes · stops receiving service · stops losing
service vs today · OD accessibility · mean transfers · one-seat share · share
needing 2+ transfers · access walk · route runtime distribution · maximum route
runtime · service-weighted distance from COTA · observed/modelled runtime share
· common-lines exposure · peak segment loads · geographic distribution of gains
and losses.

Those last are not optimization constraints. They are the handoff to
Experiments 6 and 7.

## 22. What Experiment 4 may conclude

If it succeeds:

> Holding COTA's current operating-resource envelope fixed, releasing legacy
> route structure produces approximately X additional system benefit beyond the
> best constrained redesign.

**Not** "COTA should implement this map," and emphatically **not** "COTA planners
failed to find this map." We have not represented all the constraints they
solve. The size of the Exp 4 − Exp 3 gap measures the value of structural
freedom *under our model*; Experiments 6–7 measure how much of that freedom
exists in reality.

## 23. The null is precommitted as a fine result

> Once frequencies and constrained route mutations are optimized, a greenfield
> redesign buys little or nothing.

That would be astonishingly flattering to COTA's existing topology. If instead
Exp 4 finds another 10–20%, most of the remaining gap is structural rather than
schedulational. Both are interesting, and we do not get to decide beforehand
which story is better.

## 24. Definition of ready

Do not launch the greenfield search until every one of these exists:

1. Experiment 3 closed and frozen.
2. `pre_exp4_baseline_v1` exists.
3. Synthetic routes/networks exist independently of legacy route ids.
4. **The current COTA local network can be reconstructed through that
   representation and reproduces its score and resources.**
5. Peak express service explicitly separated.
6. The observed-link graph built and audited.
7. The frozen route pool contains the current network.
8. Synthetic route-period service can be OFF; no fake baseline headways.
9. Discovery path reuse benchmarked against exact rebuilds.
10. The outer network search recovers an exhaustively known optimum.
11. A committed gate on common-lines exposure.
12. Committed transfer-depth, path-cap and OD-cap adequacy gates.
13. Demand-robustness claims written before the winner is known.
14. Structural-distance measurement exists.
15. Every rejection condition in `ACCEPTANCE.md` before the first full network
    is scored.

Item 4 is the one to build first and the one most likely to fail quietly. It is
the Experiment 4 form of the rule that caught three defects in Experiment 3:
**do not trust a new representation until it reproduces a number the old one
already produced.**
