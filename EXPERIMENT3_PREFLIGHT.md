# Experiment 3 preflight — the nine items, and where each one lives

Everything below is committed and tagged **`pre-exp3-v2`**. Stage A has not run:
nothing in Experiment 3 has been scored, and no candidate exists.

`pre-exp3-v1` is preserved, unmoved, and its baseline file is byte-identical to
what it was tagged with. The Experiment 1 numbers are untouched. No superseded
artifact was deleted.

---

## 1. The corrected v2 canonical manifest and baseline

`outputs/CANONICAL_RESULTS.json` · `outputs/canonical/pre_exp3_baseline_v2.json`

| experiment | status |
|---|---|
| exp1 | CLOSED, certified λ≥2 |
| exp2 | CLOSED — no candidate promoted |
| exp2b | CLOSED — certified NULL |
| exp3 | NOT STARTED — contract committed, gates committed |

The **generators** were fixed, not just their output. `freeze_records.py` had
`exp2: "CLOSED pending the 2B subset search"` and `exp2b: RUNNING / headline:
pending` as string literals, so regenerating the manifest would have reverted
three-day-old statuses. 2B's headline is now **read from
`outputs/exp2b_certification.json`** rather than typed, so the manifest cannot
drift from the artifact it describes — and if the certification is missing it
says so instead of quoting a number it cannot see.

`build_exp3_baseline.py` no longer says Experiment 2B "may still find a subset
that clears the floor". It did not. The conservative incumbent is COTA's
unchanged geometry **as a settled finding**, not a default held open. The
baseline is versioned (`--version v2`); v1 is never overwritten.

**A structural bug found by the new tag check.** A record that stamps `HEAD` is
committed *after* the commit it names, so regenerating it writes a different
value, which dirties the tree, which changes the value again. It never
converges — so a tag script requiring its own checks to leave the tree clean
could never have passed. The one-commit lag documented on v1 was not inherent to
self-hashing records; it was this bug, described instead of fixed. Both
generators now stamp **the last commit that changed a hashed input**, which
moves only when an input moves. Regenerating an unchanged freeze is now a
byte-for-byte no-op, verified.

**The tag script checks the tree twice** — before, and after its own checks have
written their artifacts. It refuses if running the preconditions changed a
tracked file, because the tag would then point at a commit that does not contain
the records that just passed. It fired on the first attempt at v2.

## 2. The aligned Experiment 3 contract and gates

`ACCEPTANCE.md` · `EXPERIMENT3_CONTRACT.md`

The old gates 3-1…3-9 were written for **stop consolidation** — walking traded
against vehicle running time. Experiment 3 is route mutation and never measures
that quantity. They are preserved verbatim as **SC-1…SC-4, marked deferred**,
with the negative finding quoted in full, and ten operative gates replace them
with an explicit old→new mapping so nothing is lost.

The deferred finding, kept because gate 3-4 rests on it: *the eleven natural
experiments COTA's schedule offers rest on five stops, three of them bays nine
metres apart on one platform; relaxing every threshold takes the wayside
comparison count from 0 to 0.*

| gate | forbids |
|---|---|
| 3-1 | scoring under an evaluator that cannot state its own waiting model |
| 3-2 | letting a fixed-frequency screen decide what gets evaluated |
| 3-3 | comparing against a floor measured for a different quantity or effort |
| 3-4 | crediting a runtime saving to skipping stops on an unchanged alignment |
| 3-5 | leaving a sole-access stop unserved |
| 3-6 | ranking mutations individually and taking the top N |
| 3-7 | quoting a margin over anything but the incumbent re-solved in the same run |
| 3-8 | exceeding the vehicle-hour budget or the 197.0 peak-vehicle baseline |
| 3-9 | letting a high modelled-link exposure carry a headline |
| 3-10 | promoting one map when seeds disagree structurally inside the floor |
| 12 | matching nominal effort and calling it matched convergence |

`stopedits.py`, `stopevidence.py` and the break-even framework remain available
for a future experiment. They are marked rather than deleted precisely so they
cannot become the Experiment 3 search by default.

## 3. The exact primary objective and promotion rule

`EXPERIMENT3_CONTRACT.md` §5a · `src/cota_opt/exp3.py`

```
objective(plan) = generalized_cost + λ · w_unserved · unserved_demand
```

λ = 2. **`w_unserved` is read from `config/cost_weights.yaml`** (`weights.
unserved`, currently 60.0) by `exp3.unserved_weight()` — one implementation,
never hardcoded, with a test that changes the config and demands the objective
change with it.

**All six components are reported alongside it, always**: generalized cost,
unserved demand, served demand, generalized cost per served trip, weekday
revenue vehicle-hours, peak vehicles. A table showing the objective without the
components is not a result — Experiment 1 turns on total cost *rising* while
cost per served trip *falls*, and the scalar hides that.

**The comparison object** is COTA's unchanged geometry with frequency
re-optimized in the same envelope. `exp1_final.json` is the *reference*, not the
thing a margin is computed from: **every promoted comparison re-solves the
unchanged network at matched effort, in the same run, with replicates.** D24 is
why — the entire Experiment 2 geometry claim came from a well-solved edited
network against a badly-solved unedited one at nominally identical effort.

