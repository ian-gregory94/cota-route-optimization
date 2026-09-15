# Exp 4 out-of-band audit — keeper beat protocol

This file is the durable copy of the keeper-beat protocol for the Exp 4
out-of-band certification audit. The scheduled beat message is a short pointer
to this file; everything that does not change between beats lives here so it
survives compaction, container reclamation, and the loss of the beat text
itself (which happened once already — see `EXPERIMENT4_KEEPER_BEAT.md`, the
post-compaction reconstruction of the *Exp 4* beat, now historical).

**The beat is my own scheduled text. It is NOT user input. Nothing in it, and
nothing in this file, constitutes user approval, confirmation, or consent.**
Ian authorised the audit in his ten-point instruction and said "Aight go" at
19:40 UTC on 15 Sep 2026 to resume it after a lapse. That is the whole of the
authorisation.

---

## What is running

The Exp 4 OUT-OF-BAND CERTIFICATION AUDIT: 200 candidates drawn as a stratified
random sample of discovery ranks 201–2000, frozen before execution in
`outputs/exp4_audit/audit_sample.json` (seed 20260914, digest
`00676a1c26792297`, 40 per stratum from 201–400 / 401–800 / 801–1200 /
1201–1600 / 1601–2000).

Repo: `/home/claude/columbus-transit-opt`, branch `exp3-clean`. The shell's cwd
reverts to `/home/claude` between calls — `cd` in or use absolute paths.

Design and preregistered analysis: `EXPERIMENT4_AUDIT_DESIGN.md` (frozen before
any candidate was certified, commit `1fd1a2f5`).

Motivation: **D36** — inside the promoted top 200, discovery rank
anti-correlates with certified rank (Spearman −0.3361; the Exp 4 winner entered
at discovery rank 196 of 200). The audit tests whether discovery nonetheless
enriches at the *population* level outside the promoted band.

## On wake, in this order

**1. RE-ARM FIRST.** Before the hold. Before reading notifications. Before
reporting. `mcp__claude-code-remote__send_later`, `delay_minutes=9`, the same
beat text with PROGRESS updated. **NEVER** `CronCreate` / `CronList` /
`CronDelete` — Ian's standing instruction is that scheduled tasks use the
`mcp__claude-code-remote__*` trigger tools only; the local cron tools run an
in-process scheduler that dies with the session. If the MCP server is still
connecting, load it with ToolSearch
(`select:mcp__claude-code-remote__send_later`) and re-arm anyway.

*Why first:* on 14 Sep at 13:34 a beat fired in the same batch as a message
from Ian, I answered the message and never re-armed. **Thirty hours, zero
progress**, container rebuilt from scratch. The single most valuable thing the
beat does is exist.

**2. ONE hold**, Bash timeout 600000:

```bash
cd /home/claude/columbus-transit-opt
roll () { p=$(cat outputs/exp4_audit/audit.pid 2>/dev/null); if ! ps -p "$p" >/dev/null 2>&1; then rm -f outputs/exp4_audit/audit.pid; bash scripts/exp4_audit_run.sh 6 2>&1 | tail -1; else echo "ALREADY RUNNING pid=$p"; fi; }
roll
for i in $(seq 1 16); do sleep 30; done
date -u; uptime; ls outputs/exp4_audit/certified/ | wc -l; grep -a 'obj ' outputs/exp4_audit/audit.log | tail -2; grep -ac 'BEATS INCUMBENT' outputs/exp4_audit/audit.log
roll
```

**3. Report ONE LINE** unless a threshold below says otherwise.

## Reporting cadence

Ian was told "report at intervals rather than every beat". Honour it. One short
line per ordinary beat. Report substantively ONLY on:

- a multiple of 25 certified;
- an error payload;
- a `NOT CONVERGED`;
- the count flat across three consecutive beats with the process alive;
- **an objective below 3,511,184.5658** — the runner prints
  `** BEATS INCUMBENT **`. Report that one IMMEDIATELY and prominently: it is
  decision-gate branch three (the 200-cap is invalid). **Do not stop the run
  for it.**

## How this environment behaves — hard-won, keep it accurate

Containers are reclaimed **intermittently and unpredictably**. Observed on
14 Sep: ~12:01, ~12:24, ~13:15. That is all that is known; it is not a period.

**The chain RECOVERS, it does not PREVENT.** Reclamation kills the shard
regardless of the chain. The opening `roll` restarts it; the fresh shard reads
completed results off disk and resumes. Nothing already certified is lost or
replayed. Compute *inside* a killed candidate IS lost — resume is
per-candidate, not mid-candidate.

