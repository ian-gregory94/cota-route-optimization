"""State identity, cache keys and the objective — the things a wrong answer hides behind.

Experiment 2's defect was a cache key that omitted the waiting model, so three
days of Model A scores were served to a Model B run under a Model B label. The
tests here are the shape of that failure applied to every term of Experiment 3's
key, plus the permutation invariance that makes a state a set.
"""
import itertools

import pytest

from cota_opt import exp3
from cota_opt.geometry import GeometryEdit


def E(kind="truncate", route="A", **kw):
    kw.setdefault("description", "x")
    return GeometryEdit(kind=kind, route_id=route, **kw)


# -- the objective ---------------------------------------------------------

class F:
    """A FitnessVector stand-in with only the fields the objective reads."""
    def __init__(self, gc, unserved, served=100.0, vh=2500.0, peak=197.0):
        self.generalized_cost = gc
        self.unserved_demand = unserved
        self.served_demand = served
        self.revenue_veh_hours = vh
        self.peak_vehicles = peak
        self.gc_per_served_trip = gc / served if served else 0.0


def test_objective_is_gc_plus_lambda_times_weight_times_unserved():
    w = exp3.unserved_weight()
    f = F(gc=1000.0, unserved=10.0)
    assert exp3.objective(f, lam=2.0) == pytest.approx(1000.0 + 2.0 * w * 10.0)


def test_the_weight_comes_from_config_not_a_constant(tmp_path):
    """Change the config, and the objective changes with it."""
    (tmp_path / "cost_weights.yaml").write_text(
        "weights:\n  unserved: 7.0\n  walking: 2.0\n")
    assert exp3.unserved_weight(tmp_path) == 7.0
    f = F(gc=0.0, unserved=1.0)
    assert exp3.objective(f, lam=2.0, base=tmp_path) == pytest.approx(14.0)


def test_metrics_never_report_the_objective_alone():
    m = exp3.metrics(F(gc=1000.0, unserved=10.0))
    for k in exp3.COMPONENTS:
        assert k in m, f"{k} missing: the objective hides what the components show"
    assert "objective" in m and "lambda" in m


def test_peak_vehicles_is_reported_because_hours_are_not_buses():
    assert "peak_vehicles" in exp3.COMPONENTS
    assert "revenue_veh_hours" in exp3.COMPONENTS


# -- noise floors ----------------------------------------------------------

def test_a_floor_needs_three_replicates():
    with pytest.raises(ValueError, match="at least 3"):
        exp3.noise_floor([F(1.0, 1.0), F(1.0, 1.0)], effort="60000/2/32")


def test_a_floor_is_measured_for_the_objective_and_every_component():
    reps = [F(gc=1000.0, unserved=10.0), F(gc=1002.0, unserved=10.1),
            F(gc=998.0, unserved=9.9)]
    nf = exp3.noise_floor(reps, effort="60000/2/32")
    for k in ("objective", *exp3.COMPONENTS):
        assert k in nf.relative_pct
    assert nf.n_replicates == 3


def test_a_margin_may_not_be_compared_against_another_quantitys_floor():
    reps = [F(1000.0, 10.0), F(1002.0, 10.1), F(998.0, 9.9)]
    nf = exp3.noise_floor(reps, effort="60000/2/32")
    with pytest.raises(KeyError, match="different quantity"):
        nf.clears("unserved_demand_at_some_other_effort", 5.0)


def test_a_zero_spread_floor_does_not_let_everything_through():
    """Identical replicates give a zero floor; `clears` must still be strict."""
    reps = [F(1000.0, 10.0)] * 3
    nf = exp3.noise_floor(reps, effort="e")
    assert nf.relative_pct["objective"] == 0.0
    assert nf.clears("objective", 0.001)
    assert not nf.clears("objective", 0.0)


# -- state identity --------------------------------------------------------

def test_state_key_is_permutation_invariant():
    a = E(route="A", drop_stops=("S4",))
    b = E(route="B", drop_stops=("S5",))
    c = E(kind="add_stop", route="C", append_stops=("S3",))
    keys = {exp3.state_key(p) for p in itertools.permutations([a, b, c])}
    assert len(keys) == 1


def test_state_digest_is_permutation_invariant():
    a = E(route="A", drop_stops=("S4",))
    b = E(route="B", drop_stops=("S5",))
    digests = {exp3.state_digest(p) for p in itertools.permutations([a, b])}
    assert len(digests) == 1


def test_the_null_state_has_its_own_identity():
    assert exp3.state_key([]) == exp3.NULL_STATE
    assert exp3.state_digest([]) != exp3.state_digest([E()])


