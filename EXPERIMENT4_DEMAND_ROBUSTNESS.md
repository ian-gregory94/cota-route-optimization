# Experiment 4 — demand-robustness claims (gate 4-12)

**Committed before any Experiment 4 network has been scored.** The discipline is
the timing: a claim invented after the sweep can always be made to survive. The
executable form is `src/cota_opt/exp4_claims.py`; this file is the same content
in prose so it can be read without running anything.

Both outcomes named in ACCEPTANCE.md gate 4-12 are admissible in advance —
*substantial benefit survives materially different demand shapes*, or *the
apparent gain disappears when commute geometry is perturbed*. The second is a
result, not a failure.

## The claims

### `sign`

> Releasing route structure does not make the network worse than the Experiment 3 incumbent.

*Rests on:* nothing in the demand model; a sign flip under any perturbation means the gain was an artifact of demand shape

### `beats_noise`

> The greenfield margin exceeds the noise floor measured in the same run, at the same effort, for the same quantity.

*Rests on:* the floor being measured in-run; an inherited floor would make this claim untestable (D32)

### `ordering`

> The greenfield winner still beats the best constrained redesign (Experiment 3's leader) under this demand shape.

*Rests on:* the comparison being the right one: gate 4-15 permits a claim only against the best constrained redesign, never against today's schedule alone

### `magnitude_stable`

> The margin keeps its order of magnitude: it does not move by more than a factor of two from the baseline demand.

*Rests on:* the baseline row being present; a factor-of-two band is deliberately loose, because a result that keeps its sign, ordering and shape while moving 15% is a different kind of result from one that inverts

### `not_od_truncation`

> The margin is not an artifact of the top-20,000 OD truncation: it survives on a materially wider OD universe.

*Rests on:* gate 4-9's OD-truncation requirement

### `not_commute_geometry`

> The margin survives a demand shape 50% flatter and less directional than commuting.

*Rests on:* a STRESS DIRECTION, not an estimate of non-commute travel. Surviving it means the conclusion does not depend on commute geometry. It does NOT mean non-commute demand was modelled, and this claim may never be quoted as though it were.

## The perturbations

| name | kind | why it is plausible |
|---|---|---|
| `baseline` | none | commute LODES exactly as Experiments 1-3 used it |
| `scale_0.7` | scale | ridership materially below the LODES-implied total; a pure rescale cancels out of ratio measures unless crowding binds, so this doubles as a test of D5 |
| `scale_1.5` | scale | ridership materially above it, same reasoning |
| `periods_flat` | periods | the period profile was shaped from typical US bus demand, not from anything COTA observed; a flatter day is at least as defensible as the assumed peak |
| `periods_peaked` | periods | the opposite tilt, so a conclusion cannot survive by sitting on one side of the assumed profile |
| `noncommute_30` | noncommute | 30% of flow given the flatter, less directional shape -- a stress direction for commute geometry, not an estimate |
| `noncommute_50` | noncommute | half, which is past what anyone would defend as a point estimate and is the point: it asks how much geometry the conclusion can lose |
| `retention_wider_od` | retention | the top 20,000 pairs are 64.9% of accessible flow; the optimizer does not get to redesign Columbus around the computationally convenient top of the OD table (gate 4-9) |

## What a surviving claim does not mean

Commute-only LODES demand remains the largest unquantified error in this project and NO perturbation here addresses it. 24.7% of regional flow is transit-accessible; the top 20,000 pairs carry 64.9% of that; the period profile came from typical US bus demand rather than from COTA observations. Every claim above is conditional on that proxy. A claim surviving all eight perturbations has been shown not to rest on the assumptions that were varied -- which is a strictly weaker statement than being right about demand in Columbus.

A claim that survives every perturbation is **not thereby true**. It has been
shown not to rest on the assumptions that were varied, which is strictly
weaker. A claim that breaks names the assumption it was resting on, and that
is the more informative outcome of the two.
