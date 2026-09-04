# Phase 5 — how escalated and non-escalated results are combined

Frozen before any escalated effect has been read. Written because the §6
escalation covers a **subset**, and the Stage B analysis script assumes it
covers everything — a mismatch that has to be resolved by a rule, not by
whatever produces a tidy answer.

## The mismatch, stated exactly

`scripts/exp3_stage_b_report.py` builds its expected-cell set as *every*
promoted state × 5 seeds = 200, regardless of `--escalated`. §6 escalates only
the candidates it triggers on: **33 + control = 170 cells**. Run unmodified,
`--escalated` refuses with 30 "missing" cells. That refusal is the script
behaving correctly on a design it was not told about; it is not a bug in the
escalation.

## What the escalation does and does not cover

From `outputs/exp3/escalation_manifest.json`, generated mechanically and
committed before the batch started:

| set | n |
|---|---|
| promoted (Stage A negative) | 39 |
| certified at Stage B | 30 |
| escalated (the §6 manifest) | 33 |
| escalated **and** certified | 24 |
| certified but **not** escalated | 6 |
| escalated but not certified (the §6 failures) | 9 |

Trigger composition of the 33: 24 unresolved-pairwise, 9 failed-criterion,
1 ddof-sensitive (inside the 9).

**The Stage B leader `add_stop-010#22c4c35ac5b2` is not in the manifest.** That
is §6 working as written, not an oversight: it certified at 20 restarts, its
spread was stable, its verdict did not depend on the SD convention, and all 29
of its pairwise comparisons resolved. None of §6's triggers fires on a
candidate with nothing unresolved about it.

The consequence is worth stating plainly rather than discovering later: **the escalation contains no 40-restart measurement of the leader**, so it cannot
confirm the leader's own margin at higher effort. What it can do is change *who
else is certified* and resolve the pairwise relations that were open.

## The rule

Ian's Phase 5 instruction is *escalated supersedes lower-effort for the
triggering decision; do not average regimes*. Transcribed into the three
decisions this report makes:

1. **Certification.** For each of the 33 escalated candidates, the 40-restart
   verdict supersedes the 20-restart verdict outright. For the 6 candidates §6
   did not trigger, the Stage B verdict stands unchanged — their certification
   was never a triggering decision and no higher-effort measurement of them
   exists. Every row is labelled with the regime that produced it.

2. **Pairwise distinguishability.** A comparison is computed **within one
   regime or not at all.**
   * both members escalated → 40-restart comparison; supersedes Stage B for
     that pair.
   * either member not escalated → 40-restart comparison is impossible, so the
     20-restart comparison stands and is labelled as such.
   A 20-restart effect is never differenced against a 40-restart effect. The
   firewall would refuse it anyway — the two carry different contract digests —
   and that refusal is a feature being relied on, not routed around.

3. **§8 outcome.** The certified set is whatever (1) produces. The leader test
   — certified, and distinguishable from every other certified candidate — is
   then evaluated over that set using (2)'s within-regime comparisons. If
   escalation promotes a previously-failed candidate into the certified set,
   the leader's comparison against it is computed from the **Stage B**
   receipts, which exist for all 39 promoted states; that is a legitimate
   20-restart comparison that Stage B simply never had occasion to print,
   because §5 compares only certified candidates.

Nothing is averaged and no number is combined across regimes. What differs
between rows is the *effort at which each was measured*, and that is carried in
the output rather than smoothed away.

## The asymmetry this leaves, disclosed rather than resolved

After Phase 5 the certified set is measured at two efforts, and the leader is
on the weaker side of that split: the escalated candidates have been examined
at 2× the restarts, the leader has not. Two honest readings follow and both
are reported:

* the leader's margin is **unconfirmed at 40 restarts**, because §6 gave no
  reason to look;
* candidates that survive certification at 40 restarts have passed a stricter
  test than the leader has.

If the escalated results produce a candidate that certifies at 40 restarts
with a margin comparable to or larger than the leader's, the two cannot be
separated within a common regime and **no leader may be named** — that is §8
outcome (2), and it is an acceptable terminal state. Losing the leader to a
regime split is a result, not a problem to be engineered around.

## What is not permitted here

* Re-running the leader at 40 restarts *after* seeing that escalation
  threatened it. Any such run would be a measurement chosen by its expected
  answer. If the leader is to be escalated, the decision must be justified by a
  rule and recorded before the escalated numbers are read — and §6 already
  declined to escalate it.
* Widening the manifest.
* Comparing across regimes "for reference".
* Treating the 6 non-escalated candidates as though 20 restarts and 40
  restarts were the same measurement.
