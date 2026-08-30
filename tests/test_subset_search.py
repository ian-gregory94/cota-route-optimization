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


# --------------------------------------------------------------------------
# the analysis that turns raw subset scores into the experiment's answer
# --------------------------------------------------------------------------

from exp2b_subsets import analyse


def _frame(rows, lam=2.0):
    out = []
    for key, members, unserved, gc in rows:
        out.append({
            "set_key": key, "members": list(members),
            "cardinality": len(members), "lambda": lam,
            "modelB_unserved": unserved, "modelB_gc": gc,
            "modelB_served": 30000.0 - unserved,
            "modelB_gc_per_trip": gc / (30000.0 - unserved),
        })
    return pd.DataFrame(out)


def test_vs_noedit_is_measured_against_the_empty_set():
    df = analyse(_frame([
        ("<none>", (), 10000.0, 1_000_000.0),
        ("a", ("a",), 9900.0, 1_010_000.0),
    ]), floor=0.288)
    r = df[df.set_key == "a"].iloc[0]
    assert r["unserved_vs_noedit_pct"] == pytest.approx(-1.0)
    assert r["gc_vs_noedit_pct"] == pytest.approx(1.0)
    # and the empty set is its own reference, so it must read as exactly zero
    z = df[df.set_key == "<none>"].iloc[0]
    assert z["unserved_vs_noedit_pct"] == pytest.approx(0.0)


def test_perfectly_additive_pair_reads_as_additive():
    df = analyse(_frame([
        ("<none>", (), 10000.0, 1_000_000.0),
        ("a", ("a",), 9900.0, 1_000_000.0),      # -1.0 pts
        ("b", ("b",), 9800.0, 1_000_000.0),      # -2.0 pts
        ("a+b", ("a", "b"), 9700.0, 1_000_000.0),  # -3.0 pts = the sum
    ]), floor=0.288)
    r = df[df.set_key == "a+b"].iloc[0]
    assert r["sum_of_singles_unserved_pct"] == pytest.approx(-3.0)
    assert r["interaction_unserved_pts"] == pytest.approx(0.0, abs=1e-9)
    assert r["interaction_class"] == "additive within measurement"


def test_a_pair_delivering_less_than_its_members_is_substituting():
    """D20's pattern: each edit helps, the pair delivers under half of it."""
    df = analyse(_frame([
        ("<none>", (), 10000.0, 1_000_000.0),
        ("a", ("a",), 9900.0, 1_000_000.0),
        ("b", ("b",), 9800.0, 1_000_000.0),
        ("a+b", ("a", "b"), 9950.0, 1_000_000.0),   # -0.5 against a promised -3
    ]), floor=0.288)
    r = df[df.set_key == "a+b"].iloc[0]
    assert r["interaction_unserved_pts"] == pytest.approx(2.5)
    assert r["interaction_class"] == "substituting"


def test_a_pair_beating_its_members_is_synergistic():
    df = analyse(_frame([
        ("<none>", (), 10000.0, 1_000_000.0),
        ("a", ("a",), 9900.0, 1_000_000.0),
        ("b", ("b",), 9800.0, 1_000_000.0),
        ("a+b", ("a", "b"), 9500.0, 1_000_000.0),   # -5 against a promised -3
    ]), floor=0.288)
    r = df[df.set_key == "a+b"].iloc[0]
    assert r["interaction_unserved_pts"] == pytest.approx(-2.0)
    assert r["interaction_class"] == "synergistic"


def test_singles_and_the_empty_set_are_never_classified():
    df = analyse(_frame([
        ("<none>", (), 10000.0, 1_000_000.0),
        ("a", ("a",), 9900.0, 1_000_000.0),
    ]), floor=0.288)
    assert set(df["interaction_class"]) == {""}


def test_a_set_whose_member_was_not_measured_gets_no_interaction():
    """A partial sweep must leave the term missing, not silently treat the
    absent single as zero -- which would read as a large false synergy."""
    df = analyse(_frame([
        ("<none>", (), 10000.0, 1_000_000.0),
        ("a", ("a",), 9900.0, 1_000_000.0),
        ("a+b", ("a", "b"), 9700.0, 1_000_000.0),
    ]), floor=0.288)
    r = df[df.set_key == "a+b"].iloc[0]
    assert not np.isfinite(r["interaction_unserved_pts"])
    assert r["interaction_class"] == ""


def test_lambdas_are_analysed_independently():
    a = _frame([("<none>", (), 10000.0, 1e6), ("a", ("a",), 9900.0, 1e6)], lam=1.0)
    b = _frame([("<none>", (), 20000.0, 2e6), ("a", ("a",), 19000.0, 2e6)], lam=2.0)
    df = analyse(pd.concat([a, b], ignore_index=True), floor=0.288)
    got = {r["lambda"]: r["unserved_vs_noedit_pct"]
           for _, r in df[df.set_key == "a"].iterrows()}
    assert got[1.0] == pytest.approx(-1.0)
    assert got[2.0] == pytest.approx(-5.0)


