# Experiment 5 — premise audit

**Written 2026-09-21, before any Experiment 5 compute. Nothing was launched.**
Commissioned by Ian to determine whether the unresolved fleet / deadhead /
terminal inputs invalidate or materially distort the proposed resource
frontier. Read against the live repo at `81a0cad3`; the stale
`source\repos` clone was not used.

## STATUS: `EXP5_REFRAME_REQUIRED`

The resource frontier is meaningful only after the fleet axis is replaced by a
measurable quantity **and** the level grid is moved into a range where anything
binds. Three independent defects, any one of which alone would be sufficient:

1. **The fleet axis cannot be measured.** All 200 Exp 4 candidates return
   `UNDECIDABLE`, and 200 of 200 have a fleet bracket that contains the *entire*
   Exp 5 fleet-cap grid. The axis carries zero discriminating information (§3).
2. **No cell binds.** Every certified candidate spends 36–37% of the hours cap
   and 44–46% of the fleet-proxy cap. Zero of 200 plans exceed even the
   tightest 0.75× level, so all sixteen cells would return the same
   unconstrained optimum (§6).
3. **The only path that could apply the fleet cap measures it with the proxy
   `contract.py` refuses by name** (§8, D5-C).

Had the recommendation been to keep fleet on the axis, the status would be
`EXP5_BLOCKED`: the fleet dimension is not merely imprecise, it is
feasibility-changing and candidate-specific. What makes this a reframe rather
than a block is that the second resource is already carried as a first-class
object and is exactly computable.

---

## 1. What resource does Exp 5 actually constrain?

**Two, declared as such in the `exp5_resource` module docstring:**

| axis | quantity | type | source |
|---|---|---|---|
| hours | scheduled weekday **revenue vehicle-hours**, 2517.183333 | continuous, unrounded | `outputs/CANONICAL_ENVELOPE.json` → `weekday_revenue_vehicle_hours` |
| fleet | **block-derived peak vehicles, per period** — early 135 · am_peak 187 · midday 173 · pm_peak 197 · evening 178 · owl 149 | integral, `floor` on scaling | same artifact → `peak_vehicles_by_period` |

Traced:

* `exp5_resource.load_canonical()` reads the artifact and nothing else, and
  refuses to exist without it. It does not recompute the constants — "a second
  computation is a second opinion."
* `ResourceEnvelope.__post_init__` enforces the semantics: `fleet_semantics`
  must be `"block_derived_peak_vehicles"`, `fleet_rounding` must be `"floor"`,
  and `fleet_by_period` must be a mapping of **at least two** integer entries —
  a one-entry dict is rejected by name as "a scalar cap in a dict costume."
* `ResourceEnvelope.scale()` gives `hours * m` exactly and
  `floor(m * canonical_p)` per period.
* `stage_a_grid` (diagonal, 6 cells) and `stage_b_grid` (hours axis + fleet
  axis, 10 cells) at `LEVELS = (0.75, 0.90, 1.00, 1.10, 1.25, 1.50)`.
* `ResourceEnvelope.feasible(hours_used, fleet_used_by_period)` decides on
  **both** dimensions, and all six fleet periods independently; a missing
  period is a failure, not a pass.
* `Exp5Feasibility.__post_init__` refuses a verdict whose `fleet_source` does
  not begin with `"block"`, so that concurrency is carried in
  `concurrency_diagnostic` where it cannot move the boolean.

**The distinctions the module already makes correctly.** `REJECTED_AS_CAP`
names six quantities that are not the cap, including
`FitnessVector.peak_vehicles` (peak *concurrency*, 176.49 on the baseline
against the block-derived 197), `routewise_peak` (150.73), the NTD VOMS figure
of 198, any scalar cap, and — explicitly — the 1.307 interlining ratio, which
is "evidence of proxy error, not an exchange rate." None of this audit's
findings is about the caps. **The caps are sound. The problem is the usage
side.**

## 2. Can the current data/model compute that resource?

**Hours: yes, exactly.** Vehicle-hours is a property of the timetable and not
of the blocking. `outputs/exp4/blocking_validation.json` records
`production_feasibility/vehicle_hours/matching_independent = true`, and
`ProductionFeasibility`'s docstring says the same: "that arm is decidable
outright." Every one of the 200 Exp 4 certified records carries
`fitness_EXACT.revenue_veh_hours`.

**Fleet: no.** The quantity `ResourceEnvelope.feasible()` needs —
`fleet_used_by_period` for a *candidate* network — is the one the project has
already measured as not well-posed.

