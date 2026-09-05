"""Score one Experiment 3 network state: the whole chain, once, in one place.

    mutate geometry -> validate the RESULT -> rebuild path sets and check
    adequacy -> re-optimize frequency in the same envelope -> evaluate under the
    frozen Model B evaluator

Never `mutate -> keep the old headways -> compare`. Experiment 1 established
that the aggregate optimum is identified while individual route-period
allocations are not, so scoring a mutation against one arbitrary headway plan
measures that plan's accidents; Experiment 2 showed the cost of the shortcut
directly, when the fixed-frequency screen ranked the worst candidate of twelve
first out of sixty.

One function, because the alternative is two subtly different copies of a
fifteen-step chain — and this project has already had one experiment scored for
three days by an evaluator that differed from the one its log named.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from . import exp3
from .contract import ContractLimits, StateCheck, validate_applied
from .geometry import GeometryEdit, apply_edits

log = logging.getLogger(__name__)


@dataclass
class ScoredState:
    """A state's score, its provenance, and the contract check that let it through."""

    state_key: str
    state_digest: str
    cardinality: int
    members: list[str]
    lam: float
    seed: int
    effort: str
    seconds: float
    incumbent_scale: float = 1.0
    metrics: dict[str, float] = field(default_factory=dict)
    contract: dict[str, Any] = field(default_factory=dict)
    evaluator: dict[str, Any] = field(default_factory=dict)
    plan: dict[str, float] = field(default_factory=dict)
    edit_report: dict[str, Any] = field(default_factory=dict)

    def row(self) -> dict[str, Any]:
        out = {"state_key": self.state_key, "state_digest": self.state_digest,
               "cardinality": self.cardinality,
               "members": "|".join(self.members),
               "lambda": self.lam, "seed": self.seed, "effort": self.effort,
               "seconds": round(self.seconds, 2),
               "incumbent_scale": self.incumbent_scale}
        out.update(self.metrics)
        out["evidence_class"] = self.contract.get("facts", {}).get(
            "evidence_class", "unknown")
        out["modelled_share_pct"] = self.contract.get("facts", {}).get(
            "modelled_share_pct", None)
        out["network_edit_distance_pct"] = self.contract.get("facts", {}).get(
            "network_edit_distance_pct", float("nan"))
        out["waiting_model"] = self.evaluator.get("common_lines", "UNKNOWN")
        out["peak_fleet_check"] = self.contract.get("facts", {}).get(
            "peak_fleet_check", "ran")
        # `peak_vehicles` here is the frequency model's peak CONCURRENCY, not
        # the block-derived fleet proxy Experiment 1 validated against NTD.
        # Renamed so nobody reads 176 as a fleet count.
        out["peak_concurrency"] = out.pop("peak_vehicles", None)
        # NaN is not valid JSON and this row is written to JSONL.
        return {k: (None if isinstance(v, float) and v != v else v)
                for k, v in out.items()}