**Noise floors** are measured for the objective **and** each component, from
zero-edit replicates, 3σ, in the same run at the same effort. The existing
0.130- and 0.287-point figures are floors on *unserved demand* and do not
transfer; `NoiseFloor.clears()` raises rather than silently comparing against
the wrong quantity.

**Promotion is a band, not a top N**: everything within 2.0 floors of the
leader, plus the best 2 states featuring each mutation kind, plus the best state
at each cardinality (not required to be nested). At discovery effort every state
within a floor is a tie, and a top-N rule discards the true winner whenever the
ranking is off by one floor — which here it has been.

## 4. The implemented contract validator and boundary tests

`src/cota_opt/contract.py` · `tests/test_contract.py` (39) ·
`tests/test_geometry_order.py` (9)

Enforced at four points, not one: **generate, apply, cache-load, promote**.
Generator filtering alone is insufficient because intentions are not outcomes —
truncating one route can strand a stop the mutation never names, and
individually small edits can exceed the edit-distance boundary together. Every
violation **raises**; an invalid mutation never becomes a silent no-op.

Limits live in `ContractLimits` as data, and a test checks the numbers against
the contract document. Each is tested **at the limit and one step past it** —
the exact-limit cases catch a `>` written where `>=` was meant, which is how a
documented 40% cap becomes an undocumented 41% one.

**Three contradictions between the contract and the code, resolved:**

* The contract claimed `apply_edits` already refused two mutations naming a
  common route. **It did not** — only splices consumed their routes, and two
  truncations of one line composed in application order. That gap is why a
  network state could not have an order-free digest. `apply_edits` now enforces
  it, and `test_geometry_order.py` applies a state's mutations in **every order**
  and demands the same network back. Experiment 2's ladder behaviour stays
  reachable behind `require_disjoint_routes=False`.
* The contract advertised four operations the code could not construct.
  **`split`, `change_terminal` and `add_stop` are implemented and tested**;
  *change transfer point* is narrowed to "a reroute on one of the two routes",
  because a second name for one mutation would give it two canonical identities.
  A test parses the contract's own table and asserts every advertised kind is in
  `EDIT_KINDS`.
* **Gate 3-4 was too blunt and I had to fix it properly.** I first rejected
  every `straighten`, which made the contract advertise an operation the pool
  would never produce. The real distinction is not whether stops were removed
  but **whether the bus's path changed**: removing stops off a deviation means
  the vehicle drives a different street (priceable, permitted); removing stops
  that sat on the line means it drives the same street and the only saving is
  dwell (unmeasurable, forbidden). Separated by circuity at 1.10, well below the
  1.6 the straighten generator proposes at, with a test that reads the
  generator's own default and asserts the bands cannot overlap. Without
  coordinates the check assumes the worst — a check that cannot tell must not
  wave things through.

## 5. The frozen atomic mutation pool and rejection audit

`outputs/exp3/mutation_pool.json` · `outputs/exp3/incompatible_pairs.json` ·
`tests/test_mutate.py` (11)

**84 accepted of 189 proposed**, 189 structurally incompatible pairs, 14
peak-express routes excluded.

| kind | accepted | quota |
|---|---|---|
| truncate | 12 | 12 |
| straighten | 12 | 12 |
| extend | 12 | 12 |
| reroute | 12 | 12 |
| splice | 12 | 12 |
| add_stop | 10 | 10 |
| change_terminal | 10 | 10 |
| **split** | **4** | 10 |

Ranked by **structural and demand rules only** — running-time share against
uniquely-reached demand. Nothing was discarded on a fixed-frequency score (gate
3-2), and nothing was discarded for scoring badly alone, which would assume
exactly the composability 2B exists to have tested.

**Two things went wrong building it, both fixed rather than worked around.**

The first pool accepted **zero splits**. The generator measured the share on the
route's longest pattern while the validator summed over every pattern, so ten
proposals were made at 30% by one arithmetic and rejected under 30% by the
other. The one operation that raises the route count was advertised and
unreachable. There is now one `split_shares` used by both, pinned by a test.

The first audit reported **zero rejections**, which is ambiguous: either the
generators respect every rule, or the checker is a no-op. Generators are now
asked for 3× each quota and the surplus is trimmed afterwards, so the quota's
effect is visible instead of buried inside each generator's shortlist — and a
**liveness probe** hands the validator deliberately illegal mutations, one per
rule, recording which rule caught each. `all_rules_fire: true`.

The split quota is **not filled**, 4 of 10, and the artifact says so rather than
leaving a reader to read a limit as a choice: COTA's network does not contain
more cuts leaving both halves above 30%.

## 6. The canonical network-state digest and cache-key tests

`src/cota_opt/exp3.py` · `tests/test_exp3_identity.py` (23)

