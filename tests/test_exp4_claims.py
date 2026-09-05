"""Gate 4-12 — the claims must be breakable, and honest about what they cover."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cota_opt.exp4_claims import (EXP4_CLAIMS, EXP4_PERTURBATIONS,  # noqa: E402
                                  UNTESTED_LIMITATION)
from cota_opt.robustness import check, summary                      # noqa: E402


def _row(**kw):
    base = dict(perturbation="baseline", effect_pct=-1.0, sd_pct=0.01,
                effect_vs_exp3_leader_pct=-0.5, baseline_effect_pct=-1.0)
    base.update(kw)
    return base


def test_every_claim_can_be_broken():
    """A claim nothing can falsify is decoration, not a claim."""
    good = check(EXP4_CLAIMS, [_row()])
    assert good["survives"].all(), good[~good["survives"]].to_dict("records")

    # each claim has at least one row that breaks it
    breakers = {
        "sign": _row(effect_pct=+1.0),
        "beats_noise": _row(effect_pct=-0.01, sd_pct=1.0),
        "ordering": _row(effect_vs_exp3_leader_pct=+0.5),
        "magnitude_stable": _row(effect_pct=-5.0, baseline_effect_pct=-1.0),
        "not_od_truncation": _row(perturbation="retention_wider_od",
                                  effect_pct=+0.2),
        "not_commute_geometry": _row(perturbation="noncommute_50",
                                     effect_pct=+0.2),
    }
    assert set(breakers) == {c.key for c in EXP4_CLAIMS}
    for key, row in breakers.items():
        v = check(EXP4_CLAIMS, [row])
        broken = set(v[~v["survives"]]["claim"])
        assert key in broken, f"{key} survived a row built to break it"


def test_a_claim_that_cannot_be_evaluated_counts_as_broken():
    """A missing field must not read as a pass -- for the claims that read it.

    Two claims are conditional on a specific perturbation and are vacuously true
    elsewhere, by design: `not_od_truncation` governs only the wider-OD row and
    `not_commute_geometry` only the 50% noncommute row. They short-circuit
    before touching any field, which is correct -- a conditional claim is not
    evidence about rows it does not govern. The other four are unconditional and
    must break when the field they need is absent.
    """
    v = check(EXP4_CLAIMS, [{"perturbation": "baseline"}])
    broken = set(v[~v["survives"]]["claim"])
    assert broken == {"sign", "beats_noise", "ordering", "magnitude_stable"}

    # and each conditional claim DOES break when its own row lacks the field
    for key, pert in (("not_od_truncation", "retention_wider_od"),
                      ("not_commute_geometry", "noncommute_50")):
        v = check(EXP4_CLAIMS, [{"perturbation": pert}])
        assert key in set(v[~v["survives"]]["claim"]), (
            f"{key} survived its own perturbation with the field missing")


def test_the_perturbation_set_covers_the_gate_4_12_directions():
    kinds = {p.kind for p in EXP4_PERTURBATIONS}
    assert {"scale", "periods", "noncommute", "retention"} <= kinds
    assert all(p.rationale for p in EXP4_PERTURBATIONS), "each needs a reason"


def test_the_untested_limitation_is_stated_and_not_upgraded():
    """The commute-only LODES limitation must survive this module intact."""
    t = UNTESTED_LIMITATION
    assert "largest unquantified error" in t
    assert "NO perturbation here addresses it" in t
    assert "24.7%" in t
    # and the noncommute claim must say what it is not
    nc = next(c for c in EXP4_CLAIMS if c.key == "not_commute_geometry")
    assert "STRESS DIRECTION, not an estimate" in nc.rests_on
    assert "does NOT mean non-commute demand was modelled" in nc.rests_on


def test_summary_says_what_survival_does_not_mean():
    s = summary(check(EXP4_CLAIMS, [_row()]))
    assert "is not thereby true" in s["interpretation"]
