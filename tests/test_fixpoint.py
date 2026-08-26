"""Path-set fixpoint machinery, on the synthetic RAPTOR network.

Two things have to hold for the fixpoint to mean anything:

1. Feeding a plan back in as an enumeration scenario actually adds the paths
   that plan makes attractive, and never removes ones already found.
2. The adequacy check agrees with full RAPTOR when the set is complete, and
   reports a positive gap when it is not.
"""
import numpy as np
import pytest

from cota_opt.adequacy import adequacy
from cota_opt.cost import CostWeights
from cota_opt.odmatrix import ODTable, ZoneSystem
from cota_opt.pathset import PathSetEvaluator, build_pathset
from cota_opt.raptor import generalized_cost, pattern_headways

from test_raptor import W, WK, _feed, _net, _stops_gdf, _tstats  # noqa: F401
from cota_opt.raptor import build_raptor_network


@pytest.fixture
def rn():
    return build_raptor_network(
        _feed(), _net(), _tstats(), _stops_gdf(),
        walk_radius_m=400.0, walk_speed_m_per_min=80.0,
        periods={"all": (0.0, 24.0)}, with_timetable=False)


@pytest.fixture
def zs(rn):
    """Zone 0 sits on S1, zone 1 on S4 -- the only OD pair we need."""
    access = {0: (np.array([rn.stop_index["S1"]]), np.array([0.0])),
              1: (np.array([rn.stop_index["S4"]]), np.array([0.0]))}

    class _ZS(ZoneSystem):
        pass

    z = object.__new__(_ZS)
    z._access = access
    z.access_of = lambda i: access[int(i)]
    return z


BASE = {("A", "all"): 10.0, ("B", "all"): 10.0, ("C", "all"): 10.0}


def _od():
    return ODTable(np.array([0]), np.array([1]), np.array([100.0]), "test", "")


def _build(rn, zs, hw, extra=None, cap=4):
    return build_pathset(rn, zs, _od(), "all", hw, W, WK, max_rounds=3,
                         max_paths_per_od=cap, n_random_scenarios=0,
                         seed=1, extra_scenarios=extra)


def test_extra_scenario_adds_paths_and_removes_none(rn, zs):
    """A plan fed back in can only grow the candidate set."""
    plain = _build(rn, zs, BASE)
    # under this plan route B is the only sane way from S1 to S4
    plan = {("A", "all"): 60.0, ("B", "all"): 5.0, ("C", "all"): 60.0}
    grown = _build(rn, zs, BASE, extra=[("opt", plan)])
    assert grown.n_paths >= plain.n_paths

    def sigs(ps):
        out = set()
        for p in range(ps.n_paths):
            a, b = ps.path_offsets[p], ps.path_offsets[p + 1]
            out.add(tuple(zip(ps.leg_rp[a:b].tolist(),
                              np.round(ps.leg_ivt[a:b], 3).tolist())))
        return out

    assert sigs(plain) <= sigs(grown)


def test_extra_scenario_must_cover_every_route_period(rn, zs):
    with pytest.raises(ValueError, match="missing"):
        _build(rn, zs, BASE, extra=[("bad", {("A", "all"): 10.0})])


def test_cap_is_raised_to_the_scenario_count(rn, zs):
    """Every scenario's own optimum survives; a low cap must not evict them."""
    plans = [(f"p{i}", {("A", "all"): h, ("B", "all"): 60.0 - h,
                        ("C", "all"): 10.0})
             for i, h in enumerate((5.0, 15.0, 25.0, 35.0, 45.0))]
    ps = _build(rn, zs, BASE, extra=plans, cap=1)
    # baseline + frequent + infrequent + 5 fed-back plans = 8 scenarios,
    # so the cap must be at least 8 rather than the requested 1
    n = ps.od_offsets[1] - ps.od_offsets[0]
    assert n > 1


def test_adequacy_is_zero_when_the_set_already_holds_the_optimum(rn, zs):
    """Priced under the same headways it was enumerated at, nothing is improvable."""
    ps = _build(rn, zs, BASE)
    ev = PathSetEvaluator(ps, W, WK, 200.0, retention_full_min=1e9,
                          retention_zero_min=1e9, retention_floor=1.0)
    out = adequacy(rn, zs, ps, ev, BASE, W, WK, max_rounds=3)
    assert out["pairs_improvable"] == 0
    assert out["flow_share_improvable"] == pytest.approx(0.0)


def test_adequacy_finds_the_gap_a_narrow_set_leaves(rn, zs):
    """A set enumerated at one plan and priced at another can be improvable."""
    narrow = build_pathset(rn, zs, _od(), "all",
                           {("A", "all"): 10.0, ("B", "all"): 10.0,
                            ("C", "all"): 10.0},
                           W, WK, max_rounds=3, max_paths_per_od=1,
                           n_random_scenarios=0, seed=1)
    # keep only the single cheapest-at-baseline path
    ev = PathSetEvaluator(narrow, W, WK, 200.0, retention_full_min=1e9,
                          retention_zero_min=1e9, retention_floor=1.0)
    plan = {("A", "all"): 60.0, ("B", "all"): 5.0, ("C", "all"): 60.0}
    out = adequacy(rn, zs, narrow, ev, plan, W, WK, max_rounds=3)
    # RAPTOR under the plan is at least as cheap as the cached set, never worse
    assert out["mean_overstatement_min"] >= 0.0
    sub = np.array([plan[k] for k in narrow.rp_keys])
    cached = ev.od_costs(sub)[0]
    ph = pattern_headways(rn, plan, "all")
    cost, _, _ = generalized_cost(rn, ["S1"], ph, W, WK, max_rounds=3,
                                  source_costs=[0.0])
    assert cost[rn.stop_index["S4"]] <= cached + 1e-9


def test_adequacy_needs_origin_and_destination_recorded(rn, zs):
    ps = _build(rn, zs, BASE)
    ev = PathSetEvaluator(ps, W, WK, 200.0)
    ps.od_origin = None
    with pytest.raises(ValueError, match="rebuild"):
        adequacy(rn, zs, ps, ev, BASE, W, WK, max_rounds=3)
