"""Score an Experiment 4 network. The entry point Gen2 will target.

This is the frozen evaluation interface for Experiment 4:

    Exp4Selection -> assemble -> (TransitNetwork, tstats) -> solve_on_network

`solve_on_network` is Generation 1's evaluation core, extracted verbatim from
`score_state` and shared by both experiments. Experiment 4 therefore inherits,
without re-implementation and without the option of drifting from them:

* the path assignment and RAPTOR semantics (`build_raptor_network`,
  `build_zone_system`, the path-level setup);
* the waiting model, asserted out of the setup that does the scoring rather
  than requested and hoped for (gate 3-1, D23);
* vehicle-hour and peak-vehicle accounting, and the pinned envelope;
* the frequency model, its ladders, and the solver's own account of itself.

What differs from `score_state`, and why
----------------------------------------
Only the two ends, and each difference is forced by the change of question:

* **The front.** `score_state` applies `GeometryEdit`s to the legacy network and
  validates the result against the mutation contract. There is no legacy network
  here to edit and no edit to validate, so the front is `assemble`, whose own
  failure modes (unknown line, unobserved link, stop outside the fixed universe)
  are refusals rather than repairs.
* **The back.** The state key, digest, cardinality and members come from the
  selection instead of from a list of edits.

Everything between is the same code path. That is deliberate: a greenfield
network must be scored on the same yardstick as the incumbent it claims to beat,
or the margin is an artifact of the yardstick.

Starts
------
Default ``starts="greedy"``. There is no incumbent schedule for a network COTA
has never run, so an incumbent start is not merely inadvisable, it is undefined:
`fit_incumbent` would be scaling a schedule that does not exist. The greedy
build starts every route-period at its worst allowed headway -- which, with
``allow_off=True``, is OFF -- and spends the envelope on whichever service buys
the most. A greenfield solve therefore starts from an empty network, which is
the right shape for a question about what to build.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from .exp4_assemble import AssembledNetwork, assemble
from .exp4_network import Exp4Selection
from .exp3_score import solve_on_network


@dataclass
class ScoredExp4Network:
    """One scored Experiment 4 network. Mirrors ScoredState's shape."""

    state_key: str
    state_digest: str
    cardinality: int
    members: list[str]
    lam: float
    seed: int
    effort: str
    seconds: float
    metrics: dict[str, Any]
    #: All seven FitnessVector fields, verbatim. `metrics` carries the objective
    #: and exp3's six COMPONENTS; gate 4-7 compares the fitness vector itself,
    #: and a comparison that quietly drops a field it cannot find is a
    #: comparison of nothing.
    fitness: dict[str, float]
    evaluator: dict[str, Any]
    assembly: dict[str, Any]
    plan: dict[str, float]
    n_off_route_periods: int = 0
    off_route_periods: list[str] = field(default_factory=list)

    def row(self) -> dict[str, Any]:
        r = {"state": self.state_key, "state_digest": self.state_digest,
             "cardinality": self.cardinality, "lam": self.lam,
             "seed": self.seed, "effort": self.effort,
             "seconds": round(self.seconds, 3),
             "n_off_route_periods": self.n_off_route_periods}
        r.update({k: v for k, v in self.metrics.items()})
        return r


def score_exp4_network(
    selection: Exp4Selection, *, harness, stops_gdf, pool: Mapping[str, Any],
    graph, pool_version: str, first_dep_sec_by_period: Mapping[str, float],
    limits, constraints, lam: float, seed: int,
    iterations: int, restarts: int, width: int,
    waiting_model: str = "same_route",
    starts: str = "greedy",
    allow_off: bool = True,
    pathset_cache=None,
) -> tuple[ScoredExp4Network, AssembledNetwork]:
    """Assemble the selection and score it on the Gen1 evaluation core.

    Returns the score AND the assembled network, so a caller that wants to
    inspect what was scored does not have to re-assemble it and hope the two
    agree.
    """
    t0 = time.time()

    built = assemble(selection, pool, graph, harness.baseline.network.stops,
                     pool_version=pool_version,
                     first_dep_sec_by_period=first_dep_sec_by_period)

    core = solve_on_network(
        built.network, built.tstats, harness=harness, stops_gdf=stops_gdf,
        lam=lam, seed=seed, iterations=iterations, restarts=restarts,
        width=width, constraints=constraints, pathset_cache=pathset_cache,
        waiting_model=waiting_model, starts=starts, allow_off=allow_off)

    from .frequency import is_off
    plan = {f"{k[0]}|{k[1]}": float(v)
            for k, v in core["plan"].headways.items()}
    off_keys = sorted(k for k, v in plan.items() if is_off(v))

    from . import exp3
    scored = ScoredExp4Network(
        state_key=selection.state_key,
        state_digest=selection.state_digest,
        cardinality=selection.cardinality,
        members=selection.members,
        lam=lam, seed=seed,
        effort=f"{iterations}/{restarts}/{width}",
        seconds=time.time() - t0,
        metrics=exp3.metrics(core["fit"], lam),
        fitness={f: float(getattr(core["fit"], f)) for f in (
            "generalized_cost", "unserved_demand", "served_demand",
            "revenue_veh_hours", "peak_vehicles", "mean_wait_min",
            "gc_per_served_trip")},
        evaluator={**core["evaluator_checks"],
                   "incumbent_repair": core["repair_audit"],
                   "starts": starts, "allow_off": allow_off},
        assembly=built.report.as_dict(),
        plan=plan,
        n_off_route_periods=len(off_keys),
        off_route_periods=off_keys,
    )
    return scored, built
