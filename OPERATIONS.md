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

## The rule that would have caught most of today

**15. Do not re-implement a validated pipeline. Call it, and prove equivalence
against a number it already produced.**

`exp3_score.score_state` was written as a fresh implementation of a fifteen-step
chain Experiment 2B already had working. That single decision produced three
separate load-bearing defects, none of which raised an error:

* **The envelope was not pinned.** `config/constraints.yaml` holds the sentinel
  `weekday_revenue_vehicle_hours: baseline`, resolved against whatever network
  the setup is handed. Passing the raw config gave every state its *own*
  envelope — a splice lengthens its routes, its "baseline" budget grows to
  match, and the optimizer is handed more hours to spend. Every state was being
  judged against a different budget, which is the one thing the whole method
  depends on not happening. 2B pins it once from the unedited network and passes
  that same object to every state.
* **The incumbent was not refitted to the envelope**, so the optimizer discarded
  it and fell back to a greedy build — `exchanges=0` on every solve, −5.03% on
  unserved demand where Experiment 1 reaches −6.65%, and **byte-identical
  results across three seeds**. That last part is the dangerous one: identical
  replicates make the same-run noise floor exactly zero, and a zero floor
  licenses every margin that is not precisely nil. 2B wrote the docstring
  explaining this.
* **A hand-rolled `SimpleNamespace` stood in for 2B's `_Baseline` proxy**,
  copying the attributes I thought mattered instead of delegating all of them.

The equivalence test is `scripts/exp3_score_invariant.py`: score two states 2B
recorded and reproduce its numbers within one noise floor. The zero-edit state
now matches 2B's to the digit — 9812.3 unserved, 1,785,263 generalized cost,
2507.8 vehicle-hours. Before the fixes it read 9745.9.

The same rule has a validator form, `scripts/exp3_validator_invariant.py`: the
contract validator must accept all twelve candidates 2B applied, scored and
reported. It refused seven of them once.

**Neither test rests on my judgement about what the code should do.** They rest
on numbers a previous experiment already produced and published. That is the
only kind of check that catches a second implementation which merely looks
right — which is how this project lost three days to an evaluator reporting the
wrong waiting model.

**16. Count your warnings.** A `log.warning` that fires on two thirds of runs
is not a warning, it is an unhandled code path with a polite name. `incumbent
plan is infeasible under this budget` printed in every log of Experiments 1, 2,
2B and 3 and was read as noise; it was silently selecting a different optimizer
for treated networks than for the control (D27). Before trusting a batch of
results, aggregate the log lines it produced and look at the counts — not the
lines. Any warning firing on more than a few percent of runs gets explained or
promoted to an error.

**17. A pattern that matches your own command line kills you.** `pkill -f
exp3_validate_loop`, run from a tool call whose command string contained that
text, matched its own shell and terminated the call before anything ran. This
is rule 12 — never let a liveness check match itself — reappearing on the other
side: rule 12 was about a check that always finds itself alive, this is a kill
that always finds itself dead. Match on a bracketed pattern (`[e]xp3_...`), a
pidfile, or a recorded pid; never on a literal string you have just typed into
the same command.

**18. A loop that cannot progress must stop, not spin.** A `NameError` in the
re-score slice made every iteration fail in under a second — and the slice
committed as it went, so the loop produced empty commits at machine speed while
reporting "40 of 40 remaining" each time. Every batch loop now compares the
work remaining before and after a slice and exits after two consecutive
no-progress iterations. A stalled loop that says so is recoverable; one that
looks busy is not.

**19. Smoke-test the changed path, not the one you remember.** Rule 10 says to
smoke-test the exact invocation, and this was a forty-state, multi-hour loop
launched over a code path edited twenty minutes earlier and never run. The
crash was in the first line of the first state. One foreground state before the
loop costs three minutes and is the whole cost of finding out.

**20. A background loop commits its own outputs, never `git add -A`.** The 2B
confirmation loop committed every fifteen minutes with `git add -A`, and twice
it swept up source edits being made in the foreground — so a `NameError` fix and
two new operations rules landed in history under "chore: Experiment 2B
matched-start confirmation cell". Nothing was lost and the tree was correct, but
the audit trail said a routine cell had changed the scoring path, which is worse
than useless in a project whose whole defence is its provenance. Every batch
loop now names the paths it owns.

**21. `grep -c` prints a count AND exits non-zero when it finds nothing.** So
`n=$(... | grep -c pattern || echo 0)` emits *two* lines — `0` from grep and `0`
from the fallback — and `n` becomes `$'0\n0'`. `[ "$n" -eq 0 ]` then fails as a
syntax error rather than matching, the loop never reaches its exit condition,
and it spins after its work is done: the 2B confirmation loop ran for twenty
minutes past completion, committing as it went. Use `n=$(...); n=${n:-0}`, and
assert the count is actually a number before branching on it — every loop here
now refuses to continue on a non-numeric count.

