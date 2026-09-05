"""Gate 4-12 — Experiment 4's demand-robustness claims, written before the winner.

`robustness.Claim` exists so a conclusion can be stated as a predicate that a
sweep is able to break. The discipline is the timing: a claim invented after the
sweep can always be made to survive. These are committed while no Experiment 4
network has been scored, so none of them can have been shaped by a result.

What a surviving claim does and does not mean
---------------------------------------------
A claim that survives every perturbation is **not thereby true**. It is not
resting on the demand assumptions that were varied. The largest demand error in
this project is not varied by any perturbation here and cannot be: LODES gives
home-to-work flows only, 24.7% of regional flow is transit-accessible, and the
top 20,000 pairs carry 64.9% of that. `noncommute_proxy` is a *stress
direction* -- flatter across the day, less directional -- not an estimate of
non-commute travel. Nothing in this module upgrades that limitation into a
finding, and a claim surviving the noncommute stress means only that it does not
depend on commute *geometry*, not that non-commute demand has been modelled.

Both admissible outcomes are named in advance (ACCEPTANCE.md gate 4-12):
"substantial benefit survives materially different demand shapes", or "the
apparent gain disappears when commute geometry is perturbed". The second is a
result, not a failure.
"""
from __future__ import annotations

from .robustness import Claim, Perturbation

#: The perturbation set. Each is a plausible alternative demand shape, not an
#: error bar, and each names why it is plausible.
EXP4_PERTURBATIONS: tuple[Perturbation, ...] = (
    Perturbation("baseline", "none", {},
                 "commute LODES exactly as Experiments 1-3 used it"),
    Perturbation("scale_0.7", "scale", {"factor": 0.7},
                 "ridership materially below the LODES-implied total; a pure "
                 "rescale cancels out of ratio measures unless crowding binds, "
                 "so this doubles as a test of D5"),
    Perturbation("scale_1.5", "scale", {"factor": 1.5},
                 "ridership materially above it, same reasoning"),
    Perturbation("periods_flat", "periods", {"toward": ("midday", "evening")},
                 "the period profile was shaped from typical US bus demand, "
                 "not from anything COTA observed; a flatter day is at least as "
                 "defensible as the assumed peak"),
    Perturbation("periods_peaked", "periods", {"toward": ("am_peak", "pm_peak")},
                 "the opposite tilt, so a conclusion cannot survive by sitting "
                 "on one side of the assumed profile"),
    Perturbation("noncommute_30", "noncommute", {"share_b": 0.30},
                 "30% of flow given the flatter, less directional shape -- a "
                 "stress direction for commute geometry, not an estimate"),
    Perturbation("noncommute_50", "noncommute", {"share_b": 0.50},
                 "half, which is past what anyone would defend as a point "
                 "estimate and is the point: it asks how much geometry the "
                 "conclusion can lose"),
    Perturbation("retention_wider_od", "retention", {"top_n": 40_000},
                 "the top 20,000 pairs are 64.9% of accessible flow; the "
                 "optimizer does not get to redesign Columbus around the "
                 "computationally convenient top of the OD table (gate 4-9)"),
)


def _f(row: dict, key: str) -> float:
    v = row.get(key)
    if v is None:
        raise KeyError(f"result row has no {key!r}; a claim that cannot be "
                       f"evaluated counts as broken")
    return float(v)


#: The claims. `test` takes one result row and returns True where the claim
#: holds. Every threshold is stated here, before any Experiment 4 number exists.
EXP4_CLAIMS: tuple[Claim, ...] = (
    Claim(
        key="sign",
        statement="Releasing route structure does not make the network worse "
                  "than the Experiment 3 incumbent.",
        test=lambda r: _f(r, "effect_pct") <= 0.0,
        rests_on="nothing in the demand model; a sign flip under any "
                 "perturbation means the gain was an artifact of demand shape",
    ),
    Claim(
        key="beats_noise",
        statement="The greenfield margin exceeds the noise floor measured in "
                  "the same run, at the same effort, for the same quantity.",
        test=lambda r: abs(_f(r, "effect_pct")) > 3.0 * _f(r, "sd_pct"),
        rests_on="the floor being measured in-run; an inherited floor would "
                 "make this claim untestable (D32)",
    ),
    Claim(
        key="ordering",
        statement="The greenfield winner still beats the best constrained "
                  "redesign (Experiment 3's leader) under this demand shape.",
        test=lambda r: _f(r, "effect_vs_exp3_leader_pct") < 0.0,
        rests_on="the comparison being the right one: gate 4-15 permits a "
                 "claim only against the best constrained redesign, never "
                 "against today's schedule alone",
    ),
    Claim(
        key="magnitude_stable",
        statement="The margin keeps its order of magnitude: it does not move "
                  "by more than a factor of two from the baseline demand.",
        test=lambda r: (
            0.5 <= abs(_f(r, "effect_pct")) / abs(_f(r, "baseline_effect_pct"))
            <= 2.0),
        rests_on="the baseline row being present; a factor-of-two band is "
                 "deliberately loose, because a result that keeps its sign, "
                 "ordering and shape while moving 15% is a different kind of "
                 "result from one that inverts",
    ),
    Claim(
        key="not_od_truncation",
        statement="The margin is not an artifact of the top-20,000 OD "
                  "truncation: it survives on a materially wider OD universe.",
        test=lambda r: (r.get("perturbation") != "retention_wider_od"
                        or _f(r, "effect_pct") < 0.0),
        rests_on="gate 4-9's OD-truncation requirement",
    ),
    Claim(
        key="not_commute_geometry",
        statement="The margin survives a demand shape 50% flatter and less "
                  "directional than commuting.",
        test=lambda r: (r.get("perturbation") != "noncommute_50"
                        or _f(r, "effect_pct") < 0.0),
        rests_on="a STRESS DIRECTION, not an estimate of non-commute travel. "
                 "Surviving it means the conclusion does not depend on commute "
                 "geometry. It does NOT mean non-commute demand was modelled, "
                 "and this claim may never be quoted as though it were.",
    ),
)

#: Stated so it cannot be lost in the summary. This is not a claim, because
#: nothing in the sweep can test it.
UNTESTED_LIMITATION = (
    "Commute-only LODES demand remains the largest unquantified error in this "
    "project and NO perturbation here addresses it. 24.7% of regional flow is "
    "transit-accessible; the top 20,000 pairs carry 64.9% of that; the period "
    "profile came from typical US bus demand rather than from COTA "
    "observations. Every claim above is conditional on that proxy. A claim "
    "surviving all eight perturbations has been shown not to rest on the "
    "assumptions that were varied -- which is a strictly weaker statement than "
    "being right about demand in Columbus."
)
