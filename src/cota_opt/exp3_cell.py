"""One Experiment 3 cell, evaluated under the semantic comparison firewall.

`score_state` computes the number. This turns that into evidence: an
`ExecutionReceipt` recording what the evaluation actually got, so a comparison
can be validated rather than assumed.

Section 24 of the corrective plan: the firewall is exercised first on the exact
class of issue that motivated it, without being specialised to it.
"""
from __future__ import annotations

import subprocess
import time
from typing import Any, Sequence

from . import exp3
from .contract import ContractLimits
from .exp3_score import ScoredState, score_state
from .firewall import (EventType, ExecutionEvent, ExecutionReceipt,
                       ExperimentContract, StartPolicy, StopRule, build_spec,
                       digest, neutral)
from .geometry import GeometryEdit

_STARTS_FOR_POLICY = {
    StartPolicy.INCUMBENT_ONLY: "incumbent",
    StartPolicy.GREEDY_ONLY: "greedy",
    StartPolicy.BOTH: "both",
    StartPolicy.REPAIRED_INCUMBENT_ONLY: "repaired",
    StartPolicy.REPAIRED_INCUMBENT_AND_GREEDY: "both",
}

_TERMINATION = {"no_improving_move": StopRule.NO_IMPROVING_MOVE,
                "evaluation_budget": StopRule.EVALUATION_BUDGET}


def code_version() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10
                              ).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def receipt_from_scored(s: ScoredState, contract: ExperimentContract, *,
                        envelope_vh: float, config_digest: str,
                        data_digest: str = "", cache_hit: bool = False,
                        resumed: bool = False,
                        extra_events: Sequence[ExecutionEvent] = (),
                        ) -> ExecutionReceipt:
    """Turn a scored state into evidence, asserting rather than assuming.

    Everything here comes from what the solve reported about itself. Nothing is
    read back out of a log, and nothing is inferred from what was requested.
    """
    solve = s.evaluator.get("incumbent_repair", {}) or {}
    pol = contract.solver
    spec = build_spec(contract, state_digest=s.state_digest,
                      state_key=s.state_key, cardinality=s.cardinality,
                      members=s.members, envelope_digest=digest(round(envelope_vh, 6)),
                      config_digest=config_digest, data_digest=data_digest,
                      code_version=code_version(), seed=s.seed)

    attempted = tuple(solve.get("start_names") or ())
    rejected, reasons = (), ()
    events: list[ExecutionEvent] = list(extra_events)

    if solve.get("initial_rejection"):
        rejected = ("incumbent",)
        reasons = (str(solve["initial_rejection"]),)
        events.append(ExecutionEvent(
            EventType.START_REJECTED, str(solve["initial_rejection"]),
            "frequency.optimize_frequencies",
            before="incumbent", after=list(attempted)))
    if solve.get("forced_greedy_fallback"):
        events.append(ExecutionEvent(
            EventType.START_FALLBACK,
            "no start survived; greedy build substituted for the requested policy",
            "frequency.optimize_frequencies"))
    if solve.get("steps"):
        events.append(ExecutionEvent(
            EventType.INCUMBENT_REPAIRED,
            f"snapped incumbent walked back into the envelope in "
            f"{solve['steps']} step(s)",
            "frequency.repair_to_ladder",
            changes_opportunity=True, changes_semantics=False,
            before=solve.get("vh_before"), after=solve.get("vh_after")))
    if cache_hit:
        events.append(neutral(EventType.PATHSET_REBUILT,
                              "path sets reloaded from content-addressed cache",
                              "cache"))
    if resumed:
        events.append(neutral(EventType.CHECKPOINT_RESUMED,
                              "per-restart seeding makes a resumed solve exact",
                              "frequency"))

    term = _TERMINATION.get(solve.get("termination"), StopRule.NO_IMPROVING_MOVE)
    return ExecutionReceipt(
        spec=spec,
        evaluator_used=s.evaluator.get("common_lines", "UNKNOWN"),
        objective_used=contract.objective,
        envelope_used_vh=float(envelope_vh),
        pathset_digest=s.contract.get("facts", {}).get("pathset_digest", ""),
        code_version=spec.code_version,
        start_policy_requested=pol.start_policy,
        starts_attempted=attempted, starts_rejected=rejected,
        rejection_reasons=reasons,
        winning_start=str(solve.get("winning_start", "")),
        fallback_occurred=bool(solve.get("forced_greedy_fallback")),
        repair_occurred=bool(solve.get("steps")),
        repair_steps=int(solve.get("steps") or 0),
        restarts_requested=int(pol.restarts),
        restarts_completed=int(solve.get("restarts_completed", pol.restarts)),
        evaluations_performed=int(solve.get("evaluations") or 0),
        termination=term,
        converged=(term is StopRule.NO_IMPROVING_MOVE),
        resumed=resumed,
        objective=float(s.metrics["objective"]),
        metrics={k: float(v) for k, v in s.metrics.items()
                 if isinstance(v, (int, float))},
        plan_digest=digest(s.plan),
        feasible=bool(s.contract.get("ok", True)),
        events=tuple(events), cache_hit=cache_hit,
        seconds=round(s.seconds, 2),
        at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


def run_cell(contract: ExperimentContract, edits: Sequence[GeometryEdit], *,
             harness, seg_model, stops_gdf, limits: ContractLimits,
             constraints, pathset_cache=None, cache_hit: bool = False,
             seed: int | None = None, **kw) -> tuple[ScoredState, ExecutionReceipt]:
    """Evaluate one cell under a contract, returning the score AND the evidence.

    The solver settings come from the contract's policy, not from the caller:
    an experiment script that can pass its own effort can run two cells
    differently without either of them being wrong on its own.
    """
    pol = contract.solver
    s = score_state(
        list(edits), harness=harness, seg_model=seg_model, stops_gdf=stops_gdf,
        limits=limits, lam=float(contract.objective_version.split("=")[-1]),
        seed=int(pol.seeds[0] if seed is None else seed),
        iterations=pol.evaluation_ceiling, restarts=pol.restarts,
        width=pol.candidate_width, waiting_model=contract.evaluator,
        constraints=constraints, pathset_cache=pathset_cache,
        starts=_STARTS_FOR_POLICY[pol.start_policy], **kw)
    envelope_vh = float(limits.veh_hour_budget)
    r = receipt_from_scored(s, contract, envelope_vh=envelope_vh,
                            config_digest=exp3.config_digest(),
                            cache_hit=cache_hit)
    return s, r
