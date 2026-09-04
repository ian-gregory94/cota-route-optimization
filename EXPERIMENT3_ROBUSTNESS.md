# Phase 7 — effort robustness across Stage A, Stage B and the §6 escalation

Experiment 2's central lesson was that a geometry result can be an artifact of
insufficient search: its leading candidates reversed sign when re-solved at
higher effort, and the claim was withdrawn (D23, D26). Experiment 3 runs the
same dimension of the same network, so the first question anyone should ask of
its leader is whether it is the same kind of mistake.

This is a **diagnostic**, reported after the fact. It is not a gate and no
candidate certifies or fails to certify because of anything on this page. The
criterion is §4's and nothing here is added to it.

## The three efforts

| stage | restarts | evaluation ceiling | candidate width | seeds |
|---|---|---|---|---|
| Stage A (census) | 2 | 60,000 | 32 | 1 |
| Stage B (certification) | 20 | 400,000 | full | 5 |
| §6 escalation | 40 | 400,000 | full | 5 |

**Stage A → Stage B is exactly the effort transition that broke Experiment 2.**
Experiment 2's geometry candidates were screened at 60,000/2/32 and re-solved at
400,000/20 — the same two configurations, on the same network, under the same
Model B evaluator. The comparison below is therefore like-for-like, not a
flattering re-scaling.

## The comparison

| | effort transition | median \|shift\| | max \|shift\| | sign changes |
|---|---|---|---|---|
| **Experiment 2** geometry leaders (n=2) | 60,000/2/32 → 400,000/20 | **0.645 pts** | 0.645 pts | **2 of 2** |
| **Experiment 3** promoted set (n=39) | 60,000/2/32 → 400,000/20 | **0.00207 pts** | 0.00661 pts | 1 of 39 |
| **Experiment 3** escalated set (n=33) | 20 → 40 restarts | 0.00130 pts | 0.00164 pts | 0 of 33 |

Experiment 2's two leaders moved **0.645 points and both crossed zero**:
`splice|011|034|WESHIGW` −0.585% → +0.060%, `splice|033|034|WESHIGW`
−0.485% → +0.160%. A measured benefit became nothing.

Experiment 3's promoted set, across the identical transition, moved a median of
**0.00207 points** — roughly **310× smaller** — and one candidate of 39 changed
sign: `add_stop-141#2fc0aa211ecb`, −0.00054% → +0.00017%. That is the smallest
effect in the set, it is two orders of magnitude below the leader, and it is not
certified at either effort. Nothing rests on it.

The leader itself: **−0.18885% at Stage A → −0.18657% at Stage B**, a shift of
+0.00228 points, or 1.2% of its own magnitude.

## Rank stability under escalation

Among the 33 escalated candidates, doubling the restarts left **27 of 33 ranks
unchanged**, and no rank moved by more than one place. The best escalated
candidate is `straighten-102#4dd646541565` at both efforts.

## What did move

One verdict changed, and it is the one the design named in advance.
`straighten-021#110f4a755fe7` — identified in
`EXPERIMENT3_D33_STAGEB_DESIGN.md` as *"the smallest certified margin, the most
veto-vulnerable claim in the whole set"* — **lost certification**:
−0.00780% (SD 0.002379%, ratio 3.28) at 20 restarts, −0.00616% (SD 0.003120%,
ratio 1.97) at 40. Certified count 30 → 29.

That is escalation doing its job at the bottom of the table, which is where §6
pointed it.

## The direction of the difference, stated against Experiment 3's interest

Experiment 3's effects are *stable* under effort where Experiment 2's were not.
That is the favourable reading and it is supported. Two qualifications belong
next to it:

* **The escalation tested the weak end.** §6 escalates what is unresolved or
  failing, which is by construction the smaller margins. The five largest
  margins — the leader among them — have never been solved above 20 restarts.
  The best margin that *has* been confirmed at 40 restarts is −0.08017%,
  2.33× smaller than the leader's. The leader leads on the weaker measurement.
* **The Stage B → escalation jump is small.** 20 → 40 restarts at an unchanged
  ceiling and width is a 2× change; Experiment 2's was 6.7× the iterations and
  10× the restarts *and* a width change. The Stage A → Stage B row is the one
  carrying the weight of this comparison, and it is the row quoted above.

## D32 seed-invariance — why nine candidates share one SD

Nine Stage B candidates report a paired SD of 0.002379%, matching the control's
own σ of 0.002380% to six figures. That looks like duplicated data and is not.

Verified from the receipts, not inferred: each of those nine reaches **the same
objective on all five seeds** — five identical values, own SD exactly 0.000000 —
while the control lands on four distinct objectives (SD 70.34 in objective
units). When the treatment arm has no seed variance of its own, the paired
difference inherits the control's variance exactly, so its SD *is* the control
σ. For contrast, candidates whose objective does vary with seed give distinct
SDs: `truncate-101#3d4f770cd393` (3 distinct objectives, SD 52.55),
`add_stop-008#f178c37040f5` (3 distinct, SD 109.99).

The nine are:
`add_stop-033#273b2cd43dfd`, `straighten-004#600ca164ad60`,
`extend-024#26db14321a47`, `reroute-006#dbfb2f9ee60d`,
`change_terminal-101-EMO4THW#56a30c84c920`, `reroute-023#1dc299b50907`,
`change_terminal-141-STAHIGW#b5ce9b1e03b5`, `straighten-021#110f4a755fe7`,
`reroute-009#8323c2fb0368`.

This is recorded so that a later reader who notices nine identical SDs
investigates the right thing. It is a property of those candidates' solve
landscape, not an artifact of the pipeline.

## What this section does not license

Effort-stability is **not** evidence that the effect is real in the world. It
says the number does not move when the solver looks harder, which rules out one
specific failure mode — the one that killed Experiment 2 — and rules out nothing
else. Model error, demand-model error, and the local-optimality limits stated in
D33 are all untouched by anything here.