| input | state | where |
|---|---|---|
| deadhead travel time between terminals | **OPEN**, no defensible source | `FLEET_AND_BLOCKING.md`; `DeadheadOracle.time_sec` **raises** rather than returning zero |
| terminal identity | **degenerate on candidates** — `parent_station` empty in all 2,949 stop rows; 83.3% of candidate trips end at a terminal that is never any trip's origin | `exp4_blocking.terminal_identity()`; `TERMINAL_IDENTITY_PROVENANCE` |
| trip-to-trip compatibility | defined and frozen (`ConnectionRule`, `min_layover_sec=300`), but **needs the deadhead it does not have**; an unknown connection is infeasible, not free | `ConnectionRule.feasible()` |
| block construction | minimum path cover via Hopcroft–Karp; `minimum_blocks = n_trips − maximum_matching` | `block_candidate_schedule()` |
| minimum-block count | **graph invariant, usable** | `CandidateBlockResult.minimum_blocks` |
| per-period fleet from the blocking | **NOT invariant** — the concurrency of one maximum matching among many of equal size | `CandidateBlockResult.payload()["CERTIFICATION"]` |
| per-period invariant lower bound | usable, but **refutation-only** | `period_lower_bounds()` |
| interlining | not assumed; the solver builds chains from the connection rule, and the 1.307 factor is forbidden as a conversion | `REJECTED_AS_CAP["concurrency_times_interlining_factor"]` |

**Merely imprecise vs. able to make an infeasible candidate look feasible.**

*Imprecise:* the 300 s minimum layover; the 0.51% disagreement between the
block-derived 197 and NTD's VOMS 198; the 7 published transitions that sit
under the 300 s assumption.

*Feasibility-masking:* the per-period fleet figure. It is not noise around a
true value — it is a different number depending on the order of a list, and
`ProductionFeasibility` exists precisely to refuse it. Measured on the real
weekday baseline, from `outputs/exp4/blocking_validation.json` `test_b`, two
**equally maximum** matchings (`minimum_blocks = 212` for both):

| period | matching A | matching B | swing | invariant LB | envelope cap |
|---|---|---|---|---|---|
| am_peak | 195 | 210 | **15** | 165 | 187 |
| midday | 199 | 210 | 11 | 162 | 173 |
| pm_peak | 202 | 209 | 7 | 180 | 197 |
| evening | 192 | 196 | 4 | 162 | 178 |
| owl | 176 | 180 | 4 | 131 | 149 |
| early | 133 | 137 | 4 | 119 | 135 |

Note what this does against the Exp 5 grid. The step between adjacent resource
levels at `early` is 13 vehicles (0.90×→1.00×: 121→135) and at `owl` is 14
(134→149). **A 15-vehicle swing that depends on list order is larger than a
whole resource level.** At am_peak the 1.00×→1.10× step is 18, so the swing is
83% of a level. The fleet axis cannot distinguish adjacent cells on the
baseline, where the data is at its best.

## 3. Could these unresolved issues change candidate ordering?

First, a scoping point that changes what "ordering" means here. **Experiment 5
does not rank candidate networks against each other.** `exp5_frontier.
treatment_isolation()` requires a single `network_digest` across all cells and
fails the run if topology, evaluator or seed differ. Exp 5 fixes one topology
and varies the envelope; what is compared is the certified objective **across
resource cells**. So the ordering at risk is the frontier's own shape.

### Classification

| unresolved assumption | class | evidence |
|---|---|---|
| **per-period fleet from a maximum matching** | **feasibility-changing** | swings up to 15 vehicles between equally-maximum matchings; exceeds a full resource level at `early` and `owl`. A plan's admissibility at a cell would be a property of list order |
| **deadhead provenance OPEN** | **feasibility-changing**, and **local distortion** on top | bracket widths across the 200 Exp 4 candidates run **253 to 411 vehicles**, a 1.62× ratio with stdev 20.8 — not a common shift |
| **terminal identity degeneracy (D24)** | **feasibility-changing**, candidate-specific | it drives the upper bound: `pearson(n_trips, upper) = +0.80` while `pearson(n_trips, lower) = −0.09`. Residual spread at *fixed* trip count is still 13–48 vehicles, so trip count does not explain it away |
| 300 s minimum layover | **common-mode shift** | one constant applied identically to every trip pair in every candidate |
| NTD VOMS 198 vs block-derived 197 | **common-mode shift** | 0.51%, applies to the cap, identical across cells |
| interlining behaviour | **unknown** | not assumed anywhere; the 1.307 factor is forbidden as a conversion and nothing substitutes for it |
| hours accounting | **not an issue** | matching-independent by construction |