def test_missing_zero_edit_row_does_not_fabricate_a_comparison():
    df = analyse(_frame([("a", ("a",), 9900.0, 1e6)]), floor=0.288)
    assert "unserved_vs_noedit_pct" not in df or df["unserved_vs_noedit_pct"].isna().all()


# --------------------------------------------------------------------------
# filenames every filesystem can hold
# --------------------------------------------------------------------------

from run_exp2_eval import safe_name, WINDOWS_FORBIDDEN


def test_safe_name_removes_every_character_windows_forbids():
    got = safe_name('a<b>c:d"e/f\\g|h?i*j')
    assert not any(c in got for c in WINDOWS_FORBIDDEN)


def test_safe_name_keeps_a_candidate_key_readable():
    assert safe_name("single:splice|033|034|WESHIGW") == "single-splice-033-034-WESHIGW"


def test_safe_name_strips_trailing_dots_and_spaces():
    # Windows silently drops these, so two labels could collide into one file
    assert safe_name("plan. ") == "plan"
    assert safe_name("...") == "unnamed"


def test_safe_name_is_injective_on_the_frozen_candidate_set():
    """Sanitising must not merge two candidates into one filename."""
    import json
    p = Path(__file__).resolve().parents[1] / "outputs" / "exp2_candidate_classes.json"
    if not p.exists():
        pytest.skip("classification artifact not built in this checkout")
    keys = json.loads(p.read_text())["rule"]["eligible_for_2B"]
    labels = [f"single:{k}" for k in keys]
    assert len({safe_name(x) for x in labels}) == len(labels)


def test_no_tracked_path_is_unusable_on_windows():
    """A repo that cannot be checked out on Windows shows those files as
    permanently deleted there, and a "commit all" from such a clone removes
    them from history. This caught 24 of them."""
    import subprocess
    root = Path(__file__).resolve().parents[1]
    try:
        out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True,
                             text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git not available")
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    # U+F07C is what Windows substitutes for a pipe when a file crosses from a
    # Linux checkout: it looks like "|" and is not one, so a Windows clone
    # committed 24 lookalike duplicates of files this repo already had.
    bad = [p for p in out.stdout.splitlines()
           if any(c in Path(p).name for c in WINDOWS_FORBIDDEN)
           or "\uf07c" in p]
    assert not bad, f"paths unusable on Windows: {bad[:5]}"


# --------------------------------------------------------------------------
# sharding
# --------------------------------------------------------------------------

def _shard(subs, i, n):
    return [c for j, c in enumerate(subs) if j % n == i]


def test_shards_partition_the_sweep_exactly():
    """Disjoint and complete. An overlap wastes a worker's hours on subsets
    the other already solved; a gap silently drops them from a sweep whose
    whole claim is that it is exhaustive."""
    subs = feasible_subsets(CANDS, _pairs(CANDS))
    for n in (2, 3, 4):
        parts = [_shard(subs, i, n) for i in range(n)]
        keys = [{set_key(c) for c in p} for p in parts]
        assert sum(len(p) for p in parts) == len(subs)
        assert set().union(*keys) == {set_key(c) for c in subs}
        for a in range(n):
            for b in range(a + 1, n):
                assert not (keys[a] & keys[b])


def test_every_shard_still_ascends_in_cardinality():
    subs = feasible_subsets(CANDS, _pairs(CANDS))
    for i in range(3):
        sizes = [len(c) for c in _shard(subs, i, 3)]
        assert sizes == sorted(sizes)


def test_shard_zero_holds_the_empty_set():
    """The zero-edit reference every other subset is measured against. It has
    to be solved, and shard 0 is the one that gets it under any n."""
    subs = feasible_subsets(CANDS, _pairs(CANDS))
    for n in (1, 2, 3, 5):
        assert () in _shard(subs, 0, n)


def test_shard_is_parsed_before_it_is_used():
    """Regression: the shard filter was inserted above the line that parses
    --shard, so every sharded worker died on an UnboundLocalError before doing
    any work -- and the supervisor dutifully restarted it, forever."""
    src = (Path(__file__).resolve().parents[1] / "scripts"
           / "exp2b_subsets.py").read_text()
    assert src.index("si, sn = (int(x)") < src.index("if sn > 1:")


# --------------------------------------------------------------------------
# the evaluator must be the model the run asked for
# --------------------------------------------------------------------------

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def test_the_evaluation_script_threads_the_pricing_through():
    """Regression, and the most expensive bug in this project so far.

    run_exp2_eval.py built its evaluator with build_setup() and did not pass
    common_lines, so it fell back to the config default -- `pattern`, Model A.
    Every run launched with --common-lines same_route logged the harness's
    "waiting model: same_route" and then scored every plan under Model A. Three
    discoveries, two noise floors and a full-effort falsification test were
    labelled Model B and were not.
    """
    src = (SCRIPTS / "run_exp2_eval.py").read_text()
    i = src.index("setup = build_setup(")
    call = src[i:src.index("return setup", i)]
    assert "common_lines=" in call, (
        "build_setup called without common_lines: the evaluator will silently "
        "use the config default instead of the model the run asked for")
    assert "H.common_lines" in src


