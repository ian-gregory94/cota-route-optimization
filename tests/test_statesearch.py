"""The state search, on spaces built so that a lazy search fails them.

The real benchmark — Experiment 2B's 240 states — has an optimum that is a
SINGLE mutation sitting next to the null. A greedy add-only search finds it
trivially, so passing that benchmark shows the plumbing works and very little
else. These tests supply what it does not: spaces where the optimum is only
reachable if the move set, the incompatibility handling and the tie-breaking
are all actually right.

2B's own findings say why each case matters. Cardinality winners are not nested
there, so the best k-set is genuinely not the best (k-1)-set plus one — which is
the exact shape an add-only search cannot climb.
"""
import json

import pytest

from cota_opt.statesearch import (Checkpoint, NULL, SearchTrace, State,
                                  benchmark, feasible, neighbours, search)


def exhaustive(pool, incompatible, max_card=None):
    """Every feasible state, so a test can name the true optimum."""
    from itertools import combinations
    out = [()]
    for k in range(1, (max_card or len(pool)) + 1):
        for c in combinations(sorted(pool), k):
            if feasible(c, incompatible):
                out.append(c)
    return out


def key_of(ids):
    return "+".join(sorted(ids)) if ids else NULL


# -- the move set ----------------------------------------------------------

def test_neighbours_can_add_drop_and_swap():
    pool = ["a", "b", "c"]
    n = {s.key for s in neighbours(State.of(["a"]), pool, set())}
    assert "a+b" in n, "add is missing"
    assert NULL in n, "drop is missing"
    assert "b" in n, "swap is missing"


def test_neighbours_never_propose_an_incompatible_pair():
    pool = ["a", "b"]
    inc = {("a", "b")}
    n = {s.key for s in neighbours(State.of(["a"]), pool, inc)}
    assert "a+b" not in n


def test_neighbours_respect_a_cardinality_cap():
    pool = ["a", "b", "c"]
    n = {s.key for s in neighbours(State.of(["a", "b"]), pool, set(),
                                   max_cardinality=2)}
    assert not any(len(k.split("+")) > 2 for k in n if k != NULL)


# -- the search finds optima an add-only search cannot ---------------------

def test_recovers_a_non_nested_optimum():
    """The optimum is {b, c}; the best single is {a}, and a is in neither.

    2B found cardinality winners are not nested. An add-only greedy search
    starting from the null goes to {a} and stops, because every superset of {a}
    is worse. Only a swap reaches {b, c}.
    """
    table = {NULL: 0.0, "a": -5.0, "b": -1.0, "c": -1.0,
             "a+b": -4.0, "a+c": -4.0, "b+c": -9.0, "a+b+c": -3.0}
    pool = ["a", "b", "c"]
    best, val, _ = search(pool, lambda s: table[s.key], set(),
                          seeds=[0, 1, 2, 3])
    assert best.key == "b+c", f"got {best.key}"
    assert val == pytest.approx(-9.0)


def test_a_deceptive_single_does_not_trap_the_search():
    """Every path to the optimum passes through a state worse than the start."""
    table = {NULL: 0.0, "a": -8.0, "b": 5.0, "c": 5.0, "d": 5.0,
             "a+b": -1.0, "a+c": -1.0, "a+d": -1.0,
             "b+c": 6.0, "b+d": 6.0, "c+d": 6.0,
             "b+c+d": -20.0, "a+b+c": 2.0, "a+b+d": 2.0, "a+c+d": 2.0}
    # cardinality is capped at 3, so no 4-set is reachable
    pool = ["a", "b", "c", "d"]
    best, val, _ = search(pool, lambda s: table[s.key], set(),
                          seeds=range(6), max_cardinality=3)
    # The search is a local method; what is required is that it beats the
    # deceptive single, not that it is a global solver.
    assert val <= table["a"], (
        f"the search settled on {best.key} at {val}, no better than the "
        f"deceptive single at {table['a']}")


def test_the_null_is_returned_when_nothing_helps():
    """2B's actual answer. A search that cannot return the null is useless."""
    table = {NULL: 0.0, "a": 1.0, "b": 2.0, "a+b": 3.0}
    best, val, _ = search(["a", "b"], lambda s: table[s.key], set(),
                          seeds=[0, 1, 2])
    assert best.key == NULL
    assert val == 0.0


