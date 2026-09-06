# Gate 4-7 — corrected to one factor, measured, and it does not close

**2026-09-05. Verdict: ARMED. The reason is now identified.**

The previous measurement was unidentified: it varied reuse and enumeration
richness together. The corrected design varies only reuse. Under it the
substrate is proved sound and the approximation is proved biased.

Amendment: `decisions/2026-09-05-gate-4-7-amendment.md`.
Instrument: `scripts/exp4_gate47.py`. Numbers: `outputs/exp4/gate47.json`.

## The correction, and the fact that forced it

At **survival fraction 1.000** the filter keeps every path and is therefore the
identity. The old benchmark still showed a difference there — and the reuse arm
was *better* in 4 of 5 cases. A difference that survives the identity
transformation was never caused by it.

Equalising the enumeration setting removes it exactly. On `large_gap`'s
supernetwork, the master enumerated at the exact-rebuild setting is
**byte-identical** to the independent rebuild, in all six periods, and the arms
agree at **0.000e+00** on all seven FitnessVector fields.

Across the full corrected run this holds everywhere: **10 survival-1.000
candidates, signed objective gap exactly `{0.0}`, all identical.** Filtering is
the identity, the remap is correct, and PINNED_OFF binds in both arms. **Zero
hard failures.**

So the substrate is sound. What remains is the approximation itself.

## Result — the original matrix, unchanged, one-factor

80 candidates over the five frozen deception spaces. No scenario, cap,
threshold, tolerance or sample composition was tuned.

| case | n | universe digest | surv-1.000 | leader | inversions | promoted | worst obj gap | min surv | median × |
|---|---|---|---|---|---|---|---|---|---|
| greedy_finds_nothing | 16 | `f004170af4470817` | 2/2 ✓ | **CHANGED** | 13/120 | changed | 2.653e-03 | 0.019 | 4.36 |
| large_gap | 16 | `daec48aa6c61130c` | 2/2 ✓ | preserved | 35/120 | preserved | 3.511e-03 | 0.019 | 5.51 |
| moderate_gap | 16 | `5c4791978f343039` | 2/2 ✓ | **CHANGED** | 35/120 | changed | 2.559e-03 | 0.101 | 5.55 |
| greedy_overbuilds | 16 | `403475a00ec83517` | 2/2 ✓ | preserved | 28/120 | changed | 1.750e-02 | 0.000 | 5.38 |
| weak_junction | 16 | `e743d3f702f2eeaf` | 2/2 ✓ | preserved | 29/120 | changed | 2.787e-03 | 0.019 | 5.15 |

**Exact leader preserved in 3 of 5. 140 of 600 ranking pairs inverted. Promoted
set preserved in 1 of 5.** Worst field relative difference 5.18; worst unserved
gap 533.0 trips. Median speedup ≈ 5×.

Gate 4-7 requires the exact leader preserved in **every** case. It is not.

## The smallest concrete reuse-induced discrepancy

`greedy_finds_nothing`, and it is as small and as clean as the defect gets.

| | network | true objective (FRESH) | scored under REUSE | error |
|---|---|---|---|---|
| exact leader | 3-line subset `#d73f3849068f` | **3,632,624.117** | 3,635,089.409 | **+2,465.29** |
| reuse leader | supernetwork, 4 lines `#1be3cd377edf` | 3,632,777.951 | 3,632,777.951 | **0.00** |

The two networks are nearly tied: the true margin is **153.83**, or 4.235e-05
relative. Reuse scores the supernetwork **exactly** — survival 1.000, error zero
— and penalises the 3-line subset by **2,465**, sixteen times the margin. The
leader flips.

The mechanism is visible in one line of path counts, `am_peak`:

```
master 323    reuse keeps 134    exact rebuild finds 139
```

**Five paths exist in the candidate that the supernetwork's enumeration never
proposed.** Not dropped by the filter — never enumerated. A route worth taking
only once the better lines are gone is dominated in the supernetwork and never
enters its top-k for that OD pair.

## The bias is systematic and directional

This is not noise, and it is the part that matters for Experiment 4.

| active lines | candidates | reuse scores it worse | median signed gap | median survival |
|---|---|---|---|---|
| 1 | 23 | 13/23 | **+267.24** | 0.135 |
| 2 | 39 | 24/39 | **+354.62** | 0.285 |
| 3 | 8 | 4/8 | **+256.99** | 0.675 |
| 4 | 4 | 0/4 | **0.00** | 1.000 |
| 5 | 6 | 0/6 | **0.00** | 1.000 |

The penalty is **exactly zero** where the candidate is the supernetwork and
grows as the candidate thins. Reuse therefore scores sparse networks worse than
they are, which means **it biases the search toward activating more lines** — a
directional bias on the very decision Experiment 4 exists to make.

The shortfall behind it, across 480 period-candidate observations:

* an exact rebuild finds more paths than the filtered master keeps in **62%** of
  them — median **26** paths missing, maximum **181**;
* in **12** observations the rebuild finds more paths than the master holds *in
  total* (worst **340 against 338**).

**The supernetwork master is not a superset of candidate paths.** That claim was
written into `exp4_masterpath.py` as the justification for the whole approach —
"contains, by construction, every ride any candidate network could offer" — and
it is false. The patterns are a subset; the *enumerated* paths are not. The
docstring has been corrected in place.

Raising `max_paths_per_od` does not reach these paths. The shortfall is
dominance in a different network, not truncation in this one.

