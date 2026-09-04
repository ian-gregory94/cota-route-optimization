# Phase 5b — symmetric escalation of the remaining six

Frozen before any Phase 5b cell runs. Authorised by Ian on 2026-09-04 after the
two-regime asymmetry was reported.

## Why this runs

`EXPERIMENT3_PHASE5_DESIGN.md` recorded the weakness plainly: §6 escalates what
is *unresolved or failing*, which is by construction the *smaller* margins, so
the six largest-margin candidates — the Stage B leader among them — were never
solved above 20 restarts. The certified set was therefore split across two
solver efforts, with the leader on the softer side.

That document also fixed what may and may not be done about it:

> Re-running the leader at 40 restarts *after* seeing that escalation threatened
> it [is not permitted]. Any such run would be a measurement chosen by its
> expected answer. […] Closing the asymmetry requires escalating **all six**
> non-escalated candidates, a rule that does not depend on which candidate it
> favours.

This is that step, and only that step.

## The rule, and why it is symmetric

> **Escalate every promoted candidate that has no measurement at the escalation
> effort, so that the entire certified comparison set is evaluated under one
> solver-effort regime.**

The rule names no candidate and no outcome. It is stated over a property of the
*measurement* (does a 40-restart cell exist for this state?), not over a
property of the *result* (does this candidate lead?). Its membership is
therefore fully determined before any new number exists, and it can only
*remove* the leader's current advantage — the leader is the one presently
benefiting from having been tested less hard. A rule that can only hurt the
favoured hypothesis is not a rule chosen to protect it.

`add_stop-010#22c4c35ac5b2` is in this set because it lacks a 40-restart
measurement, exactly like the other five. Not because it is the leader.

## The set — determined mechanically, not chosen

The six promoted states absent from `outputs/exp3/escalation_manifest.json`:

| state | Stage B effect | SD | \|m\|/SD | Stage B verdict |
|---|---|---|---|---|
| `add_stop-010#22c4c35ac5b2` | −0.18657% | 0.002375% | 78.55 | certified (leader) |
| `reroute-031#dfd049714f7d` | −0.16110% | 0.002836% | 56.81 | certified |
| `truncate-035#7cdb09a45253` | −0.13714% | 0.002376% | 57.71 | certified |
| `truncate-025#d3209fe02367` | −0.13169% | 0.002376% | 55.42 | certified |
| `truncate-101#3d4f770cd393` | −0.09780% | 0.004017% | 24.35 | certified |
| `add_stop-007#02161399a599` | −0.05700% | 0.002690% | 21.19 | certified |

6 states × 5 predeclared seeds = **30 cells**. The control already has its five
40-restart cells inside the existing 170, so no control cells are added and none
are re-run.

On completion the escalated store holds **200 cells** — control + all 39
promoted candidates × 5 seeds — mirroring Stage B's design exactly at double the
effort.

## What is held fixed

Everything. The escalation contract `EXP3_STAGE_B_ESCALATED`
(`45e23ae01be4d071`, 40 restarts, 400,000 ceiling, full width), the five
predeclared seeds, the evaluation path pinned by `EVAL_PATH_FROZEN`
(`src-bd82ac5a6dae`), the firewall, the §4 criterion, the §5 pairwise test, the
ddof convention, and the corrected §8 classifier. Cells are written to the same
`observations_stageB_esc` store under the same contract, because they are the
same regime.

`escalation_manifest.json` is **not modified**. The §6 escalation set is a
record of what §6 triggered and stays that way; Phase 5b is a separate,
separately-declared set with its own manifest.

## What counts as a result — declared now

Any of these is an acceptable terminal state and none is to be engineered
around:

* the leader keeps its margin and its separations → the previous conclusion
  stands, now on uniform effort;
* the leader's margin moves but it still separates from every certified
  candidate → §8 outcome (1) with a revised figure;
* the leader stops separating from some certified candidate → **§8 outcome (2)**,
  reported as a set with no leader named;
* the leader loses certification outright → it is not certified, and whatever
  the table then says is the result.

**If anything changes, it changes.** No threshold, candidate membership,
convention, or classifier will be revisited after these numbers are visible. The
only code permitted to change afterwards is code that is demonstrably display-
only, and any such change is disclosed with the payload digest shown unmoved —
as was done twice already (`outputs/exp3/classifier_audit/`,
`outputs/exp3/phase5_audit/`).

## Analysis after completion

`scripts/exp3_escalation_report.py` needs no rule change. Its regime bookkeeping
is written over "is this state in the escalated store?" and will simply find
every promoted state there, so every row becomes `escalated` and every pairwise
comparison becomes a within-regime 40-restart comparison. The two-regime
branches remain in the code and become unreachable rather than being deleted, so
the same script reproduces both the two-regime and the uniform table depending
only on what the store contains.

The Phase 5 (two-regime) report is **preserved** at
`outputs/exp3/escalation_report.json` alongside its audit trail. The uniform
result is written to a new file. Neither supersedes the other by deletion.

## Cost

30 cells, 2 shards on 2 cores, recent cells 1550–1789 s: **roughly 6.5–7.5
hours**. An earlier estimate of 3.5 h given to Ian was arithmetically wrong
(the per-shard division was applied twice) and is corrected here.
