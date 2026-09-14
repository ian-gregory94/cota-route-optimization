# Experiment 4 — closeout

Run completed 2026-09-14 03:18:05 UTC. 200 of 200 promoted candidates
certified. Every number below was recomputed from `outputs/exp4/run/certified/`
at closeout, not copied from a checkpoint commit.

## The result

```
exact_leader        exp4|exp4-pool-v1|65lines#ecb2ffc4bcce
objective_EXACT     3,511,184.5657525407
rounds              12 (converged)
lines               65
```

| | objective | rel. to leader | rounds |
|---|---|---|---|
| 1st | 3,511,184.5658 | — | 12 |
| 2nd `...08f377545e31` | 3,511,557.9642 | +0.0106% | 11 |
| 3rd | 3,514,611.1824 | +0.0976% | 14 |
| worst `...96485eb1a98e` | 3,591,198.3836 | +2.2788% | 11 |

Median gap 0.7721%. Nine candidates within 0.18% of the leader.

`rank_certified` produced the ordering, on the complete set, on
`objective_EXACT` alone, under the frozen tie-break `0297e180cf30369d`.
Digests: proposal `2b8e18c681689a55`, promotion `ec6288fc8ec9b7d0`,
certification `2125984c82b60a83`, envelope `b6c647d3766338a6`.

## The margin is the first thing to say about it

First to second is **373.40 absolute, 0.0106% relative**. Second to third is
0.0976% — nine times larger. The effects this project reports are ~0.19%,
eighteen times the winning margin.

The leader also changed at candidate **190 of 200**. `...08f377545e31` led from
candidate 16 through candidate 189 — 174 consecutive candidates, and every
checkpoint commit from the 20 mark to the 180 mark reported it as the best so
far. Cutting the run anywhere before candidate 190 would have reported a
different winner. That is not evidence that 200 was enough.

## Execution

```
first certified   2026-09-12 15:06:24 UTC
last certified    2026-09-14 03:18:05 UTC
wall span         36.19 h
compute           130,308 s = 36.20 h   (mean 652 s, range 413–735)
shards            six, 6.0 h bound each
```

Zero errors. Zero `PathsetScopeViolation`. Zero empty-scope
`CertificationError`. All 200 converged; none reached `MAX_ROUNDS = 40`.

Six shard boundaries were crossed with nothing lost and nothing replayed: the
bound is checked at the top of each candidate, so the one in flight always
finishes and writes its JSON, and a fresh shard reads completed results off
disk. Wall span and compute time agree to two decimal places — the container
was held continuously with no idle gap.

Rounds to convergence: `3:2  5:6  7:2  8:3  9:3  10:12  11:29  12:13  13:112
14:18`. One bucket holds 56% of the field.

## What Experiment 4 establishes

**The best certified objective under the canonical vehicle-hours envelope is
3,511,184.5658, achieved by `...ecb2ffc4bcce`.** That is the whole of the
positive claim.

**Fast convergence excludes a candidate from contention.** Computed on the
complete set:

```
best rank among rounds <=  8 :  80 of 200   (13 such candidates)
best rank among rounds <= 10 :  70 of 200   (28 such candidates)
```

The top **69** is entirely 11+ rounds. The boundary widened monotonically as
the field filled in — 60th at n=180, 66th at n=191, 70th at n=200 — so more
data strengthened it. The stated falsifier, a candidate inside the top fifty
converging in ten rounds or fewer, did not occur.

This is consistent with the `(N,K)`-block-local contract rather than a
discovery about it: with `N_KEYS=8, K_RUNGS=3`, a plan with no improving 8-key
block within 3 ladder rungs stops early because it sits in a shallow basin.
The uncomfortable half is that those same candidates are the ones whose
certified objective is least trustworthy as a bound on the global optimum —
the residual is unmeasured and structurally widest exactly where convergence is
fastest. **The claim is about certified rank, not about truth.**

Note what it does *not* say: nothing about where in the remaining field a fast
candidate lands (they run 70th to 199th), and nothing about which of the slow
buckets wins. The leader converged in 12 rounds, two short of the deepest in
the field.

**Discovery rank anti-correlates with certified rank** — see the next section.

## D36 — discovery's ordering is inverted, and the cap nearly cost the run its answer

```
spearman(discovery rank, certified rank), n=200      -0.3361
spearman(exact objective, overstatement)             -0.9930
spearman(discovery rank, rounds)                     -0.0202
```

The certified winner was **discovery rank 196 of 200**. Promotion took the top
200 of 2000 proposals by discovery score; the winner sat **four slots above the
cut**, separated from the 201st proposal by 12.02 on a score of 3.62 million
(0.0003%). Rank 200 and rank 201 differ by 5.57, or 0.000154%.