## Widening is still not the remedy

The gate says "widened or abandoned". Widening was tried before the amendment —
3× scenarios, 2× per-OD cap — and moved nothing. It is now clear why: widening
changes the *enumeration*, which is the factor the amendment removed from the
comparison. Reintroducing it makes gate 4-7 unidentified again without touching
the reuse bias at all.

## Enumeration richness, as its own diagnostic

With reuse held **off** in both arms, changing only `n_random_scenarios` 0 → 6
across the same 80 candidates:

* **leader changes in 3 of 5 cases**
* **promoted set changes in 5 of 5**
* 67 of 600 ranking pairs inverted, worst objective gap 3.766e-03

So richness is a **first-order effect on the answer**, comparable in size to
reuse itself. Mixing the two was guaranteed to produce something uninterpretable.

This is informational and closes nothing, but it is not a small finding: the
production enumeration setting materially changes which network wins. That is
gate 4-9's subject (path-model adequacy), and it makes the choice of
`n_random_scenarios` a live methodological decision rather than an inherited
default. `outputs/exp4/enumeration_richness.json`.

## Where that leaves Experiment 4

Gate 4-7 stays **ARMED**, no longer for want of an object or a band. The options
the gate itself names:

1. **Abandon reuse for discovery** and pay for exact rebuilds — the conservative
   branch gate 4-7 already permits, at roughly 5× the discovery cost measured
   here.
2. **Repair the master** so it is a genuine superset: enumerate on the
   supernetwork *and* on structured sub-networks, so paths that only become
   attractive once lines are absent are proposed at least once. Untested, and it
   is a design change, not a parameter.
3. **Change what discovery selects on** — rank stability across efforts, or
   certification of a wider frontier — which §3 already names as the branch to
   take if discovery-effort comparison is not licensed.

None is chosen here. What is settled is that the choice can no longer be made by
tuning a benchmark parameter, because the benchmark now measures one thing.

**Not done:** D18 not started, C9 not closed, nothing promoted, no Experiment 4
search. All freezes, tags, firewalls and integrity checks intact.

---

# Disposal — 2026-09-06

Gate 4-7 is not closed by proving master-path reuse unbiased. **It is not
unbiased.** This document measured the bias and D18 found the same shape in the
frequency solver. No further measurement is going to unfind either.

It is closed by making the approximation **non-operative for inference**.

## What changed

The Experiment 4 execution contract is now:

> **Gen2 discovery → permissive deterministic promotion → `solve_exact`
> certification → exact-only conclusions.**

Under it:

* **reuse is permitted**, in proposal-only discovery, where speed is the whole
  point;
* **reuse output cannot determine any conclusion.** A discovery objective is a
  `ProposalScore`, which refuses comparison, ordering, float conversion and
  formatting. Its one accessor is `for_promotion_only()`. A future one-line
  `sorted(candidates, key=discovery_score)` raises instead of silently
  producing a wrong answer;
* **every promoted candidate is rebuilt and exact-certified** by
  `exp4_certify.certify`, which takes no `pathset_cache` parameter at all — the
  biased shortcut cannot reach a certified number because there is no argument
  through which to pass it.

## The bias is contained, not absent

Stated plainly so nobody later reads this gate as a clean bill of health:

| finding | status |
|---|---|
| master-path reuse penalises sparse networks (median +267/+355/+257 at 1/2/3 active lines, exactly 0.00 at survival 1.000) | **real, measured, unchanged** |
| the supernetwork master is not a superset of candidate paths (exact rebuild finds more paths in 62% of 480 observations) | **real, measured, unchanged** |
| D18: the frequency heuristic's gap tracks structure (ratio 1.283) | **real, measured, unchanged** |
| any of the above can reach an Experiment 4 conclusion | **no — blocked by the proposal/certification boundary** |

## The risk that remains, and it is a different kind

Containment converts an **inferential** risk into a **recall** risk. Reuse can
no longer make a wrong network look good, because certification re-scores it.
What it can still do is fail to *propose* a good network at all — and a
candidate discovery never proposes is one certification never sees.

That is what C9 now measures, and it is why C9 was redefined from "identify the
exact leader inside the D18 promotion band" (a test that cannot exist, since
D18 emitted no band) to:

> **Can proposal-only discovery discard a candidate that exact certification
> would have selected?**

Agreement between discovery scores and certified scores is explicitly **not**
the criterion. D18 established they diverge structurally, and the architecture
is built on the assumption that they always will.

## Why certification is admissible where discovery is not

Because its quality does not depend on the treatment dimension. Measured:

| | sparse | dense | spread |
|---|---|---|---|
| D18: Gen1 delivered gap | +0.373% | +0.165% | **0.208 pp** |
| certification improvement over Gen1 | +1.166% | +1.183% | **0.018 pp** |

Certification compresses the structure-correlated component by more than an
order of magnitude. That is the empirical claim the architecture rests on, and
it is measured rather than argued.

**The residual is stated, not hidden.** Certification establishes
(8,3)-block-local optimality — no block of 8 route-periods moved within 3 rungs
improves it — not global optimality. The distance from that fixed point to the
global optimum is unmeasured. It is strictly smaller than the gap D18 measured,
because the certified plan is at least as good as the delivered one by
construction, but "smaller than a forbidden quantity" is not "zero" and no
Experiment 4 conclusion may pretend otherwise.
