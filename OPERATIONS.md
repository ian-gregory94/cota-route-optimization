# How work survives here

Every rule below was bought with lost work. They are written down because the
same failures recurred across Experiments 1, 2 and 3, and each time the cause
was a lesson that lived in someone's memory instead of in the code.

## The environment, as measured rather than assumed

**The sandbox is recycled when the session goes idle.** Not suspended —
destroyed. Observed 2026-08-30: the container rebooted at 20:42:45Z while the
session was idle, killing two workers and a keeper. Uptime read 2 minutes when
the session came back.

**The disk survives; the processes do not.** The checkpoint files written before
that reboot were all still there. That is the whole architecture in one line.

**`setsid` does not help.** It was the right fix for a different failure — a
child in the launching shell's process group dies when the Bash tool call ends,
which is what killed the *first* Phase A1 launch. But no process-group trick
survives the machine going away.

**Experiment 2 hit this and answered it correctly.** `outputs/supervisor.log`
shows `started fixpoint` at 21:11, 21:28, 21:56, 22:10 — a supervisor
restarting the same job from its checkpoint all night. The work got done
because every restart was cheap, not because any process ran to completion.

## The rules

**1. Work in slices short enough to finish inside a live tool call.**
`scripts/exp3_slice.sh` runs one bounded slice and exits. Run it again and it
continues. There is no long-lived job to lose.

**2. Never start a unit of work the slice cannot finish.** Checking the
deadline only *after* a state is the wrong end of the loop: a worker that
begins a 413-second state one second before its deadline runs seven minutes
past it and is killed mid-enumeration, throwing away everything it did. Two
workers did exactly that on the first slice. Stopping early wastes at most one
state's idle time; starting late wastes a whole state.

**3. fsync every checkpoint write.** The container can vanish between two
states, and a record sitting in the page cache is not a record. One millisecond
against a 413-second state is not a trade-off.

**4. Commit at every slice boundary.** Git is the only store that outlives the
container. The disk survived the reboot on 2026-08-30; that was luck to observe,
not a property to depend on.

**5. Tolerate a torn final line.** A crash mid-write costs the last line of an
append-only JSONL file and nothing else — so the reader skips unparseable lines
rather than refusing the file.

**6. A progress number that overstates is worse than none.** The first slice
reported 18 states when 9 existed, because it counted lines across the merged
file *and* the shard files. Count unique keys, always.

**7. Heartbeat, so "alive but slow" is distinguishable from "dead".** A
413-second state produces no output for seven minutes. Without a heartbeat the
only way to tell a working process from a hung one is to guess, and the guess
that matters was made wrongly twice in one day.

**8. Never let a liveness check match itself.** Experiment 2's supervisor used
`pgrep` on a pattern that matched its own launcher, so it refused to start three
times while nothing was running. Use a pidfile, or a pattern that excludes the
checking process.

**9. Distinguish declining from dying.** A job that exits non-zero in under
thirty seconds is refusing to start, not crashing mid-run. Restarting it
immediately produces an infinite loop — which is what happened when
`exp2b_subsets.py` had its shard filter above the `--shard` parse and the
supervisor restarted two dead workers forever.

**10. Smoke-test the exact invocation, not an approximation of it.** That same
`UnboundLocalError` shipped because the smoke test predated the sharding patch.
The command that runs in production is the command that gets tested.

**11. Wait for memory before starting, not after being killed.** Two workers
each holding a RAPTOR network, a zone system and six periods of path sets can
exhaust the box, and the failure is a kill with no traceback —
indistinguishable from every other silent death.

**12. Shard a canonically sorted list, and check the union afterwards.**
Experiment 2B's Stage A finished at 183 of 240 because the partition was
`index % n` over a list that was re-sorted mid-sweep: 37 subsets solved twice,
57 never. The completeness check downstream is what caught it.

**13. A downstream stage refuses an incomplete upstream one.** Phase A2's
neighbour ordering is derived from the Phase A1 singles, so a partial census
does not merely lose coverage — it silently changes the search. A2 will not
start until every single is scored.

**14. Sweep the tree before every commit.** `scripts/presweep.sh` exists because
a running job re-introduced a pipe-named path mid-merge, and because a Windows
`commit -a` swept in a `_merge_debris/` folder and 24 lookalike duplicates.

## Checking on a run

```
bash scripts/exp3_status.sh      # where it is, no reconstruction from memory
bash scripts/exp3_slice.sh 470   # do the next slice, commit, exit
```

`exp3_status.sh` answers the only question that matters after a gap: how far did
it get, is anything running, and when did it last make progress.