### The measurement that settles it

Computed from the frozen `outputs/exp4/run/status.json` (read only; nothing
under `outputs/exp4/` was modified), over all 200 certified candidates, every
one of which returned `UNDECIDABLE`:

```
fleet bracket lower   min  65   median  71   max  76
fleet bracket upper   min 325   median 374   max 478
bracket WIDTH         min 253   median 303   max 411
```

The Exp 5 fleet-cap grid spans **101 … 295** vehicles across all six periods
and all six levels.

> **200 of 200 candidates (100.0%) have a fleet bracket that contains the
> entire Exp 5 fleet-cap grid.** The same holds for the pm_peak axis alone
> (147 … 295).

Every cell on the fleet axis is simultaneously possibly-feasible and
possibly-infeasible for every candidate. The axis carries **zero** discriminating
information. This is not a tolerance problem that a tighter bound would fix at
the margin; the bracket is wider than the experiment.

The leader makes it sharpest: `...ecb2ffc4bcce`, 476 trips, bracket
**71 ≤ fleet ≤ 373** — a width of 302 on a range the whole experiment spans in
194.

## 4. Is there a defensible substitute resource?

**Yes: revenue vehicle-hours, which Exp 5 already carries as a first-class,
exactly computable axis.** It needs no deadhead, no terminal identity and no
blocking. `ResourceEnvelope` holds it unrounded and continuous, and
`FitnessVector.revenue_veh_hours` supplies the usage side exactly.

Two further quantities are usable but must not be called fleet:

* **`minimum_blocks`** (`CandidateBlockResult.minimum_blocks`) — a graph
  invariant, identical under any maximum matching, comparable against the
  baseline measured with the same instrument. It is a **path-cover count**,
  which is why `FLEET_KINDS` separates `CANDIDATE_BLOCK_BOUND` from
  `PUBLISHED_BLOCK_PEAK`. It answers "does this candidate need more or fewer
  blocks than the baseline under the same connection model", not "how many
  buses".
* **`period_lower_bounds()`** — matching-independent per period, so it can
  **refute** a candidate and never approve one. Retaining it as a refutation-only
  screen costs nothing and preserves the one fleet-ish claim that is sound.

**Rejected as substitutes.** `FitnessVector.peak_vehicles` and `peak_by_period`
are peak concurrency, already in `REJECTED_AS_CAP`, and `contract.py` refuses to
compare concurrency against a block-derived budget on the grounds that doing so
"would pass every plan while appearing to check something." "Peak scheduled
buses under an explicit zero-deadhead assumption" is the existing
`ZeroDeadheadRelaxation`, whose own `provenance()` marks it `is_bound_only` and
whose verdicts `provenance_is_certification_grade()` refuses — it lets a bus
cross the city in zero seconds. It may bound, label it as such, and it may never
be the axis.

**Under no naming may the reframed axis be called "fleet."**

## 5. Can conservative bounds rescue Exp 5?

**No, not on the fleet axis.** The bounding logic already exists and is already
applied — `CandidateFleetBound`, the two bracket oracles, the Dilworth
cross-check that independently confirms the lower end. The bounds are not weak
for want of effort; they are as tight as a missing input permits, and they are
still wider than the whole experiment for 100% of candidates.

The "robust ordering" rescue does not apply, for two reasons:

1. **Exp 5 does not order candidates.** One topology, sixteen cells. There is no
   A-versus-B comparison for a both-ends-agree argument to stabilise.
2. **Where the argument would apply — does cell *i* admit the plan that cell
   *j* admits? — the ends do not agree.** Optimistic (71) admits every cell;
   pessimistic (373) admits none. That is the maximum possible disagreement.

**Bounds are not needed on the hours axis**, which is exact.

## 6. A second defect, independent of fleet: nothing binds

This was not in the brief and it is at least as serious.

Computed over all 200 Exp 4 certified records:

```
revenue_veh_hours   min 910.15   median 923.99   max 939.65
                    = 36.16% .. 37.33% of the 2517.183333 cap

peak_vehicles proxy min  87.43   median  88.75   max  90.22
                    = 44.38% .. 45.80% of the 197 pm_peak cap
```

Against the preregistered levels:

| level | hours cap | certified plans exceeding it |
|---|---|---|
| 0.75× | 1887.888 | **0 of 200** |
| 0.90× | 2265.465 | **0 of 200** |
| 1.00× | 2517.183 | **0 of 200** |
| 1.10× | 2768.902 | **0 of 200** |
| 1.25× | 3146.479 | **0 of 200** |
| 1.50× | 3775.775 | **0 of 200** |

**No Exp 5 cell binds on any Exp 4 candidate, including the tightest.** A
frontier whose constraint never binds returns the same unconstrained optimum in
every cell. Monotonicity (E5-5) would pass trivially, traversal invariance
(E5-7) would pass trivially, the marginals (§12) would all be zero, and the
structural-response matrix (§14) would be empty — sixteen certified cells
reporting that nothing changed, at full certification cost each.

**The hours axis would need levels below ≈0.37× to bind at all.** The grid
bottoms out at 0.75×, twice as loose as the binding threshold.

**Why the optimum spends so little is an open question and this audit does not
answer it.** The leader `...ecb2ffc4bcce` has **315 of 390 route-periods OFF
(80.8%)** and spends 36.66% of the hours cap; across all 200 the OFF share runs
78.5% to 86.9%. Two explanations are consistent with the evidence and they have
different consequences:

* the λ=2 objective genuinely prefers that little service, in which case the
  levels simply need to move down; or
* the block-local neighbourhood cannot reach denser plans — the certified
  guarantee reads *"no block of 8 route-periods moved within 3 ladder rungs of
  the certified plan improves the objective"*, and lifting a route from OFF to a
  useful headway may exceed 3 rungs — in which case the unspent budget is a
  property of the search, and a resource frontier built on it would be measuring
  the optimizer rather than the network.

**Separating those two is a prerequisite for Exp 5, and it is cheap**: evaluate
the leader's plan with a handful of OFF route-periods forced on at each rung and
see whether the objective improves. If it does, the search is the constraint,
not the resource.

## 7. The D38 gate for Exp 5

**As currently specified, Exp 5 uses no approximate score to propose or order
anything.** `exp5_frontier.CellResult.objective` is documented as an EXACT-stage
value, the sixteen cells are enumerated exhaustively rather than selected, and
the `ProposalScore` / `objective_APPROXIMATE` machinery lives in
`exp4_inference.py` and `exp4_promotion.py`, neither of which `exp5_*` imports.
`grep` confirms the only non-test reference to `exp5` outside its own modules is
an unrelated `"exp5_matrix"` experiment name in `scripts/run_matrix.py`.

So D38's failure mode does not arise today. It would arise the moment a search
or selection stage is added, and the guard should be preregistered now.

### The gate, to be run before any expensive Exp 5 ranking

1. **Generate and freeze** the Exp 5 candidate pool (whatever a "candidate"
   becomes — a frequency plan within the fixed topology, or a cell-local warm
   start), with a recorded seed and digest, before any exact compute.
2. **Compute only the cheap score** across the whole frozen pool.
3. **Report**, for that score: absolute range, relative range
   `(max−min)/min`, standard deviation, stdev as a percentage of the mean,
   and the count of distinct values at 6 dp (quantization and ties).
4. **Compare** the score's relative range against the relative range of the
   *exact* objective on any set where both are known.
5. **Decision rule.** If the cheap score's relative range is **smaller than the
   exact objective's relative range on a comparable set**, it is not a usable
   ranker. Do not rank on it. Switch to stratified or uniform random sampling of
   the frozen pool, or redesign the surrogate, and say which.
6. **Never** spend exact compute to discover after the fact whether a ranking
   signal existed. That is what Exp 4 did, and the audit that had to follow cost
   seven days.

### The gate run now, on the surrogate Exp 5 would be tempted to use

`FitnessVector.peak_vehicles` is the obvious cheap stand-in for fleet. Across
the 200 Exp 4 certified candidates:

```
peak_vehicles   absolute range  87.4327 .. 90.2185  (2.7858 wide)
                relative range  3.1862%
                stdev           0.6624  (0.7463% of mean)
                distinct at 6dp 198 of 200

objective_EXACT relative range  2.2788%   (same 200 candidates)
```

**It passes the variance test** — 3.19% of spread against the exact objective's
2.29%, a ratio of 1.40×. Contrast the discovery score that D38 condemned: 0.159%
against 2.2788%, a ratio of 0.07×.

