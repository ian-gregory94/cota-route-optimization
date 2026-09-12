"""Exact certification: the only stage permitted to decide anything.

Every candidate that can affect an Experiment 4 conclusion is re-evaluated here
with `gen2_frequency.solve_exact` under the frozen production objective, and the
result of THIS module -- never a discovery score -- determines baseline
comparison, fitness, treatment effects, ordering, leader selection, separation
and frontier membership.

WHAT "EXACT" CAN AND CANNOT MEAN HERE
-------------------------------------
Full enumeration of the ladder is not available and that is measured, not
assumed: at 336.6 us per combination a one-line network (6 route-periods, 14
rungs) is 7.53e6 combinations and 42 minutes, and the spaces grow as 14^R --

    1 line   6 rp   14^6  = 7.53e6      42 minutes
    2 lines  12 rp  14^12 = 5.67e13     ~600 years
    3 lines  18 rp  14^18 = 4.27e20
    5 lines  30 rp  14^30 = 2.42e34

So certification enumerates a NEIGHBOURHOOD, exhaustively, in rounds, until no
block improves. The property it establishes is stated exactly rather than
implied:

    **(N,K)-block-local optimality** -- no block of N route-periods, moved
    within K ladder rungs of the certified plan, improves the objective.

That is a real, checkable, and above all UNIFORM guarantee: every candidate gets
the same property regardless of its structure, which is precisely what D18
showed the Gen1 heuristic does not do.

WHY BLOCK ROTATION
------------------
A fixed partition of the keys means two keys in different blocks are never
enumerated together, so cross-block interactions are never explored and the
"fixed point" is an artifact of the partition. The offset rotates by N//2 each
round, so over rounds every pair of keys eventually shares a block. Measured:
without rotation the search was still improving at round 5 and reported no fixed
point; with rotation it converges at rounds 14-16.

WHAT WAS MEASURED
-----------------
On the frozen C10 geometry, certification against the Gen1 delivered plan:

    structure        route-periods   improvement over Gen1   rounds   seconds
    sparse (1 line)        6              +1.165792%           16         9
    dense (5 lines)       30              +1.183453%           14       145

Two things matter in that table. First, Gen1's delivered plans are substantially
suboptimal -- over 1%, against effects this project reports at 0.19%. Second,
and this is the justification for the whole architecture: the improvement is
**0.018 pp apart across structures**, where D18 measured the *delivered* gap
0.208 pp apart. Certification compresses the structure-correlated component by
more than an order of magnitude, which is what makes exact-stage comparisons
admissible where discovery-stage ones are not.

The residual -- (N,K)-block-local optimum versus global optimum -- is unmeasured
and is stated as a limitation wherever certified numbers are reported. It is
strictly smaller than the gap D18 measured, because the certified plan is at
least as good as the delivered one by construction.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from .exp4_inference import CertifiedResult
from .firewall.core import digest

# ---------------------------------------------------------------------------
# The certification contract. Preregistered, and NOT tuned against any result.
#
# N_KEYS = 8   3^8 = 6,561 combinations per block enumeration. Large enough that
#              the block captures real interactions between route-periods,
#              small enough that a 30-route-period network certifies in ~2.5
#              minutes -- comfortably inside the ~8 minutes D28 established as
#              the certification budget.
# K_RUNGS = 3  the delivered rung plus one either side. Matches D33 and D18, so
#              the neighbourhood this certifies over is the same shape as the
#              one the gap was measured on.
# MAX_ROUNDS   a stop, not a target. Convergence was measured at 14-16 rounds;
#              40 leaves generous headroom, and a run that hits it is recorded
#              as NOT CONVERGED rather than silently reported as certified.
# ---------------------------------------------------------------------------
N_KEYS = 8
K_RUNGS = 3
MAX_ROUNDS = 40

CERTIFICATION_CONTRACT = {
    "instrument": "gen2_frequency.solve_exact over a rotating block neighbourhood",
    "n_keys": N_KEYS, "k_rungs": K_RUNGS, "max_rounds": MAX_ROUNDS,
    "rotation": "offset advances by n_keys // 2 each round",
    "anchor": "the plan being certified, re-anchored after every improvement",
    "guarantee": (f"no block of {N_KEYS} route-periods moved within {K_RUNGS} "
                  f"ladder rungs of the certified plan improves the objective"),
    "version": 1,
}
CERTIFICATION_DIGEST = digest(CERTIFICATION_CONTRACT)


class CertificationError(RuntimeError):
    """Certification could not establish its own guarantee."""


class PathsetScopeViolation(CertificationError):
    """A candidate's path-set cache was used outside that candidate."""


