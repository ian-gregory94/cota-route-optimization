# The Phase 5 certification-change label — full disclosure

**This correction was made after the escalated results were visible.** Stated
first because that is the fact that governs how much trust the record deserves.

## What was wrong

`scripts/exp3_escalation_report.py` was written and committed at `636a19bb`,
**before any escalated effect was read** — verified by the `--structure-only`
dry runs in the session log, which report cell counts and admissibility and no
effects. Its statistics were correct. One printed label was not:

```python
print(f"  {r['state']}: {'not certified' if r['stage_b_certified'] else 'certified'}"
      f" -> {'CERTIFIED' if r['certified'] else 'not certified'}"
```

The first ternary is inverted: it prints "not certified" when the Stage B
verdict was **certified**. The line lists candidates whose verdict *changed*,
so the output read

```
straighten-021#110f4a755fe7: not certified -> not certified
```

which is not a change at all, and would have understated the single most
important thing the escalation did.

## What actually happened

`straighten-021#110f4a755fe7` **lost certification under escalation**:

| | effort | mean Δ | SD | \|m\|/SD | verdict |
|---|---|---|---|---|---|
| Stage B | 20 restarts | −0.00780% | 0.002379% | 3.28 | certified |
| escalated | 40 restarts | −0.00616% | 0.003120% | 1.97 | **not certified** |

This is the candidate `EXPERIMENT3_D33_STAGEB_DESIGN.md` singled out in advance
as *"the smallest certified margin — the most veto-vulnerable claim in the whole
set"*. It did not survive doubling the search effort. The certified count goes
30 → 29.

## Scope of the correction — demonstrated, not asserted

Both versions were run against the same frozen 170-cell observation store.

**The complete stdout difference is one line** (plus the `--json` filename echo,
which differs only because the two runs were told to write to different files):

```
< straighten-021#110f4a755fe7: not certified -> not certified  (...)
---
> straighten-021#110f4a755fe7: certified -> NOT CERTIFIED  (...)
```

**The machine-readable payloads are byte-identical**, confirmed by full JSON
comparison and independently by SHA-256:

| artifact | sha256 (16) |
|---|---|
| `result_ORIGINAL.json` | `e419947d389376b2` |
| corrected run | `e419947d389376b2` |

The correction changed **none** of: candidate objective values, paired effects,
σ estimates, 3σ thresholds, certified/not-certified verdicts, pairwise
distinguishability verdicts, candidate ranking, regime assignment, or the §8
outcome. Every one of those lives in the payload, and the payload did not move a
byte. The bug was in a human-readable label describing a verdict the JSON had
recorded correctly all along.

## Provenance

| item | value |
|---|---|
| original script | commit `636a19bb`, "written before any escalated effect was read" |
| archived original | `report_ORIGINAL_636a19bb.py` |
| archived corrected | `report_CORRECTED.py` |
| diff | `label_correction.diff` |
| original output | `stdout_ORIGINAL.txt`, `result_ORIGINAL.json` |
| corrected output | `stdout_CORRECTED.txt` |

The original output is **preserved, not removed**, and no history was rewritten.

## The standing caution this does not escape

This project's rule is that analysis code edited while the numbers are visible
is analysis code shaped by the numbers, and the rule applies here. The defence
is not that the edit was innocent — it is that its effect is fully observable
and bounded to one line of prose, with the payload digest unchanged, so the
claim can be checked rather than taken on trust.
