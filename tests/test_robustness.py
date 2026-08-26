"""Demand perturbations, and conclusions written so a sweep can break them."""
import numpy as np
import pandas as pd
import pytest

from cota_opt.odmatrix import ODTable
from cota_opt.robustness import (Claim, Perturbation, blend, check,
                                 noncommute_proxy, scale_od, summary,
                                 tilt_periods)


def _od():
    return ODTable(np.array([0, 1, 0, 2]), np.array([1, 0, 2, 0]),
                   np.array([100.0, 40.0, 60.0, 10.0]), "lodes", "")


SHARES = {"early": 0.05, "am_peak": 0.22, "midday": 0.33,
          "pm_peak": 0.24, "evening": 0.12, "owl": 0.04}


# -- scale -------------------------------------------------------------------

def test_scaling_multiplies_every_flow_and_says_so():
    o = scale_od(_od(), 1.25)
    assert o.flow.sum() == pytest.approx(_od().flow.sum() * 1.25)
    assert "1.25" in o.notes and o.source.endswith("x1.25")


def test_scaling_preserves_the_shape_exactly():
    a, b = _od(), scale_od(_od(), 3.0)
    assert np.allclose(a.flow / a.flow.sum(), b.flow / b.flow.sum())


def test_a_non_positive_scale_is_refused():
    for bad in (0.0, -1.0):
        with pytest.raises(ValueError):
            scale_od(_od(), bad)


# -- period tilt -------------------------------------------------------------

def test_a_tilt_still_sums_to_one():
    out = tilt_periods(SHARES, ["midday"], 0.5)
    assert sum(out.values()) == pytest.approx(1.0)


def test_tilting_toward_midday_raises_midday_and_lowers_the_rest():
    out = tilt_periods(SHARES, ["midday"], 0.5)
    assert out["midday"] > SHARES["midday"]
    assert out["am_peak"] < SHARES["am_peak"]
    assert out["pm_peak"] < SHARES["pm_peak"]


def test_a_negative_strength_moves_demand_away():
    out = tilt_periods(SHARES, ["am_peak", "pm_peak"], -0.5)
    assert out["am_peak"] < SHARES["am_peak"]
    assert out["midday"] > SHARES["midday"]


def test_a_zero_tilt_changes_nothing():
    out = tilt_periods(SHARES, ["midday"], 0.0)
    assert all(out[k] == pytest.approx(v) for k, v in SHARES.items())


def test_an_unknown_period_is_refused_rather_than_ignored():
    with pytest.raises(ValueError, match="lunchtime"):
        tilt_periods(SHARES, ["lunchtime"], 0.5)


def test_a_tilt_that_would_zero_a_period_is_refused():
    with pytest.raises(ValueError):
        tilt_periods(SHARES, ["midday"], -1.0)


# -- the stress direction ----------------------------------------------------

def test_the_proxy_keeps_the_same_pairs_and_the_same_total():
    od = _od()
    p = noncommute_proxy(od, np.array([1.0, 2.0, 0.5]))
    assert np.array_equal(p.origin, od.origin) and np.array_equal(p.dest, od.dest)
    assert p.flow.sum() == pytest.approx(od.flow.sum())


def test_the_proxy_is_symmetric_where_both_directions_exist():
    od = _od()          # (0,1) and (1,0) are both present
    p = noncommute_proxy(od, np.array([1.0, 2.0, 0.5]))
    fwd = p.flow[(p.origin == 0) & (p.dest == 1)][0]
    rev = p.flow[(p.origin == 1) & (p.dest == 0)][0]
    assert fwd == pytest.approx(rev)


def test_the_proxy_says_it_is_not_an_estimate():
    p = noncommute_proxy(_od(), np.array([1.0, 2.0, 0.5]))
    assert "STRESS DIRECTION" in p.notes and "not an estimate" in p.notes