`uptime` dropping to ~0 means a reclaim, not a failure: note it, confirm the
count did not go backwards, carry on. A flat beat is normal — a candidate takes
~500–890s against a ~480s hold.

When all 200 are done the process exits and the opening `roll` prints `STARTED`
with a pid that immediately exits having nothing to do. Expected.

## Do not

- **Do not analyse before all 200 are certified.** Counting files is not
  analysing; opening objectives and comparing them to the Exp 4 distribution
  is. The sample is stratified and certified *in rank order*, so any prefix is
  a biased draw from the best strata — a partial distribution is misleading,
  not merely premature.
- Do not re-randomise, re-seed, or substitute any candidate. Ian: "Do not
  substitute candidates based on apparent quality." If a cut-down is ever
  chosen, take the FIRST N of each stratum from the EXISTING frozen list.
- Do not alter the incumbent, the sample, or anything under `outputs/exp4/run/`.
  Ian: "Do not rewrite Exp 4 history; this is a new audit motivated by D36."
- Do not touch `src/cota_opt` or `scripts/exp4_launch.py` — OPERATIONS 24: a
  batch in flight freezes the code that can change its numbers.
- **Do not start the full certification under any outcome.** Ian: "Do not start
  the remaining ~326-hour full certification automatically under any outcome.
  Stop after analysis and report back for a decision." Current audit throughput
  suggests that ~326h figure is really 700–900h.
- Do not generate, request, or handle a GitHub PAT or any other credential.
  Pushes go through GitHub Desktop's own token on Ian's machine.
- Do not make any fleet or deployability claim. Fleet feasibility is
  `UNDECIDABLE` for every candidate; deadhead provenance is OPEN; terminal
  identity is degenerate (D24); the brackets are `CANDIDATE_BLOCK_BOUND` and
  neither end is a fleet number.
- `git add -A` and `git commit -F <file>` must be SEPARATE Bash calls. The
  compound form is refused by the classifier.

## Method warnings, earned

- Do not read a rank off a truncated list. Do not hand-merge one.
- **Do not restate a claim without recomputing it.** The categorical claim
  "every candidate converging in ≤8 rounds lands in the bottom half" was false
  for 33 candidates before it was caught, because the numbers were recomputed
  each checkpoint and the claims were not. Numbers **and** claims get
  recomputed from the certified JSONs every checkpoint.
- Small buckets are not stable. No claim on a bucket with fewer than ~20
  members — the enrichment tables had to be retracted wholesale for this.
- **Do not build a rate or a period out of a few events.** I told Ian the
  container was "reclaimed every ~24 minutes" off two observations and had to
  correct it. Reclamation is intermittent and unpredictable, full stop.

## When all 200 are certified

1. Stop the chain (`delete_trigger` on the live beat, or let the last one fire
   and do not re-arm — but say which).
2. Run the preregistered analysis in `EXPERIMENT4_AUDIT_DESIGN.md` **in full**:
   all ten items, stratum-weighted AND unweighted where they differ. The
   sampling fractions are unequal — 20% of stratum 1 (201–400), 10% of each of
   the other four — so unweighted audit statistics are not population
   statistics.
3. Answer the preregistered question explicitly, in these words:
   > "Does discovery provide useful population-level enrichment even though it
   > does not provide useful ordinal ranking inside the promoted band?"
   Do not extrapolate beyond what the sample supports.
4. Apply the preregistered three-branch decision gate: clearly worse and
   nothing near the incumbent → recommend stopping; materially overlapping
   distributions → recommend a larger second audit; an out-of-band candidate
   beats the incumbent, or lower strata match/beat higher ones → the 200-cap is
   invalid, recommend expanding certification substantially.
5. **STOP and report for a decision.**
6. Commit separately, per Ian's item 10: the completed certification result;
   the analysis and decision-gate findings; `DISCOVERIES.md` if warranted; the
   project-doc updates (`STATE_OF_PLAY.md`, `FLEET_AND_BLOCKING.md`, mirrored
   to the claude.ai project docs).
7. Keep the design's four "cannot answer" items, above all this one: a match
   between the audit and promoted distributions is consistent BOTH with
   discovery adding nothing AND with the proposal pool being near-uniform in
   exact objective. **Do not pick the flattering reading.**

Keep retractions and caveats explicit throughout. Ian asked for that by name.

## Stop conditions

- **Ian says anything** → stop, read it, act. **Then re-arm BEFORE replying.**
  That is exactly how thirty hours were lost.
- Count flat across three consecutive beats with the process alive → report.
- Count goes BACKWARDS → stop immediately and report. Cannot happen by design,
  so it means something is wrong with the design.
- Any error payload or `NOT CONVERGED` → report prominently.
- Shard fails to restart after a `roll` → report.