`mutation_id` hashes everything that changes what a mutation does and nothing
that does not — rewording a description must not create a new candidate, and
reordering `drop_stops` must not either. `GeometryEdit.key` truncates stop lists
and genuinely collides; a test asserts the collision exists and that the
canonical id does not inherit it.

`state_digest` is **permutation-invariant**, which is only legitimate because
`apply_edits` refuses two mutations on one route.

`cache_key` carries state digest, waiting model, λ, seed, effort, config digest
and pool version. A parametrized test moves **each term independently** and
demands the key move — the Experiment 2 defect, one term at a time, where a cell
keyed on the candidate alone was reused across two waiting models and a resumed
run inherited three days of Model A numbers under a Model B label.

The frozen pool **round-trips**: all 84 mutations reload to the same canonical
id. A pool that cannot be reloaded is not frozen, and an id that shifts on
reload would make every cached score for it unreachable while looking identical
in the artifact. That defect was live until Stage A tried to load the pool and
`GeometryEdit` refused it.

## 7. The benchmark: the heuristic recovers the known optimum

`outputs/exp3/search_benchmark.json` · `scripts/exp3_benchmark.py` ·
`tests/test_statesearch.py` (15)

Neighbourhood search over states — add one, drop one, **swap** one. Swap is not
redundant with add-then-drop: 2B found cardinality winners are not nested, so
reaching the better state means passing through a worse one, which an add-only
search will not do.

On 2B's **240 exhaustively enumerated states**:

* recovers `splice|011|034|WESHIGW` from **all 8 declared seeds independently**;
* evaluates 57 states of 240 with all seeds together;
* a **resumed run does zero work** and returns the same answer;
* state hashing, incompatibility and checkpointing all reproduce.

Two things are recorded in the artifact rather than left implicit:

* **Necessary, not sufficient.** That optimum is a single mutation adjacent to
  the null, so a greedy add-only search finds it trivially. The unit tests
  supply what it cannot: a non-nested optimum only a swap reaches, a deceptive
  single that traps add-only search, a space whose answer is the null, and a
  benchmark harness proven able to **fail**.
* **The recovered optimum later certified as NULL** (D22). The benchmark
  validates search recovery, not the intervention. Conflating those is the exact
  error gate 12 exists to prevent.

The benchmark refuses a non-exhaustive table: a partial table would let the
search "pass" by never being offered the states it would have got wrong.

## 8. Clean test and reproducibility results

`outputs/repro_check.json` · `pyproject.toml` · `tests/test_repro_guards.py`

**14 checks pass. 458 tests, 0 skipped.**

A clean install ran 348 tests while the committed record claimed 356. The
realtime module's `importorskip` fired because `gtfs-realtime-bindings` was
never declared — present on the machine that wrote the record, absent on a clean
one, and the difference showed only as a smaller number nobody read.

* `realtime` and `ntd` are **named optional extras**, and `dev` pulls both in,
  so the suite a contributor runs is the whole suite. They stay optional on the
  merits: no result depends on the realtime collector, and nothing imports the
  NTD parser at runtime.
* **repro_check fails on any skip**, in place and in the fresh clone, and
  reports *which* tests did not run rather than only how many.
* A new check reads the imports: **every third-party module imported anywhere in
  `src`, `scripts` or `tests` must map to a declared distribution.** Running the
  tests cannot detect an undeclared dependency — `importorskip` hides it — but
  reading the imports can. It immediately found a second one, `pdfplumber`,
  which parses the NTD profile the VOMS = 198 fleet validation came from.
* The fresh-clone check now **states its own scope**: it reuses the running
  interpreter's site-packages, so it proves the clone has every committed *file*
  it needs, not that a clean install resolves every dependency.

## 9. Stage A: command, state count, checkpoint, runtime

```
python scripts/exp3_stage_a.py --dry-run     # plan only, scores nothing
python scripts/exp3_stage_a.py               # the sweep
```

| | |
|---|---|
| pool | 84 mutations, `exp3-pool-v1`, 189 incompatible pairs |
| objective | λ=2 scalarized, weight read from config |
| effort | 60,000 / 2 / 32 — 2B's discovery effort, so the two are comparable |
| restart seeds | 0…11 (12) |
| max cardinality | 4 |
| **states to score** | **≤ 603** — 600 search budget + 3 zero-edit replicates |
| measured cost/state | ~75 s at this effort, from 2B's Stage A log |
| **estimated runtime** | **~12.6 h**, resumable |
| **checkpoint** | `outputs/exp3/stageA_states.jsonl` (append-only, keyed on the full cache key) |
| plan artifact | `outputs/exp3/stageA_plan.json` |
| outputs | `outputs/exp3/stageA_states.csv`, `outputs/exp3/stageA_result.json` |

The noise floor is measured from the three zero-edit replicates **before the
search starts**, so no state can be promoted against a floor that does not exist
yet. A contract-refused state is recorded and priced out of the search rather
than allowed to kill a sweep hundreds of states in — 2B had a worker die on one
bad subset and get restarted onto it forever.

---

**Stage A has not been launched.** Everything above is committed and tagged;
nothing has been scored.