**And it is still the wrong quantity.** This is the point worth carrying: **the
D38 gate is necessary, not sufficient.** A surrogate can carry ample variance
and still measure something other than what the constraint is about.
`peak_vehicles` is peak concurrency; it reads 176.49 where the block-derived
figure reads 197 on the identical baseline at the identical period. Passing a
variance gate does not earn it the axis, and `REJECTED_AS_CAP` still governs.

## 8. Two discrepancies found during the audit, documented and not patched

Per instruction, recorded rather than silently fixed. Neither changes this
audit's conclusion.

### D5-A — the code overstates the measured matching instability

`src/cota_opt/exp4_blocking.py:821`, in `ProductionFeasibility`'s docstring:

> "reversing the adjacency order produces a different maximum matching of the
> same size whose per-period concurrency **differs by up to 26 vehicles** on the
> real baseline"

The validation artifact it rests on, `outputs/exp4/blocking_validation.json`
`test_b`, gives a maximum per-period swing of **15** (am_peak 195 → 210). No
period reaches 26. `FLEET_AND_BLOCKING.md` states 15, which is right, though its
parenthetical example "midday 199 → 210" is a swing of 11 rather than 15.

Direction: the code is **more** conservative than the evidence, so the
`UNDECIDABLE` verdict it produces is not undermined. The number is still wrong
and a reader checking it against the artifact will not reconcile it.

### D5-B — the `Exp5Feasibility` fleet-source guard does not test the property that matters

`src/cota_opt/exp5_resource.py:345`:

```python
if not self.fleet_source.startswith("block"):
    raise ResourceError(...)
```

The guard keeps concurrency out, which is what it was written for. It does not
separate a **matching-independent** instrument from a **matching-dependent**
one, and every candidate-side fleet instrument in the project begins with
`"block"`:

* `"blocks.reconstruct"` — the value the test suite actually uses
  (`tests/test_exp5_resource.py:120`). It reads `block_id` off real trips and
  therefore **cannot measure a candidate network at all**;
  `FLEET_AND_BLOCKING.md` says so in as many words. It is also the one string
  `CandidateBlockResult` refuses for itself: "Deliberately NOT named a
  reconstruction."
* `"block_candidate_schedule"` — would pass, and supplies precisely the
  per-period figure that `CandidateBlockResult.payload()["CERTIFICATION"]`
  says "is NOT invariant; it is a diagnostic and may not decide feasibility."

So the one Exp 5 feasibility construction exercised anywhere in the repo is
built on a fleet source that cannot measure the thing it is being asked about,
and the guard passes it. Since `Exp5Feasibility` has **no production caller** —
tests only — nothing has been decided wrongly. It would be, on first use.

The fix is not a longer prefix. The guard should require a declared
matching-independence property carried by the instrument, the way
`provenance_is_certification_grade()` already interrogates
`deadhead_provenance` rather than trusting a name. **Not implemented here**, per
instruction.

### D5-C — the only code path that would apply Exp 5's fleet cap compares the quantity `contract.py` refuses by name

**This is the most consequential of the three and it is the reason the fleet
axis cannot simply be wired up.**

Experiment 5's treatment *is* the resource cap, and the cap can only reach a
frequency plan through the optimizer. That path is
`src/cota_opt/frequency.py:374`:

```python
def _feasible(model, fit, budget) -> bool:
    if fit.revenue_veh_hours > budget.vh_cap() * (1.0 + _EPS_REL):
        return False
    for p, v in fit.peak_by_period.items():
        if p in budget.peak_vehicles_by_period:
            if v > budget.peak_cap(p) * (1.0 + _EPS_REL):
                return False
    return True
```

`fit.peak_by_period` is summed from `FrequencyModel.peak_vehicles()`
(`frequency.py:280`):

```python
cycle = 2.0 * svc.runtime_min * (1.0 + self.layover)
return cycle / headway
```

That is the cycle-over-headway sum — `routewise_peak` by construction, which
`exp5_resource.REJECTED_AS_CAP` lists at **150.73** and
`FLEET_AND_BLOCKING.md` calls "the same proxy before interlining." It is a
third proxy, further from the block-derived 197 than the 176.49 concurrency
figure is.

`src/cota_opt/contract.py:451–465` refuses exactly this comparison, in these
words:

> "Comparing concurrency to a block-derived budget would pass every plan while
> appearing to check something, so the check records that it did **NOT RUN**
> rather than running wrong."

So the repository contains both behaviours: the certification gate refuses the
comparison and records that it declined; the search filter performs it.

**This is not a bug in `_feasible`.** `ResourceBudget` (`frequency.py:63`) is a
plain `dict[str, float]` with no declared semantics, and a loose search filter
is a defensible thing for a search to have — `HANDOFF.md:303` says so
outright: *"The optimizer's fleet constraint is loose."*