def score_state(edits: Sequence[GeometryEdit], *, harness, seg_model,
                stops_gdf, limits: ContractLimits, lam: float, seed: int,
                iterations: int, restarts: int, width: int,
                sole_access_stops: Sequence[str] = (),
                constraints: dict | None = None,
                pathset_cache=None,
                waiting_model: str = "same_route",
                starts: str = "incumbent") -> ScoredState:
    """Apply, validate, rebuild, re-optimize, evaluate. Raises on a violation.

    The contract check runs on the RESULT, after the network exists, because
    intentions are not outcomes: truncating one route can strand a stop the
    mutation never names.
    """
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "scripts"))
    from exp2_treatments import _Baseline, fit_incumbent, pinned  # 2B's own
    from .configs import (load_constraints, load_cost_weights,
                          period_of_seconds, service_periods)
    from .cost import CostWeights
    from .exp2 import build_setup as path_level_setup
    from .frequency import optimize_frequencies
    from .odmatrix import build_zone_system
    from .raptor import build_raptor_network
    from .routeclass import classify_routes

    t0 = time.time()
    H = harness
    a = H.assumptions
    pa = a["path_assignment"]
    periods = service_periods(a)
    net, ts = H.baseline.network, H.baseline.tstats
    before = net
    report = None

    if edits:
        ed = apply_edits(net, ts, seg_model, list(edits))
        net, ts, report = ed.network, ed.tstats, ed.report

    # STRUCTURE first, cheaply, before any expensive work: a state that
    # violates the contract structurally should not cost seven minutes to find
    # out. The ENVELOPE is deliberately not checked here -- the edited
    # baseline's vehicle-hours are not the constraint, the optimized plan's
    # are, and checking the wrong one refused half the pool.
    edited_vh = float(ts["runtime_min"].sum() / 60.0)
    check = validate_applied(before, net, list(edits), limits,
                             sole_access_stops=sole_access_stops,
                             coords=seg_model.coords, report=report,
                             edited_baseline_veh_hours=edited_vh,
                             waiting_model=waiting_model)
    check.raise_if_bad()

    core = solve_on_network(
        net, ts, harness=H, stops_gdf=stops_gdf, lam=lam, seed=seed,
        iterations=iterations, restarts=restarts, width=width,
        constraints=constraints, pathset_cache=pathset_cache,
        waiting_model=waiting_model, starts=starts)
    fit, repair_audit, got, scale, plan = (
        core["fit"], core["repair_audit"], core["waiting_model_used"],
        core["incumbent_scale"], core["plan"])

    # ENVELOPE, on the plan that was actually produced. Re-run rather than
    # folded into the structural check because only now does the number exist.
    final = validate_applied(before, net, list(edits), limits,
                             sole_access_stops=sole_access_stops,
                             coords=seg_model.coords, report=report,
                             veh_hours=fit.revenue_veh_hours,
                             edited_baseline_veh_hours=edited_vh,
                             waiting_model=got)
    final.raise_if_bad()

    return ScoredState(
        state_key=exp3.state_key(edits),
        state_digest=exp3.state_digest(edits),
        cardinality=len(list(edits)),
        members=sorted(exp3.mutation_id(e) for e in edits),
        lam=lam, seed=seed,
        effort=f"{iterations}/{restarts}/{width}",
        seconds=time.time() - t0,
        metrics=exp3.metrics(fit, lam),
        incumbent_scale=scale,
        contract={"ok": final.ok,
                  "rules_checked": sorted(set(check.rules_checked)
                                          | set(final.rules_checked)),
                  "facts": {**check.facts, **final.facts}},
        evaluator={**core["evaluator_checks"], "incumbent_repair": repair_audit},
        edit_report=(report.as_dict() if report is not None else {}),
        plan={f"{k[0]}|{k[1]}": float(v) for k, v in plan.headways.items()},
    )


