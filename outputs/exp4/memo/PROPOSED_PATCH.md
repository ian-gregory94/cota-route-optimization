# Memoize the exact path set WITHIN one certification

**ADOPTED** in commit `3fa753a5`, on Ian's instruction. This file is kept as
the record of what was measured and decided, not as a live proposal. Two
things were added beyond what is described below, and the code is what
governs:

- the scope is a typed `_CandidatePathsets` stamped with the candidate's
  `state_digest`, which refuses to serve another candidate and refuses to
  start non-empty, and `certify` raises if it comes back unused. See
  "Scope and invalidation" in `src/cota_opt/exp4_certify.py`.
- a pre-existing guard, `test_certification_never_takes_a_pathset_cache`,
  banned the string `pathset_cache` from `certify`'s source outright. It was
  narrowed to the parameter ban it actually needs, and joined by two stronger
  tests. The reason is written into the test itself.

Measured after adoption: candidate 1 certified in **672s (11.2 min)**, against
the ~105 hours the rebuild configuration needed.

## The defect

`certify()` calls `solve_on_network` once per block per round. For a 65-line
candidate that is 390 route-periods / 8 per block = 49 blocks per round, 13
rounds, plus one gen1 start = **638 calls**. Every call runs
`build_setup` -> `build_pathset`, rebuilding the entire path set from
scratch.

Every one of those 638 calls hands `build_setup` the same network, zones, OD
table and baseline headways. Only `ladder_override` varies between them, and
the ladder reaches the frequency solver, not the path enumeration. So calls
2..638 each spend ~595s rebuilding an object identical to the one call 1
already built.

Measured on candidate 1 (`exp4|exp4-pool-v1|65lines#00a1a066ae8e`):

|                              | per candidate | 200 candidates        |
| ---------------------------- | ------------- | --------------------- |
| rebuild every call (current) | ~105 h        | ~21,000 h (~2.4 years)|
| memoized within the candidate| 21.7 min      | ~72 h (~3 days)       |

The live run spent 6h33m on candidate 1 and was roughly 6% through it.
The current configuration cannot certify even one candidate in a shard.

## Why this is NOT Gate 4-7

Gate 4-7 rejected a **master path set shared ACROSS candidates**: keyed by
period alone, so candidate n is scored against candidate n-1's paths, worst
1.307 relative error on revenue vehicle-hours. It also established that
filtering a supernetwork master is a *restriction* of the choice set that
biases the search toward activating more lines -- which is why discovery may
use it (discovery only proposes) and certification may not (certification
decides).

This change shares nothing across candidates and imports no master. The
cache is created inside `certify`, holds only the exact path set that call 1
built for THIS candidate, and dies with the call. Certification still
enumerates its own paths, exactly once instead of 638 times.

## Evidence

`ab_memoization.py` runs both arms on a 6-line selection, where the rebuild
arm is affordable:

    ARM A (rebuild, ground truth): obj 3621684.228486466  rounds 3  converged True  384s  calls 16
    ARM B (memoized):              obj 3621684.228486466  rounds 3  converged True   31s  calls 16
    delta 0

Identical objective to the last digit, identical round count, identical
convergence flag. The risk this tests is `PathSetEvaluator` mutating the
`PathSet` it wraps; a mutation would have moved the objective or the
trajectory, and neither moved.

The 65-line candidate cannot serve as its own ground truth: the rebuild arm
needs ~105 hours. `candidate1_memoized.json` recorded the memoized arm alone at
objective 3,535,267.053668 -- **that figure is SUPERSEDED and was never
candidate 1's certified objective**. The probe ran with seed 20250829, a
transposed 20260825; certification is seed-dependent, so the number was
answering a different question. Under the launcher's own seed candidate 1
certified at **3,520,906.5169**, rounds 13, converged True, 672s.

The memoization claim is untouched by this: both A/B arms shared the seed, so
their equality still holds. Only the number was wrong, and it was wrong for a
reason that had nothing to do with caching. The identity check now pins the
launcher's seed so the same mistake fails a test instead of reaching a file.

## The change

In `src/cota_opt/exp4_certify.py`, inside `certify()`:

```python
    # ONE exact path set per candidate, built once and reused across this
    # candidate's ~638 block solves. Every one of those calls passes
    # build_setup identical network/zones/OD/baseline headways -- only
    # ladder_override varies, and it reaches the solver, not the enumeration.
    #
    # This is NOT Gate 4-7's rejected master cache. Nothing is shared across
    # candidates and no supernetwork master is imported: the dict is created
    # here, holds only paths THIS candidate enumerated, and dies with this
    # call. Certification still builds its own paths; it stops building them
    # 637 redundant times.
    #
    # Verified identical, not "close": outputs/exp4/memo/ab_memoization.json.
    pathsets: dict = {}

    common = dict(harness=harness, stops_gdf=stops_gdf, lam=lam, seed=seed,
                  constraints=constraints, waiting_model=waiting_model,
                  starts="greedy", allow_off=allow_off,
                  pathset_cache=pathsets,
                  pinned_off=frozenset(pinned_off))
```

`solve_on_network` already accepts `pathset_cache` and threads it to
`build_setup`; no other file changes.

## Not included

`build_raptor_network` is rebuilt per call too, upstream of the path set --
a second redundancy with the same argument available. It is NOT part of this
patch and has NOT been tested. At ~2s per call it is worth about 20 minutes
per candidate against the path set's ~105 hours, so it can wait for its own
A/B.

## Cost of adopting

Zero certified results existed, so nothing was discarded by restarting
certification. Candidate 1's in-flight 6h33m was lost either way -- it writes
nothing until it completes, and a container reclaim ended it at ~6% before the
decision was even made. That is the loop the rebuild configuration was stuck
in: every reclaim threw away every partial candidate, so no result could ever
become durable. At ~11 minutes a candidate, results now land well inside a
keeper window.

All 200 promoted candidates were preserved; `CAP_N` was not reduced and
`promotion.json` is unchanged.
