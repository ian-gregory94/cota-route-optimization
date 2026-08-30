"""The Experiment 3 atomic mutation pool, and the audit of what was rejected.

Frozen before scoring, generated from rules declared before generation. Three
properties matter more than the pool's contents:

**Deterministic.** Same network, same config, same pool — byte for byte. The
pool version is part of every cache key, so a pool that quietly changed would
otherwise be served the old pool's scores.

**Structural and demand rules only.** Nothing here evaluates a plan. Gate 3-2
forbids a fixed-frequency screen from deciding what gets evaluated: D19 found
the screen's first pick of sixty to be the worst of twelve, and D23 found the
ranking to move again under a corrected waiting model. Proposals are ranked by
running-time share against uniquely-reached demand — properties of the network,
not of any evaluation of it — and that ranking bounds a pool; it never selects
a winner.

**Every rejection is recorded, with its reason.** A pool reported only as "412
candidates" cannot be argued with. The audit says what was proposed, what
survived, and which rule removed each one that did not, so a reader can ask
whether a rule is doing what it claims — and so a later experiment can lift a
rule and know exactly what it gets back.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np

from . import candidates as cand
from .contract import (ContractLimits, ContractViolation,
                       split_shares, validate_mutation)
from .exp3 import POOL_VERSION, mutation_id
from .geometry import GeometryEdit
from .network import RoutePattern, TransitNetwork

log = logging.getLogger(__name__)


#: Per-kind caps, declared here and applied after ranking. Quotas exist so one
#: prolific generator cannot flood the pool -- splices alone could fill it,
#: which is how Experiment 2 ended up a splice-only experiment without anyone
#: choosing that. Committed before scoring, as the contract requires.
KIND_QUOTA = {
    "truncate": 12,
    "straighten": 12,
    "extend": 12,
    "reroute": 12,
    "splice": 12,
    "add_stop": 10,
    "change_terminal": 10,
    "split": 10,
}


@dataclass
class PoolAudit:
    """What was proposed, what survived, and why the rest did not."""

    pool_version: str
    accepted: list[GeometryEdit] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    proposed: int = 0
    quotas: dict[str, int] = field(default_factory=dict)
    unfilled: dict[str, Any] = field(default_factory=dict)
    liveness: dict[str, Any] = field(default_factory=dict)

    def reject(self, e: GeometryEdit, rule: str, why: str) -> None:
        self.rejected.append({"id": mutation_id(e), "kind": e.kind,
                              "route_id": e.route_id, "rule": rule,
                              "reason": why, "description": e.description})

    def as_dict(self) -> dict[str, Any]:
        return {
            "pool_version": self.pool_version,
            "proposed": self.proposed,
            "accepted": len(self.accepted),
            "rejected": len(self.rejected),
            "quotas": self.quotas,
            "accepted_by_kind": dict(Counter(e.kind for e in self.accepted)),
            "rejected_by_rule": dict(Counter(r["rule"] for r in self.rejected)),
            "rejected_by_kind": dict(Counter(r["kind"] for r in self.rejected)),
            "quotas_not_filled": self.unfilled,
            "quotas_not_filled_note":
                "The network does not contain this many legal proposals of "
                "these kinds. Stated rather than left for a reader to infer "
                "from a count that looks like a choice.",
            "rule_liveness": self.liveness,
            "mutations": [{"id": mutation_id(e), "kind": e.kind,
                           "route_id": e.route_id, "with_route": e.with_route,
                           "junction": e.junction,
                           "description": e.description,
                           # Every field GeometryEdit needs to be rebuilt. A
                           # frozen pool that cannot be RELOADED is not frozen:
                           # the next run would have to regenerate it, and a
                           # regenerated pool is a different pool the moment
                           # anything upstream moves.
                           "raw": {"drop_stops": list(e.drop_stops),
                                   "append_stops": list(e.append_stops),
                                   "replace_between": (list(e.replace_between)
                                                       if e.replace_between
                                                       else None),
                                   "replace_with": list(e.replace_with)},
                           "evidence": {k: v for k, v in e.evidence.items()
                                        if isinstance(v, (int, float, str,
                                                          bool, type(None)))}}
                          for e in self.accepted],
            "rejections": self.rejected,
            "note": "Ranked by structural and demand rules only. No proposal "
                    "was discarded on a fixed-frequency score (gate 3-2), and "
                    "no proposal was discarded for scoring badly alone — "
                    "Experiment 2B's whole finding is that a candidate that "
                    "hurts alone can substitute for one that helps.",
        }


# ---------------------------------------------------------------------------
# generators for the three operations Experiment 2 never had
# ---------------------------------------------------------------------------

def split_candidates(net: TransitNetwork, ctx: cand.StopContext,
                     min_share: float = 0.30,
                     min_stops: int = 10,
                     exclude_routes: set[str] | None = None,
                     top_n: int = 10) -> list[GeometryEdit]:
    """Long routes cut at an interior stop that already connects elsewhere.

    Splitting is the only operation that raises the route count, and the case
    for it is a specific one: a long route forces every rider on it to pay for
    running time they do not use, and its frequency is set by its longest
    section. Cutting at a stop several routes already serve turns a captive
    through-ride into a transfer that the network can absorb -- and the
    frequency optimizer, given two shorter routes, can price them separately.

    Ranked by how balanced the cut is and how well-connected the junction is:
    both structural. A cut at a stop nothing else serves creates a transfer
    with nothing to transfer to.
    """
    skip = exclude_routes or set()
    out: list[tuple[float, GeometryEdit]] = []
    for rid in sorted(net.route_stops):
        if rid in skip:
            continue
        p = cand._longest_pattern(net, rid)
        if p is None or len(p.stops) < min_stops:
            continue
        n = len(p.stops)
        for i, sid in enumerate(p.stops):
            if i < 1 or i > n - 2:
                continue
            # The validator's arithmetic, not a second copy of it. These two
            # disagreed once and the pool silently lost every split.
            head_f, tail_f = split_shares(net, rid, sid)
            share = min(head_f, tail_f)
            if share < min_share:
                continue
            head, tail = i + 1, n - i
            others = len(net.stop_routes.get(sid, set()) - {rid})
            if others < 1:
                continue
            # balance in [0, 1], 1 = a perfectly even cut; connectivity capped
            # so a downtown hub cannot dominate on connections alone.
            balance = 2.0 * share
            score = balance + min(others, 4) / 8.0
            out.append((score, GeometryEdit(
                kind="split", route_id=rid, junction=sid,
                description=(
                    f"split route {rid} at {sid} into two independently "
                    f"scheduled routes of {head} and {tail} stops "
                    f"({100 * share:.0f}% / {100 * (1 - share):.0f}%); "
                    f"{others} other route(s) already serve the cut, so the "
                    f"transfer it creates has somewhere to go"),
                evidence={"junction": sid, "head_stops": head,
                          "tail_stops": tail, "min_share": share,
                          "other_routes_at_junction": others})))
    return cand._best(out, top_n, key=lambda e: e.route_id)


def terminal_candidates(net: TransitNetwork, ctx: cand.StopContext,
                        limits: ContractLimits,
                        min_move_m: float = 150.0,
                        exclude_routes: set[str] | None = None,
                        top_n: int = 10) -> list[GeometryEdit]:
    """Terminals moved to a nearby stop that reaches more unique demand.

    Bounded by the contract's 1,200 m rule, which is two access radii -- far
    enough to matter, near enough that the move cannot silently strand a
    catchment the model would then have to re-house.
    """
    skip = exclude_routes or set()
    out: list[tuple[float, GeometryEdit]] = []
    for rid in sorted(net.route_stops):
        if rid in skip:
            continue
        p = cand._longest_pattern(net, rid)
        if p is None or len(p.stops) < 4:
            continue
        for term in (p.stops[0], p.stops[-1]):
            here = ctx.exclusive_weight(term)
            for other in sorted(ctx.coords):
                if other == term or other in p.stops:
                    continue
                d = cand._straight_m(ctx, term, other)
                if not (min_move_m <= d <= limits.terminal_move_m):
                    continue
                gain = ctx.exclusive_weight(other) - here
                if gain <= 0:
                    continue
                out.append((gain / max(d, 1.0), GeometryEdit(
                    kind="change_terminal", route_id=rid, junction=term,
                    append_stops=(other,),
                    description=(
                        f"move route {rid}'s terminal from {term} to {other}, "
                        f"{d:.0f} m away, reaching {gain:.0f} more units of "
                        f"demand no other route serves"),
                    evidence={"from": term, "to": other, "metres": d,
                              "exclusive_demand_gain": float(gain)})))
    return cand._best(out, top_n, key=lambda e: (e.route_id, e.junction))


def add_stop_candidates(net: TransitNetwork, ctx: cand.StopContext,
                        max_detour_m: float = 400.0,
                        exclude_routes: set[str] | None = None,
                        top_n: int = 10) -> list[GeometryEdit]:
    """Existing stops a route passes close to without serving.

    The cheapest mutation in the vocabulary and the one most likely to be
    dismissed as trivial, which is exactly why it is in the pool: Experiment 2B
    found that the expensive edits all lose to the budget, so an edit that costs
    almost nothing is the one with a chance of surviving it.
    """
    skip = exclude_routes or set()
    out: list[tuple[float, GeometryEdit]] = []
    for rid in sorted(net.route_stops):
        if rid in skip:
            continue
        p = cand._longest_pattern(net, rid)
        if p is None or len(p.stops) < 3:
            continue
        on_route = set(p.stops)
        for sid in sorted(ctx.coords):
            if sid in on_route:
                continue
            w = ctx.exclusive_weight(sid)
            if w <= 0:
                continue
            best = None
            for i in range(len(p.stops) - 1):
                a, b = p.stops[i], p.stops[i + 1]
                detour = (cand._straight_m(ctx, a, sid)
                          + cand._straight_m(ctx, sid, b)
                          - cand._straight_m(ctx, a, b))
                if best is None or detour < best:
                    best = detour
            if best is None or best > max_detour_m:
                continue
            out.append((w / max(best, 1.0), GeometryEdit(
                kind="add_stop", route_id=rid, append_stops=(sid,),
                description=(
                    f"add stop {sid} to route {rid}: a {best:.0f} m detour "
                    f"reaching {w:.0f} units of demand no other route serves"),
                evidence={"stop": sid, "detour_m": float(best),
                          "exclusive_demand": float(w)})))
    return cand._best(out, top_n, key=lambda e: (e.route_id,))


# ---------------------------------------------------------------------------
# the pool
# ---------------------------------------------------------------------------

#: Generators are asked for this multiple of each quota, and the surplus is
#: trimmed afterwards. Two reasons, both about the audit being worth reading.
#:
#: Generating exactly the quota makes every rejection invisible: proposals die
#: inside `_best` with no record, the audit reports zero rejections, and a
#: broken filter is indistinguishable from a clean pool. Oversampling also puts
#: the contract validator in front of proposals the generators' own heuristics
#: would have hidden, which is how the split-share disagreement between the
#: generator and the validator was found at all.
OVERSAMPLE = 3


def build_pool(net: TransitNetwork, ctx: cand.StopContext, zs,
               stop_ids: list[str], od_zone_flow: np.ndarray,
               trips_by_route: dict[str, int],
               limits: ContractLimits,
               exclude_routes: set[str] | None = None,
               quotas: dict[str, int] | None = None,
               pool_version: str = POOL_VERSION,
               oversample: int = OVERSAMPLE) -> PoolAudit:
    """Every generator, contract-validated, quota-capped, fully audited.

    The order of operations is deliberate: generate wide, validate everything,
    then trim to quota. An illegal proposal appears in the audit with the rule
    that removed it rather than never existing, and the quota's effect is
    visible rather than buried inside each generator's own shortlist. A pool
    that silently declines to propose something cannot be told apart from a
    generator that could not think of it.
    """
    q = dict(KIND_QUOTA if quotas is None else quotas)
    ex = set(exclude_routes or set())
    audit = PoolAudit(pool_version=pool_version, quotas=q)
    n = lambda k: max(1, q.get(k, 10) * oversample)          # noqa: E731

    raw: list[GeometryEdit] = []
    raw += cand.truncation_candidates(net, ctx, exclude_routes=ex,
                                      top_n=n("truncate"))
    raw += cand.straighten_candidates(net, ctx, exclude_routes=ex,
                                      top_n=n("straighten"))
    raw += cand.extension_candidates(net, ctx, zs, stop_ids, od_zone_flow,
                                     trips_by_route, exclude_routes=ex,
                                     top_n=n("extend"))
    raw += cand.reroute_candidates(net, ctx, exclude_routes=ex,
                                   top_n=n("reroute"))
    raw += cand.splice_candidates(net, ctx, exclude_routes=ex,
                                  top_n=n("splice"))
    raw += split_candidates(net, ctx, exclude_routes=ex, top_n=n("split"))
    raw += terminal_candidates(net, ctx, limits, exclude_routes=ex,
                               top_n=n("change_terminal"))
    raw += add_stop_candidates(net, ctx, exclude_routes=ex,
                               top_n=n("add_stop"))
    audit.proposed = len(raw)

    seen: set[str] = set()
    legal: list[GeometryEdit] = []
    for e in raw:
        mid = mutation_id(e)
        if mid in seen:
            audit.reject(e, "duplicate",
                         "an identical mutation was already proposed")
            continue
        try:
            validate_mutation(e, net, ctx.coords, limits)
        except ContractViolation as v:
            audit.reject(e, v.rule, v.detail)
            continue
        seen.add(mid)
        legal.append(e)

    # Trim to quota, keeping generator order (which is structural rank). What
    # the quota cut is recorded, not discarded silently: a reader can see
    # exactly what a wider pool would have contained.
    kept_by_kind: dict[str, int] = {}
    for e in legal:
        cap = q.get(e.kind, 10)
        if kept_by_kind.get(e.kind, 0) >= cap:
            audit.reject(e, "quota",
                         f"the {e.kind} quota of {cap} was already full; this "
                         f"proposal was legal and ranked below the cut")
            continue
        kept_by_kind[e.kind] = kept_by_kind.get(e.kind, 0) + 1
        audit.accepted.append(e)

    # Deterministic final order: by id, so the pool is a set with a canonical
    # listing and a shard partition cannot depend on generation order. That is
    # not hypothetical -- Experiment 2B lost 57 of 240 subsets to exactly this.
    audit.accepted.sort(key=mutation_id)
    got = Counter(e.kind for e in audit.accepted)
    audit.unfilled = {k: {"quota": v, "accepted": got.get(k, 0)}
                      for k, v in q.items() if got.get(k, 0) < v}
    audit.liveness = probe_rules(net, ctx.coords, limits)
    log.info("mutation pool %s: %d proposed, %d accepted (%s), %d rejected",
             pool_version, audit.proposed, len(audit.accepted),
             dict(got), len(audit.rejected))
    if audit.unfilled:
        log.info("quotas NOT filled: %s — the network does not contain that "
                 "many legal proposals of those kinds", audit.unfilled)
    return audit


def probe_rules(net: TransitNetwork, coords: dict[str, tuple[float, float]],
                limits: ContractLimits) -> dict[str, Any]:
    """Confirm each contract rule actually fires, on mutations built to break it.

    An audit reporting zero contract rejections is ambiguous: either the
    generators respect every rule, or the checker is a no-op. This resolves it
    by handing the validator deliberately illegal mutations and recording which
    rule caught each. A probe that does NOT raise is the interesting result and
    is recorded as a failure, because it means a rule the contract advertises is
    not being enforced.
    """
    live = {p.route_id for p in net.patterns.values()}
    any_route = sorted(live)[0] if live else "?"
    probes: list[tuple[str, str, GeometryEdit]] = []
    probes.append(("existing-stops-only", "a stop that does not exist",
                   GeometryEdit(kind="add_stop", route_id=any_route,
                                append_stops=("__NO_SUCH_STOP__",),
                                description="probe")))
    probes.append(("live-routes", "a route that does not exist",
                   GeometryEdit(kind="truncate", route_id="__NO_SUCH_ROUTE__",
                                drop_stops=(), description="probe")))
    served = sorted({s for p in net.patterns.values() for s in p.stops})
    if len(served) >= 2 and coords:
        far = max(served[1:], key=lambda s: _probe_dist(coords, served[0], s))
        probes.append(("terminal-move", "a terminal moved beyond the limit",
                       GeometryEdit(kind="change_terminal", route_id=any_route,
                                    junction=served[0], append_stops=(far,),
                                    description="probe")))
    out: dict[str, Any] = {"checked": [], "not_enforced": []}
    for rule, what, e in probes:
        try:
            validate_mutation(e, net, coords, limits)
        except ContractViolation as v:
            out["checked"].append({"rule": rule, "probe": what,
                                   "caught_by": v.rule})
            continue
        except Exception as exc:                      # noqa: BLE001
            out["checked"].append({"rule": rule, "probe": what,
                                   "caught_by": type(exc).__name__})
            continue
        out["not_enforced"].append({"rule": rule, "probe": what})
    out["all_rules_fire"] = not out["not_enforced"]
    out["note"] = ("Deliberately illegal mutations, one per rule, handed to the "
                   "validator. This is what makes a zero-contract-rejection "
                   "audit evidence about the GENERATORS rather than about the "
                   "checker.")
    return out


def _probe_dist(coords: dict[str, tuple[float, float]], a: str, b: str) -> float:
    if a not in coords or b not in coords:
        return 0.0
    (x1, y1), (x2, y2) = coords[a], coords[b]
    return ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5


def edit_from_record(m: dict[str, Any]) -> GeometryEdit:
    """Rebuild a GeometryEdit from a frozen pool record, losslessly.

    Paired with the `raw` block PoolAudit writes. `tests/test_mutate.py` round-
    trips every accepted mutation through this and asserts the canonical id
    comes back unchanged — because an id that shifts on reload would make the
    pool version meaningless and every cached score unreachable.
    """
    raw = m.get("raw") or {}
    return GeometryEdit(
        kind=m["kind"], route_id=m["route_id"],
        description=m.get("description", ""),
        with_route=m.get("with_route"), junction=m.get("junction"),
        drop_stops=tuple(raw.get("drop_stops") or ()),
        append_stops=tuple(raw.get("append_stops") or ()),
        replace_between=(tuple(raw["replace_between"])
                         if raw.get("replace_between") else None),
        replace_with=tuple(raw.get("replace_with") or ()))


def incompatible_pairs(edits: Sequence[GeometryEdit]) -> list[tuple[str, str]]:
    """Pairs that may never appear in one state, by structure alone.

    Two mutations naming a common route, or one removing a stop the other
    anchors on. Structure, never measured performance -- excluding a candidate
    because it scores badly alone would assume exactly the composability
    Experiment 2B exists to have tested.
    """
    out: list[tuple[str, str]] = []
    ids = [mutation_id(e) for e in edits]
    for i, a in enumerate(edits):
        for j in range(i + 1, len(edits)):
            b = edits[j]
            shares = a.routes_touched() & b.routes_touched()
            a_anchor = ({a.junction} if a.junction else set()) | (
                set(a.replace_between) if a.replace_between else set())
            b_anchor = ({b.junction} if b.junction else set()) | (
                set(b.replace_between) if b.replace_between else set())
            strands = (set(a.drop_stops) & b_anchor) or (set(b.drop_stops)
                                                         & a_anchor)
            if shares or strands:
                out.append(tuple(sorted((ids[i], ids[j]))))
    return sorted(set(out))