class _CandidatePathsets(dict):
    """Period-keyed exact path sets, valid for ONE candidate and no other.

    `exp2.build_setup` keys a `pathset_cache` by PERIOD NAME ALONE. That key is
    sufficient exactly while the network, zones, OD table and baseline headways
    are invariant. Across one candidate's block solves they are: `certify`
    passes the same `network` and `tstats` to every call, and only
    `ladder_override` varies, which reaches the frequency solver and not the
    path enumeration. Across candidates they are not.

    Sharing one of these between candidates is precisely the reuse Gate 4-7
    measured and rejected: keyed by period alone, every candidate after the
    first was scored against the previous candidate's paths, worst 1.307
    relative error on revenue vehicle-hours. The period key cannot carry that
    distinction, so this type carries it instead -- the scope is stamped with
    the candidate it was built for and refuses to serve any other.

    The realistic way this invariant dies is not malice but a refactor: hoisting
    the construction to module scope, or to a default argument (Python evaluates
    those once, so `pathsets=_CandidatePathsets(...)` in a signature is shared by
    every call forever). Both leave the scope non-empty when the SECOND candidate
    arrives, which `assert_fresh_for` turns into a loud failure instead of a
    quietly wrong objective.
    """

    __slots__ = ("state_digest",)

    def __init__(self, state_digest: str) -> None:
        super().__init__()
        self.state_digest = state_digest

    def assert_fresh_for(self, state_digest: str) -> None:
        """Refuse a scope that has outlived, or was built for, another candidate."""
        if self.state_digest != state_digest:
            raise PathsetScopeViolation(
                f"path-set scope is stamped for candidate "
                f"{self.state_digest!r} but certification is running "
                f"{state_digest!r}. A scope keyed by period alone is only "
                f"valid within one candidate; reusing it across candidates is "
                f"the Gate 4-7 reuse measured at 1.307 relative error on "
                f"revenue vehicle-hours.")
        if len(self):
            raise PathsetScopeViolation(
                f"path-set scope for {state_digest!r} already holds periods "
                f"{sorted(self)} before certification has enumerated anything. "
                f"It outlived a previous candidate -- most likely hoisted to "
                f"module scope or to a default argument -- and would have "
                f"scored this candidate against another candidate's paths.")


