"""The enumeration cache key must mean what pathsets_with says it means.

pathsets_with documents that its tag identifies the scenario list exactly,
because the tag IS the cache key -- two lists sharing a tag return each other's
path sets. Joining scenario names satisfied the type and not the contract:
'opt_it0_lam2.0' is stable across runs while the plan it carries is not. After
the search RNG changed, iteration 1 loaded path sets enumerated from the
previous run's plans, from a cache hit that looked perfectly healthy.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fixpoint import scenario_tag


def _plan(**kw):
    base = {("001", "am_peak"): 12.0, ("002", "midday"): 30.0}
    base.update({tuple(k.split("_", 1)): v for k, v in kw.items()})
    return base


def test_no_scenarios_is_the_base_set():
    assert scenario_tag([]) == "base"


def test_the_same_plans_under_the_same_names_hash_the_same():
    a = scenario_tag([("opt_it0_lam2.0", _plan())])
    b = scenario_tag([("opt_it0_lam2.0", _plan())])
    assert a == b


def test_different_plans_under_the_same_name_do_not_collide():
    """This is the bug: a stable name over a changed plan."""
    a = scenario_tag([("opt_it0_lam2.0", _plan())])
    b = scenario_tag([("opt_it0_lam2.0", {**_plan(), ("001", "am_peak"): 15.0})])
    assert a != b


def test_a_single_ladder_step_moves_the_key():
    a = scenario_tag([("s", _plan())])
    b = scenario_tag([("s", {**_plan(), ("002", "midday"): 29.0})])
    assert a != b


def test_the_name_still_participates():
    """Two identical plans under different names are different scenario lists."""
    a = scenario_tag([("opt_it0_lam2.0", _plan())])
    b = scenario_tag([("opt_it1_lam2.0", _plan())])
    assert a != b


def test_scenario_order_is_part_of_the_list():
    p, q = _plan(), {**_plan(), ("001", "am_peak"): 20.0}
    assert scenario_tag([("a", p), ("b", q)]) != scenario_tag([("b", q), ("a", p)])


def test_dictionary_insertion_order_within_a_plan_does_not_matter():
    """The plan is a mapping; its iteration order is not part of its identity."""
    fwd = {("001", "am_peak"): 12.0, ("002", "midday"): 30.0}
    rev = {("002", "midday"): 30.0, ("001", "am_peak"): 12.0}
    assert scenario_tag([("s", fwd)]) == scenario_tag([("s", rev)])


def test_the_tag_is_short_and_marked():
    t = scenario_tag([("s", _plan())])
    assert t.startswith("sc-") and len(t) == 19
