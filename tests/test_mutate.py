"""The frozen pool must reload into exactly what was frozen.

A pool that cannot be reloaded is not frozen: the next run regenerates it, and a
regenerated pool is a different pool the moment anything upstream moves. Worse,
`POOL_VERSION` is part of every cache key, so a mutation whose canonical id
shifts on reload makes every cached score for it unreachable while looking
identical in the artifact.
"""
import json
from pathlib import Path

import pytest

from cota_opt.exp3 import mutation_id
from cota_opt.geometry import EDIT_KINDS, GeometryEdit
from cota_opt.mutate import KIND_QUOTA, edit_from_record, incompatible_pairs

POOL = Path(__file__).resolve().parents[1] / "outputs" / "exp3" / "mutation_pool.json"


def _pool():
    if not POOL.exists():
        pytest.skip("the pool has not been generated in this working copy")
    return json.loads(POOL.read_text())


def test_every_frozen_mutation_round_trips_to_the_same_id():
    doc = _pool()
    for m in doc["mutations"]:
        e = edit_from_record(m)
        assert mutation_id(e) == m["id"], (
            f"{m['id']} reloads as {mutation_id(e)}; every cached score for it "
            f"would be unreachable")


def test_round_tripping_preserves_every_field_that_changes_behaviour():
    doc = _pool()
    for m in doc["mutations"]:
        e = edit_from_record(m)
        raw = m["raw"]
        assert list(e.drop_stops) == raw["drop_stops"]
        assert list(e.append_stops) == raw["append_stops"]
        assert list(e.replace_with) == raw["replace_with"]
        assert (list(e.replace_between) if e.replace_between else None) \
            == raw["replace_between"]


def test_the_pool_has_a_quota_for_every_kind_it_can_produce():
    assert set(KIND_QUOTA) == set(EDIT_KINDS), (
        f"quota and vocabulary disagree: {set(KIND_QUOTA) ^ set(EDIT_KINDS)}")


def test_no_kind_exceeds_its_quota():
    doc = _pool()
    for kind, n in doc["accepted_by_kind"].items():
        assert n <= KIND_QUOTA[kind], f"{kind}: {n} > {KIND_QUOTA[kind]}"


def test_unfilled_quotas_are_stated_not_hidden():
    """A count that looks like a choice must say when it was a limit."""
    doc = _pool()
    for kind, n in doc["accepted_by_kind"].items():
        if n < KIND_QUOTA[kind]:
            assert kind in doc["quotas_not_filled"], (
                f"{kind} accepted {n} of {KIND_QUOTA[kind]} without saying so")


def test_every_rule_fires_on_a_deliberately_illegal_mutation():
    doc = _pool()
    assert doc["rule_liveness"]["all_rules_fire"], (
        f"rules not enforced: {doc['rule_liveness']['not_enforced']}")
    assert doc["rule_liveness"]["checked"], "no probes were run"


def test_every_rejection_carries_a_rule_and_a_reason():
    doc = _pool()
    for r in doc["rejections"]:
        assert r["rule"] and r["reason"], r


def test_the_pool_is_sorted_canonically():
    """Enumeration order must not depend on generation order.

    2B lost 57 of 240 subsets to exactly this: the shard partition was index %
    n, so it depended on a list that was re-sorted mid-sweep.
    """
    doc = _pool()
    ids = [m["id"] for m in doc["mutations"]]
    assert ids == sorted(ids)


def test_incompatible_pairs_are_symmetric_and_structural():
    a = GeometryEdit(kind="truncate", route_id="A", drop_stops=("S1",),
                     description="a")
    b = GeometryEdit(kind="add_stop", route_id="A", append_stops=("S2",),
                     description="b")
    c = GeometryEdit(kind="truncate", route_id="B", drop_stops=("S3",),
                     description="c")
    pairs = incompatible_pairs([a, b, c])
    ia, ib = mutation_id(a), mutation_id(b)
    assert tuple(sorted((ia, ib))) in pairs
    assert len(pairs) == 1, "only the shared-route pair is incompatible"


def test_a_stop_one_mutation_anchors_on_and_another_removes_is_incompatible():
    a = GeometryEdit(kind="truncate", route_id="A", drop_stops=("S9",),
                     description="removes S9")
    b = GeometryEdit(kind="splice", route_id="B", with_route="C",
                     junction="S9", description="joins at S9")
    assert len(incompatible_pairs([a, b])) == 1


def test_the_frozen_pool_reloads_with_no_incompatibility_drift():
    """The committed pairs file must match what the loaded pool implies."""
    doc = _pool()
    pairs_file = POOL.parent / "incompatible_pairs.json"
    if not pairs_file.exists():
        pytest.skip("pairs file absent")
    committed = {tuple(sorted(p))
                 for p in json.loads(pairs_file.read_text())["pairs"]}
    edits = [edit_from_record(m) for m in doc["mutations"]]
    assert set(incompatible_pairs(edits)) == committed
