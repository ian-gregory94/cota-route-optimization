"""The Experiment 3 treatment contract, enforced instead of described.

`EXPERIMENT3_CONTRACT.md` states what a mutation may do. This module is the
same rules as code, checked at four points rather than one:

* when a mutation is **generated** — a proposal that cannot be legal is never
  offered;
* when a state is **applied** — because a set of individually legal mutations
  can be jointly illegal, and only the resulting network knows;
* when a state is **loaded from cache** — a cached score was computed under
  whatever rules held when it was written, and rules change;
* when a state is **promoted** — the last point before a number acquires
  authority.

Generator filtering alone is not enough, and that is not a hypothetical. In
Experiment 2 the screen decided what got evaluated and D19 found its top pick
of sixty to be the worst of twelve; a filter that runs once, early, on
intentions rather than outcomes is exactly the shape of failure this project
has already had.

Every violation **raises**. A contract check that returns False and lets the
caller decide is a suggestion, and an invalid mutation that becomes a silent
no-op is worse than one that crashes: the run continues, the state is scored,
and the score describes a network nobody asked for.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from .geometry import CONSUMING_KINDS, EDIT_KINDS, GeometryEdit
from .network import TransitNetwork


class ContractViolation(ValueError):
    """A mutation or state the treatment contract does not permit."""

    def __init__(self, rule: str, detail: str) -> None:
        super().__init__(f"[{rule}] {detail}")
        self.rule = rule
        self.detail = detail


@dataclass(frozen=True)
class ContractLimits:
    """The numbers from EXPERIMENT3_CONTRACT.md section 3, in one place.

    Held as data so a test can assert them against the document, and so a
    future experiment that legitimately needs different limits has to construct
    a different object rather than edit a constant and inherit this one's
    gates.
    """

    terminal_move_m: float = 1200.0
    max_route_stop_visit_loss: float = 0.40
    max_network_edit_distance: float = 0.15
    min_split_share: float = 0.30
    modelled_share_primary_pct: float = 2.0

    #: Gate 3-8. Hours are not buses.
    veh_hour_budget: float | None = None
    peak_vehicle_budget: float | None = None

    #: Gate 3-1. The evaluator must be able to state its own waiting model.
    required_waiting_model: str = "same_route"

    #: Gate 3-4's dividing line. Dropping a stop is a legitimate *straighten*
    #: when the stop sat on a real deviation -- the bus then drives a different
    #: street, and the running-time change is a genuine alignment change the
    #: estimator can price. It is forbidden *stop-skipping* when the stop sat
    #: essentially on the line between its neighbours, because then the bus
    #: drives the same street and the only saving is the dwell this feed cannot
    #: measure. Circuity is (d(a,x) + d(x,b)) / d(a,b): 1.0 is exactly on the
    #: line. Anything at or below this ratio is skipping.
    #:
    #: 1.10 sits well below the 1.6 minimum the straighten generator proposes
    #: at, so the two rules cannot both fire on one mutation.
    min_deviation_circuity: float = 1.10


@dataclass
class StateCheck:
    """What the validator found. Carried into the artifact, not just asserted."""

    ok: bool
    rules_checked: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)

    def raise_if_bad(self) -> "StateCheck":
        if not self.ok:
            raise ContractViolation("state", "; ".join(self.violations))
        return self


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def stop_visits(net: TransitNetwork) -> dict[str, int]:
    """Stop-visits per route: the denominator every removal cap is measured in.

    Stop-visits rather than distance because the demand model reaches the
    network through stops, so that is the unit in which "how much of this route
    is left" means anything to the evaluation.
    """
    out: dict[str, int] = {}
    for p in net.patterns.values():
        out[p.route_id] = out.get(p.route_id, 0) + len(p.stops)
    return out


def served_stops(net: TransitNetwork) -> set[str]:
    return {s for p in net.patterns.values() for s in p.stops}


def visits_per_stop(net: TransitNetwork) -> dict[str, int]:
    """How many pattern-visits each stop receives, across all routes."""
    out: dict[str, int] = {}
    for p in net.patterns.values():
        for s in p.stops:
            out[s] = out.get(s, 0) + 1
    return out


def edit_distance(before: TransitNetwork, after: TransitNetwork) -> float:
    """(stop-visits added + removed) / baseline stop-visits, as a fraction.

    Measured **per stop, not per route id**, and that distinction is the whole
    correctness of the rule. Matching by route id makes a splice read as
    deleting two routes and creating a third — maximal churn — even though
    nearly every stop-visit survives the merge untouched. Under that reading
    every splice in the pool scored 18-22% and was refused for exceeding 15%,
    which made the contract contradict itself: it lists `splice` as permitted
    and quotas twelve of them.

    Route ids are bookkeeping. What the 15% line is for is how much of the
    network's actual service pattern moved, so that is what this counts.
    `route_churn` below keeps the route-identity view as a reported fact, since
    it is interesting even though it is not the constraint.
    """
    a, b = visits_per_stop(before), visits_per_stop(after)
    base = sum(a.values()) or 1
    moved = sum(abs(b.get(s, 0) - a.get(s, 0)) for s in set(a) | set(b))
    return moved / base


def route_churn(before: TransitNetwork, after: TransitNetwork) -> float:
    """The route-identity view: how much changed when matched by route id.

    Reported, never enforced. A splice scores high here by construction and
    that is a true statement about route identity, not about service.
    """
    a, b = stop_visits(before), stop_visits(after)
    base = sum(a.values()) or 1
    return sum(abs(b.get(r, 0) - a.get(r, 0))
               for r in set(a) | set(b)) / base


def split_shares(net: TransitNetwork, route_id: str,
                 junction: str) -> tuple[float, float]:
    """Each half's share of a route's stop-visits, if it were cut at `junction`.

    ONE implementation, used by both the generator that proposes splits and the
    validator that accepts them. They previously computed this differently --
    the generator measured on the route's longest pattern, the validator summed
    over every pattern -- so the generator proposed at 30% by its own arithmetic
    and the validator rejected all ten proposals at under 30% by its. The pool
    ended up with zero splits, which is the "advertised operation the search
    cannot reach" failure one level up from the code.

    The validator's reading is the right one and is what this returns:
    stop-visits over ALL of the route's patterns, because that is the unit the
    removal cap and the demand model both work in. Patterns that never reach
    the junction are counted in the denominator and in neither half -- they
    survive the split intact, attached to whichever half contains them, so they
    are part of the route's size but not evidence that either half is big.
    """
    pats = [p for p in net.patterns.values() if p.route_id == route_id]
    total = sum(len(p.stops) for p in pats)
    if not total:
        return 0.0, 0.0
    reach = [p for p in pats if junction in p.stops]
    head = sum(p.stops.index(junction) + 1 for p in reach)
    tail = sum(len(p.stops) - p.stops.index(junction) for p in reach)
    return head / total, tail / total


def _dist_m(coords: dict[str, tuple[float, float]], a: str, b: str) -> float:
    if a not in coords or b not in coords:
        return math.inf
    (x1, y1), (x2, y2) = coords[a], coords[b]
    return math.hypot(x1 - x2, y1 - y2)


# ---------------------------------------------------------------------------
# 1. the mutation, on its own
# ---------------------------------------------------------------------------

def validate_mutation(e: GeometryEdit, net: TransitNetwork,
                      coords: dict[str, tuple[float, float]],
                      limits: ContractLimits) -> None:
    """Everything decidable from the mutation and the network it applies to."""
    if e.kind not in EDIT_KINDS:
        raise ContractViolation("legal-operations",
                                f"{e.kind!r} is not a permitted operation; "
                                f"permitted: {', '.join(EDIT_KINDS)}")

    known = served_stops(net)
    named = (set(e.drop_stops) | set(e.append_stops) | set(e.replace_with)
             | ({e.junction} if e.junction else set())
             | (set(e.replace_between) if e.replace_between else set()))
    unknown = sorted(named - known)
    if unknown:
        raise ContractViolation(
            "existing-stops-only",
            f"{e.key} names stop(s) {unknown} that no route serves. A mutation "
            f"may change which routes serve a stop; it may not create one, "
            f"because ridership at a place that has never had service is "
            f"outside what this demand proxy can supply.")

    live = {p.route_id for p in net.patterns.values()}
    absent = sorted(e.routes_touched() - live)
    if absent:
        raise ContractViolation("live-routes",
                                f"{e.key} names route(s) {absent} that the "
                                f"network does not contain")

    if e.kind == "change_terminal":
        d = _dist_m(coords, e.junction, e.append_stops[0])
        if d > limits.terminal_move_m:
            raise ContractViolation(
                "terminal-move",
                f"{e.key} moves a terminal {d:.0f} m, over the "
                f"{limits.terminal_move_m:.0f} m limit. That is two access "
                f"radii, so a longer move can strand a catchment the model "
                f"would then have to re-house — it is a different route, not a "
                f"mutated one.")

    if e.kind == "split":
        pats = [p for p in net.patterns.values()
                if p.route_id == e.route_id and e.junction in p.stops]
        if not pats:
            raise ContractViolation(
                "split-junction",
                f"{e.key}: {e.junction} is on no pattern of {e.route_id}")
        for p in pats:
            i = p.stops.index(e.junction)
            if i < 1 or i > len(p.stops) - 2:
                raise ContractViolation(
                    "split-junction",
                    f"{e.key}: {e.junction} is a terminal of pattern "
                    f"{p.pattern_id}, so one half would be a single stop")
        head_f, tail_f = split_shares(net, e.route_id, e.junction)
        for name, frac in (("first", head_f), ("second", tail_f)):
            if frac < limits.min_split_share:
                raise ContractViolation(
                    "split-share",
                    f"{e.key}: the {name} half keeps {100.0 * frac:.1f}% of "
                    f"the route's stop-visits, under the "
                    f"{100 * limits.min_split_share:.0f}% floor. Below that it "
                    f"is not half a route, it is a truncation with extra "
                    f"steps.")


# ---------------------------------------------------------------------------
# 2. the set of mutations, before anything is applied
# ---------------------------------------------------------------------------

def validate_state_proposal(edits: Sequence[GeometryEdit], net: TransitNetwork,
                            coords: dict[str, tuple[float, float]],
                            limits: ContractLimits) -> None:
    """Pairwise structure. Cheap, and it runs before any network is built."""
    for e in edits:
        validate_mutation(e, net, coords, limits)

    seen: dict[str, str] = {}
    for e in edits:
        for r in sorted(e.routes_touched()):
            if r in seen:
                raise ContractViolation(
                    "incompatible-pair",
                    f"{seen[r]} and {e.key} both name route {r}. Two mutations "
                    f"on one route are structurally incompatible: their "
                    f"combined effect would depend on application order, and a "
                    f"state whose meaning depends on order has no order-free "
                    f"digest.")
            seen[r] = e.key

    # One mutation's terminal or transfer stop removed by another's truncation.
    removed = {s for e in edits for s in e.drop_stops}
    for e in edits:
        anchors = ({e.junction} if e.junction else set()) \
            | (set(e.replace_between) if e.replace_between else set())
        clash = sorted(anchors & removed)
        if clash:
            owner = next(o.key for o in edits
                         if set(o.drop_stops) & set(clash))
            if owner != e.key:
                raise ContractViolation(
                    "incompatible-pair",
                    f"{owner} removes stop(s) {clash} that {e.key} uses as a "
                    f"terminal or junction")


# ---------------------------------------------------------------------------
# 3. the resulting network — the checks only an outcome can answer
# ---------------------------------------------------------------------------

def validate_applied(before: TransitNetwork, after: TransitNetwork,
                     edits: Sequence[GeometryEdit],
                     limits: ContractLimits,
                     sole_access_stops: Iterable[str] = (),
                     coords: dict[str, tuple[float, float]] | None = None,
                     report: Any = None,
                     veh_hours: float | None = None,
                     edited_baseline_veh_hours: float | None = None,
                     peak_vehicles: float | None = None,
                     waiting_model: str | None = None) -> StateCheck:
    """Check the network a state actually produced.

    Intentions are not outcomes. Truncating one route can strand a stop the
    mutation never names, and a set of individually small edits can exceed the
    network edit-distance boundary together — neither is visible before the
    network exists, which is why this cannot be folded into the generator.
    """
    checked: list[str] = []
    bad: list[str] = []
    facts: dict[str, Any] = {}

    # gate 3-1 — the evaluator states its own waiting model
    checked.append("evaluator-declares-model")
    if waiting_model is not None:
        facts["waiting_model"] = waiting_model
        if waiting_model != limits.required_waiting_model:
            bad.append(
                f"the evaluator priced under {waiting_model!r}, not "
                f"{limits.required_waiting_model!r} (Model B). An unasserted "
                f"evaluator scored three days of Experiment 2 under the wrong "
                f"model.")

    # section 3 — no stop leaves the network INVENTORY
    #
    # Corrected 2026-08-30. This used to refuse any state where a stop ended up
    # served by no route, and that is not what the contract says. The rule is
    # that a mutation may not change which stops EXIST; a truncation
    # legitimately ends service at the stops on the tail it removes -- that is
    # what truncation is, it is explicitly permitted under a 40% cap, and the
    # cost of it appears in the evaluation as unserved demand, priced by the
    # model rather than forbidden by a gate.
    #
    # Conflating the two refused 11 mutations outright and would have silently
    # narrowed Experiment 3 to the interventions that happen to strand nobody.
    # Sole access is the real protection, and it is gate 3-5 below.
    checked.append("no-stop-removed-from-inventory")
    invented = sorted(set(after.stops) - set(before.stops))
    vanished = sorted(set(before.stops) - set(after.stops))
    lost = sorted(served_stops(before) - served_stops(after))
    facts["stops_left_unserved"] = len(lost)
    facts["stops_left_unserved_sample"] = lost[:8]
    if invented or vanished:
        bad.append(f"the stop inventory changed: {len(invented)} created, "
                   f"{len(vanished)} removed. A mutation may change which "
                   f"routes serve a stop; it may not change which stops exist.")

    # gate 3-5 — sole access is protected
    checked.append("sole-access-protected")
    sole = set(sole_access_stops)
    stranded = sorted(sole - served_stops(after))
    facts["sole_access_stranded"] = len(stranded)
    if stranded:
        bad.append(f"sole-access stop(s) {stranded[:5]} left unserved")

    # section 3 — per-route removal cap
    checked.append("route-stop-visit-cap")
    a, b = stop_visits(before), stop_visits(after)
    worst = ("", 0.0)
    for r, n in a.items():
        if r not in b:
            continue                    # consumed by a splice/split, not a loss
        frac = (n - b[r]) / n if n else 0.0
        if frac > worst[1]:
            worst = (r, frac)
        if frac > limits.max_route_stop_visit_loss:
            bad.append(
                f"route {r} loses {100 * frac:.1f}% of its stop-visits, over "
                f"the {100 * limits.max_route_stop_visit_loss:.0f}% cap. Past "
                f"that it is not the route any more and the demand attributed "
                f"to it stops being a fair comparison.")
    facts["worst_route_loss_pct"] = round(100 * worst[1], 3)
    facts["worst_route"] = worst[0]

    # section 3 — the Experiment 3 / Experiment 4 boundary
    checked.append("network-edit-distance")
    ed = edit_distance(before, after)
    facts["network_edit_distance_pct"] = round(100 * ed, 3)
    facts["route_churn_pct"] = round(100 * route_churn(before, after), 3)
    if ed > limits.max_network_edit_distance:
        bad.append(
            f"network edit distance {100 * ed:.1f}% exceeds "
            f"{100 * limits.max_network_edit_distance:.0f}%. That is a real "
            f"result about Experiment 4, not this one — the line is a single "
            f"number precisely so it cannot be argued case by case.")

    # gate 3-9 — modelled-link exposure sets the evidence class
    checked.append("modelled-share-evidence-class")
    if report is not None:
        share = float(getattr(report, "as_dict", lambda: {})()
                      .get("modelled_share_pct", 0.0))
        facts["modelled_share_pct"] = round(share, 4)
        facts["evidence_class"] = ("primary"
                                   if share <= limits.modelled_share_primary_pct
                                   else "secondary")

    # gate 3-4 — no runtime credit for skipping stops on an unchanged alignment
    checked.append("no-skip-stop-runtime-credit")
    offenders = _skip_stop_offenders(before, after, edits, coords,
                                     limits.min_deviation_circuity)
    facts["skip_stop_offenders"] = offenders
    if offenders:
        bad.append(
            f"{offenders} route(s) keep their alignment end to end while "
            f"dropping intermediate stops from it. The seconds a bus saves by "
            f"not serving a stop are not measurable from this feed, so a "
            f"mutation may not be credited with them — that is the deferred "
            f"consolidation question re-entering in disguise.")

    # gate 3-8 — the envelope.
    #
    # Corrected 2026-08-30. This was being handed the EDITED BASELINE's
    # vehicle-hours, before frequency was re-optimized, and it refused 42 of
    # the 84 pool mutations for exceeding the budget by fractions of a percent.
    # That is backwards: the method is mutate, then re-optimize frequency
    # INSIDE the envelope, and the optimizer rescales headways to fit. A
    # mutation that lengthens the network is not over budget; it is a mutation
    # the optimizer has to pay for out of frequency, which is exactly the
    # trade-off Experiment 3 exists to measure.
    #
    # `veh_hours` here must therefore be the OPTIMIZED plan's, and the edited
    # baseline's is recorded as a fact rather than enforced.
    checked.append("envelope")
    if edited_baseline_veh_hours is not None:
        facts["edited_baseline_veh_hours"] = edited_baseline_veh_hours
    if veh_hours is not None and limits.veh_hour_budget is not None:
        facts["optimized_veh_hours"] = veh_hours
        if veh_hours > limits.veh_hour_budget + 1e-6:
            bad.append(f"the OPTIMIZED plan uses {veh_hours:.1f} vehicle-hours, "
                       f"over the pinned budget of "
                       f"{limits.veh_hour_budget:.1f}")
    # The fleet half of gate 3-8 needs the BLOCK-DERIVED peak, the proxy
    # Experiment 1 validated against NTD's VOMS of 198. The frequency model's
    # own `peak_vehicles` is peak concurrency, a different and systematically
    # smaller quantity -- on the unedited network it reads 176 against the
    # block-derived 197. Comparing concurrency to a block-derived budget would
    # pass every plan while appearing to check something, so the check records
    # that it did NOT run rather than running wrong.
    if limits.peak_vehicle_budget is not None:
        if peak_vehicles is None:
            facts["peak_fleet_check"] = (
                "NOT RUN — needs the block-derived peak (blocks.py), not the "
                "frequency model's peak concurrency. Deferred to Stage B/C, "
                "where blocks are reconstructed.")
        else:
            facts["peak_vehicles_block_derived"] = peak_vehicles
            if peak_vehicles > limits.peak_vehicle_budget + 1e-6:
                bad.append(f"{peak_vehicles:.1f} peak vehicles exceeds the "
                           f"{limits.peak_vehicle_budget:.1f} baseline. Hours "
                           f"are not buses: a plan can respect the hour budget "
                           f"and still need a bigger fleet, which is a "
                           f"different experiment with a different cost.")

    return StateCheck(ok=not bad, rules_checked=checked, violations=bad,
                      facts=facts)


def _skip_stop_offenders(before: TransitNetwork, after: TransitNetwork,
                         edits: Sequence[GeometryEdit],
                         coords: dict[str, tuple[float, float]] | None = None,
                         min_circuity: float = 1.10) -> list[str]:
    """Routes that kept their alignment and dropped stops off the middle of it.

    Gate 3-4, made structural. The distinction that matters is not "were stops
    removed" but **did the bus's path change**:

    * a *straighten* removes stops that sat on a deviation, so the vehicle now
      drives a different street. The running-time change is a real alignment
      change and the estimator can price it. Permitted.
    * *stop-skipping* removes stops that sat essentially on the line between
      their neighbours. The vehicle drives the same street; the only saving is
      dwell, which this feed cannot measure. Forbidden.

    Circuity separates them. Without coordinates the geometry is unknowable, so
    the conservative reading applies and any same-ends stop removal is flagged
    — a check that cannot tell must not wave things through.
    """
    touched = {r for e in edits for r in e.routes_touched()}
    out: list[str] = []
    by_route_before: dict[str, list] = {}
    for p in before.patterns.values():
        by_route_before.setdefault(p.route_id, []).append(p)
    by_route_after: dict[str, list] = {}
    for p in after.patterns.values():
        by_route_after.setdefault(p.route_id, []).append(p)

    for rid in sorted(touched & set(by_route_after) & set(by_route_before)):
        for pa in by_route_before[rid]:
            pb = next((q for q in by_route_after[rid]
                       if q.pattern_id == pa.pattern_id), None)
            if pb is None or pb.stops == pa.stops:
                continue
            if not pb.stops or not pa.stops:
                continue
            same_ends = (pb.stops[0] == pa.stops[0]
                         and pb.stops[-1] == pa.stops[-1])
            is_subsequence = set(pb.stops) < set(pa.stops)
            if not (same_ends and is_subsequence):
                continue
            if _was_a_real_deviation(pa.stops, pb.stops, coords, min_circuity):
                continue
            out.append(rid)
            break
    return out


def _was_a_real_deviation(old_stops: Sequence[str], new_stops: Sequence[str],
                          coords: dict[str, tuple[float, float]] | None,
                          min_circuity: float) -> bool:
    """Did removing these stops actually change the path the bus drives?

    For each maximal run of removed stops, compare the old path length through
    them against the straight line between the surviving neighbours. A ratio
    above `min_circuity` means the bus was detouring and now is not.
    """
    if not coords:
        return False                      # cannot tell: assume the worst
    kept = set(new_stops)
    i = 0
    saw_deviation = False
    while i < len(old_stops):
        if old_stops[i] in kept:
            i += 1
            continue
        j = i
        while j < len(old_stops) and old_stops[j] not in kept:
            j += 1
        a = old_stops[i - 1] if i > 0 else None
        b = old_stops[j] if j < len(old_stops) else None
        if a is None or b is None:
            i = j + 1
            continue
        chain = [a, *old_stops[i:j], b]
        through = sum(_dist_m(coords, chain[k], chain[k + 1])
                      for k in range(len(chain) - 1))
        direct = _dist_m(coords, a, b)
        if not math.isfinite(through) or not math.isfinite(direct) or direct <= 0:
            return False                  # cannot tell: assume the worst
        if through / direct < min_circuity:
            return False                  # this run was stops on the line
        saw_deviation = True
        i = j + 1
    return saw_deviation
