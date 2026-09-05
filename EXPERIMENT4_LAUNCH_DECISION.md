# Experiment 4 — launch decision

# NO-GO

**2026-09-05.** Readiness: **20 MET · 2 OPEN · 1 MANUAL** of 23.
Gates: **10 MET · 5 ARMED · 0 OPEN** of 15.

Experiment 4's production search is **not** started. Two readiness items are
open and one is unconfirmed, and they reduce to a single unmeasured quantity.

## What is open

| item | criterion | state |
|---|---|---|
| **D18** | The gap benchmark has been run on Experiment 4 networks, its four questions answered in order, and question 3's answer recorded — including the branch where it forbids discovery-effort comparison. | **OPEN — not run** |
| **C9** | Discovery path reuse benchmarked against exact rebuilds. | **OPEN — benchmarked, does not close** |
| **C15** | Every ACCEPTANCE.md rejection condition in place before scoring. | **MANUAL — unconfirmed** |

### They are one blocker, not three

D18 produces Experiment 4's **promotion band**. Gate 4-7 closes only when the
discovery approximation "identifies the exact leader within the promotion
band", and C9 tracks gate 4-7. So:

```
D18 not run  →  no promotion band  →  gate 4-7 cannot be adjudicated  →  C9 OPEN
```

C9 has one escape that does not need the band: if the approximation identified
the exact leader in **every** case with **zero** ranking inversions and an
**unchanged** promoted set, it would identify the leader within any band however
narrow. That was measured this session and it does not hold — 2 of 5 leaders,
120 of 600 ranking pairs inverted, promoted set changed in 4 of 5 cases.

C15 is a judgement, not a computation, and it stays unconfirmed by design. It
got harder this session rather than easier: **D35** showed a constraint can be
fully written, validated at construction, hashed into the state digest, and
still reach nothing that scores. "The machinery exists" is exactly the claim
C15 is supposed to doubt.

### D18 is not optional

EXPERIMENT4_DESIGN §3 is explicit: if the gap tracks network structure,
**Experiment 4 cannot compare networks at discovery effort at all**, and the
search must select on something else. D18 is therefore not a refinement of the
threshold — it is a precondition for the experiment having an admissible
comparison. Launching without it risks discovering, after the compute is spent,
that none of the comparisons were licensed.

## What closed this session

**D21b — the Gen1→Gen2 bridge.** One real Gen1 question (the optimal frequency
plan for an assembled Experiment 4 network under a pinned envelope, λ=2)
answered twice, the arms differing only in the solver.

| | Gen1 | Gen2 exact |
|---|---|---|
| objective | 3,645,587.5951 | 3,645,586.3245 |
| envelope used | 193.200 vh | 199.333 vh of 200.0 |
| seconds | 0.4 | 2,578.7 |

**SUPERSEDED.** Optimization gap **1.270619** absolute, **3.4854e-07** relative,
over 7,529,536 combinations (7,529,389 feasible), 2 of 6 headways differing.
Run twice, 43 minutes each, **byte-identical both times**.

Generation 1's heuristic did not find the exact optimum of its own frequency
subproblem, and left 6.1 vehicle-hours of the envelope unspent. Under the
generation scheme this supersedes rather than corrects: both answers are kept,
and every Gen1 receipt still carries the `code_version` it was produced under.

**D16 — the Experiment 4 contracts, in force.** 14/14 against the criterion's
own three clauses, executed independently and *not* closed by D21b closing. The
construction guard was fired for every declared dimension in turn.

The promotion dropped the draft's provisional `evaluations_performed` tolerance,
because that field had been reclassified OPPORTUNITY → OUTCOME on 2026-09-04 and
`compare()` walks only identity and opportunity — the entry had matched no field
since, and carrying it forward would have advertised effort protection that does
not exist. `compare_exp4` now **requires** both `AllowanceRecord`s by signature,
so there is no call that skips the effort check.

