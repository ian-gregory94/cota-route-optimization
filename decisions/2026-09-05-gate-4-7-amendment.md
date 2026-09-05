# Gate 4-7 — preregistration amendment: the comparison was unidentified

**2026-09-05. Amends ACCEPTANCE.md gate 4-7 and EXPERIMENT4_CONTRACT.md §12.**
**Narrows the gate's decisive comparison to one factor. Weakens nothing.**

## The frozen wording, verbatim

ACCEPTANCE.md:

> **Gate 4-7 — the discovery approximation is benchmarked, and buys no
> conclusions.** Discovery may score networks against a frozen supernetwork
> master path set rather than rebuilding paths per state […] On a preregistered
> sample the approximation is compared against exact rebuilds for objective gap,
> unserved gap, ranking stability, omitted and improvable flow, and whether the
> promoted set changes; if it cannot identify the exact leader within the
> promotion band, it is widened or abandoned. **Every promoted network is
> rebuilt exactly.**

EXPERIMENT4_CONTRACT.md §12 adds the master's construction:

> build a **supernetwork** containing all candidate lines and enumerate a rich
> **master path set** under multiple service/frequency scenarios.

## Why an amendment was required

The original design specifies **two** things that differ between the arms:

1. the REUSE arm filters a shared master instead of rebuilding paths — the
   factor the gate is about; and
2. the master is enumerated "under multiple service/frequency scenarios", while
   the exact rebuild enumerates at the production setting `solve_on_network` has
   always used (`n_random_scenarios=0`).

So the arms differ in **reuse and enumeration richness together**, and no
measurement made under that design can attribute an observed difference to
either one. This is not a hypothetical objection. It was demonstrated:

**At survival fraction 1.000 — where the filter keeps every path and is
therefore the identity — the two arms still differed, and the REUSE arm was
*better* in 4 of 5 cases** (`outputs/exp4/masterpath_benchmark.json`). A
difference that survives the identity transformation cannot have been caused by
that transformation.

It also explains why the gate's own prescribed remedy failed. The gate says the
approximation is "widened or abandoned"; widening was tried first, 3× on
scenarios and 2× on the per-OD cap, and it changed the verdict not at all — same
leader missed, same inversions, same worst field difference to four digits.
Widening makes the master **more** different from the exact arm, so it moves the
confound rather than the approximation.

Equalising the enumeration setting removes the second factor completely.
Measured on `large_gap`'s supernetwork before the corrected benchmark was
written: the master enumerated at the exact-rebuild setting is **byte-identical**
to the independent enumeration for that network, survival is 1.000 in all six
periods, and all seven FitnessVector fields agree at **0.000e+00**.

## The amendment

Gate 4-7's decisive comparison is narrowed to **one factor**:

1. **One canonical candidate universe per case**, built once from the
   preregistered sample rule before either arm exists, canonicalised,
   deterministically ordered, and digested. Both arms receive exactly that
   tuple; the digest, the count and the ordered ids are asserted equal before
   any candidate is scored.
2. **Admission is arm-independent.** A candidate enters the universe iff it
   **assembles** — a property of the selection and the pool involving no
   scoring, no enumeration and no evaluator. A candidate that assembles and then
   fails to score in one arm only is recorded as a discrepancy, never skipped.
3. **Both arms enumerate under identical settings**, fixed as module constants
   rather than options, and set to what the exact-rebuild path uses in
   production — because "exact rebuild" is what certification runs, and
   discovery must agree with certification rather than with a comparator
   invented for the benchmark.
4. **The arms differ only in reuse.** REUSE filters the frozen supernetwork
   master onto the candidate's own route-period vector. FRESH rebuilds the
   candidate's paths, RAPTOR network, zone system, route classes, model, ladders
   and envelope. **FRESH does not enumerate its own candidate universe** — that
   was the confound.
5. **Route-period keys are derived from the assembled network**, not read out of
   either arm's path sets, so neither arm's enumeration defines the other's
   input. The derivation is asserted against the evaluator's own `rp_keys` on
   every candidate.
6. **Survival = 1.000 must be exactly the identity**, checked before anything
   else. With one universe and no filtering there is nothing left for reuse to
   approximate, so a difference there is a reuse/state-reconstruction **defect**
   to be debugged, not approximation error to be reported as a gap.
7. **Enumeration richness moves to its own diagnostic**
   (`scripts/exp4_enumeration_richness.py`), with reuse held OFF in both arms.
   It is informational. It has no gate and cannot close one. A large effect
   there is a finding about the **path model** — gate 4-9's subject — not about
   reuse.

**Closure is unchanged in strictness and stated explicitly**: reuse must
preserve the **exact leader in every case**, with **zero ranking inversions**
and an **unchanged promoted set**. "Same leader most of the time" does not
close it and neither does the existence of a benchmark.

One thing the amendment gives back: because a leader reproduced *exactly* is
reproduced within any promotion band however narrow, this closure is
**band-independent**. Gate 4-7 no longer waits on D18 — and borrows nothing from
it either.

## What is NOT amended

* No tolerance is loosened. The corrected design is **stricter**: it adds the
  survival-1.000 identity requirement, the universe-digest assertion, the
  asymmetric-failure check and the pinned-off check, none of which existed.
* The preregistered sample is unchanged — the same five frozen deception spaces,
  the same rule, the same cardinality bounds, the same cap.
* "Every promoted network is rebuilt exactly" stands untouched.
* The original measurements are **preserved, not deleted**:
  `scripts/exp4_masterpath_benchmark.py` and
  `outputs/exp4/masterpath_benchmark.json` remain, marked superseded. They are
  the evidence that the amendment was necessary, and a superseded artifact looks
  entirely legitimate from the inside — which is exactly why this project keeps
  them.

## Consequence for §12's "rich master"

§12 requires the master to be enumerated "under multiple service/frequency
scenarios". Under this amendment the decisive comparison holds enumeration equal
at the exact-rebuild setting, so a production master built richer than
certification's rebuild would **reintroduce the confound in production**, not
just in the benchmark: discovery and certification would then disagree for two
reasons at once, and gate 4-7 would be unidentifiable again on live results.

So either the production master is enumerated at certification's setting, or
certification's setting is raised to match the master and the change is gated on
its own evidence. **That choice is not made here.** It is recorded as an open
methodological question for whoever sets the production enumeration policy, with
the richness diagnostic as its input.

## Result under the corrected design

Gate 4-7 **does not close**, and now for an identified reason. Detail in
`EXPERIMENT4_GATE47.md`; the numbers are in `outputs/exp4/gate47.json`.
