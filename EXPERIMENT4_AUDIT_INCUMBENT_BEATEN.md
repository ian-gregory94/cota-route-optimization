# Exp 4 audit — an out-of-band candidate beats the incumbent

**Recorded 2026-09-15 21:16 UTC, at audit candidate 10 of 200. The audit is
still running; this note exists so the finding is on git immediately rather
than at closeout.**

## The fact

`outputs/exp4_audit/certified/55075e8f4c1e69c0.json`

| field | value |
|---|---|
| state_key | `exp4\|exp4-pool-v1\|65lines#eca7a2a1fb46` |
| state_digest | `eca7a2a1fb46c76c` |
| discovery rank (of 2000) | **237** |
| stratum | 201–400 |
| objective_EXACT | **3,510,666.7802095017** |
| objective_APPROXIMATE (discovery) | 3,624,634.8869983507 |
| rounds | 12, converged |
| seconds | 726.71 |
| lines | 65 |

Exp 4 incumbent, unchanged and not to be altered (Ian's item 5):
`exp4|exp4-pool-v1|65lines#ecb2ffc4bcce`, objective **3,511,184.5657525407**.

**Difference: 517.7855 absolute, 0.014747% better than the incumbent.**

Recomputed against the completed Exp 4 promoted 200: this candidate would
insert at **exact rank 1 of 201**.

## Why this matters

Exp 4 promoted the top 200 of 2000 proposals **by discovery score**. This
candidate was excluded by that cap. Its discovery score sat 106.2675 above the
rank-200 cut score (3,624,528.6195) — **0.002932%** of the cut score — while
its own discovery overstatement was **3.2463%** of its exact objective. The
quantity that decided promotion is roughly **1,100× smaller than the error in
the quantity**.

Its overstatement of 3.2463% **exceeds the maximum over the entire promoted
200** (0.9116%–3.2279%, D36), where the maximum was carried by the Exp 4
leader. That is consistent with D36's mechanism —
spearman(exact objective, overstatement) = −0.9930, i.e. the most overstated
candidates are the best ones — but it is a single observation and is not
offered as confirmation of anything.

## Decision-gate consequence

This satisfies the trigger for **branch three** of the preregistered gate in
`EXPERIMENT4_AUDIT_DESIGN.md`, in Ian's words:

> "If an out-of-band candidate beats the incumbent, or the lower-ranked strata
> show equal/better exact performance, flag the 200-cap as invalid and
> recommend expanding certification substantially or to the full remaining
> pool."

**The 200-cap is flagged as invalid.** The formal recommendation is still
deferred to closeout at 200/200, because the size of the expansion that is
warranted depends on the full audit distribution, which does not exist yet.

## What this does NOT establish

- It does not establish that the audit population is better than the promoted
  population. This is candidate 10 of 200, and the audit certifies in rank
  order, so the prefix is a biased draw from the best stratum.
- It does not establish how many further improvements exist, how large they
  are, or where in the rank space they live.
- It does not make this candidate a new incumbent for the audit's purposes.
  Ian's item 5 fixes the benchmark at 3,511,184.5658 and it stays fixed.
- It does not bear on fleet feasibility or deployability. Fleet remains
  `UNDECIDABLE`; no such claim is made.
- It does not authorise starting the full remaining certification. Ian's item
  9 is explicit and unconditional; it is not started.

## What happens next

The audit continues to 200/200 unchanged — same pipeline, same frozen sample,
no re-seeding, no substitution. The preregistered analysis and the decision
gate are applied at completion, and then it stops for Ian's decision.
