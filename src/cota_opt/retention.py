"""The one definition of who still makes the trip, and what counts as unserved.

There were two of these. The production evaluator applied a retention curve to
generalized cost, so an OD pair could be perfectly reachable and still
contribute most of its demand to "unserved" because the only available trip was
bad enough that people would not take it. The Experiment 2 screen counted
demand as unserved only when *no* path existed at all.

Those are different quantities with the same name, which is how a screen ends
up ranking geometry candidates on a concept the authoritative model does not
use: a through-routing that makes existing journeys materially better scores
zero on binary reachability, while an extension into empty territory scores
enormously.

So there is now exactly one implementation, and both callers use it. Binary
reachability survives as its own named measure, ``unreachable_demand``, because
it answers a real and separate question about geographic coverage — it is just
not the same question as "unserved".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Retention:
    """Linear fall-off from full retention to a floor, in generalized minutes."""

    full_min: float = 60.0
    zero_min: float = 210.0
    floor: float = 0.10

    @classmethod
    def from_assumptions(cls, assumptions: dict[str, Any]) -> "Retention":
        pa = assumptions["path_assignment"]
        return cls(full_min=float(pa["cost_retention_full_min"]),
                   zero_min=float(pa["cost_retention_zero_min"]),
                   floor=float(pa["cost_retention_floor"]))

    def keep(self, cost: np.ndarray | float) -> np.ndarray:
        """Share of an OD's travellers who still make the trip at this cost."""
        frac = np.clip((np.asarray(cost, float) - self.full_min)
                       / (self.zero_min - self.full_min), 0.0, 1.0)
        return 1.0 - frac * (1.0 - self.floor)


def score(cost: np.ndarray, flow: np.ndarray, ret: Retention) -> dict[str, float]:
    """Generalized cost and the three ways demand goes unserved.

    ``unreachable`` — no path exists at all, which no frequency plan can fix.
    ``discouraged`` — a path exists but is bad enough that travellers drop it.
    ``unserved``    — the sum of those two, and the quantity the optimizer and
                      every reported frontier actually use.
    """
    cost = np.asarray(cost, float)
    flow = np.asarray(flow, float)
    reachable = np.isfinite(cost)
    unreachable = float(flow[~reachable].sum())

    keep = np.zeros_like(flow)
    keep[reachable] = ret.keep(cost[reachable])
    served = flow * keep
    discouraged = float(flow[reachable].sum() - served.sum())
    served_total = float(served.sum())
    gc = float((served[reachable] * cost[reachable]).sum())
    return {
        "generalized_cost": gc,
        "unreachable_demand": unreachable,
        "discouraged_demand": discouraged,
        "unserved_demand": unreachable + discouraged,
        "served_demand": served_total,
        "gc_per_served_trip": gc / served_total if served_total > 0 else np.inf,
    }
