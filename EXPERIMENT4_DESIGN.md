# Experiment 4 — design, rewritten after D27–D33

*Extends `EXPERIMENT4_CONTRACT.md`. The contract's 24 sections, 15 gates and 17
rejection conditions stand; this says what the last week of failures changes
about how the experiment must be built and run.*

Experiment 4 releases route structure: instead of mutating the existing network,
it selects whole networks from a frozen finite pool of lines over the observed
link graph. That is a much larger and more adaptive search than Experiment 3,
and every one of the six discoveries below makes it *more* dangerous, not less.

---

## What the failures changed

| discovery | what it was | what it changes for Experiment 4 |
|---|---|---|
| **D27** | the optimizer's start set was decided by the treatment | any per-network adaptive behaviour is a candidate confound; the contract must enumerate recoveries and classify each |
| **D28** | the iteration ceiling was never binding; restarts are the lever | effort is specified in restarts and convergence is asserted, never inferred from a ceiling |
| **D29** | every link observed ≠ every turn observed; 150 of 206 pool lines use a novel turn | transition evidence enters route provenance and the receipt |
| **D30** | the remediation set was an inference until measured | scope claims about which states need work get measured before the work, not after |
| **D32** | replicate spread measures solver variance; the pipeline is deterministic so it is zero | Experiment 4's materiality threshold must be designed **before** its search, from an error measurement |
| **D33** | the heuristic is locally optimal almost everywhere and its error is not treatment-correlated | the method that established this is reusable and becomes a **precondition** for Experiment 4 |

---

## 1. The firewall is a precondition, and Experiment 4 is the hard case

Experiment 3 compared two networks differing by one edit. Experiment 4 compares
networks that may share almost nothing: different lines, different service
activation, different path sets, different feasible frequency space. Almost
everything differs, so a whitelist written carelessly would permit almost
everything and the firewall would pass anything.

The Experiment 4 contract therefore declares its treatment dimensions
**narrowly and with written justifications**, and everything else defaults to
refusal:

```
allowed_treatment_differences (Experiment 4, proposed)
  network_digest        the network itself — this IS the treatment
  active_routes         which lines run, including OFF — part of the treatment
  route_headways        the frequency plan is an outcome of the network
  pathset_digest        a different network has different shortest paths;
                        the path-set POLICY must still match exactly
  n_route_periods       different networks have different decision counts
```

Everything else — evaluator, objective, envelope, pool version, path-set policy,
solver policy, start policy, restart count, termination, convergence, every
event type — must match, or the comparison is refused. In particular
`starts_attempted`, `fallback_occurred` and `opportunity_events.*` are **not**
declared: the D27 class of failure must remain fatal in a search where it is far
more likely.

**Open question for the contract, not to be settled by whoever hits it first.**
Networks with different route counts have different numbers of frequency
decisions, so `evaluations_performed` and `restarts_completed` will differ
structurally. Experiment 3 handled this with a declared relative tolerance. For
Experiment 4 the honest instrument is a tolerance **normalised by decision
count** — search per dimension, not search in total — and that has to be written
into the contract before the first network is scored.

## 2. Recovery behaviours must be enumerated before the search, not discovered during it

Experiment 4's search will meet networks that Experiment 3 never could: ones
whose path enumeration finds no route for some OD pairs, whose minimum-service
plan already breaks the envelope, whose active-route set leaves stops stranded.
Each of those has a tempting local recovery, and **every tempting local
recovery is a D27 waiting to happen** — because whether it fires depends on the
network, which is the treatment.

Before the search runs, each anticipated recovery is classified and written
down:

| recovery | classification | why |
|---|---|---|
| retry a failed cache read | operationally neutral | provably the same computation |
| rebuild a deterministic path set | operationally neutral | same inputs, same output |
| resume from a checkpoint | operationally neutral *if* restart-seeded | already proved exact for the frequency solve |
| repair an infeasible frequency plan into the envelope | **semantic** | changes the start set; declared with D30-style evidence or not at all |
| drop an unroutable OD pair | **semantic** | changes the objective's support |
| relax the envelope to make a network feasible | **semantic** | changes the constraint; refuse instead |
| substitute a smaller path set when enumeration is slow | **semantic** | changes the evidence class |

Anything not on this list defaults to semantic (`ExecutionEvent` with
`changes_opportunity=True`), which means it refuses comparisons until someone
declares it deliberately.

## 3. A materiality threshold, designed before the search

D32 is not an Experiment 3 problem. Experiment 4's pipeline will be deterministic
for the same reason — greedy wins, and the seed never reaches the answer — so
its replicate spread will also be zero and will also bound nothing.

So Experiment 4 does **not** get to define its floor from replicates. Its
threshold comes from the D33 method, run on Experiment 4 networks **before** the
search, and answering the same four questions in the same order. The fourth is
the only one that yields a usable number:

1. absolute gap of the delivered plan against exhaustive enumeration of a
   reduced neighbourhood, under the production objective;
