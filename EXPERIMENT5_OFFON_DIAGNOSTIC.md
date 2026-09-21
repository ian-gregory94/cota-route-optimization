# Exp 5 pre-flight diagnostic — why the certified plan leaves 63% of the hours unspent

**Run 2026-09-21. Diagnostic only. Experiment 5 was not launched.** The
optimizer, the Exp 4 artifacts, the canonical envelope and the Exp 5 design are
unmodified. Everything written went to `outputs/exp5_diag/`.

## STATUS: `OBJECTIVE_PREFERS_SPARSE_SERVICE` — by the letter, and its stated interpretation is WRONG

The criteria for that status are met exactly: **no admissible OFF→ON
perturbation improves the exact objective**, and **every ON state is reachable
by the optimizer** (all 315 OFF route-periods sit one rung from service).

The interpretation attached to it — "the low hour utilization is plausibly
caused by λ=2 / the objective itself" — is **refuted by the same measurement**.

> **The hours are unspent because the PEAK-VEHICLE cap is binding at all six
> periods, at 99.71–99.97% of cap with a tolerance of 0.0, while the hours cap
> sits at 36.66%.** It is neither the objective nor the neighbourhood. It is the
> other constraint, and Experiment 5 was designed around the one that does not
> bind.

The four offered statuses have no case for "a different constraint binds," so
the missing fifth is named here: **`OTHER_RESOURCE_CONSTRAINT_BINDS`.** That is
what happened.

---

## Precondition: the certified objective was reproduced exactly

Before any probe is meaningful the diagnostic had to reproduce what
certification produced, on the same network, same pathset, same evaluator:

```
certified   3511184.5657525407
reproduced  3511184.5657525407      relative error 0.000e+00
```

Bit-exact. Every delta below is therefore comparable to the certified number.

Leader `exp4|exp4-pool-v1|65lines#ecb2ffc4bcce`, 390 route-periods, **315 OFF
(80.77%)**, 922.7448 revenue vehicle-hours.

## 1. OFF → ON reachability, traced through the implementation

Traced, not inferred from comments: `frequency.build_ladders` (rung
construction) and `exp4_certify._restricted` (the neighbourhood), with
`OFF = math.inf` (`frequency.py:121`).

`build_ladders` sorts the finite rungs ascending and then **appends OFF last**,
so OFF is the highest index and the worst finite headway is its immediate
neighbour. `_restricted` anchors on the current value and takes `k` rungs
around it; anchored on OFF it returns the last three of the ladder.

| measurement | value |
|---|---|
| OFF route-periods | **315 of 390 (80.77%)** |
| ladder size, every OFF key | 14 rungs (13 finite + OFF) |
| rung distance OFF → first ON | **1, for all 315** |
| reachable within the 3-rung guarantee | **315 of 315 (100%)** |
| requiring more than 3 rungs to reach any service | **0** |
| unreachable by the active neighbourhood | **0** |
| finite rungs inside the k=3 window | 2, for all 315 |
| best headway reachable in one move | 60.0 min (all 315) |
| best headway anywhere in the ladder | 5.0 min (all 315) |

**The search operator.** One operator: a block of `n_keys = 8` route-periods is
freed, every other key is frozen to a single rung, and the block is solved by
exhaustive enumeration (`solver="exact"`) over `k_rungs = 3` rungs per free key.
Blocks rotate each round; over 40 rounds every key is freed many times. A
single-coordinate move is a member of that enumeration, so **a one-rung OFF→ON
activation is inside the operator's reach in a single accepted move.**

**Reachability is not the problem.** The one thing the operator cannot do in a
single move is jump from OFF to a short headway — the 5-minute rung is 13 rungs
away and would need a chain of accepted intermediate steps.

## 2. Exact OFF→ON probes

Plan held fixed, one OFF route-period moved to each of its 13 finite rungs,
scored with the exact evaluator. No approximate or discovery score was used to
choose or filter anything.

**4,095 probes over 315 OFF route-periods.**

### Pass 1 — objective and hours only

| | |
|---|---|
| probes improving the objective | **3,076 of 4,095 (75.1%)** |
| improving, inside the k=3 window | 242 |
| improving, outside it | 2,834 |
| probes exceeding the hours cap | **0 of 4,095** |
| best improvement | `syn-646ea6f969eead36\|midday` → 5 min, **−18,769.4260** |

On that evidence alone the answer looked like a serious optimizer defect: 242
improving moves inside the neighbourhood, contradicting a converged run.
The best in-window move, `syn-646ea6f969eead36|midday` → 60 min, improved the
objective by **−9,749.43**.

### Pass 2 — the full feasibility test the search actually applies

