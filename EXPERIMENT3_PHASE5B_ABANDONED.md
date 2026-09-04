# Phase 5b — started, abandoned, and why

Phase 5b was authorised, designed, launched, and **abandoned without completing
a single cell**. This record exists so the attempt is visible rather than
quietly absent from the history.

## What it was for

`EXPERIMENT3_PHASE5_DESIGN.md` recorded that §6 escalates what is *unresolved or
failing* — by construction the *smaller* margins — so the six largest-margin
candidates, the leader among them, were never solved above 20 restarts. Phase 5b
would have escalated all six, putting the whole certified set in one regime. Its
rule, manifest and worker are frozen at `cebb7f00` / `459c4919`.

## Why it stopped

Operational, not scientific. A 40-restart cell needs ~26–30 minutes of
continuous container uptime, and this container reclaims after roughly 8 minutes
of **session** idleness (OPERATIONS 28). The only measured way to hold it is a
foreground loop of `sleep` beats — about 18 cells per 3 hours, against roughly 2
under a wake-only regime.

Ian declined the foreground hold. Two launches were made anyway, in case the
container happened to stay up:

| launch | outcome |
|---|---|
| 2026-09-04 18:45Z | killed before any cell completed; `remaining=15` on both shards |
| 2026-09-04 19:35Z | killed before any cell completed; `remaining=15` on both shards |

1 h 35 min elapsed, **zero cells produced**. Asked how to proceed, Ian chose to
freeze on the two-regime table.

## The integrity point that matters

**No Phase 5b cell ever completed**, verified from the observation store rather
than asserted:

```
escalated store total          : 170
distinct states in store       : 34  (control + 33 candidates)
Phase 5b target states present : 0 of 6
store == section 6 design      : True
```

Receipts are written only on cell completion, so a killed cell leaves nothing
behind — no partial rows, no contamination. The escalated store therefore holds
exactly the §6 batch and nothing else.

The consequence for the record: **the decision to abandon Phase 5b cannot have
been influenced by Phase 5b results, because there are none.** That is the
failure mode this project guards against everywhere else — a measurement
stopped, extended, or discarded once its direction is visible — and here it is
excluded by the arithmetic rather than by assurance. Had even one of the six
returned a number before the stop, this document would have to argue the point
instead of demonstrating it.

## What this leaves standing

Experiment 3's terminal result is the two-regime table, complete and unchanged:
§8 outcome (1), leader `add_stop-010#22c4c35ac5b2` at −0.18657%, 29 certified.
The asymmetry Phase 5b would have removed is **not** removed, and remains stated
at full strength in §7 of `EXPERIMENT3_CLOSURE.md` — the leader is measured at 20
restarts, all 28 of its comparisons are at 20 restarts, and the best margin
confirmed at 40 restarts is 2.33× smaller than its own.

That is a real limitation of the result, not a formality. It is the first thing
a later reader should test if they want to overturn the leader, and the work is
already scoped: 30 cells, ~7 hours under a foreground hold, manifest and worker
committed and ready to run unchanged.
