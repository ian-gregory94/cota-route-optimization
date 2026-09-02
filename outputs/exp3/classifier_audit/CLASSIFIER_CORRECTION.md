# The §8 classifier correction — full disclosure

**The correction was made after the Stage B numerical results were visible.**
That is stated first because it is the fact that matters for how much this
record should be trusted, and no part of what follows should be read as
softening it.

## What the original classifier did, and why it was wrong

The analysis script was written and committed at `3a21ba57`, **before any Stage
B cell had run**. Its statistics were correct. Its final classification step was
not:

```python
elif all(p["resolved"] for p in pw):
    print(f"(1) A LEADER among {len(certified)} certified: ...")
```

It required **every** pairwise relationship among **all** certified candidates
to resolve before it would name a leader. With 30 certified candidates that is
435 relationships, and 39 of them did not resolve — so it printed **outcome
(2)**, "certified, not all distinguishable, no leader named".

`EXPERIMENT3_STAGE_B_PREREGISTRATION.md` §8 outcome (1) does not say that. It
says:

> **A certified small route-mutation improvement** — one candidate certified
> against the control *and* distinguishable from every other certified
> candidate.

That condition is **existential and per-candidate**: *some* candidate must
separate from every other certified candidate. It is not a property of the
whole pairwise matrix. Unresolved pairs among lower-ranked candidates say
nothing about whether the leader separates from all of them.

`add_stop-010#22c4c35ac5b2` has **29 of 29** pairwise comparisons resolved.
None of the 39 unresolved pairs involves it. It satisfies §8 outcome (1) as
written.

The correction is therefore a **reporting/classification bug fix**, not a
statistical-method change. It brings the code into agreement with the frozen
text; it does not change the frozen text, and the text was not reinterpreted
after the fact — §8's wording is unchanged and quoted above verbatim.

## Scope of the correction — demonstrated, not asserted

Both classifier versions were run against the **same frozen 200-cell
observation store**. Artifacts are in this directory.

**The complete stdout difference is one line:**

```
< Outcome: (2) 30 CERTIFIED, NOT ALL DISTINGUISHABLE — reported as a set, no leader named (§8).
---
> Outcome: (1) A CERTIFIED LEADER: add_stop-010#22c4c35ac5b2
>   certified against the control and distinguishable from all 29 other certified candidates.
>   39 of 435 pairs elsewhere in the set remain unresolved; none involves the leader.
```

(plus one line echoing the `--json` filename, which differs only because the two
runs were told to write to different files).

**The machine-readable payloads are byte-identical**, confirmed two ways —
a full sorted-key JSON comparison, and independently by SHA-256:

| artifact | sha256 (16) |
|---|---|
| `result_ORIGINAL.json` | `0598f5a526484568` |
| `result_CORRECTED.json` | `0598f5a526484568` |

The correction changed **none** of the following:

* candidate objective values
* paired effects
* σ estimates
* 3σ thresholds
* certified / not-certified verdicts
* pairwise distinguishability verdicts
* candidate ranking
* the §6 escalation set

Every one of those lives in the JSON payload, and the payload did not move a
single byte.

## Provenance

| item | value |
|---|---|
| original classifier | commit `3a21ba57`, "Stage B analysis, written before any Stage B result" |
| corrected classifier | commit `89983e4e` |
| diff | `classifier_correction.diff` |
| original source (archived, runnable) | `classifier_ORIGINAL_3a21ba57.py` |
| corrected source (archived) | `classifier_CORRECTED_89983e4e.py` |
| original output | `stdout_ORIGINAL.txt`, `result_ORIGINAL.json` |
| corrected output | `stdout_CORRECTED.txt`, `result_CORRECTED.json` |
| artifact digests | `DIGESTS.json` |

The original classification is **preserved, not removed**, and no git history
was rewritten. The original script remains reachable at `3a21ba57` and is also
archived here in runnable form so the comparison can be reproduced without
consulting git.

## Reproducing this check

```bash
git show 3a21ba57:scripts/exp3_stage_b_report.py > scripts/_audit_original.py
python scripts/_audit_original.py --json /tmp/orig.json > /tmp/orig.txt
rm scripts/_audit_original.py          # ROOT is __file__.parents[1]; it must live in scripts/
python scripts/exp3_stage_b_report.py --json /tmp/corr.json > /tmp/corr.txt
diff /tmp/orig.txt /tmp/corr.txt       # one Outcome line
sha256sum /tmp/orig.json /tmp/corr.json # identical
```

## The standing caution this does not escape

This project's own rule is that analysis code written or edited while the
numbers are visible is analysis code shaped by the numbers. That rule applies
here. The defence is not that the edit was innocent — it is that the edit's
effect is **fully observable and bounded**: one printed line, zero movement in
every number and every verdict, with the preregistered text quoted above so the
reading can be checked against it directly rather than taken on trust.

From this point onward, the corrected classifier is the one in force.
