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
