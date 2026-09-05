# Experiment 4 — what is actually blocking, and why it is not weakened

Readiness work on 2026-09-05 closed every gate that could be closed by checking
or building something small. Four remain. Three of them share one root cause,
and it is worth naming precisely because it is easy to mistake for a missing
check when it is a missing *capability*.

## RESOLVED 2026-09-05 — the substrate now exists

The root cause below has been removed. `exp4_network.Exp4Selection` +
`exp4_assemble.assemble` + `exp4_score.score_exp4_network` assemble a network
from pool line ids and score it on `exp3_score.solve_on_network`, which is
Gen1's evaluation core extracted verbatim and shared by both experiments.

**Measured, not asserted:** an assembled network reproduces the legacy scoring
path **exactly** — 0.000e+00 relative difference across all seven
`FitnessVector` fields (`outputs/exp4/equivalence_isolated.json`).

That test also found **D34**: the evaluator is not invariant to pattern
identifier renaming, worst 8.568e-04 on peak vehicles. No Gen1 result is
affected, but a score is a property of *(network, pattern order)*, and peak
vehicles is a constraint, so a network at its cap could cross it on renaming
alone.

The two gates below therefore move, but neither closes, and the reasons are
measured rather than asserted — see "What survived" at the end.

## The original root cause (historical)

**There was no way to assemble an Experiment 4 network and score it.**

Verified rather than assumed:

* `src/cota_opt/routepool.py` exposes `generate_pool` and `PoolAudit`, and
  nothing else. It builds the 206-line pool and audits it. It cannot turn a set
  of pool line ids into a network.
* The entire scoring path is edit-based over the legacy network:
  `exp3_cell.run_cell(contract, edits: Sequence[GeometryEdit], ...)` →
  `exp3_score.score_state(edits: Sequence[GeometryEdit], ...)`. A `GeometryEdit`
  mutates COTA's existing routes. Experiment 4 *selects whole networks from a
  synthetic pool*, which is not expressible as a sequence of edits to the
  legacy network.
* There is no outer network search. Greps for `network_search`, `outer`,
  `select.*network` and `first_improvement` across `src/cota_opt/` return
  nothing.

So the missing piece is Experiment 4's core machinery: a network-assembly layer
(pool line ids → a scoreable network) and the outer search over it. That is the
experiment, not a readiness check for it.

## What that blocks

| gate | needs |
|---|---|
| **C9 / 4-7** — discovery path reuse benchmarked against exact rebuilds | scoring the same Experiment 4 networks twice, once against a frozen supernetwork master path set and once with exact per-network rebuilds. Requires assembly + scoring. |
| **C10 / 4-14** — the search recovers a deliberately embedded known optimum | enumerating every feasible network in a small envelope and running the outer search from incumbent, random and deceptive starts, including a drop-a-good-route case, a non-nested optimum, a required swap, and an optimal incumbent. Requires assembly + scoring + the search itself. |

Neither can be run against machinery that does not exist, and neither may be
marked MET on the strength of the gate being written down. `scripts/exp4_gates.py`
distinguishes MET from ARMED for exactly this reason, and these two are OPEN
rather than ARMED because even the machinery that would fire them is absent.

## The separate blocker

**D21b — the Gen1→Gen2 bridge suite** has a different root cause: there is no
Gen2 to bridge to. `methodology_generation` exists as a contract and spec field
and defaults to `"gen1"`, but no alternative algorithm is implemented — no
exact or MILP/CP-SAT frequency solver, no incremental evaluator. `METHODOLOGY.md`
puts four steps between the Gen1 freeze and Gen2: the exact frequency benchmark,
the optimization-gap measurement, the evidence-based reopening decision, and
incremental evaluation with full-rebuild canaries. None has been started, and
the bridge suite is what compares the two generations once the second exists.

Gen1 is frozen (`gen1-frozen-v1`), which was the precondition. The rest is Gen2
development.

## D16 rides on D21b

**D16 — an Experiment 4 `ExperimentContract` in force** is blocked by the draft's
own stated condition, not by anything missing in it. `exp4_draft.py` defines
`EXP4_DISCOVERY_DRAFT` and `EXP4_CERTIFICATION_DRAFT` with justifications, and
says they "become active only when Gen1 is frozen **and** the Gen1->Gen2 bridge
suite has run." Gen1 is now frozen; the bridge suite is not, so the contracts
stay drafts and are deliberately not exported from `firewall/`.

That chain is D16 -> D21b -> Gen2, and it is the reason three of the four open
items resolve to the same place.

## D18, excluded by instruction

The gap benchmark on Experiment 4 networks is the fourth open item and was
deliberately not attempted. It is also downstream of the same assembly layer —
it measures the delivered-vs-exact gap on Experiment 4 *networks* — and it
additionally needs the long-running container hold that remains an open
compute-policy decision.

## Why nothing here was weakened

Each of these could have been made green cheaply and dishonestly: mark the gate
MET because ACCEPTANCE.md contains its text; run a degenerate "recovery test" on
the Experiment 2B space, which gate 4-14 rules out in advance ("passing the 2B
benchmark is explicitly insufficient — its winner is a singleton adjacent to the
null"); or call the bridge suite done because Gen1 is frozen. The gates exist to
stop exactly that.

## What survived, after the substrate

* **C9 / gate 4-7** — the substrate half is *measured and exact*. The gate's own
  subject is a frozen master path set versus exact per-network rebuilds, which
  needs the outer search to produce networks to compare. **ARMED, not met.**
* **C10 / gate 4-14** — **run, and not closed for a measured reason.** Every
  feasible network in four enumerated spaces was assembled, scored and ranked,
  and the optimum found by exhaustive enumeration, so the substrate is
  validated. But the four deceptive cases the gate names cannot be built on the
  cheap surrogate: weighted set coverage is submodular (535,599
  diminishing-returns checks, zero violations), greedy carries a (1 − 1/e)
  guarantee on it, and greedy found the exact optimum in all four spaces. The
  production evaluator is **not** submodular — lines meeting at a junction
  create transfer value exceeding their sum — so a benchmark that can genuinely
  defeat a search must use it, which requires the outer search and real compute.
  Substituting a surrogate greedy always solves would produce a green gate that
  proves nothing, which is the failure mode gate 4-14 already names when it
  rules out the 2B benchmark.
* **D16, D21b** — unchanged. Still the Gen2 chain.
* **D18** — unchanged. Still the compute-policy decision.

**Status: 16 of 23 readiness items met, 1 manual, 6 open. Every open item is a
capability gap — machinery that does not exist yet — rather than an unchecked
claim, and four of the six (C9, C10, D16, D21b) reduce to two missing pieces: an
Experiment 4 network-assembly and scoring layer, and a Gen2 algorithm.**

One footnote on this file's own honesty: the readiness script over-claimed twice
while being written, and both were caught by re-reading it rather than by it
failing. D21 reported MET on half its own text (Gen1 frozen, bridge suite not),
and D16 flipped to MET the moment `EXP4_ALLOWANCE` was exported, because the
check tested for a NAME beginning with EXP4 rather than for an
`ExperimentContract` instance. Both are fixed and both are recorded here,
because a gate that can be satisfied by accident is worth less than no gate.
