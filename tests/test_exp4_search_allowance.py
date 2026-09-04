"""The Experiment 4 effort contract: allocated opportunity, not realised counts.

Staged mechanism (`scripts/exp4_staging/search_allowance.py`), tested before it
is put in force. Every test below is one of the cases the contract enumerates.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cota_opt.firewall.search_allowance import (AllowanceError,  # noqa: E402
                                           AllowanceRecord, SearchAllowance,
                                           comparable)

K = 400
CEILING = 400_000
A = SearchAllowance(k=K, absolute_ceiling=CEILING)
DIGEST = "alw-abc123"


def rec(d: int, *, allowance=A, digest=DIGEST, budget=None, limited=None,
        performed=0):
    b, lim = allowance.allocate(d)
    return AllowanceRecord(
        decision_dimensions=d, allowance_digest=digest,
        evaluation_budget=b if budget is None else budget,
        budget_limited=lim if limited is None else limited,
        evaluations_performed=performed)


# --- allocation ----------------------------------------------------------

def test_equal_decision_counts_get_equal_budgets():
    assert A.allocate(173) == A.allocate(173)
    assert rec(173).evaluation_budget == rec(173).evaluation_budget


def test_budgets_scale_by_the_declared_function():
    b1, _ = A.allocate(100)
    b2, _ = A.allocate(200)
    assert b1 == K * 100
    assert b2 == K * 200 == 2 * b1


def test_a_network_with_no_decisions_is_not_a_cell():
    with pytest.raises(AllowanceError):
        A.allocate(0)


def test_the_rounding_rule_must_be_one_of_the_declared_ones():
    with pytest.raises(AllowanceError):
        SearchAllowance(k=K, absolute_ceiling=CEILING, rounding="to_taste")
    assert SearchAllowance(k=K, absolute_ceiling=CEILING,
                           rounding="up_to_1000").allocate(101)[0] == 41_000


def test_a_minimum_budget_is_applied_deterministically():
    a = SearchAllowance(k=10, absolute_ceiling=CEILING, minimum_budget=5_000)
    assert a.allocate(10)[0] == 5_000          # 10*10 = 100, floored to 5000
    assert a.allocate(1_000)[0] == 10_000      # above the minimum


# --- the same allowance on both sides ------------------------------------

def test_identical_k_is_required():
    other = SearchAllowance(k=K * 2, absolute_ceiling=CEILING)
    a = rec(100)
    b = rec(100, allowance=other, digest="alw-other")
    ok, why = comparable(a, b, A)
    assert not ok
    assert any("allowance" in w for w in why)


def test_different_decision_counts_are_fine_under_the_same_allowance():
    ok, why = comparable(rec(173), rec(150), A)
    assert ok, why


# --- realised counts are diagnostic --------------------------------------

def test_different_realised_evaluation_counts_are_allowed():
    """Same stopping contract, different outcomes. That is what outcomes are."""
    ok, why = comparable(rec(173, performed=4_000),
                         rec(150, performed=61_500), A)
    assert ok, why


def test_realised_counts_do_not_enter_the_verdict_at_all():
    a, b = rec(173, performed=1), rec(173, performed=999_999)
    assert comparable(a, b, A)[0]


# --- post-hoc interference -----------------------------------------------

def test_a_post_hoc_budget_increase_is_rejected():
    """A receipt can say anything; it cannot say what the function would not."""
    cheat = rec(100)
    cheat = AllowanceRecord(decision_dimensions=100,
                            allowance_digest=DIGEST,
                            evaluation_budget=cheat.evaluation_budget * 3,
                            budget_limited=False)
    ok, why = comparable(rec(100), cheat, A)
    assert not ok
    assert any("chose after seeing" in w for w in why)


def test_a_budget_that_ignores_the_decision_count_is_rejected():
    flat = AllowanceRecord(decision_dimensions=150, allowance_digest=DIGEST,
                           evaluation_budget=K * 173, budget_limited=False)
    ok, _ = comparable(rec(173), flat, A)
    assert not ok


def test_a_mislabelled_budget_limited_flag_is_rejected():
    r = rec(100)
    lying = AllowanceRecord(decision_dimensions=100, allowance_digest=DIGEST,
                            evaluation_budget=r.evaluation_budget,
                            budget_limited=True)      # ceiling does not bind
    ok, why = comparable(rec(100), lying, A)
    assert not ok
    assert any("contradicts the allocation" in w for w in why)


# --- the ceiling is honest about itself ----------------------------------

def test_the_ceiling_binds_and_is_marked():
    d = CEILING // K + 50
    budget, limited = A.allocate(d)
    assert budget == CEILING and limited is True


def test_a_ceiling_bound_comparison_is_refused_by_default():
    big = rec(CEILING // K + 50)
    assert big.budget_limited
    ok, why = comparable(rec(100), big, A)
    assert not ok
    assert any("equivalent normalised search opportunity" in w for w in why)


def test_a_ceiling_bound_comparison_needs_a_written_justification():
    big = rec(CEILING // K + 50)
    assert not comparable(rec(100), big, A, permit_budget_limited="  ")[0]
    ok, why = comparable(
        rec(100), big, A,
        permit_budget_limited="both arms converged well inside the ceiling; "
                              "see the Experiment 4 convergence audit")
    assert ok, why


def test_both_arms_ceiling_bound_still_needs_the_declaration():
    """Equally starved is not the same as equally fed."""
    d = CEILING // K + 50
    ok, _ = comparable(rec(d), rec(d), A)
    assert not ok


def test_the_preregistered_allowance_is_declared_and_does_not_bind_on_gen1_sizes():
    """k, the ceiling, the minimum and the rounding are preregistered.

    The allowance must not bind in ordinary cases. If it did, it would silently
    become the stopping rule and the stopping contract would stop meaning
    anything -- which is D28 wearing different clothes, where an iteration
    ceiling that never bound was quoted as search depth.
    """
    from cota_opt.firewall import EXP4_ALLOWANCE as A

    assert (A.k, A.absolute_ceiling, A.minimum_budget, A.rounding) == (
        2000, 400_000, 20_000, "up_to_1000")

    # Gen1's network carries 173 route-periods; the ceiling must not bind there.
    budget, limited = A.allocate(173)
    assert not limited and budget == 346_000

    # The floor protects a heavily reduced network from a meaningless search.
    assert A.allocate(3) == (20_000, False)

    # The ceiling exists and is honest when it fires.
    assert A.allocate(200) == (400_000, False)
    assert A.allocate(205)[1] is True


def test_changing_the_preregistered_allowance_changes_its_digest():
    """A post-hoc change to k must be detectable, not merely discouraged."""
    from cota_opt.firewall import EXP4_ALLOWANCE as A
    from cota_opt.firewall import SearchAllowance, digest

    tampered = SearchAllowance(k=A.k * 2, absolute_ceiling=A.absolute_ceiling,
                               minimum_budget=A.minimum_budget,
                               rounding=A.rounding)
    assert digest(tampered.digest_fields) != digest(A.digest_fields)
