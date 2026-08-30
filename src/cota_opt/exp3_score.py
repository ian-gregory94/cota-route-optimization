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
    metrics: dict[str, float] = field(default_factory=dict)
    contract: dict[str, Any] = field(default_factory=dict)
    evaluator: dict[str, Any] = field(default_factory=dict)
    edit_report: dict[str, Any] = field(default_factory=dict)

    def row(self) -> dict[str, Any]:
        out = {"state_key": self.state_key, "state_digest": self.state_digest,
               "cardinality": self.cardinality,
               "members": "|".join(self.members),
               "lambda": self.lam, "seed": self.seed, "effort": self.effort,
               "seconds": round(self.seconds, 2)}
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
                pathset_cache=None,
                waiting_model: str = "same_route") -> ScoredState:
    """Apply, validate, rebuild, re-optimize, evaluate. Raises on a violation.

    The contract check runs on the RESULT, after the network exists, because
    intentions are not outcomes: truncating one route can strand a stop the
    mutation never names.
    """
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

    from types import SimpleNamespace
    b_ed = SimpleNamespace(**{k: getattr(H.baseline, k)
                              for k in dir(H.baseline)
                              if not k.startswith("_")
                              and not callable(getattr(H.baseline, k))})
    b_ed.network, b_ed.tstats = net, ts

    judge = path_level_setup(b_ed, rn, zs, H.od, seed=seed, route_classes=rcls,
                             with_crowding=False,
                             lock_classes=("peak_express",),
                             constraints=load_constraints(),
                             n_random_scenarios=0, pathset_cache=pathset_cache,
                             common_lines=waiting_model)

    # Gate 3-1, asserted rather than requested: read the model out of the setup
    # that will actually do the scoring, not out of what the caller asked for.
    got = judge.checks.get("common_lines")
    if got != waiting_model:
        raise ValueError(
            f"the evaluator came back priced as {got!r}, not {waiting_model!r}. "
            f"An unasserted evaluator scored three days of Experiment 2 under "
            f"the wrong model while its log reported the right one.")

    r = optimize_frequencies(
        judge.model, judge.budget, ladder=[], unserved_multiplier=lam,
        local_search_iterations=iterations, seed=seed, ladders=judge.ladders,
        n_restarts=restarts, candidate_width=width, greedy_start=False)
    hw = dict(judge.baseline_plan.headways)
    for k, v in r.plan.headways.items():
        if k in hw:
            hw[k] = float(v)
    fit = judge.model.evaluate_array(np.array([hw[k] for k in judge.model.keys]))

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
        contract={"ok": final.ok,
                  "rules_checked": sorted(set(check.rules_checked)
                                          | set(final.rules_checked)),
                  "facts": {**check.facts, **final.facts}},
        evaluator=dict(judge.checks),
        edit_report=(report.as_dict() if report is not None else {}),
    )