def test_the_evaluation_script_refuses_a_mismatched_evaluator():
    src = (SCRIPTS / "run_exp2_eval.py").read_text()
    assert 'setup.checks.get("common_lines")' in src
    assert "refusing to score plans under a" in src


def test_build_setup_records_where_its_pricing_came_from():
    """A run's own artifacts must show whether the pricing was chosen or
    defaulted. Nothing in the affected runs recorded it, which is why the
    mislabel survived three days."""
    src = (Path(__file__).resolve().parents[1] / "src" / "cota_opt"
           / "exp2.py").read_text()
    assert 'checks["common_lines_source"]' in src
    # and the fallback must be a WARNING, not an INFO line a reader can miss
    assert "CONFIG DEFAULT" in src
    i = src.index("CONFIG DEFAULT")
    assert "log.warning" in src[max(0, i - 300):i], (
        "the config-default fallback must warn: an INFO line is exactly what "
        "nobody read for three days")


def test_ladder_from_refuses_to_fall_back_silently():
    """The rung cells are tagged "m" whenever --ladder-from was PASSED, not
    whenever it was honoured. A missing file therefore produced a
    screen-ordered ladder filed as the measured-ordered one, and nothing
    downstream could tell the difference."""
    src = (SCRIPTS / "run_exp2_eval.py").read_text()
    i = src.index("ladder_from")
    seg = src[i:i + 3000]
    assert "falling back to screen order" not in seg
    assert "Refusing to fall back to" in seg


# --------------------------------------------------------------------------
# evaluator provenance in the artifact, not the log
# --------------------------------------------------------------------------

from types import SimpleNamespace

from cota_opt.experiment import Experiment


def _exp(tmp_path):
    return Experiment(name="t", seed=1, algorithm="a", root=tmp_path)


def test_declaring_model_b_records_it(tmp_path):
    e = _exp(tmp_path)
    e.declare_evaluator(SimpleNamespace(checks={
        "common_lines": "same_route", "common_lines_source": "explicit"}),
        expected="same_route")
    assert e.record.evaluator["common_lines"] == "same_route"
    assert e.record.evaluator["source"] == "explicit"


def test_declaring_model_b_against_a_model_a_setup_raises(tmp_path):
    """The bug, as a test. A run asking for Model B and handed a Model A
    evaluator must produce no artifact rather than a mislabelled one."""
    e = _exp(tmp_path)
    with pytest.raises(ValueError, match="asked for"):
        e.declare_evaluator(SimpleNamespace(checks={
            "common_lines": "pattern", "common_lines_source": "config default"}),
            expected="same_route")


def test_a_setup_that_cannot_say_raises(tmp_path):
    e = _exp(tmp_path)
    with pytest.raises(ValueError, match="does not report common_lines"):
        e.declare_evaluator(SimpleNamespace(checks={}), expected="same_route")


def test_the_saved_artifact_carries_the_evaluator(tmp_path):
    e = _exp(tmp_path)
    e.declare_evaluator(SimpleNamespace(checks={
        "common_lines": "same_route", "common_lines_source": "explicit"}),
        expected="same_route")
    import json
    d = json.loads(e.save().read_text())
    assert d["evaluator"]["common_lines"] == "same_route"


def test_saving_without_declaring_leaves_the_field_null_not_absent(tmp_path):
    """An artifact that never declared must be distinguishable from one that
    declared Model A — silence is not evidence of either."""
    import json
    d = json.loads(_exp(tmp_path).save().read_text())
    assert "evaluator" in d and d["evaluator"] is None


def test_every_scoring_script_declares_its_evaluator():
    for name in ("run_exp2_eval.py", "exp2_treatments.py", "exp2b_subsets.py"):
        src = (SCRIPTS / name).read_text()
        assert "declare_evaluator(" in src, f"{name} writes artifacts without "
        "recording which model scored them"


def test_the_partition_does_not_depend_on_input_order():
    """The shard slice is index %% n, so it depends on the enumeration order,
    which depends on the candidate list's order — and that list is written
    sorted by MEASURED EFFECT. Re-sorting it mid-sweep gave two workers two
    different partitions: 37 subsets solved twice, 57 never solved, in a sweep
    whose whole claim is exhaustiveness."""
    inc = _pairs(CANDS)
    a = feasible_subsets(sorted(CANDS), inc)
    b = feasible_subsets(sorted(CANDS, reverse=True), inc)
    for n in (2, 3):
        for i in range(n):
            sa = {set_key(c) for c in a[i::n]}
            sb = {set_key(c) for c in b[i::n]}
            assert sa == sb, (
                "shard membership changed when the candidate list was "
                "reordered; sort the list before enumerating")


def test_the_script_sorts_its_candidate_list():
    src = (SCRIPTS / "exp2b_subsets.py").read_text()
    assert 'sorted(classes["rule"]["eligible_for_2B"])' in src