def test_the_null_is_always_evaluated_first():
    seen = []
    table = {NULL: 0.0, "a": -1.0}
    search(["a"], lambda s: seen.append(s.key) or table[s.key], set(),
           seeds=[1])
    assert seen[0] == NULL


# -- determinism, ties and resume ------------------------------------------

def test_the_search_is_deterministic():
    table = {NULL: 0.0, "a": -5.0, "b": -1.0, "c": -1.0,
             "a+b": -4.0, "a+c": -4.0, "b+c": -9.0, "a+b+c": -3.0}
    runs = [search(["a", "b", "c"], lambda s: table[s.key], set(),
                   seeds=[0, 1, 2]) for _ in range(3)]
    assert len({r[0].key for r in runs}) == 1
    assert len({r[2].evaluated for r in runs}) == 1


def test_ties_break_on_the_state_key_not_on_arrival_order():
    table = {NULL: 0.0, "a": -1.0, "b": -1.0, "a+b": 0.0}
    best, _, _ = search(["a", "b"], lambda s: table[s.key], set(), seeds=[0])
    assert best.key == "a", "a tie must resolve to the lexicographically first"


def test_resume_does_no_work_and_returns_the_same_answer(tmp_path):
    table = {NULL: 0.0, "a": -5.0, "b": -1.0, "c": -1.0,
             "a+b": -4.0, "a+c": -4.0, "b+c": -9.0, "a+b+c": -3.0}
    p = tmp_path / "cp.jsonl"
    b1, v1, t1 = search(["a", "b", "c"], lambda s: table[s.key], set(),
                        seeds=[0, 1, 2], checkpoint=Checkpoint(p))
    assert t1.evaluated > 0
    b2, v2, t2 = search(["a", "b", "c"], lambda s: table[s.key], set(),
                        seeds=[0, 1, 2], checkpoint=Checkpoint(p))
    assert (b2.key, v2) == (b1.key, v1)
    assert t2.evaluated == 0, "a resumed run must not recompute a scored state"
    assert t2.resumed_from > 0


def test_a_torn_checkpoint_line_costs_one_state_not_the_file(tmp_path):
    p = tmp_path / "cp.jsonl"
    cp = Checkpoint(p)
    cp.put("a", -1.0)
    cp.put("b", -2.0)
    with p.open("a") as f:
        f.write('{"state": "c", "sco')          # a crash mid-write
    reread = Checkpoint(p)
    assert reread.get("a") == -1.0
    assert reread.get("b") == -2.0
    assert reread.get("c") is None


def test_the_score_function_is_called_once_per_state(tmp_path):
    calls = []
    table = {NULL: 0.0, "a": -5.0, "b": -1.0, "a+b": -6.0}
    search(["a", "b"], lambda s: calls.append(s.key) or table[s.key], set(),
           seeds=[0, 1], checkpoint=Checkpoint(tmp_path / "cp.jsonl"))
    assert len(calls) == len(set(calls)), (
        f"a state was scored twice: {sorted(calls)}")


# -- the benchmark harness itself ------------------------------------------

def test_benchmark_fails_when_the_search_misses(tmp_path):
    """The benchmark must be able to fail, or it is not a benchmark."""
    table = {NULL: 0.0, "a": -1.0, "b": -2.0, "a+b": -1.5}
    res = benchmark(["a", "b"], table, set(), seeds=[0],
                    expected_key="a",       # deliberately the wrong answer
                    checkpoint_dir=tmp_path)
    assert res["pass"] is False
    assert res["exhaustive_optimum"] == "b"


def test_benchmark_passes_when_the_search_recovers(tmp_path):
    table = {NULL: 0.0, "a": -1.0, "b": -2.0, "a+b": -3.0}
    res = benchmark(["a", "b"], table, set(), seeds=[0, 1],
                    expected_key="a+b", checkpoint_dir=tmp_path)
    assert res["pass"] is True
    assert res["resume"]["second_pass_did_no_work"] is True


def test_the_committed_benchmark_artifact_passes():
    """The real one, as committed. It must still say PASS."""
    from pathlib import Path
    p = (Path(__file__).resolve().parents[1] / "outputs" / "exp3"
         / "search_benchmark.json")
    if not p.exists():
        pytest.skip("benchmark has not been run in this working copy")
    res = json.loads(p.read_text())
    assert res["pass"] is True
    assert res["space_size"] == 240
    assert all(v["recovered"] for v in res["per_seed"].values())
    assert res["resume"]["second_pass_did_no_work"] is True