2. its distribution across network structures — and Experiment 4's structures
   vary far more than Experiment 3's single-edit variants, so the strata must
   include high-branching networks, sparse networks, networks with many OFF
   routes, and networks whose lines overlap heavily (where D33 found the error
   concentrated);
3. whether the gap moves systematically with network structure;
4. therefore the network-level effect distinguishable from structure-correlated
   solver error.

**If (3) says the gap tracks structure, Experiment 4 cannot compare networks at
discovery effort at all**, and the search must select on something else — rank
stability across efforts, or certification of a wider frontier. That
possibility is written down now so that meeting it is not a crisis.

D33 measured 0.0018 points for single-edit variants. **That number does not
transfer.** Experiment 4's networks differ far more, and its own benchmark must
be run.

## 4. Effort is restarts, and convergence is asserted

D28: at certification effort each restart terminated after ~4,000 of its 400,000
permitted evaluations. Experiment 4 states its effort as restart counts,
records `restarts_completed` and `converged` in every receipt, and refuses a
certification comparison in which either arm did not converge. The iteration
ceiling is recorded for reproducibility and is not evidence of anything.

Practical consequence, and a welcome one: a certification solve costs about
eight minutes rather than the hour its iteration count implies, so Experiment 4
can afford to certify a **wider frontier** than originally budgeted. That is a
design freedom bought by D28 and should be spent.

## 5. Transition-level evidence enters the contract

D29: the pool reports `modelled_share = 0.0` on all 206 lines, and **150 of them
still ask for a turn COTA has never operated** — 40 of 40 crosstown lines among
them, which is what joining two radial corridors at a junction means.

Every line carries, per direction: observed-link share, observed-**transition**
share, unsupported transition count, and support counts. Evidence class is the
worse of the two directions:

| class | meaning | pool |
|---|---|---|
| 0 | legacy sequence — operated today | 41 |
| 1 | observed-turn synthesis — every link *and* turn observed | 15 |
| 2 | observed-edge synthesis — every link observed, ≥1 novel turn | **150** |
| 3 | modelled geometry — ≥1 unobserved link | 0 |

**Class 2 is reported, not rejected**, and no threshold on it is added after
seeing these numbers. If a class-2 constraint is wanted it must be declared
before the search, and the honest form is a reporting requirement on the
promoted frontier — *this network asks for N turns nobody has driven, here they
are* — rather than a filter that silently removes the crosstown ideas the
experiment exists to test.

## 6. Scope claims get measured

D30: the claim "only these 40 states need re-scoring" was an inference until
eight stratified states were run both ways and came back bit-identical. It cost
eight states and bought nine hours.

Experiment 4 will make the same shape of claim constantly — *this generator's
lines are equivalent to that one's*, *this subspace can be pruned*, *these
networks are structurally identical*. Each one gets a stratified sample measured
before it is acted on, and the measurement is recorded with its scope stated
(D30's own note bounds itself to discovery effort, this pool, those states).

## 7. What Experiment 4 inherits, and what it must not

**Inherits:** the observed-link graph (2,763 stops, 2,952 directed links,
strongly connected, 166 stops with multiple continuations and only 62 true
junctions, more than half the links supported by a single trip); the frozen
route pool with legacy inclusion proved; direction-paired reconstruction, since
COTA stop ids encode direction and outbound paths cannot be reversed; the
firewall; the resumable solve runner; the gap-benchmark method.

**Must not inherit:** any discovery-effort ranking from Experiment 3's
superseded census; the 0.039% floor; the 0.00657% certification spread; and the
habit of quoting an iteration ceiling as search depth.

**Blocked on:** Experiment 3 closing under the firewall and Gen1 being frozen.
Experiment 4 is the first experiment designed natively around Gen2, and Gen2
does not exist until Gen1 is frozen and the bridge suite has run.

## 8. The interpretive limit, stated up front

The observed-link graph has 2,952 directed links but only **166 stops offering
more than one continuation, and 62 true junctions**. Experiment 4 is therefore
not optimizing arbitrary bus networks over Columbus. It is **recombining COTA's
observed corridor vocabulary at a small number of existing junctions**, and more
than half its links rest on a single observed trip.

That belongs in the headline result, not a limitations paragraph. A finding that
reads "the best network we could build from COTA's own corridors beats the
current one by X" is worth having; one that reads "we optimized Columbus transit"
would be false.

## 9. Definition of ready — amended

The contract's 15 items stand. Six are added:

16. An `ExperimentContract` for Experiment 4 exists, with every declared
    treatment difference carrying a written justification, and refuses at
    construction if any is missing.
17. Every anticipated recovery behaviour is classified operationally neutral or
    semantic, in writing, before the search.
18. The gap benchmark has been run on Experiment 4 networks, its four questions
    answered in order, and question 3's answer recorded — including the branch
    where it forbids discovery-effort comparison.
19. The effort ladder is stated in restarts with convergence asserted, and no
    document quotes an iteration ceiling as search depth.
20. Transition-level evidence is attached to every pool line and to the receipt,
    with class-2 handling declared before any result is seen.
21. Gen1 is frozen and the Gen1→Gen2 bridge suite has run.