def solve_on_network(net, ts, *, harness, stops_gdf, lam: float, seed: int,
                     iterations: int, restarts: int, width: int,
                     constraints, pathset_cache=None,
                     waiting_model: str = "same_route",
                     starts: str = "incumbent",
                     allow_off: bool = False) -> dict:
    """Score a network that already exists. The Gen1 evaluation core.

    Extracted from :func:`score_state` verbatim so Experiment 4 can reuse it
    rather than fork it. Everything here is network-agnostic: it takes the
    ``(TransitNetwork, tstats)`` pair that `apply_edits` produces for
    Experiments 1-3 and that `exp4_assemble.assemble` produces for Experiment 4,
    and applies the same path assignment, RAPTOR semantics, waiting model,
    vehicle-hour and peak-vehicle accounting and envelope to both.

    The alternative -- a second scoring path for Experiment 4 -- would let the
    two diverge silently, and this project has already lost three days to an
    evaluator that reported one model while running another (D23).

    ``allow_off`` is threaded to `build_ladders` and defaults to False, so
    Generation 1 is bit-identical through this function.
    """
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "scripts"))
    from exp2_treatments import _Baseline, fit_incumbent  # 2B's own
    from .configs import period_of_seconds, service_periods
    from .exp2 import build_setup as path_level_setup
    from .frequency import optimize_frequencies
    from .odmatrix import build_zone_system
    from .raptor import build_raptor_network
    from .routeclass import classify_routes

    H = harness
    a = H.assumptions
    pa = a["path_assignment"]
    periods = service_periods(a)

    rn = build_raptor_network(
        H.baseline.feed, net, ts, stops_gdf,
        walk_radius_m=float(pa["walk_radius_m"]),
        walk_speed_m_per_min=float(pa["walk_speed_m_per_min"]),
        periods=periods, with_timetable=False)
    zs = build_zone_system(
        H.baseline.demand["bg_frame"], stops_gdf,
        radius_m=float(pa["access_radius_m"]),
        walk_speed_m_per_min=float(pa["walk_speed_m_per_min"]),
        stop_index=rn.stop_index)
    tp = ts.copy()
    tp["period"] = tp["first_dep_sec"].map(
        lambda x: period_of_seconds(x, periods))
    rcls = classify_routes(tp.dropna(subset=["period"]), H.baseline.routes)

    # 2B's own proxy, not a copy of the fields I thought mattered. It
    # delegates every attribute to the real baseline and overrides only the
    # network and trip stats, so nothing can be missed or snapshotted stale.
    b_ed = _Baseline(H.baseline, net, ts)

    # THE ENVELOPE IS PINNED ONCE, FROM THE UNEDITED BASELINE.
    #
    # `config/constraints.yaml` says `weekday_revenue_vehicle_hours: baseline`,
    # a sentinel resolved against whatever network the setup is handed. Passing
    # the raw config therefore gave every state its OWN envelope: a splice
    # lengthens its routes, its "baseline" budget grows to match, and the
    # optimizer is handed more hours to spend. Every state was being judged
    # against a different budget, which is the one thing the whole method
    # depends on not happening.
    #
    # `constraints` must be the pinned object, computed once by the caller from
    # the unedited network. Refusing to run without it, rather than falling
    # back to the config, because a silent fallback here is invisible in every
    # artifact it produces -- which is exactly how Experiment 2 lost three days.
    if constraints is None:
        raise ValueError(
            "score_state needs the PINNED envelope, computed once from the "
            "unedited baseline with exp2_treatments.pinned(). Falling back to "
            "config/constraints.yaml gives every state its own budget, because "
            "the config's value is the sentinel 'baseline' and it resolves "
            "against whichever network is being scored.")

    judge = path_level_setup(b_ed, rn, zs, H.od, seed=seed, route_classes=rcls,
                             with_crowding=False,
                             lock_classes=("peak_express",),
                             constraints=constraints,
                             n_random_scenarios=0, pathset_cache=pathset_cache,
                             common_lines=waiting_model, allow_off=allow_off)

    # Gate 3-1, asserted rather than requested: read the model out of the setup
    # that will actually do the scoring, not out of what the caller asked for.
    got = judge.checks.get("common_lines")
    if got != waiting_model:
        raise ValueError(
            f"the evaluator came back priced as {got!r}, not {waiting_model!r}. "
            f"An unasserted evaluator scored three days of Experiment 2 under "
            f"the wrong model while its log reported the right one.")

    # The incumbent must be REFITTED to the envelope before the solve, and
    # this is not a refinement -- it is the difference between optimizing and
    # not. Experiment 2 wrote the reason down: "a splice lengthens a route, so
    # the edited network's own schedule can cost more than the envelope allows
    # -- by as little as 0.4 vehicle-hours, which is enough for the optimizer
    # to discard the incumbent and fall back to a greedy build."
    #
    # Without it every solve here reported `exchanges=0`, reached -5.03% on
    # unserved demand where Experiment 1 reaches -6.65%, and returned
    # BYTE-IDENTICAL results for three different seeds. That last part is the
    # dangerous one: identical replicates make the same-run noise floor exactly
    # zero, and a zero floor licenses every margin that is not precisely nil.
    incumbent, scale = fit_incumbent(judge, judge.budget.revenue_veh_hours)

    # ...and even then the optimizer may still refuse it. `fit_incumbent`
    # scales in CONTINUOUS headway space; `optimize_frequencies` snaps the
    # plan it is handed to the nearest ladder rung, which moves about half the
    # route-periods to a SHORTER headway and costs vehicle-hours. The
    # rescaled-then-snapped plan lands back outside the envelope, and the
    # optimizer falls back to the greedy build this call disabled.
    #
    # That fallback is correlated with the treatment: lengthening edits push
    # the incumbent over the envelope, shortening edits and the unedited
    # control do not. So which optimizer a state gets is decided by the
    # treatment applied to it, which is the one thing a controlled comparison
    # may not allow.
    #
    # `starts` selects the start set explicitly instead of letting an
    # unhandled infeasibility decide it:
    #   "incumbent" -- what Experiments 2, 2B and 3-A1 were scored with:
    #                  the incumbent if the ladder snap leaves it feasible,
    #                  and SILENTLY the greedy build if it does not.
    #   "repaired"  -- the incumbent walked back onto the ladder inside the
    #                  envelope, so the incumbent branch is always taken.
    #   "greedy"    -- the greedy build alone.
    #   "both"      -- repaired incumbent AND greedy, best kept. The only
    #                  start set whose composition does not depend on the
    #                  treatment.
    # Default is "incumbent" so nothing already recorded changes meaning.
    if starts not in ("incumbent", "repaired", "greedy", "both"):
        raise ValueError(f"unknown starts={starts!r}")
    repair_audit: dict[str, Any] = {"starts": starts}
    initial = incumbent
    use_greedy = False
    if starts in ("repaired", "both"):
        from .frequency import repair_to_ladder
        fixed, repair_audit = repair_to_ladder(
            judge.model, judge.budget, judge.ladders, incumbent)
        repair_audit["starts"] = starts
        repair_audit["repaired"] = fixed is not None
        if fixed is not None:
            initial = fixed
    if starts == "greedy":
        initial = None            # no initial => greedy build is the only start
        use_greedy = True
    if starts == "both":
        use_greedy = True         # greedy IS added alongside; best-of is kept

    r = optimize_frequencies(
        judge.model, judge.budget, ladder=[], unserved_multiplier=lam,
        local_search_iterations=iterations, seed=seed, ladders=judge.ladders,
        initial=initial,
        n_restarts=restarts, candidate_width=width, greedy_start=use_greedy)
    # Carry the solve's own account of itself through verbatim. Anything the
    # execution receipt needs must come from here, never from a log: that
    # dependency is what let a treatment-correlated fallback run for four
    # experiments (D27).
    for k in ("exchanges", "n_starts", "evaluations", "searches",
              "termination", "restarts_completed", "initial_offered",
              "initial_rejection", "forced_greedy_fallback"):
        repair_audit[k] = r.meta.get(k)

    # WHICH start won, not just how many there were. `optimize_frequencies`
    # builds its start list as [initial (if feasible)] + [greedy (if asked or
    # if nothing else)], so the index maps back to a name here. The names used
    # are this layer's, because only this layer knows the incumbent it handed
    # over had been repaired.
    names = ([] if initial is None else [starts if starts != "both" else "repaired"])
    if use_greedy:
        names.append("greedy")
    bs = r.meta.get("best_start", -1)
    won = (names[bs] if 0 <= bs < len(names) else
           ("resumed" if bs < 0 else f"#{bs}"))
    repair_audit["best_start"] = won
    repair_audit["winning_start"] = won
    repair_audit["start_names"] = names
    hw = dict(judge.baseline_plan.headways)
    for k, v in r.plan.headways.items():
        if k in hw:
            hw[k] = float(v)
    fit = judge.model.evaluate_array(np.array([hw[k] for k in judge.model.keys]))

    return {"fit": fit, "plan": r.plan, "repair_audit": repair_audit,
            "waiting_model_used": got, "incumbent_scale": scale,
            "evaluator_checks": dict(judge.checks), "judge": judge,
            "raptor": rn, "solver_meta": dict(r.meta)}