**22. Two writers, one git index.** Foreground commits raced the background
loop's, and `git commit` failed with "cannot lock ref 'HEAD'". Worse, the loop's
`git add` (before rule 20) swept up foreground edits, filing a census builder
under a confirmation-cell message. Only one process should commit a given path.
When a loop is running, stage explicit paths, expect the lock to be contended,
and retry — and never assume your own `git add` will still be staged when your
`git commit` runs.

**23. A loop must not commit its own log.** Every batch loop was committing the
log file it was appending to, so each slice produced a commit whose only change
was the log growing. Forty substantive commits became 2,646, and the history
stopped being readable at exactly the moment its readability mattered most.
Commit the artifacts a loop produces — rows, receipts, results — and leave logs
to the working tree. If a log is worth keeping, commit it once at the end.

**24. A batch in flight freezes the code that can change its numbers.** The
evaluation path's content digest is an identity field, so two cells produced
either side of an edit to `src/cota_opt` are refused for comparison — correctly.
Editing during a batch therefore splits it into two incomparable halves. This
cost a whole certification batch once and five census states the next day, and
both times the safeguard was a rule to be remembered rather than a check that
could fail. A running batch now writes `outputs/exp3/EVAL_PATH_FROZEN` with the
digest it started under, and `test_repro_guards.py` goes red the moment the
evaluation path diverges from it. Delete the marker when the batch is done.

**25. The bracket trick fails when your own command repeats the name.**
`ps | awk '/[e]xp3_rescore/'` is supposed to exclude the searching process,
because the pattern `[e]xp3_rescore` does not literally appear in it. But the
same command also contained a heredoc that used the plain string `exp3_rescore`
a dozen times — so the pattern matched the tool call's own shell, the kill
landed on itself, and the heredoc never wrote its file. Rule 17 was already
about a kill that finds itself; this is the same failure surviving the fix
meant to prevent it. **Use a pidfile.** Every batch worker now writes
`outputs/exp3/<name>.pid` and is stopped by reading that file, which has no
pattern to get wrong.

**26. Shard the whole list, not the remaining one.** Rule 12 says to shard a
canonically sorted list; it did not say *which* list, and the Stage B runner
partitioned the **residual** — the cells not yet done. That makes a cell's shard
change as other cells finish: remove one element and every later element shifts
across the modulo boundary. Two workers then converge on the same cell, and a
cell can move between them mid-run. Partition the COMPLETE list once, so a cell
belongs to exactly one shard from start to finish, and subtract the finished
ones afterwards. The symptom that exposed it was a shard whose remaining count
did not drop after it completed a cell.

**27. A watchdog is verified by an effect you can see, never by its own
status.** The hourly keeper that was supposed to revive this batch had been
failing at startup on every firing while reporting `enabled: true` and a healthy
`next_run_at`. Nine hours were lost. The first fix was to read
`last_run.status` — and having read `SUCCEEDED`, the keeper was declared
working. **It was not.** `SUCCEEDED` means the session ran; it says nothing
about whether the session did the thing. The keeper was firing in a *different
container*, where this repository does not exist, so it "succeeded" at finding
nothing. Proven by firing it with an instruction to write a marker file into
`outputs/exp3/` and observing that the marker never appeared here.

The rule is therefore not "check the status." It is: **a watchdog is verified
only by an effect observable from the place the work actually lives.** Write a
marker, watch a counter move, look for a file — something the watchdog must
touch *here* to have done its job. Everything else is the watchdog grading its
own homework.

The most galling part is that this was already known. The previous keepalive
trigger is *named* `COTA job keepalive (disabled — fires in a different
container)`. It was diagnosed and disabled on 2026-08-29, and a new keeper with
the identical defect was built on 2026-08-31 without reading the name of the one
sitting next to it in the list. **Disabled things carry the reason they were
disabled; read it before building the replacement.**

**28. This container dies of SESSION idleness, not process idleness.** Busy
workers do not keep it alive. The shard loops committed a cell at 21:20:55 and
the container was still reclaimed at 21:26:58 — roughly fifteen minutes after
the last *foreground tool call*, with both workers running the whole time. Disk
survives, processes do not, so the batch resumes without rework, but every
reclaim costs whatever wall clock passes before something wakes the session.

Only a turn delivered into **this** session revives **this** container. A
scheduled task that starts a fresh session cannot do it (rule 27). What works is
a self-bound wake — `send_later`, which delivers an ordinary user turn back here
— re-armed by each wake so the chain continues. The foreground alternative is to
keep making tool calls, which is cheaper per beat but ends when the turn ends.

**The checkable signal is `persist_session`.** A trigger listing shows
`persist_session: true` with a `persistent_session_id` when the firing is bound
to an existing session, and shows neither when the firing spawns a fresh one
somewhere else. `send_later` sets it; a plain `create_trigger` does not. Read
that field before believing any watchdog is pointed at the work — it is the one
piece of evidence available *without* running the probe, and this project's
earlier A2 reminders had it set correctly before the Stage B keepers were built
without it. The regression was invisible because both kinds report `SUCCEEDED`.

Estimate the interval from the observed reclaim window and leave margin; do not
tune it to the edge, because the cost of one missed beat is hours and the cost
of an extra beat is seconds.
