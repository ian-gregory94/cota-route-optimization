"""The two pieces of new machinery a 22-hour enumeration depends on.

Neither of these fails loudly. A content digest that collides makes a cache
return the wrong artifact and the run reports plausible numbers for the wrong
network -- which has already happened once in this project, when a path-set
cache was keyed by scenario NAME and a rerun with different scenario content
produced a healthy-looking cache hit. A subset enumerator that emits a set two
of whose splices share a route makes apply_edits raise 200 subsets into a
sweep, or, worse, would silently do nothing if apply_edits were ever made
lenient.

So both are tested for the property that matters rather than for a sample
output: the digest separates anything that differs and ignores anything that
does not, and the enumeration is exactly the set of subsets the incompatibility
relation permits.
"""
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from cota_opt.cache import digest
from exp2b_subsets import feasible_subsets, set_key


# --------------------------------------------------------------------------
# content digest
# --------------------------------------------------------------------------

def test_digest_is_stable_across_equal_values():
    a = {"x": np.arange(5), "df": pd.DataFrame({"a": [1, 2]}), "s": "q"}
    b = {"s": "q", "df": pd.DataFrame({"a": [1, 2]}), "x": np.arange(5)}
    assert digest(a) == digest(b)


def test_digest_separates_a_single_changed_element():
    base = np.arange(100.0)
    other = base.copy()
    other[57] += 1e-9
    assert digest(base) != digest(other)


def test_digest_separates_shape_and_dtype():
    assert digest(np.zeros(6)) != digest(np.zeros((2, 3)))
    assert digest(np.zeros(6, dtype=np.float32)) != digest(np.zeros(6, dtype=np.float64))


def test_digest_separates_dataframe_column_names():
    assert (digest(pd.DataFrame({"a": [1, 2]}))
            != digest(pd.DataFrame({"b": [1, 2]})))


def test_digest_separates_sequence_order():
    assert digest([1, 2, 3]) != digest([3, 2, 1])


def test_digest_separates_nested_difference():
    a = {"net": {"pat": [np.arange(3), np.arange(4)]}}
    b = {"net": {"pat": [np.arange(3), np.arange(5)]}}
    assert digest(a) != digest(b)


def test_digest_distinguishes_types_with_equal_reprs():
    # 1 == 1.0 == True in Python; a cache key must not treat them as one input
    keys = {digest(1), digest(1.0), digest(True), digest("1")}
    assert len(keys) == 4


def test_digest_terminates_on_a_cycle():
    d = {}
    d["self"] = d
    assert isinstance(digest(d), str)


# --------------------------------------------------------------------------
# subset enumeration
# --------------------------------------------------------------------------

def _pairs(keys):
    """The project's own rule: a splice consumes both its routes, so two
    splices sharing a route cannot coexist."""
    def routes(k):
        p = k.split("|")
        return {p[1], p[2]}
    out = set()
    for a, b in itertools.combinations(keys, 2):
        if routes(a) & routes(b):
            out.add((a, b))
            out.add((b, a))
    return out


CANDS = ["splice|001|021|A", "splice|005|006|B", "splice|005|021|C",
         "splice|006|021|D", "splice|033|034|E"]


def test_every_emitted_subset_is_pairwise_compatible():
    inc = _pairs(CANDS)
    for combo in feasible_subsets(CANDS, inc):
        for a, b in itertools.combinations(combo, 2):
            assert (a, b) not in inc


def test_enumeration_is_complete():
    """Not a sample: every compatible subset of the powerset must appear."""
    inc = _pairs(CANDS)
    got = {frozenset(c) for c in feasible_subsets(CANDS, inc)}
    want = set()
    for r in range(len(CANDS) + 1):
        for combo in itertools.combinations(CANDS, r):
            if not any((a, b) in inc for a, b in itertools.combinations(combo, 2)):
                want.add(frozenset(combo))
    assert got == want


def test_enumeration_has_no_duplicates_and_includes_the_empty_set():
    subs = feasible_subsets(CANDS, _pairs(CANDS))
    assert len(subs) == len({frozenset(c) for c in subs})
    assert () in subs


def test_enumeration_is_ordered_by_ascending_cardinality():
    """An interrupted sweep must leave complete evidence for the small sets."""
    sizes = [len(c) for c in feasible_subsets(CANDS, _pairs(CANDS))]
    assert sizes == sorted(sizes)


def test_set_key_is_permutation_invariant():
    a = ("splice|005|006|B", "splice|033|034|E")
    assert set_key(a) == set_key(tuple(reversed(a)))
    assert set_key(()) == "<none>"


def test_no_incompatibility_means_the_full_powerset():
    subs = feasible_subsets(CANDS, set())
    assert len(subs) == 2 ** len(CANDS)


def test_frozen_candidate_set_enumerates_to_the_committed_count():
    """The committed gate 2B-1 number. If the candidate set or the
    incompatibility rule changes, this fails and the gate has to be re-stated
    rather than quietly drifting."""
    import json
    p = Path(__file__).resolve().parents[1] / "outputs" / "exp2_candidate_classes.json"
    if not p.exists():
        pytest.skip("classification artifact not built in this checkout")
    d = json.loads(p.read_text())
    inc = set()
    for pr in d["incompatible_pairs"]:
        inc.add((pr["a"], pr["b"]))
        inc.add((pr["b"], pr["a"]))
    subs = feasible_subsets(d["rule"]["eligible_for_2B"], inc)
    assert len(subs) == 240
    assert max(len(c) for c in subs) == 6