def test_distance_decay_pushes_flow_toward_short_pairs():
    od = _od()
    far = {(0, 2): 20.0, (2, 0): 20.0}
    p = noncommute_proxy(od, np.ones(3), decay_km=2.0,
                         distance=lambda i, j: far.get((i, j), 1.0))
    short = p.flow[(p.origin == 0) & (p.dest == 1)][0]
    long_ = p.flow[(p.origin == 0) & (p.dest == 2)][0]
    assert short > long_


def test_zero_weights_are_refused_rather_than_returning_nothing():
    with pytest.raises(ValueError):
        noncommute_proxy(_od(), np.zeros(3))


# -- blending ----------------------------------------------------------------

def test_a_blend_of_zero_returns_the_first_table():
    a = _od()
    b = noncommute_proxy(a, np.array([1.0, 2.0, 0.5]))
    assert np.allclose(blend(a, b, 0.0).flow, a.flow)
    assert np.allclose(blend(a, b, 1.0).flow, b.flow)


def test_a_blend_preserves_the_total():
    a = _od()
    b = noncommute_proxy(a, np.array([1.0, 2.0, 0.5]))
    assert blend(a, b, 0.3).flow.sum() == pytest.approx(a.flow.sum())


def test_blending_mismatched_pair_lists_is_refused():
    a = _od()
    b = ODTable(np.array([0]), np.array([1]), np.array([1.0]), "x", "")
    with pytest.raises(ValueError, match="same pairs"):
        blend(a, b, 0.5)


def test_a_share_outside_the_unit_interval_is_refused():
    a = _od()
    with pytest.raises(ValueError):
        blend(a, a, 1.5)


# -- claims ------------------------------------------------------------------

ROWS = [{"perturbation": "none", "unserved_change_pct": -6.4, "gc_change_pct": 0.4},
        {"perturbation": "scale_x2", "unserved_change_pct": -6.4, "gc_change_pct": 0.4},
        {"perturbation": "midday_tilt", "unserved_change_pct": -4.9, "gc_change_pct": 0.9},
        {"perturbation": "noncommute_40", "unserved_change_pct": +1.2, "gc_change_pct": 1.8}]

CLAIMS = [
    Claim("unserved_falls", "redistribution lowers unserved demand",
          lambda r: r["unserved_change_pct"] < 0, rests_on="demand shape"),
    Claim("cost_is_small", "the generalized-cost penalty stays under 1%",
          lambda r: r["gc_change_pct"] < 1.0),
]


def test_a_claim_that_holds_everywhere_survives():
    v = check([CLAIMS[1]], ROWS[:3])
    assert bool(v.iloc[0]["survives"])
    assert v.iloc[0]["broken_under"] == ""


def test_a_claim_that_breaks_names_the_perturbation_that_broke_it():
    v = check([CLAIMS[0]], ROWS)
    r = v.iloc[0]
    assert not r["survives"]
    assert r["broken_under"] == "noncommute_40"
    assert r["rests_on"] == "demand shape"


def test_a_claim_that_cannot_be_evaluated_counts_as_broken():
    """Silence on an un-testable claim would read as survival."""
    bad = Claim("typo", "references a column that is not there",
                lambda r: r["nope"] < 0)
    v = check([bad], ROWS)
    assert not bool(v.iloc[0]["survives"])
    assert "KeyError" in v.iloc[0]["broken_under"]


def test_the_summary_counts_both_sides_and_refuses_to_call_survival_truth():
    v = check(CLAIMS, ROWS)
    s = summary(v)
    assert s["n_claims"] == 2 and s["n_broken"] == 2
    assert "not thereby true" in s["interpretation"]


def test_an_empty_sweep_reports_nothing_rather_than_universal_survival():
    assert summary(pd.DataFrame())["n_claims"] == 0


# -- bookkeeping -------------------------------------------------------------

def test_a_perturbation_records_why_it_is_plausible():
    p = Perturbation("midday_tilt", "periods", {"toward": ["midday"]},
                     rationale="period shares are shaped from US norms, not COTA data")
    assert "not COTA data" in p.rationale


def test_an_unknown_perturbation_kind_is_refused():
    with pytest.raises(ValueError):
        Perturbation("x", "vibes")
