# Generation 1 — frozen

Gen1 is the methodology of Experiments 1, 2, 2B and 3, defined in
`METHODOLOGY.md` and frozen once those closed. All four are closed. This is the
terminal record.

**Frozen 2026-09-04. Manifest: `outputs/GEN1_FREEZE_MANIFEST.json`. Verify with
`python scripts/gen1_freeze.py --verify`.**

## What Gen1 concluded

| experiment | status | headline |
|---|---|---|
| **1 — frequency redistribution** | closed, certified λ≥2 | **−6.65% ± 0.06 unserved demand** at no additional buses (2,516.5 of 2,517.2 vehicle-hours, 197 of 197 peak vehicles) |
| **2 — route geometry, 12 splices** | closed, nothing promoted | **no supportable geometry claim.** Six of twelve do measurable harm, none does measurable good; the −0.5% through-routing claim was withdrawn (D24) |
| **2B — all 240 feasible subsets** | closed, certified NULL | **NULL**, and it survives a matched-start re-test (D31). No multi-edit set beats the best single at any λ |
| **3 — route mutation** | closed, frozen `exp3-final-v1` | **certified leader `add_stop-010#22c4c35ac5b2` at −0.18657%**, \|m\|/SD 78.6, 29 of 39 certified |

One certified improvement in three experiments' worth of geometry search, and it
is small. The frequency result remains the only large one.

## What is asserted, and what is merely recorded

`scripts/exp3_freeze.py --verify` asserted that the whole tree still matched the
moment of freezing, including the live `code_version()`. That check began
failing the same day it was written: commit `c2b2b947` added the Stage B
machinery and moved the source digest from `src-74b02d24b77f` to
`src-bd82ac5a6dae` — which is exactly what a project does after freezing a
stage. Stage A's evidence never stopped verifying; its receipts and contract
digest still check out today. The check was over-asserting, and an over-asserting
check gets ignored, and a check nobody runs is not a check (OPERATIONS 27).

So this freeze separates the two:

**ASSERTED — false means the record is broken:**

| | |
|---|---|
| contract digests | Stage A `00c0953c95a96ffd`, Stage B `ec7e566dc028f94d`, escalated `45e23ae01be4d071` |
| receipt counts | Stage A 104, Stage B 200, escalated 170 |
| receipt digests | hashed as a set, per store |
| `code_version` recorded *inside* each receipt | Stage B and escalated both `src-bd82ac5a6dae`; Stage A carries two, from its documented D27 re-score |
| 14 result artifacts | content hash |
| tags | `exp3-frozen-v1`, `exp3-final-v1` |

**RECORDED — reported as information, never as a failure:** the live source
digest (`src-bd82ac5a6dae` at freeze), and `DISCOVERIES.md`, `OPERATIONS.md`,
`ACCEPTANCE.md` — documents this project appends to by design.

Gen1 results stay verifiable after the source moves because **every receipt
carries the `code_version` it was produced under**. That is what makes a
generation freezable at all: the evidence is self-describing, so the tree is
free to move on.

## What Gen1 may not be blamed for

The seven reopening conditions in `METHODOLOGY.md` still apply, and a Gen2
number is never a correction of a Gen1 number — both are kept, labelled by
generation. Gen1 is not reopened because Gen2 is newer, faster, or finds an
improvement below the applicable floor.

Two things inside Gen1 are already known to be weaker than the rest and are
recorded here so Gen2 does not have to rediscover them:

* **Experiment 3's certified set is split across two solver efforts** — 23 of 29
  at 40 restarts, 6 including the leader at 20 (§7 of `EXPERIMENT3_CLOSURE.md`).
* **The Stage A census carries two `code_version`s**, from the D27 re-score. It
  is descriptive only and nothing in it is certified, which is why that is
  tolerable there and would not be anywhere else.

## What comes next

`METHODOLOGY.md`'s order of work, from here:

1. ~~firewall~~ → ~~Exp 2/2B repair~~ → ~~Exp 3 rescore~~ → ~~rebuilt frontier~~
   → ~~Exp 3 certification~~ → ~~**Gen1 freeze**~~ ← *done*
2. the exact frequency benchmark
3. the optimization-gap measurement
4. the evidence-based reopening decision
5. incremental evaluation with full-rebuild canaries
6. Gen2 — and only then Experiment 4, which is the first experiment designed
   natively around it

Experiment 4's readiness is tracked mechanically by
`scripts/exp4_readiness.py`; Gen1 freeze closes the first half of its item 21.