def _restricted(full: dict, keys, free: set, k: int, anchor: dict) -> dict:
    """One rung for every frozen key, k rungs around the anchor for free ones."""
    out = {}
    for key in keys:
        lad = sorted(full[key])
        cur = float(anchor.get(key, lad[len(lad) // 2]))

        def dist(v: float) -> float:
            if math.isinf(v) and math.isinf(cur):
                return 0.0
            if math.isinf(v) or math.isinf(cur):
                return float("inf")
            return abs(v - cur)

        i = min(range(len(lad)), key=lambda j: dist(lad[j]))
        if key not in free:
            out[key] = [lad[i]]
            continue
        lo = max(0, min(i - k // 2, len(lad) - k))
        out[key] = lad[lo:lo + k] or [lad[i]]
    return out


@dataclass
class _Cursor:
    plan: dict
    obj: float
    fit: object


def certify(network, tstats, *, state_key: str, state_digest: str,
            harness, stops_gdf, lam: float, seed: int, constraints,
            pinned_off=frozenset(), waiting_model: str = "same_route",
            allow_off: bool = True, n_keys: int = N_KEYS,
            k_rungs: int = K_RUNGS, max_rounds: int = MAX_ROUNDS,
            code_version: str = "", contract_digest: str = "",
            progress=None) -> CertifiedResult:
    """Certify one candidate. The returned objective is the only usable number.

    The starting point is Gen1's delivered plan -- not because it is trusted,
    but because starting from a feasible plan is what makes the neighbourhood
    well defined. Every rung it occupies stays available in every block, so the
    certified objective can never be worse than the delivered one; if it ever
    is, the two stages are not solving the same problem and this raises.
    """
    from .exp3_score import solve_on_network

    # ONE exact path set per candidate, built once and reused across this
    # candidate's block solves. A 65-line candidate is 390 route-periods, 49
    # blocks per round, 13 rounds -- 638 calls to `solve_on_network`, and every
    # one of them passes `build_setup` the same network, zones, OD table and
    # baseline headways. Only `ladder_override` differs between them, and the
    # ladder reaches the frequency solver, not the path enumeration. So 637 of
    # those calls were spending ~595s each rebuilding an object identical to
    # the one the first call already built: ~105 hours per candidate, ~21,000
    # hours for the promoted 200. Certification could not finish, and the
    # container reclaimed a candidate at 7h having written nothing.
    #
    # THIS IS NOT GATE 4-7. Gate 4-7 rejected a MASTER path set shared ACROSS
    # candidates: keyed by period alone, so candidate n was scored against
    # candidate n-1's paths, worst 1.307 relative error on revenue
    # vehicle-hours. It also established that filtering a supernetwork master
    # RESTRICTS the choice set and biases the search toward activating more
    # lines -- which is precisely why discovery may use it and certification
    # may not. Discovery proposes; certification decides.
    #
    # This dict is created here, holds only paths THIS candidate enumerated
    # for itself, and dies when this call returns. Nothing crosses a candidate
    # boundary and no master is imported. Certification still builds its own
    # path set -- it stops building it 637 redundant times.
    #
    # Verified IDENTICAL, not "close enough": both arms on a 6-line selection
    # where the rebuild arm is affordable returned objective
    # 3621684.228486466, rounds 3, converged True -- delta exactly 0. Equal
    # round count and convergence flag are what rule out `PathSetEvaluator`
    # mutating the `PathSet` it wraps, which is the failure this could have
    # had. See outputs/exp4/memo/ab_memoization.json.
    #
    # The scope is enforced, not just intended -- see `_CandidatePathsets`.
    pathsets = _CandidatePathsets(state_digest)
    pathsets.assert_fresh_for(state_digest)

    common = dict(harness=harness, stops_gdf=stops_gdf, lam=lam, seed=seed,
                  constraints=constraints, waiting_model=waiting_model,
                  starts="greedy", allow_off=allow_off,
                  pathset_cache=pathsets,
                  pinned_off=frozenset(pinned_off))
    t0 = time.time()

    start = solve_on_network(network, tstats, iterations=20_000, restarts=1,
                             width=0, solver="gen1", include_setup=True,
                             **common)
    judge = start["judge"]
    keys = list(judge.model.keys)
    full = {k: list(judge.ladders[k]) for k in keys}
    w_uns = judge.model.w.unserved
    cur = _Cursor(plan=dict(start["plan"].headways),
                  obj=float(start["fit"].scalarized(w_uns, lam)),
                  fit=start["fit"])
    delivered_obj = cur.obj

    ks = sorted(keys)
    rounds = 0
    blocks = 0
    combos_total = 0
    converged = False

    for rnd in range(1, max_rounds + 1):
        rounds = rnd
        improved = False
        off = ((rnd - 1) * max(n_keys // 2, 1)) % max(len(ks), 1)
        rot = ks[off:] + ks[:off]
        for b in range(0, len(rot), n_keys):
            block = set(rot[b:b + n_keys])
            lads = _restricted(full, keys, block, k_rungs, cur.plan)
            n = 1
            for k in keys:
                n *= len(lads[k])
            ex = solve_on_network(
                network, tstats, iterations=20_000, restarts=1, width=0,
                solver="exact", exact_max_combinations=max(n * 2, 1000),
                ladder_override=lads, **common)
            blocks += 1
            combos_total += n
            o = float(ex["fit"].scalarized(w_uns, lam))
            if o < cur.obj - 1e-9:
                improved = True
                cur = _Cursor(plan=dict(ex["plan"].headways), obj=o,
                              fit=ex["fit"])
        if progress:
            progress(rnd, cur.obj, blocks)
        if not improved:
            converged = True
            break

    if cur.obj > delivered_obj + 1e-6:
        raise CertificationError(
            f"{state_key}: certification returned a WORSE objective than the "
            f"delivered plan ({cur.obj:,.6f} vs {delivered_obj:,.6f}). The "
            f"delivered plan's own rungs are kept in every block, so this is "
            f"impossible unless the two stages are solving different problems.")

    # The scope must have been USED. An empty one means `pathset_cache` stopped
    # reaching `build_setup` -- the rebuild-every-call behaviour would come back
    # silently, correct but ~290x slower, and the run would die of the shard
    # bound rather than of a wrong number. Asserted because that is a failure
    # nothing else in this function would notice.
    if not pathsets:
        raise CertificationError(
            f"{state_key}: the path-set scope is empty after {rounds} rounds, "
            f"so no call reached it. `pathset_cache` is no longer threaded "
            f"through `solve_on_network` to `build_setup`, and certification "
            f"has silently returned to rebuilding the path set on every block "
            f"solve -- ~105 hours per candidate rather than ~22 minutes.")
    if pathsets.state_digest != state_digest:
        raise PathsetScopeViolation(
            f"{state_key}: the path-set scope came back stamped "
            f"{pathsets.state_digest!r}, not {state_digest!r}. The object this "
            f"candidate's paths were enumerated into is not the object that "
            f"served them.")

    from .frequency import is_off
    plan_str = {f"{r}|{p}": float(v) for (r, p), v in cur.plan.items()}
    fit = cur.fit
    fitness = {f: float(getattr(fit, f)) for f in
               ("generalized_cost", "unserved_demand", "served_demand",
                "revenue_veh_hours", "peak_vehicles", "mean_wait_min",
                "gc_per_served_trip")}

    return CertifiedResult(
        state_key=state_key, state_digest=state_digest,
        objective=float(cur.obj), fitness=fitness,
        plan_digest=digest(plan_str),
        guarantee=CERTIFICATION_CONTRACT["guarantee"],
        n_keys=n_keys, k_rungs=k_rungs, rounds=rounds, converged=converged,
        block_enumerations=blocks, combinations=combos_total,
        seconds=time.time() - t0, plan=plan_str,
        code_version=code_version, contract_digest=contract_digest)


def n_off_in(plan: dict) -> int:
    from .frequency import is_off
    return sum(1 for v in plan.values() if is_off(v))