def test_rewording_a_description_does_not_create_a_new_candidate():
    a = GeometryEdit(kind="truncate", route_id="A", drop_stops=("S4",),
                     description="shorten A")
    b = GeometryEdit(kind="truncate", route_id="A", drop_stops=("S4",),
                     description="a completely different sentence",
                     evidence={"note": "and different evidence"})
    assert exp3.mutation_id(a) == exp3.mutation_id(b)


def test_different_truncations_of_one_route_do_not_collide():
    """`GeometryEdit.key` truncates stop lists; the canonical id must not."""
    a = E(route="A", drop_stops=("S3", "S4"))
    b = E(route="A", drop_stops=("S3", "S9"))
    assert a.key == b.key, "precondition: the old key really does collide"
    assert exp3.mutation_id(a) != exp3.mutation_id(b)


def test_drop_stop_order_does_not_change_a_mutations_identity():
    a = E(route="A", drop_stops=("S3", "S4"))
    b = E(route="A", drop_stops=("S4", "S3"))
    assert exp3.mutation_id(a) == exp3.mutation_id(b)


# -- cache keys ------------------------------------------------------------

def _key(**over):
    kw = dict(waiting_model="same_route", lam=2.0, seed=1, effort="60000/2/32",
              config_digest="abc123", pool_version="exp3-pool-v1")
    kw.update(over)
    return exp3.cache_key([E()], **kw)


@pytest.mark.parametrize("field,value", [
    ("waiting_model", "pattern"),
    ("lam", 4.0),
    ("seed", 2),
    ("effort", "400000/20/0"),
    ("config_digest", "def456"),
    ("pool_version", "exp3-pool-v2"),
])
def test_every_term_that_moves_a_score_moves_the_key(field, value):
    """The Experiment 2 defect, one term at a time.

    A cell keyed on the candidate alone was reused across two waiting models,
    and the run that resumed it inherited Model A numbers under a Model B label.
    """
    assert _key() != _key(**{field: value}), (
        f"{field} does not appear in the cache key, so a run that changes it "
        f"would be served the previous run's answer")


def test_the_state_itself_moves_the_key():
    kw = dict(waiting_model="same_route", lam=2.0, seed=1, effort="e",
              config_digest="c")
    assert (exp3.cache_key([E(route="A")], **kw)
            != exp3.cache_key([E(route="B")], **kw))


def test_the_key_is_permutation_invariant_in_the_state():
    kw = dict(waiting_model="same_route", lam=2.0, seed=1, effort="e",
              config_digest="c")
    a, b = E(route="A"), E(route="B", drop_stops=("S5",))
    assert exp3.cache_key([a, b], **kw) == exp3.cache_key([b, a], **kw)


def test_config_digest_is_content_addressed(tmp_path):
    (tmp_path / "assumptions.yaml").write_text("a: 1\n")
    (tmp_path / "cost_weights.yaml").write_text("w: 1\n")
    (tmp_path / "constraints.yaml").write_text("c: 1\n")
    first = exp3.config_digest(tmp_path)
    (tmp_path / "cost_weights.yaml").write_text("w: 2\n")
    assert exp3.config_digest(tmp_path) != first
    (tmp_path / "cost_weights.yaml").write_text("w: 1\n")
    assert exp3.config_digest(tmp_path) == first, (
        "a config edited and reverted must produce the key it started with")


def test_a_scored_row_carries_every_component_the_floor_needs():
    """A rename in `row()` must not break the noise floor silently.

    It did: `peak_vehicles` became `peak_concurrency` in the row and the
    floor's field list was not updated, so a Stage A shard died with a
    KeyError after scoring a state. The floor reads exp3.COMPONENTS, so this
    asserts a row can satisfy exactly that list.
    """
    from cota_opt.exp3_score import ScoredState
    s = ScoredState(state_key="x", state_digest="d", cardinality=0,
                    members=[], lam=2.0, seed=1, effort="e", seconds=1.0,
                    metrics=exp3.metrics(F(gc=1000.0, unserved=10.0)))
    row = s.row()
    for k in exp3.COMPONENTS:
        assert k in row or (k == "peak_vehicles"
                            and "peak_concurrency" in row), (
            f"the floor needs {k} and the row does not carry it under any name")


def test_the_row_is_json_serialisable():
    """Rows go to JSONL. NaN is not valid JSON."""
    import json
    from cota_opt.exp3_score import ScoredState
    s = ScoredState(state_key="x", state_digest="d", cardinality=0,
                    members=[], lam=2.0, seed=1, effort="e", seconds=1.0,
                    metrics=exp3.metrics(F(gc=1000.0, unserved=10.0)))
    text = json.dumps(s.row())
    assert "NaN" not in text and "Infinity" not in text