The mechanism is visible in one number. Discovery always overstates the exact
objective, by 0.9116% to 3.2279%, and that overstatement is anti-correlated
with the true objective at **−0.9930**: the better the candidate, the more
discovery overstates it. The leader carries the **largest overstatement in the
field**. A near-perfect negative correlation of that shape means the discovery
score is very nearly constant, so its residual simply tracks `−exact`.

Across the same 200 candidates:

```
exact objective     range 2.2788%
discovery score     range 0.1589%      -> exact varies 14x more
stdev exact (% of mean)     0.4361%
stdev overstatement         0.4638 pts -> error exceeds signal, 1.06x
```

Discovery's approximation error is *larger* than the true variation it is
ranking. Whatever ordering it produces in this band is dominated by its own
residual, and that residual points the wrong way.

Supporting detail: of the certified top 20, only four were inside discovery's
top 100 (their discovery ranks: 33, 73, 90, 97, 106, 109, 110, 117, 122, 133,
135, 139, 142, 143, 155, 158, 195, 196, 198, 199). Of the certified top 50,
thirteen were in discovery's top 100 and thirteen were in its bottom fifty.
Discovery's own top ten certified at ranks 196, 198, 135, 133, 166, 167, 164,
102, 170, 157 — every one in the bottom half.

This is D18 in its sharpest form. The gap is not noise around the truth; it is
a structured quantity that grows with candidate quality, so ranking by
approximate objective ranks by structure-induced error. Artifact:
`outputs/exp4/run/discovery_vs_certified.json`.

**The band caveat travels with this finding.** It is measured inside the
promoted 200, whose discovery scores span 0.159%. It does not extrapolate to
proposals 201–2000, and no claim is made about what those contain.

## Retractions

Three claims were made in checkpoint commits and are wrong. They are listed
here because the commits are the project's record and a reader working forward
through them will otherwise carry the errors.

1. **"Every candidate converging in ≤8 rounds lands in the bottom half."**
   FALSE, and false since candidate 147. `...b2b43dbb7034` (8 rounds) entered
   at rank 58 of 147 and finished **80th of 200**. The claim was restated as
   holding at the 150, 160 and 170 checkpoints. Corrected at 180 (`4a0077bc`).
   Cause: numbers were being recomputed each checkpoint; *claims* were not.

2. **Every enrichment table published before the 190 checkpoint.** Superseded,
   not merely updated. At 180 the 12-round bucket read 0.00x/0.33x — the most
   depleted non-empty row — and ten candidates later it held first place
   outright. A 13-member bucket moves eight percentage points on one result.
   Final table:

   ```
   rounds  field  top20  enrich   top50  enrich
      3–10    28      0    0.00x      0    0.00x
     11      29      2    0.69x      4    0.55x
     12      13      1    0.77x      2    0.62x
     13     112     14    1.25x     38    1.36x
     14      18      3    1.67x      6    1.33x
   ```

   No claim should be built on any row here with fewer than ~20 members, which
   is six of the ten rows.

3. **Two ranks stated without being computed** — candidate 138 reported
   eleventh (actually thirteenth, `bef955bc`), candidate 157 reported fifteenth
   (actually twenty-first, `bd41e4ce`). Both came from reading a position off
   the end of a truncated top-10/top-14 printout. Every rank from candidate 161
   onward was computed against the full sorted set.

**Spearman(rounds, certified) is recorded, not argued.** Nine checkpoints:
−0.299, −0.319, −0.312, −0.302, −0.262, −0.265, −0.264, −0.271, −0.265 final.
It wandered without direction across the whole run. With 56% of the field in
one bucket it mostly measures intra-bucket scatter. It was never the evidence.

## What Experiment 4 does not establish

**No fleet requirement.** The fleet instrument returns `UNDECIDABLE` for every
candidate, including the leader. Deadhead provenance is OPEN and terminal
identity is degenerate on synthesised candidates. The envelope carries a
CANDIDATE_BLOCK_BOUND bracket (180–212 system-wide) and **neither end may be
reported as a fleet number**.

**No operational deployability claim.** Fleet was REPORTED, NOT GATED: no fleet
verdict filtered, ranked or rejected any candidate, per `READINESS_FROZEN`
(authorised by Ian, 2026-09-07). D24 remains open as post-result operational
validation.

**No global optimality.** The `(N,K)`-block-local guarantee is local. The
residual between block-local and global is unmeasured for every candidate
including the leader.

**Nothing about proposals 201–2000.** 1800 proposals were never certified. The
anti-correlation above makes the question of what they contain sharper, not
self-answering: the argument for the cap was that discovery ordering
concentrates good candidates at the top, and measured, it does the opposite.
Certifying the remainder is ~326 hours at 652 s a candidate. That is a decision
about compute, not a finding.

**Nothing about the 0.0106% margin's durability.** Two candidates separated by
a hundredth of a percent, under a local guarantee with an unmeasured residual,
are not meaningfully ordered by this experiment. They are ordered by
`rank_certified` under the frozen tie-break, which is what the contract asks
for, and that is a different statement.
