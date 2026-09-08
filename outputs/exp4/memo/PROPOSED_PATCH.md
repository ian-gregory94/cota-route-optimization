# Proposed: memoize the exact path set WITHIN one certification

NOT APPLIED. Staged pending Ian's decision, because applying it means
stopping a run he reserved the right to stop (readiness freeze: "Only an
error that makes candidate construction or objective comparison invalid may
stop the run") and because OPERATIONS 24 freezes `src/cota_opt` while a
batch is in flight.

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
needs ~105 hours. `candidate1_memoized.json` records the memoized arm alone
(objective 3,535,267.053668, rounds 13, converged True, 1302s); it inherits
its licence from the A/B above, not from a same-candidate comparison, and
that distinction should stay visible in anything that cites it.

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

Zero certified results exist, so nothing is discarded by restarting
certification. Candidate 1's in-flight 6h33m is lost either way -- it writes
nothing until it completes, and it completes in about four more days.