`ExperimentContract` and `ExecutionReceipt` were deliberately not given new
fields: the Gen1 freeze manifest asserts the Experiment 3 contract and receipt
digests and `admit()` refuses on a mismatch, so a field with a default would
have broken the freeze and every Experiment 3 receipt's admissibility. Verified —
all three contract digests and all 474 receipt digests unchanged.

## What was found this session

**D35 — `PINNED_OFF` was a label on the state digest, not a constraint on the
score.** `Exp4Selection.pinned_off` was validated at construction and hashed into
`state_digest`, then reached nothing: `assemble` recorded it in a report,
`score_exp4_network` never forwarded it, and `solve_on_network` forwarded it on
the `"exact"` branch alone. Two selections differing *only* in `pinned_off`
produced **identical fitness under different state digests** — and `state_digest`
is a declared treatment difference, so the firewall would have admitted the
comparison and reported a zero effect for a treatment that was never applied.

It was found by the master-path benchmark, whose `pinned_off` rows came back
byte-identical to its supernetwork rows in all five cases — and only because the
preregistered sample said to include a fate the subsets cannot express.

Fixed by pinning the **setup** above the solver switch, so it binds both
generations, with the result asserted on return. Free 3.642440e+06 vs pinned
3.644617e+06 — worse, which is the right direction. Equal before the fix.

**Gate 4-7's object was built, benchmarked, and does not close — for an
unexpected reason.** At survival fraction 1.000, where filtering is the identity,
the reuse arm *still* differs from the exact arm, and is **better** in 4 of 5
cases. The residual is enumeration richness, not filtering. That inverts the
gate's own remedy: widening the master makes it **more** different from the exact
arm, and 3× the scenarios plus 2× the per-OD cap changed the verdict not at all.

**Exhaustive enumeration is a one-line instrument.** Measured at 336.6 µs per
ladder combination: one line is 7.53e6 combinations and 42 minutes; two lines is
5.67e13 and roughly 600 years. Any gap benchmark on realistic networks must use a
reduced neighbourhood, as D33 did.

## Verification stack, all green

```
647 tests passed
exp3_verify_closure.py      ALL CLAIMS VERIFIED
exp3_freeze_integrity.py    ALL INTEGRITY CHECKS PASS   (zero firewall refusals)
gen1_freeze.py --verify     GEN1 VERIFIED
exp4_baseline.py --verify   BASELINE VERIFIED
exp4_equivalence.py         0.000e+00 on all seven FitnessVector fields
```

The last one is the load-bearing regression: the substrate is still bit-exact
against the legacy scoring path *after* `pinned_off` was made to bind and
`n_random_scenarios` / `max_paths_per_od` were threaded through the interface.

## The shortest path to GO

1. **Run D18's gap benchmark** on a stratified sample of Experiment 4 networks —
   high-branching, sparse, many-OFF, heavily overlapping — over a **reduced
   neighbourhood**, under the compute policy decided in
   `decisions/2026-09-05-d18-compute-policy.md`. Answer its four questions in
   order and record question 3's answer, including the branch that forbids
   discovery-effort comparison.
2. **Re-adjudicate gate 4-7** against the resulting band. If 5.7e-03 is inside
   it, C9 closes. If not, discovery pays for exact rebuilds — about 5.3× the
   measured cost — or the approximation is abandoned, which gate 4-7 already
   names as an acceptable outcome.
3. **Confirm C15 by review.** Not by a script.

Question 3 may return the answer that forbids discovery-effort comparison
outright. That possibility was written down before the search precisely so that
meeting it is not a crisis, and it remains the honest branch.

## Not done, deliberately

No production search was started. No methodology was redesigned. No acceptance
criterion was weakened — C9 was left tied to gate 4-7's closure when the looser
reading ("benchmarked" is satisfied once a benchmark exists) was available and
would have closed it. No crossover was claimed: Gen2 remains at 0.90× exhaustive
enumeration on the spaces tested, and the crossover is unmeasured. No MANUAL item
was converted to an automated MET.