Pass 1 tested `revenue_veh_hours <= cap`. `frequency._feasible` (`frequency.py:374`)
tests **both** arms:

```python
if fit.revenue_veh_hours > budget.vh_cap() * (1.0 + _EPS_REL):
    return False
for p, v in fit.peak_by_period.items():
    if p in budget.peak_vehicles_by_period:
        if v > budget.peak_cap(p) * (1.0 + _EPS_REL):
            return False
```

Re-scored against both arms:

| | |
|---|---|
| probes feasible under the full test | **0 of 4,095** |
| improving **and** admissible | **0** |
| improving but blocked by a cap | **3,076** |
| improving + admissible inside the k=3 window | **0** |
| probes the hours arm alone would have admitted | **4,095** |
| probes violating at least one peak-vehicle period | **4,095 (100%)** |

**Every single improving move is blocked, and the peak-vehicle arm blocks all of
them. The hours arm blocks none.** The 242 apparent in-window improvements were
an artifact of testing only half the constraint. The certification run did not
miss anything; it converged correctly against a constraint the first pass had
not applied.

## 3. The binding constraint, measured

```
period      used        cap       slack     % of cap
am_peak     58.9431     59.0375   0.0944     99.840%
early       88.4780     88.5563   0.0783     99.912%
evening     44.1474     44.2782   0.1307     99.705%
midday      29.5091     29.5188   0.0097     99.967%
owl         29.4829     29.5188   0.0359     99.879%
pm_peak     58.9431     59.0375   0.0944     99.840%

HOURS      922.7448   2517.1833 1594.4385     36.658%
```

Budget tolerance is **0.0**. All six vehicle periods are pinned to within
0.0097–0.1307 of a vehicle. The hours cap has **1,594 vehicle-hours of slack**.

### Where that cap comes from, and it is the project's own named failure mode

`src/cota_opt/exp2.py:324`:

```python
peak_budget = (dict(fit.peak_by_period)
               if res["peak_fleet_by_period"] == "baseline"
               else {k: float(v) for k, v in res["peak_fleet_by_period"].items()})
```

`fit` there is the **baseline plan's own evaluated fitness on this candidate's
network** (the same `fit` feeding `baseline_generalized_cost` three lines
above). `config/constraints.yaml` sets `peak_fleet_by_period: baseline`, and
`scripts/exp4_launch.py` overrides only `weekday_revenue_vehicle_hours` — it
asserts the peak entry is still the sentinel.

So the two caps have completely different provenance:

* **hours** — the canonical frozen artifact, 2517.183333, digest
  `b6c647d3766338a6`. Never binds.
* **peak vehicles** — *read off the candidate's own baseline plan*, measured
  with `FrequencyModel.peak_vehicles` = `cycle / headway`. Binds everywhere.

`FLEET_AND_BLOCKING.md` names exactly this practice as the original sin: "a cap
was being read off the thing the cap was supposed to constrain."
`exp5_resource.REJECTED_AS_CAP` names it too, under
`optimized_plan_realized_veh_hours`: "a cap may never be read off a plan's
usage." And the instrument is the `routewise_peak` proxy that the same dict
rejects at 150.73, which `contract.py:451` refuses to compare against a
block-derived budget.

**This promotes D5-C from a latent hazard to the operative constraint of
Experiment 4.** The premise audit called the proxy check "tolerable in a search
filter." It is not a loose filter here. It is the constraint that determined
every certified plan, and it is pinned to three decimal places.

### What that does and does not do to Experiment 4

It does **not** invalidate the Exp 4 ranking. Every one of the 200 candidates
was certified under the same machinery, the objective is `objective_EXACT`
throughout, and no fleet verdict filtered or ranked anything.

It **does** narrow the scope of the claim. The Exp 4 leader is the best
certified objective **under a per-candidate vehicle cap read off that
candidate's own baseline plan and measured with a proxy the project rejects for
capping**. That sentence belongs wherever the leader is quoted. It also explains
the shape of the result: the optimizer redistributed service to within 0.16% of
the baseline's own vehicle usage in every period, which is why 80.8% of
route-periods are OFF and why the hours go unspent.

## 4. Is the proposed frontier a resource frontier?

**Not as specified.** Traced from `FitnessVector.scalarized` (`frequency.py:162`):

```python
return self.generalized_cost + multiplier * w_unserved * self.unserved_demand
```

with the implied `w_unserved = 60.0` exactly, so at λ=2 an unserved passenger
trip costs **120 equivalent minutes** against a mean served cost of **63.93**.
Serving more people is strongly rewarded, and only **11.68%** of demand is
served. The objective is not what is holding service down.

