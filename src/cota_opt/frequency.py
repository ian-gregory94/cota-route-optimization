"""Frequency optimization v0 — Experiment 1 data structures and solver.

Problem
-------
Route geometry and stop patterns are **fixed**. The decision variable is the
headway of every (route, service period) that has baseline service. Total
weekday revenue vehicle-hours and per-period peak vehicle requirement are held
at (or below) the baseline envelope. Objectives: minimize passenger generalized
cost and unserved demand.

Resource accounting (documented, self-consistent)
------------------------------------------------
For a route with mean one-way runtime ``R`` minutes, ``k`` directions, in a
period of ``T`` minutes at headway ``h``:

    trips            = k * T / h
    revenue_veh_hours= trips * R / 60
    cycle_time       = 2 * R * (1 + layover_ratio)          [round trip + recovery]
    peak_vehicles    = cycle_time / h                        [continuous approx.]

Peak vehicles is a continuous relaxation of ``ceil(cycle/h)``; it is reported as
a *scheduled* fleet estimate, never as COTA's actual fleet requirement (which
depends on interlining, deadhead, run-cutting and maintenance reserve — all
UNKNOWN here).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd

from .cost import CostWeights, crowding_excess_min, demand_retention, expected_wait_min

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ServicePeriod:
    name: str
    start_hour: float
    end_hour: float

    @property
    def duration_min(self) -> float:
        return (self.end_hour - self.start_hour) * 60.0


@dataclass(frozen=True)
class RouteService:
    """Fixed (non-decision) attributes of one route in one period."""

    route_id: str
    period: str
    runtime_min: float          # mean one-way scheduled runtime
    n_directions: int
    baseline_headway_min: float
    baseline_trips: int


@dataclass
class ResourceBudget:
    """The service resource envelope the plan must respect."""

    revenue_veh_hours: float
    peak_vehicles_by_period: dict[str, float]
    tolerance: float = 0.005

    def vh_cap(self) -> float:
        return self.revenue_veh_hours * (1.0 + self.tolerance)

    def peak_cap(self, period: str) -> float:
        return self.peak_vehicles_by_period[period] * (1.0 + self.tolerance)


@dataclass
class PassengerDemand:
    """Proxy demand by (route, period), in daily passenger trips."""

    by_route_period: dict[tuple[str, str], float]
    source: str = "PROXY"
    notes: str = ""

    def get(self, route_id: str, period: str) -> float:
        return self.by_route_period.get((route_id, period), 0.0)

    def total(self) -> float:
        return float(sum(self.by_route_period.values()))


#: A route-period that runs no service at all.
#:
#: Represented as an infinite headway rather than as ``None``, a sentinel
#: object, or absence from the plan, because infinity makes every downstream
#: quantity come out right *arithmetically* instead of by special case:
#:
#:   trips          = n_directions * duration / inf = 0
#:   revenue_vh     = 0 * runtime / 60             = 0
#:   peak_vehicles  = cycle / inf                  = 0
#:   integer_fleet  = ceil(cycle / inf)            = 0
#:
#: and the path model already refuses to board a pattern whose headway is not
#: finite (``raptor.generalized_cost``: ``expected_wait_min(h) if np.isfinite(h)
#: and h < 1e5 else INF``), so an OFF route-period carries no passengers with no
#: change to RAPTOR at all. ``pattern_headways`` has always used ``np.inf`` as
#: its fallback for exactly this meaning.
#:
#: Absence from ``FrequencyPlan.headways`` is deliberately NOT the
#: representation: a missing key is indistinguishable from a bug, and a bug that
#: reads as "no service" is how a route silently disappears. OFF is a value that
#: must be written on purpose.
#:
#: Gen1 (Experiments 1, 2, 2B, 3) never produces OFF -- ``build_ladders``
#: refuses to offer it unless ``allow_off=True``, and its docstring policy that
#: "no route-period with service today may lose it entirely" is unchanged.
#: Experiment 4 treats service activation, including OFF, as a decision
#: variable, which is what the flag is for.
OFF: float = math.inf


def is_off(headway: float) -> bool:
    """True for a route-period that runs no service.

    Anything non-finite counts, and so does anything at or above the path
    model's own unusability threshold, so that OFF cannot be smuggled in as a
    very large finite number that the resource arithmetic still charges for.
    """
    return (not math.isfinite(headway)) or headway >= 1e5


@dataclass
class FrequencyPlan:
    """A candidate assignment of headways to (route, period)."""

    headways: dict[tuple[str, str], float]

    def copy(self) -> "FrequencyPlan":
        return FrequencyPlan(dict(self.headways))

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [{"route_id": r, "period": p, "headway_min": h}
             for (r, p), h in sorted(self.headways.items())])


@dataclass(frozen=True)
class FitnessVector:
    """Multi-objective evaluation of a plan."""

    generalized_cost: float          # equivalent in-vehicle minutes, served trips
    unserved_demand: float           # daily passenger trips without usable service
    revenue_veh_hours: float
    peak_vehicles: float
    peak_by_period: dict[str, float] = field(default_factory=dict)
    served_demand: float = 0.0
    mean_wait_min: float = 0.0
    gc_per_served_trip: float = 0.0

    def scalarized(self, w_unserved: float, multiplier: float = 1.0) -> float:
        return self.generalized_cost + multiplier * w_unserved * self.unserved_demand

    def dominates(self, other: "FitnessVector") -> bool:
        return ((self.generalized_cost <= other.generalized_cost
                 and self.unserved_demand <= other.unserved_demand)
                and (self.generalized_cost < other.generalized_cost
                     or self.unserved_demand < other.unserved_demand))


@dataclass
class OptimizationResult:
    plan: FrequencyPlan
    fitness: FitnessVector
    label: str = ""
    meta: dict = field(default_factory=dict)


class FrequencyModel:
    """Evaluates frequency plans: resources, passenger cost, unserved demand."""

    def __init__(
        self,
        services: dict[tuple[str, str], RouteService],
        periods: dict[str, ServicePeriod],
        demand: PassengerDemand,
        weights: CostWeights,
        assumptions: dict,
        connections: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self.services = services
        self.periods = periods
        self.demand = demand
        self.w = weights
        self.a = assumptions
        # route -> {connected_route: share of its transfers} (rows sum to 1)
        self.connections = connections or {}
        ops = assumptions["operations"]
        self.layover = float(ops["layover_ratio"])
        wait = assumptions["waiting"]
        self._wait_kw = dict(
            random_arrival_threshold_min=float(wait["random_arrival_threshold_min"]),
            schedule_coefficient=float(wait["schedule_coefficient"]))
        self._ret_kw = dict(full_min=float(wait["retention_full_min"]),
                            zero_min=float(wait["retention_zero_min"]),
                            floor=float(wait["retention_floor"]))
        crowd = assumptions["crowding"]
        self.capacity = float(crowd["bus_capacity"])
        self.crowd_penalty = float(crowd["crowding_penalty_per_excess_load"])
        pax = assumptions.get("passenger", {})
        self.avg_ride_fraction = float(pax.get("avg_ride_fraction", 0.35))
        self.access_walk_min = float(pax.get("access_walk_min", 5.0))
        self.transfer_rate = float(pax.get("transfer_rate", 0.20))
        self._build_arrays()

    # -- vectorized state -------------------------------------------------
    def _build_arrays(self) -> None:
        """Flatten the model into numpy arrays so ``evaluate`` is O(n) in C.

        Layout: one row per (route, period) service. The transfer term needs a
        per-period route×route mix, handled as a small matrix product.
        """
        self.keys: list[tuple[str, str]] = list(self.services)
        self.key_index = {k: i for i, k in enumerate(self.keys)}
        svcs = [self.services[k] for k in self.keys]
        self.route_names: list[str] = sorted({s.route_id for s in svcs})
        self.period_names: list[str] = list(self.periods)
        r_ix = {r: i for i, r in enumerate(self.route_names)}
        p_ix = {p: i for i, p in enumerate(self.period_names)}

        self._runtime = np.array([s.runtime_min for s in svcs], float)
        self._ndir = np.array([s.n_directions for s in svcs], float)
        self._T = np.array([self.periods[s.period].duration_min for s in svcs], float)
        self._demand = np.array([self.demand.get(*k) for k in self.keys], float)
        self._ri = np.array([r_ix[s.route_id] for s in svcs], int)
        self._pi = np.array([p_ix[s.period] for s in svcs], int)
        self._cycle = 2.0 * self._runtime * (1.0 + self.layover)
        self._ivt = self._runtime * self.avg_ride_fraction

        # per-period route→route transfer share matrix (rows sum to 1 where defined)
        n_r = len(self.route_names)
        C = np.zeros((n_r, n_r))
        for r, d in self.connections.items():
            if r not in r_ix:
                continue
            for other, share in d.items():
                if other in r_ix:
                    C[r_ix[r], r_ix[other]] = share
        rs = C.sum(axis=1)
        self._has_conn = rs > 0
        C[self._has_conn] /= rs[self._has_conn, None]
        self._C = C
        # mask of which (route, period) cells actually exist
        self._cell_exists = np.zeros((n_r, len(self.period_names)), bool)
        self._cell_exists[self._ri, self._pi] = True

    def _vec_wait(self, h: np.ndarray) -> np.ndarray:
        t = self._wait_kw["random_arrival_threshold_min"]
        c = self._wait_kw["schedule_coefficient"]
        return np.where(h <= t, h / 2.0, t / 2.0 + c * (h - t))

    def _vec_retention(self, h: np.ndarray) -> np.ndarray:
        full = self._ret_kw["full_min"]
        zero = self._ret_kw["zero_min"]
        floor = self._ret_kw["floor"]
        frac = np.clip((h - full) / (zero - full), 0.0, 1.0)
        return 1.0 - frac * (1.0 - floor)

    def headway_array(self, plan: FrequencyPlan) -> np.ndarray:
        return np.array([plan.headways[k] for k in self.keys], float)

    # -- per route-period physics ----------------------------------------
    def trips(self, svc: RouteService, headway: float) -> float:
        return svc.n_directions * self.periods[svc.period].duration_min / headway

    def revenue_veh_hours(self, svc: RouteService, headway: float) -> float:
        return self.trips(svc, headway) * svc.runtime_min / 60.0

    def peak_vehicles(self, svc: RouteService, headway: float) -> float:
        cycle = 2.0 * svc.runtime_min * (1.0 + self.layover)
        return cycle / headway

    # -- evaluation -------------------------------------------------------
    def evaluate(self, plan: FrequencyPlan) -> FitnessVector:
        return self.evaluate_array(self.headway_array(plan))

    def evaluate_array(self, h: np.ndarray) -> FitnessVector:
        """Vectorized evaluation. Identical arithmetic to the scalar helpers."""
        trips = self._ndir * self._T / h
        vh_i = trips * self._runtime / 60.0
        vh = float(vh_i.sum())
        peak_i = self._cycle / h
        peak_arr = np.bincount(self._pi, weights=peak_i,
                               minlength=len(self.period_names))
        peak = {p: float(peak_arr[i]) for i, p in enumerate(self.period_names)}

        rho = self._vec_retention(h)
        served = self._demand * rho
        served_total = float(served.sum())
        unserved_total = float((self._demand - served).sum())

        wait = self._vec_wait(h)

        # transfer wait: per-period route→route mix of connecting-route waits
        n_r, n_p = self._C.shape[0], len(self.period_names)
        wait_rp = np.zeros((n_r, n_p))
        wait_rp[self._ri, self._pi] = wait
        mixed = self._C @ wait_rp                       # (routes × periods)
        # a route with no connections (or no connecting service this period)
        # falls back to its own wait
        denom = self._C @ self._cell_exists.astype(float)
        t_wait_rp = np.where(denom > 0, np.divide(mixed, np.where(denom > 0, denom, 1)),
                             wait_rp)
        t_wait = t_wait_rp[self._ri, self._pi]
        t_wait = np.where(self._has_conn[self._ri], t_wait, wait)

        pax_per_trip = np.divide(served, trips, out=np.zeros_like(served),
                                 where=trips > 0)
        load = np.divide(pax_per_trip, self.capacity)
        crowd = self.crowd_penalty * np.maximum(load - 1.0, 0.0) * self._ivt

        per_trip = (
            self.w.walking * self.access_walk_min
            + self.w.waiting * wait
            + self.w.in_vehicle * self._ivt
            + self.w.crowding * crowd
            + self.transfer_rate * (self.w.transfer_wait * t_wait
                                    + self.w.transfer_penalty)
        )
        gc_total = float((served * per_trip).sum())
        wait_weighted = float((served * wait).sum())
        peak_system = float(peak_arr.max()) if len(peak_arr) else 0.0
        return FitnessVector(
            generalized_cost=gc_total,
            unserved_demand=unserved_total,
            revenue_veh_hours=vh,
            peak_vehicles=peak_system,
            peak_by_period=peak,
            served_demand=served_total,
            mean_wait_min=(wait_weighted / served_total) if served_total else 0.0,
            gc_per_served_trip=(gc_total / served_total) if served_total else 0.0,
        )

    def _transfer_wait(self, route_id: str, period: str, plan: FrequencyPlan) -> float:
        """Expected wait for the second leg, over routes this route connects to."""
        conn = self.connections.get(route_id)
        if not conn:
            return expected_wait_min(plan.headways[(route_id, period)], **self._wait_kw)
        tot = 0.0
        wsum = 0.0
        for other, share in conn.items():
            k = (other, period)
            if k not in plan.headways:
                continue
            tot += share * expected_wait_min(plan.headways[k], **self._wait_kw)
            wsum += share
        if wsum <= 0:
            return expected_wait_min(plan.headways[(route_id, period)], **self._wait_kw)
        return tot / wsum


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------

# Numerical slack, distinct from the *policy* budget tolerance. A plan whose
# vehicle-hours equal the budget to within floating-point summation noise is
# feasible; without this a zero policy tolerance rejects the incumbent itself.
_EPS_REL = 1e-9


def _feasible(model: FrequencyModel, fit: FitnessVector,
              budget: ResourceBudget) -> bool:
    if fit.revenue_veh_hours > budget.vh_cap() * (1.0 + _EPS_REL):
        return False
    for p, v in fit.peak_by_period.items():
        if p in budget.peak_vehicles_by_period:
            if v > budget.peak_cap(p) * (1.0 + _EPS_REL):
                return False
    return True


def build_ladders(model: FrequencyModel, ladder: Iterable[float],
                  max_headway: float = 60.0, min_headway: float = 5.0,
                  allow_off: bool = False,
                  ) -> dict[tuple[str, str], list[float]]:
    """Per-route-period headway options honouring the minimum-service policy.

    The worst service a route-period may be given is ``max(policy_max_headway,
    its own baseline headway)`` — the policy floor cannot *require* an
    improvement on a route-period that is already worse than the floor today,
    and no route-period with service today may lose it entirely.

    ``allow_off`` is the one exception, and it is off by default so that
    Generation 1 is unaffected: with it, every route-period additionally gets
    the :data:`OFF` rung, and the sentence above stops applying. Experiment 4
    treats service activation, including OFF, as a decision variable, so its
    ladders are built with ``allow_off=True``; Experiments 1, 2, 2B and 3 build
    theirs without it and cannot represent OFF at all.

    The flag is deliberately a parameter of ladder CONSTRUCTION rather than a
    property of a plan. A plan cannot acquire an OFF route-period unless the
    ladder it was built against offered one, which is what makes accidental
    deactivation — and, through the snap functions, accidental REactivation —
    impossible rather than merely unlikely.
    """
    base = sorted(h for h in ladder if h >= min_headway)
    out: dict[tuple[str, str], list[float]] = {}
    for k, svc in model.services.items():
        worst = max(max_headway, svc.baseline_headway_min)
        opts = [h for h in base if h <= worst]
        # today's headway is always an option, so the incumbent schedule is an
        # exactly representable — and therefore exactly feasible — search point
        opts.append(svc.baseline_headway_min)
        if worst not in opts:
            opts.append(worst)
        rungs = sorted(set(round(h, 9) for h in opts))
        if allow_off:
            rungs.append(OFF)          # last: it is the worst service there is
        out[k] = rungs
    return out


def optimize_frequencies(
    model: FrequencyModel,
    budget: ResourceBudget,
    ladder: Iterable[float],
    unserved_multiplier: float = 1.0,
    max_headway: float = 60.0,
    min_headway: float = 5.0,
    local_search_iterations: int = 3000,
    seed: int = 0,
    ladders: dict[tuple[str, str], list[float]] | None = None,
    initial: FrequencyPlan | None = None,
    candidate_width: int = 0,
    n_restarts: int = 6,
    greedy_start: bool = True,
    progress=None,
    on_pass=None,
    resume: dict | None = None,
) -> OptimizationResult:
    """Marginal-exchange search for the best frequency plan inside the budget.

    Two starting points are tried and the better kept:

    * **incumbent** — the caller's plan (normally today's schedule), and
    * **greedy build** — every route-period at its worst allowed headway, then
      spend the vehicle-hour budget on whichever single ladder step buys the
      largest objective reduction per vehicle-hour.

    From each start, an exchange heuristic repeatedly moves service hours from
    the route-period where they buy the least to the one where they buy the
    most, subject to the vehicle-hour and per-period peak-vehicle caps. Because
    the incumbent is one of the starts, the returned plan can never be worse
    than the plan it was given.

    Resumability
    ------------
    A full-effort solve is twenty restarts over forty minutes, and this sandbox
    reaps long-running processes, so losing one whole cell to a kill at minute
    thirty-nine was routine. Each restart therefore draws from its own
    generator seeded on ``(seed, restart index)`` rather than from one shared
    stream, which makes restart *k* independent of whether restarts before it
    ran in this process.

    That is what makes resuming exact rather than approximate: with
    ``resume={"next_restart": k, "best_idx": [...], "best_obj": x}`` the solve
    picks up at restart *k* and returns precisely what an uninterrupted run
    would have returned. ``progress(k, idx, obj)`` is called after every
    restart so the caller can persist that state.

    The per-restart seeding does change which random sequence is drawn, so it
    changes results relative to the shared-stream version. That is a deliberate
    trade: reproducibility under interruption is worth more than agreement with
    a scheme whose interrupted runs were not reproducible at all.
    """
    rng = np.random.default_rng(seed)
    keys = list(model.keys)
    if ladders is None:
        lad_global = sorted(h for h in ladder if min_headway <= h <= max_headway)
        if not lad_global:
            raise ValueError("empty headway ladder after applying policy bounds")
        lads = {k: list(lad_global) for k in keys}
    else:
        lads = {k: sorted(ladders[k]) for k in keys}
        if any(not v for v in lads.values()):
            raise ValueError("a route-period has an empty headway ladder")

    n = len(keys)
    max_len = max(len(lads[k]) for k in keys)
    L = np.full((n, max_len), np.nan)
    L_len = np.empty(n, int)
    for i, k in enumerate(keys):
        v = lads[k]
        L[i, :len(v)] = v
        L_len[i] = len(v)

    w_uns = model.w.unserved

    def obj(f: FitnessVector) -> float:
        return f.scalarized(w_uns, unserved_multiplier)

    def feasible(f: FitnessVector) -> bool:
        return _feasible(model, f, budget)

    # ---- starting point A: minimum service everywhere --------------------
    idx0 = L_len - 1
    h0 = L[np.arange(n), idx0]
    if not feasible(model.evaluate_array(h0)):
        raise ValueError(
            "minimum-service plan already exceeds the budget; the policy maximum "
            "headway is infeasible under this envelope")

    starts: list[np.ndarray] = []
    start_names: list[str] = []
    initial_rejection: str | None = None
    if initial is not None:
        init_idx = np.array(
            [int(np.nanargmin(np.abs(L[i] - initial.headways[k]))) for i, k in
             enumerate(keys)], int)
        init_h = L[np.arange(n), init_idx]
        drift = float(np.max(np.abs(
            init_h - np.array([initial.headways[k] for k in keys]))))
        if drift > 1e-6:
            log.warning("incumbent snapped to ladder, max drift %.4f min", drift)
        if feasible(model.evaluate_array(init_h)):
            starts.append(init_idx)
            start_names.append("incumbent")
        else:
            # Structured, not just logged. This branch silently substituted a
            # different optimizer for four experiments because the only trace
            # it left was prose (D27).
            initial_rejection = (
                f"ladder-snapped incumbent exceeds the envelope "
                f"(drift {drift:.4f} min)")
            log.warning("incumbent plan is infeasible under this budget")
    # The greedy build from minimum service costs O(n) evaluations per ladder
    # step and, as Experiment 1 showed, converges to a worse optimum than the
    # incumbent start. It is only needed when the caller gave no feasible plan.
    forced_greedy = not starts and not greedy_start
    if greedy_start or not starts:
        starts.append(_greedy_build(model, budget, L, L_len, idx0.copy(),
                                    obj, feasible))
        start_names.append("greedy")

    stats: dict = {}
    width = candidate_width if candidate_width > 0 else n
    best_idx, best_fit, best_obj, moves = None, None, float("inf"), 0
    best_start = -1        # which start produced the incumbent best
    first_restart = 0
    if resume and resume.get("best_idx") is not None:
        # rejoin at a recorded restart: re-evaluate the saved plan rather than
        # trusting a stored objective, so a resumed run cannot inherit a number
        # that no longer matches the model it is being scored against
        best_idx = np.asarray(resume["best_idx"], dtype=int)
        best_fit = model.evaluate_array(L[np.arange(n), best_idx])
        best_obj = obj(best_fit)
        moves = int(resume.get("moves", 0))
        first_restart = int(resume.get("next_restart", 0))
        log.info("resuming solve at restart %d/%d, saved objective %.6g",
                 first_restart, n_restarts, best_obj)
    else:
        for si, st in enumerate(starts):
            idx, fit, o, n_moves = _exchange_search(
                model, budget, L, L_len, st.copy(), obj, feasible,
                local_search_iterations, width, rng, stats=stats,
                on_pass=(None if on_pass is None
                         else lambda *a, _p=f"start{si}": on_pass(_p, *a)))
            if o < best_obj:
                best_idx, best_fit, best_obj, moves = idx, fit, o, n_moves
                best_start = si
        if progress is not None:
            progress(0, best_idx, best_obj, moves)

    # perturbation restarts: kick a random subset off the incumbent optimum and
    # re-converge; keep the best local optimum found. Each restart draws from
    # its own generator so it is reproducible on its own, which is what lets an
    # interrupted solve rejoin exactly where it stopped.
    assert best_idx is not None
    for restart in range(first_restart, max(0, n_restarts)):
        rng = np.random.default_rng([seed, restart])
        cand = best_idx.copy()
        k = max(1, int(0.15 * n))
        hit = rng.choice(n, size=k, replace=False)
        for i in hit:
            cand[i] = int(np.clip(cand[i] + rng.integers(-2, 3), 0, L_len[i] - 1))
        if not feasible(model.evaluate_array(L[np.arange(n), cand])):
            # pull service back until the kick fits the envelope
            for i in sorted(hit, key=lambda x: -L_len[x]):
                while cand[i] < L_len[i] - 1 and not feasible(
                        model.evaluate_array(L[np.arange(n), cand])):
                    cand[i] += 1
            if not feasible(model.evaluate_array(L[np.arange(n), cand])):
                if progress is not None:
                    progress(restart + 1, best_idx, best_obj, moves)
                continue
        idx, fit, o, n_moves = _exchange_search(
            model, budget, L, L_len, cand, obj, feasible,
            local_search_iterations, width, rng, stats=stats,
            on_pass=(None if on_pass is None
                     else lambda *a, _p=f"restart{restart}": on_pass(_p, *a)))
        if o < best_obj - 1e-9:
            best_idx, best_fit, best_obj, moves = idx, fit, o, n_moves
        if progress is not None:
            progress(restart + 1, best_idx, best_obj, moves)

    assert best_idx is not None and best_fit is not None
    h = L[np.arange(n), best_idx]
    plan = FrequencyPlan({k: float(h[i]) for i, k in enumerate(keys)})
    log.info("solve lambda=%s: obj=%.6g vh=%.1f/%.1f exchanges=%d",
             unserved_multiplier, best_obj, best_fit.revenue_veh_hours,
             budget.revenue_veh_hours, moves)
    return OptimizationResult(
        plan=plan, fitness=best_fit,
        label=f"lambda={unserved_multiplier}",
        meta={"exchanges": moves, "unserved_multiplier": unserved_multiplier,
              "seed": seed, "n_starts": len(starts), "n_restarts": n_restarts,
              "candidate_width": width, "best_start": best_start,
              # What the solve ACTUALLY got, for the execution receipt.
              "start_names": tuple(start_names),
              "winning_start": (start_names[best_start]
                                if 0 <= best_start < len(start_names) else
                                ("resumed" if best_start < 0 else "?")),
              "initial_offered": initial is not None,
              "initial_rejection": initial_rejection,
              "forced_greedy_fallback": forced_greedy,
              "restarts_completed": max(0, n_restarts) - first_restart
                                    + first_restart,
              "evaluations": stats.get("evals", 0),
              "searches": stats.get("searches", 0),
              "termination": stats.get("stopped", "no_improving_move")})


def _greedy_build(model, budget, L, L_len, idx, obj, feasible) -> np.ndarray:
    """Spend the budget from minimum service, best objective gain per veh-hour."""
    n = len(idx)
    h = L[np.arange(n), idx].copy()
    fit = model.evaluate_array(h)
    cur = obj(fit)
    while True:
        best = None
        for i in range(n):
            if idx[i] == 0:
                continue
            old = h[i]
            h[i] = L[i, idx[i] - 1]
            tf = model.evaluate_array(h)
            h[i] = old
            if not feasible(tf):
                continue
            d_vh = tf.revenue_veh_hours - fit.revenue_veh_hours
            d_obj = cur - obj(tf)
            if d_obj <= 0 or d_vh <= 0:
                continue
            r = d_obj / d_vh
            if best is None or r > best[0]:
                best = (r, i, tf, obj(tf))
        if best is None:
            return idx
        _, i, tf, o = best
        idx[i] -= 1
        h[i] = L[i, idx[i]]
        fit, cur = tf, o


def _exchange_search(model, budget, L, L_len, idx, obj, feasible,
                     max_evaluations, width, rng, on_pass=None, stats=None):
    """Move service hours from where they buy least to where they buy most.

    Each pass prices one ladder step in each direction for every route-period
    (2n evaluations), then applies as many verified-improving moves as that
    price snapshot supports before repricing. ``max_evaluations`` bounds total
    model evaluations, so runtime is predictable.
    """
    n = len(idx)
    h = L[np.arange(n), idx].copy()
    fit = model.evaluate_array(h)
    cur = obj(fit)
    moves = 0
    evals = 1

    while evals + 2 * n < max_evaluations:
        down_rate = np.full(n, -np.inf)   # objective gain per veh-hour spent
        up_rate = np.full(n, np.inf)      # objective loss per veh-hour freed
        for i in range(n):
            old = h[i]
            if idx[i] > 0:
                h[i] = L[i, idx[i] - 1]
                tf = model.evaluate_array(h)
                evals += 1
                d_vh = tf.revenue_veh_hours - fit.revenue_veh_hours
                if d_vh > 0:
                    down_rate[i] = (cur - obj(tf)) / d_vh
            if idx[i] < L_len[i] - 1:
                h[i] = L[i, idx[i] + 1]
                tf = model.evaluate_array(h)
                evals += 1
                d_vh = fit.revenue_veh_hours - tf.revenue_veh_hours
                if d_vh > 0:
                    up_rate[i] = (obj(tf) - cur) / d_vh
            h[i] = old

        order_down = [int(i) for i in np.argsort(-down_rate)[:width]
                      if np.isfinite(down_rate[i])]
        order_up = [int(j) for j in np.argsort(up_rate)[:width]
                    if np.isfinite(up_rate[j])]
        applied_this_pass = 0

        # (a) plain step-downs, if the envelope still has room
        for i in order_down:
            if down_rate[i] <= 0 or idx[i] == 0:
                continue
            old = h[i]
            h[i] = L[i, idx[i] - 1]
            tf = model.evaluate_array(h)
            evals += 1
            to = obj(tf)
            if feasible(tf) and to < cur - 1e-9:
                idx[i] -= 1
                fit, cur = tf, to
                moves += 1
                applied_this_pass += 1
            else:
                h[i] = old

        # (b) exchanges, best expected net gain first
        pairs = [(down_rate[i] - up_rate[j], i, j)
                 for i in order_down for j in order_up
                 if i != j and down_rate[i] > up_rate[j]]
        pairs.sort(reverse=True)
        for _, i, j in pairs:
            if idx[i] == 0 or idx[j] >= L_len[j] - 1:
                continue
            oi, oj = h[i], h[j]
            h[i] = L[i, idx[i] - 1]
            h[j] = L[j, idx[j] + 1]
            tf = model.evaluate_array(h)
            evals += 1
            to = obj(tf)
            if feasible(tf) and to < cur - 1e-9:
                idx[i] -= 1
                idx[j] += 1
                fit, cur = tf, to
                moves += 1
                applied_this_pass += 1
            else:
                h[i], h[j] = oi, oj
            if evals >= max_evaluations:
                break

        if on_pass is not None:
            # After each repricing pass, so a caller can see a long search
            # advancing and stop it cleanly. A certification search is an hour
            # of silence otherwise, and silence is indistinguishable from a
            # hang -- which is how this project lost two runs to processes it
            # could not tell were alive.
            on_pass(evals, max_evaluations, moves, cur)
        if applied_this_pass == 0:
            if stats is not None:
                stats["stopped"] = "no_improving_move"
            break
    else:
        if stats is not None:
            stats["stopped"] = "evaluation_budget"
    if stats is not None:
        # Accumulated, not assigned: a solve runs one of these per start and
        # one per restart, and the receipt reports the whole solve.
        stats["evals"] = stats.get("evals", 0) + evals
        stats["searches"] = stats.get("searches", 0) + 1
    return idx, fit, cur, moves


def pareto_filter(results: list[OptimizationResult]) -> list[OptimizationResult]:
    """Keep only non-dominated (generalized_cost, unserved_demand) solutions."""
    out = []
    for r in results:
        if not any(o.fitness.dominates(r.fitness) for o in results if o is not r):
            out.append(r)
    # de-duplicate identical objective pairs
    seen: set[tuple[float, float]] = set()
    uniq = []
    for r in sorted(out, key=lambda x: x.fitness.generalized_cost):
        key = (round(r.fitness.generalized_cost, 3), round(r.fitness.unserved_demand, 3))
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    return uniq


def snap_to_ladder(headway: float, ladder: Iterable[float]) -> float:
    """Nearest ladder value (used to make the baseline plan comparable).

    An OFF headway snaps to OFF when the ladder offers it, and is an error when
    it does not. It must never snap to a finite rung: ``abs(v - inf)`` is ``inf``
    for every rung, so the old nearest-value rule broke the tie on magnitude and
    turned an inactive route-period into the MOST frequent one on the ladder.
    That is the precise shape of an inactive service becoming active by default.
    """
    lad = sorted(ladder)
    if is_off(headway):
        if any(is_off(v) for v in lad):
            return OFF
        raise ValueError(
            "cannot snap an OFF route-period onto a ladder with no OFF rung; "
            "either the ladder was built without allow_off=True or this plan "
            "does not belong to this model")
    finite = [v for v in lad if not is_off(v)]
    if not finite:
        raise ValueError("ladder offers no service at all")
    return min(finite, key=lambda x: abs(x - headway))


def integer_fleet(model: FrequencyModel, plan: FrequencyPlan) -> dict[str, int]:
    """Per-period fleet with per-route integer rounding (ceil of cycle/headway)."""
    out: dict[str, int] = {p: 0 for p in model.periods}
    for key, svc in model.services.items():
        h = plan.headways[key]
        cycle = 2.0 * svc.runtime_min * (1.0 + model.layover)
        out[svc.period] += int(math.ceil(cycle / h))
    return out


def snap_plan_to_ladder(ladders: dict[tuple[str, str], list[float]],
                        plan: "FrequencyPlan") -> "FrequencyPlan":
    """Snap a plan onto the per-route-period ladder, nearest rung.

    This is exactly what :func:`optimize_frequencies` does internally to an
    ``initial`` plan. Exposed so a caller can see the plan the optimizer will
    actually start from, rather than the one it passed in.
    """
    out = {}
    for k, h in plan.headways.items():
        lad = ladders.get(k)
        if not lad:
            out[k] = float(h)
            continue
        if is_off(h):
            # Same defect as snap_to_ladder: abs(v - inf) is inf for every rung,
            # so the (distance, value) tie-break picked the smallest headway and
            # an OFF route-period came back as the most frequent one.
            if not any(is_off(v) for v in lad):
                raise ValueError(
                    f"{k} is OFF but its ladder offers no OFF rung; refusing to "
                    f"snap it onto service it was not given")
            out[k] = OFF
            continue
        finite = [v for v in lad if not is_off(v)]
        out[k] = float(min(finite, key=lambda v: (abs(v - float(h)), v)))
    return FrequencyPlan(out)


def repair_to_ladder(model: FrequencyModel, budget: ResourceBudget,
                     ladders: dict[tuple[str, str], list[float]],
                     plan: "FrequencyPlan",
                     ) -> tuple["FrequencyPlan | None", dict]:
    """Return a ladder-valued plan that fits the envelope, or ``None``.

    Why this exists
    ---------------
    ``fit_incumbent`` scales a network's own schedule until it fits the budget
    in CONTINUOUS headway space. ``optimize_frequencies`` then snaps that plan
    to the nearest ladder rung -- and nearest-rung snapping moves roughly half
    the route-periods to a *shorter* headway, which costs vehicle-hours. The
    rescaled-then-snapped plan therefore lands back outside the envelope, the
    optimizer logs ``incumbent plan is infeasible under this budget``, discards
    the incumbent, and falls back to ``_greedy_build`` -- the very build the
    caller disabled with ``greedy_start=False``, and the one Experiment 1
    measured as converging to a worse optimum.

    That fallback is not evenly distributed. Edits that lengthen routes push
    the incumbent over the envelope; edits that shorten them do not, and the
    unedited control never does. So the control is optimized from the
    incumbent and the treatments are optimized by greedy build -- a handicap
    correlated with the treatment.

    The repair walks headways UP (longer headway, less service, fewer
    vehicle-hours) one rung at a time, each time choosing the route-period
    whose step sheds the most vehicle-hours per unit of objective damage, until
    the plan fits. The result is on-ladder, so the optimizer's own snap is a
    no-op and the incumbent branch is taken.

    Returns ``(plan_or_None, audit)``. ``None`` means even minimum service on
    every route-period does not fit, which is a broken envelope, not a
    startable plan.
    """
    keys = list(model.keys)
    lads = {k: sorted(ladders[k]) for k in keys}
    idx = {}
    snapped = snap_plan_to_ladder(ladders, plan)
    for k in keys:
        lad = lads[k]
        h = float(snapped.headways[k])
        idx[k] = min(range(len(lad)), key=lambda i: (abs(lad[i] - h), lad[i]))

    def arr(ix):
        return np.array([lads[k][ix[k]] for k in keys])

    w_uns = model.w.unserved
    fit = model.evaluate_array(arr(idx))
    audit = {"steps": 0, "snapped_feasible": _feasible(model, fit, budget),
             "snap_drift_min": float(max(
                 abs(float(snapped.headways[k]) - float(plan.headways[k]))
                 for k in keys)),
             "vh_before": float(fit.revenue_veh_hours),
             "vh_cap": float(budget.vh_cap())}
    if audit["snapped_feasible"]:
        audit["vh_after"] = audit["vh_before"]
        return snapped, audit

    steps = 0
    limit = sum(len(lads[k]) for k in keys)
    while not _feasible(model, fit, budget) and steps < limit:
        cur_obj = fit.scalarized(w_uns, 2.0)
        best = None
        for k in keys:
            if idx[k] >= len(lads[k]) - 1:
                continue
            idx[k] += 1
            f2 = model.evaluate_array(arr(idx))
            idx[k] -= 1
            shed = fit.revenue_veh_hours - f2.revenue_veh_hours
            harm = max(f2.scalarized(w_uns, 2.0) - cur_obj, 1e-9)
            if shed <= 0:
                continue
            score = shed / harm
            if best is None or score > best[0]:
                best = (score, k, f2)
        if best is None:
            return None, audit
        idx[best[1]] += 1
        fit = best[2]
        steps += 1

    audit["steps"] = steps
    audit["vh_after"] = float(fit.revenue_veh_hours)
    if not _feasible(model, fit, budget):
        return None, audit
    return FrequencyPlan({k: float(lads[k][idx[k]]) for k in keys}), audit