**It is fatal for Experiment 5 specifically**, because there the cap is not a
filter around the treatment, it *is* the treatment. Wiring the canonical
block-derived envelope into `ResourceBudget.peak_vehicles_by_period` would
administer the treatment through a 24%-optimistic instrument, and the guarded
type would be laundered into the unguarded one on the way:

```
ResourceEnvelope.fleet_by_period      guarded: block_derived_peak_vehicles, int
        |   no conversion guard exists at this boundary
        v
ResourceBudget.peak_vehicles_by_period  unguarded: dict[str, float]
        |
        v
compared against FitnessVector.peak_by_period  = Σ cycle/headway
```

`ResourceEnvelope.__post_init__` and `Exp5Feasibility.__post_init__` both police
semantics carefully, and neither sits on this edge. **Not implemented here**,
per instruction — but no Exp 5 fleet axis may be built until a guard does.

And the measured consequence, from §6: the proxy reads **87.43–90.22** across
the 200 certified candidates against fleet caps of **101–295**. Even run with
the wrong instrument, the constraint would never bind. The treatment would be
inert *and* mismeasured.

## 9. Answers, in one line each

1. **Resource:** revenue vehicle-hours (continuous) **and** block-derived peak
   vehicles per period (integral), both read only from
   `outputs/CANONICAL_ENVELOPE.json`, digest `b6c647d3766338a6`.
2. **Computable?** Hours yes, exactly. **True fleet, no** — for any candidate
   network, and the code already says so with `UNDECIDABLE`. Worse, the only
   path that could apply a fleet cap to a plan (`frequency._feasible`) measures
   it with the cycle-over-headway proxy — see D5-C.
3. **Ordering/feasibility:** per-period matching fleet, deadhead provenance and
   terminal degeneracy are all **feasibility-changing**, and the last two are
   **candidate-specific** (bracket widths 253–411, 1.62× ratio). Layover and the
   VOMS disagreement are common-mode and harmless.
4. **Substitute:** **revenue vehicle-hours.** `minimum_blocks` as a comparative
   graph invariant, and `period_lower_bounds` as a refutation-only screen.
   Neither may be labelled fleet.
5. **Bounds:** cannot rescue the fleet axis — 100% of candidate brackets contain
   the entire grid, and the two ends give opposite answers at every cell.
6. **Status:** **`EXP5_REFRAME_REQUIRED`**.

## 10. What a reframed Experiment 5 would need

Not a design, a precondition list.

1. **Drop fleet from the axis.** Single-resource frontier on revenue
   vehicle-hours. Keep `period_lower_bounds` as a refutation-only screen and
   report every candidate's `CANDIDATE_BLOCK_BOUND` bracket alongside, labelled
   as the bracket it is. Concretely: pass `peak_vehicles_by_period={}` to
   `ResourceBudget` so the fleet arm of `_feasible` is provably inert, rather
   than leaving a loose proxy check that looks like a constraint.
   If the fleet axis is ever restored, a conversion guard on the
   `ResourceEnvelope` → `ResourceBudget` boundary is a precondition (D5-C).
2. **Re-choose the levels so something binds.** The current grid bottoms at
   0.75× and the binding threshold is ≈0.37×. Levels must be set from the
   measured consumption of the actual Exp 5 network, not from COTA's envelope,
   or the frontier is flat by construction.
3. **Settle why 80.8% of route-periods are OFF** before spending certification
   on sixteen cells. Cheap test in §6. If the search cannot spend the budget,
   the frontier measures the optimizer.
4. **Preregister the §7 gate** if any proposal or ranking stage is added.
5. **Keep the fleet question open and say so.** Nothing in a reframed Exp 5
   would advance it. The single artifact that would is an operator-supplied
   terminal/garage table, exactly as `FLEET_AND_BLOCKING.md` has said since
   2026-09-06.

## Scope of this audit

* No Experiment 5 compute was run. Nothing was launched.
* `outputs/exp4/` was read and not modified. The Exp 4 incumbent
  (`...ecb2ffc4bcce`, 3,511,184.5657525407) is untouched.
* `src/cota_opt/` was read and not modified. The two discrepancies in §8 are
  documented, not patched.
* Every figure here was computed fresh from the committed artifacts during this
  audit. None was copied from a prior document.
* This audit does not resolve the fleet question, does not bound deadhead, and
  makes no deployability claim.