**Hours do not appear in the objective at all.** They are purely a constraint.
So the premise behind Ian's option B — "hours acting as the resource axis rather
than *also* being penalized inside the objective" — does not hold: hours are not
penalized inside the objective today.

What Exp 5 would actually be, if run as designed:

* it retains λ=2 and adds hour caps at 0.75×–1.50× of 2517.183333;
* **every one of those caps is above the operating point of 922.74**, so the
  entire grid is non-binding on the hours axis;
* the peak-vehicle cap would continue to bind at every cell, unchanged, because
  Exp 5 does not scale it;
* so all sixteen cells return the same plan and the same objective. Monotonicity
  and traversal invariance pass trivially, marginals are zero, the structural
  matrix is empty. Sixteen full certifications reporting nothing.

**This is not a service-versus-resource Pareto frontier.** It varies a slack
constraint while a different constraint holds the solution fixed.

### A or B?

Neither, as posed. **A is already what is implemented** — minimize λ=2 subject
to caps — with a second cap that is the one doing the work. **B** changes the
objective (dropping generalized cost) without touching the binding constraint,
so it would produce the same flat frontier.

**The axis has to be the resource that binds.** Concretely, the choices are:

1. **Scale the vehicle cap and keep λ=2 and the hours cap fixed.** This is the
   only version that produces a real frontier from the current machinery. Its
   axis is honest only if labelled for what it is: a per-candidate,
   plan-derived, proxy-measured peak-vehicle cap. It is not fleet, it is not the
   canonical envelope, and the premise audit's bracket finding still applies to
   any attempt to call it fleet.
2. **Fix the provenance first** — give the peak cap a source that is not the
   plan it constrains — and then choose the axis. This is more work and is the
   only route to a frontier anyone could publish.

Option 1 answers "what does this network yield at different vehicle levels" with
a caveat that will follow the result everywhere. Option 2 answers it properly.
**Given the stated purpose of Exp 5 — what structure is worth at different
operating capacities — option 2 is the one that matches, and option 1 is worth
running first only as a shape-check, clearly labelled as such.**

## 5. Retraction — the premise audit's central recommendation was wrong

`EXPERIMENT5_PREMISE_AUDIT.md` §10 item 1 said:

> "Drop fleet from the axis. Single-resource frontier on revenue vehicle-hours.
> … Concretely: pass `peak_vehicles_by_period={}` to `ResourceBudget` so the
> fleet arm of `_feasible` is provably inert, rather than leaving a loose proxy
> check that looks like a constraint."

**That is retracted.** Zeroing `peak_vehicles_by_period` would have deleted the
only binding constraint in the problem, turning Exp 5 into a nearly
unconstrained optimization with 1,594 vehicle-hours of headroom and no vehicle
limit at all. The resulting "frontier" would have measured the removal of the
constraint, not the network.

The audit reached that recommendation because it checked whether the hours cap
and the fleet-cap *grid* would bind on the certified candidates, and never
checked what was binding **inside** the certification run. The error is the same
shape as the one that produced the pass-1 result above: testing one arm of a
two-arm constraint and reading the silence as evidence.

The audit's other conclusions are unaffected: candidate fleet is still
`UNDECIDABLE`, the brackets still contain the whole cap grid, and the 200-cap is
still invalid. `EXP5_REFRAME_REQUIRED` stands, and the reframe now has a
different target.

## 6. Grid design — still not started, per instruction

No levels are proposed. What this diagnostic establishes about the eventual
grid:

* It must be anchored on the **binding** resource, not the hours axis.
* The current operating point is **99.7–99.97% of the peak-vehicle cap** in all
  six periods, so levels above 1.00× will be non-binding on the constraint that
  matters and levels below it will bind immediately. The useful range is
  narrow and sits *below* 1.00×.
* Anchoring to the canonical 135–197 envelope would be wrong twice over: the
  operative caps are 29.5–88.6, and they are per-candidate.
* None of this can be settled until the cap's provenance is decided, because a
  grid scaled from a plan-derived cap inherits the plan.

## Scope

* Experiment 5 was not launched.
* `src/cota_opt/` unmodified. `outputs/exp4/` read-only. `CANONICAL_ENVELOPE.json`
  unmodified. `EXPERIMENT4_AUDIT_DESIGN.md` and the Exp 5 design unmodified.
* Two scripts added under `scripts/`, both read-only against Exp 4, both
  writing solely to `outputs/exp5_diag/`.
* The certified objective was reproduced bit-exactly before any probe was read.
* No approximate or discovery score was used anywhere in this diagnostic.
* No fleet or deployability claim is made. The peak-vehicle quantity discussed
  here is the cycle/headway proxy throughout and is never called fleet.
