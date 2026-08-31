# Experiment 3, Phase A1 — the singles census

> ## ⚠ SUPERSEDED FOR QUANTITATIVE INTERPRETATION
>
> **Every number below was produced under `starts="incumbent"`, where the
> optimizer's start set was decided by the treatment (D27).** Route-lengthening
> edits had their incumbent rejected after the ladder snap and silently ran a
> greedy build; route-shortening edits and the zero-edit control never did. The
> two optimizers differ by 0.224% at this effort — **5.7× the 0.039% floor
> quoted below, and larger than the mean measured effect of every kind in the
> table.**
>
> The correlation between a kind's fallback rate and its mean objective is
> **r = −0.711** over the eight kinds. The two kinds that never fell back,
> `truncate` and `straighten`, are the only two that were already being compared
> like-for-like — and they are the two that show no effect.
>
> Replayed through the semantic comparison firewall, **130 of 130 of these
> comparisons are inadmissible** (`outputs/exp3/history_audit.json`).
>
> **What is still usable:** the mutation definitions, the geometry, the contract
> checks, the path-set construction, the fact that the pool produced 84 valid
> single-mutation states, and the observation that `splice` ranks near-worst
> *despite* receiving the better optimizer.
>
> **What is not:** every magnitude, every ranking, the per-kind means, the
> floors as stated, and the promoted frontier derived from them.
>
> Corrected census: re-scored under `starts="both"` with execution receipts,
> `outputs/exp3/stageA_rescored.jsonl`. Preserved here for provenance and
> debugging. Not evidence.

**84 single mutations and 3 zero-edit replicates, at 60,000/2/32 — the same
discovery effort Experiment 2B ranked at.** Every state got its own rebuilt path
sets, its own frequency re-optimization inside the pinned envelope, and its own
Model B evaluation.

**These are discovery-stage numbers. Their magnitudes are not findings.** Gate 12
exists because a ranking at exactly this effort inverted outright once (D24), and
2B's Stage C turned a −0.585% discovery leader into a +0.007% certified null.
What A1 supports is which states to look at next, and nothing else.

## The floors, measured in this run

| quantity | 3σ of the zero-edit replicate spread |
|---|---|
| scalarized objective (λ=2) | **0.039%** |
| unserved demand | **0.130%** |

The unserved floor lands on **0.130%** — the same figure Experiment 2B measured
at this effort, arrived at independently from three fresh replicates. That is
the fourth separate corroboration that this scoring chain is 2B's chain; the
others are in `outputs/exp3/score_invariant.json`.

## The census

| kind | n | best | median | worst | clear the floor |
|---|---|---|---|---|---|
| `add_stop` | 10 | −0.401% | −0.212% | +0.062% | 7/10 |
| `reroute` | 12 | −0.372% | −0.201% | +0.116% | 10/12 |
| `extend` | 12 | −0.282% | −0.186% | −0.074% | **12/12** |
| `change_terminal` | 10 | −0.225% | −0.207% | +0.128% | 8/10 |
| `split` | 4 | −0.181% | −0.107% | −0.048% | 4/4 |
| **`splice`** | 12 | −0.160% | **+0.038%** | +0.262% | **3/12** |
| `truncate` | 12 | −0.088% | +0.041% | +0.513% | 4/12 |
| `straighten` | 12 | −0.061% | +0.007% | +0.156% | 2/12 |

50 of 84 clear the objective floor in the beneficial direction.

## What the splices are doing here

**They are the control, and they behave.** Splices were the *only* kind
Experiment 2 ever evaluated, and 2B's verdict was that six of twelve did
measurable harm and none did measurable good. Here, scored by an independent
pipeline against a fresh baseline, splices come second-from-bottom of eight
kinds with a median that is *positive* — harmful.

That matters more than any individual number above. A large majority of
mutations clearing a floor in the same direction is exactly the signature of an
**under-solved control** — D24's failure, where the unedited network was simply
the harder of the two to solve well at low effort, and every edit looked good by
comparison. If that were happening here, splices would look good too. They do
not. The differences between kinds are measuring the mutations.

## The shape of it

Additive mutations help; subtractive ones hurt; recombination does little.

* `add_stop`, `extend`, `reroute` and `change_terminal` — which put service
  somewhere it was not — occupy the whole top of the table.
* `truncate` and `straighten` — which take service away — occupy the bottom
  alongside `splice`, and produce the four worst states in the census
  (`truncate|102` at +0.513% objective, +1.268% unserved).
* `split` is small but consistent: 4/4 clear, none dramatic. It is the only
  operation that raises the route count and it had never been tested.

None of this is free. The envelope is pinned, so a mutation that adds service
has to be paid for out of frequency somewhere else, and the optimizer does that
on every state. That these still come out ahead says the marginal value of
*coverage* currently exceeds the marginal value of *frequency* at the margin
Experiment 1 left the network at — which is the same trade Experiment 1 was
making, continued past where frequency alone can reach.

**It is also the first evidence this project has had on any of them.** Experiment
2 evaluated splices and nothing else, and concluded geometry does not help. On
this evidence that conclusion was about splices.

## What happens next

Nothing here is promoted on these numbers alone. Phase A2 searches network
*states* — combinations — under the preregistered three-lane policy, and the
promotion band (2 floors of the leader, plus per-kind and per-cardinality
leaders) then selects a small frontier for Stage B, where the incumbent is
re-solved at matched effort in the same run and gate 12 applies.

2B's finding that edits do not compose is the standing prior for A2: across all
240 feasible subsets there, every multi-edit set delivered less than the sum of
its members. Whether that holds for a vocabulary that is mostly *additive*
rather than recombinative is the open question A2 exists to answer.

Artifacts: `outputs/exp3/stageA_states.csv`, `outputs/exp3/stageA_A1.json`,
`outputs/exp3/stageA_states.jsonl`.
