"""The certification path-set cache must be a pure speedup, never an answer.

`certify` reuses one exact path set across a candidate's block solves: a 65-line
candidate is 638 calls to `solve_on_network`, and rebuilding the path set in each
of them costs ~595s a time -- ~105 hours per candidate, ~21,000 hours for the
promoted 200. Reuse takes that to ~22 minutes.

The hazard is that `exp2.build_setup` keys a `pathset_cache` by PERIOD NAME
ALONE. That key is sufficient only while the network, zones, OD table and
baseline headways are invariant. Within one candidate they are -- `certify`
passes the same network and tstats to every call and varies only
`ladder_override`, which reaches the frequency solver, not the enumeration.
Across candidates they are not, and that is exactly the reuse Gate 4-7 measured
at worst 1.307 relative error on revenue vehicle-hours.

So these tests pin two separate things:

  SCOPE       -- a cache cannot reach a second candidate, and the type says so
                 rather than a comment saying so.
  INVALIDATION-- a cache that somehow did survive is rejected loudly instead of
                 answering with the previous candidate's paths.

plus the identity claim itself: memoized and rebuilt arms agree exactly, not
approximately. `pytest.approx` is deliberately NOT used on the objective -- the
claim is equality, and a tolerance would pass the precise bug this guards.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))       # exp4_c10_fixtures lives there

from cota_opt import exp4_certify
from cota_opt.exp4_certify import (
    CertificationError,
    PathsetScopeViolation,
    _CandidatePathsets,
    certify,
)


# --------------------------------------------------------------------- scope --

def test_certify_accepts_no_pathset_cache_from_its_caller():
    """Scope cannot be widened from outside.

    If `certify` ever grew a `pathset_cache` parameter, a caller could hand the
    same dict to every candidate and reintroduce Gate 4-7's reuse without
    touching this module. The absence of the parameter is the guarantee.
    """
    params = inspect.signature(certify).parameters
    assert "pathset_cache" not in params
    assert "pathsets" not in params


def test_no_pathset_scope_is_constructed_at_import_or_in_a_default():
    """A scope built once at module import is shared by every candidate forever.

    The classic form is a mutable default argument -- Python evaluates defaults
    once, at definition -- so a scope there would be created before any candidate
    exists and would still be serving paths on candidate 200.
    """
    for name, p in inspect.signature(certify).parameters.items():
        assert not isinstance(p.default, _CandidatePathsets), (
            f"{name} defaults to a path-set scope, which Python evaluates once "
            f"at definition and shares across every certification")
    module_scopes = [n for n, v in vars(exp4_certify).items()
                     if isinstance(v, _CandidatePathsets)]
    assert module_scopes == []


def test_scope_is_stamped_with_the_candidate_it_was_built_for():
    scope = _CandidatePathsets("digest-A")
    assert scope.state_digest == "digest-A"
    assert len(scope) == 0
    scope.assert_fresh_for("digest-A")          # its own candidate: fine


# -------------------------------------------------------------- invalidation --

def test_a_scope_stamped_for_another_candidate_is_refused():
    scope = _CandidatePathsets("digest-A")
    with pytest.raises(PathsetScopeViolation) as e:
        scope.assert_fresh_for("digest-B")
    assert "1.307" in str(e.value)              # names the error it prevents


def test_a_scope_that_outlived_its_candidate_is_refused():
    """The failure mode a hoisted or defaulted scope actually produces.

    It arrives at the second candidate already holding the first candidate's
    periods. Without this check `build_setup` would find the period key present
    and return the previous candidate's paths.
    """
    scope = _CandidatePathsets("digest-A")
    scope["am_peak"] = object()                 # candidate A's paths
    with pytest.raises(PathsetScopeViolation) as e:
        scope.assert_fresh_for("digest-A")      # same candidate, still refused
    msg = str(e.value)
    assert "am_peak" in msg
    assert "outlived" in msg


def test_scope_violation_is_a_certification_error():
    """So a launcher catching CertificationError cannot miss it."""
    assert issubclass(PathsetScopeViolation, CertificationError)


# ------------------------------------------------------------------ identity --
#
# The arms below run real solves. They are kept on a deliberately small
# selection because the rebuild arm is the expensive one: on a 65-line candidate
# it is ~105 hours, which is why the identity proof is established here and not
# at production scale. See outputs/exp4/memo/PROPOSED_PATCH.md.

@pytest.fixture(scope="module")
def small_candidate():
    """Smallest selection that exercises multiple periods and blocks.

    Nothing here is `importorskip` or a conditional `pytest.skip`. Both inputs
    are committed to the repository, so a missing one is a broken checkout, and
    the right response is a red test rather than a green run with the identity
    claim quietly unproven. That failure mode already cost this project once:
    an undeclared dependency silently skipped 8 tests while the reproducibility
    record claimed 356 passed.
    """
    import json

    import exp4_c10_fixtures as fixtures
    from cota_opt.configs import load_constraints
    from cota_opt.exp4_assemble import assemble
    from cota_opt.exp4_network import Exp4Selection

    env_path = ROOT / "outputs/CANONICAL_ENVELOPE.json"
    pool_path = ROOT / "outputs/exp4/run/pool.json"
    for p in (env_path, pool_path):
        assert p.exists(), f"{p} is committed and must be present"

    st = fixtures._boot()
    H, sg, graph = st["H"], st["sg"], st["graph"]
    first_dep = fixtures._first_dep_by_period()
    env = json.loads(env_path.read_text())
    c = load_constraints()
    cons = {**c, "resource": {**c["resource"],
                              "weekday_revenue_vehicle_hours":
                                  float(env["weekday_revenue_vehicle_hours"])}}

    pool = sorted(json.loads(pool_path.read_text())["lines"])

    def build(lines):
        sel = Exp4Selection(fixtures.POOL_VERSION, frozenset(lines), frozenset())
        built = assemble(sel, fixtures._BY_RID, graph, H.baseline.network.stops,
                         pool_version=fixtures.POOL_VERSION,
                         first_dep_sec_by_period=first_dep)
        return sel, built

    return {"H": H, "sg": sg, "cons": cons, "pool": pool, "build": build}


def _run(sc, lines, *, memoized, max_rounds=exp4_certify.MAX_ROUNDS):
    """Certify one selection with the path set either reused or rebuilt.

    The rebuild arm CLEARS the scope before each call rather than passing
    `pathset_cache=None`. Both force a genuine rebuild every call, but clearing
    leaves the scope populated at the end, so `certify`'s "the scope was never
    used" guard still sees what it is there to see. Passing None would trip that
    guard and the arm could not run at all.
    """
    import cota_opt.exp2 as exp2

    sel, built = sc["build"](lines)
    real = exp2.build_setup

    def always_rebuild(*a, **kw):
        cache = kw.get("pathset_cache")
        if cache is not None:
            cache.clear()                       # every call enumerates afresh
        return real(*a, **kw)

    if not memoized:
        exp2.build_setup = always_rebuild
    try:
        return certify(built.network, built.tstats, state_key="|".join(lines),
                       state_digest=sel.state_digest, harness=sc["H"],
                       stops_gdf=sc["sg"], lam=2.0, seed=20250829,
                       constraints=sc["cons"], max_rounds=max_rounds)
    finally:
        exp2.build_setup = real


@pytest.mark.slow
def test_memoized_and_rebuilt_arms_are_identical(small_candidate):
    """Equality, not closeness.

    A tolerance here would pass the exact defect this guards: `PathSetEvaluator`
    mutating the `PathSet` it wraps would move the objective by a little, and
    `approx` would wave it through. Round count and convergence flag are checked
    too -- a changed search trajectory is a failure even if the objective lands
    in the same place.
    """
    lines = small_candidate["pool"][:6]
    rebuilt = _run(small_candidate, lines, memoized=False)
    memoized = _run(small_candidate, lines, memoized=True)

    assert memoized.objective == rebuilt.objective
    assert memoized.rounds == rebuilt.rounds
    assert memoized.converged == rebuilt.converged


@pytest.mark.slow
def test_two_candidates_in_one_process_do_not_share_paths(small_candidate):
    """The Gate 4-7 failure, asked directly.

    Certifying B after A in the same process must give B exactly what B gets
    alone. If a scope leaked from A to B, B would be priced on A's paths and
    this is where that shows up.
    """
    pool = small_candidate["pool"]
    a_lines, b_lines = pool[:6], pool[6:12]

    b_alone = _run(small_candidate, b_lines, memoized=True)
    _run(small_candidate, a_lines, memoized=True)
    b_after_a = _run(small_candidate, b_lines, memoized=True)

    assert b_after_a.objective == b_alone.objective
    assert b_after_a.rounds == b_alone.rounds


@pytest.mark.slow
def test_the_scope_is_actually_populated(small_candidate, monkeypatch):
    """Reuse must really happen -- an unused scope is a 290x slowdown.

    `certify` raises if the scope comes back empty, so this checks the positive
    case: every modelled period is enumerated once and then served from the
    scope, and the same PathSet object is handed back on later calls.
    """
    import cota_opt.exp2 as exp2

    real = exp2.build_setup
    seen: list[dict] = []

    def spy(*a, **kw):
        cache = kw.get("pathset_cache")
        if cache is not None:
            seen.append({"keys": sorted(cache), "obj": id(cache)})
        return real(*a, **kw)

    monkeypatch.setattr(exp2, "build_setup", spy)
    _run(small_candidate, small_candidate["pool"][:6], memoized=True,
         max_rounds=1)                          # structural check; one round does

    assert seen, "no call received a path-set scope"
    # one scope object for the whole candidate
    assert len({s["obj"] for s in seen}) == 1
    # it starts empty and is populated on the first call, not repeatedly
    assert seen[0]["keys"] == []
    assert seen[-1]["keys"], "scope never accumulated a period"
