"""Generalized passenger cost API.

Cost is expressed in *equivalent in-vehicle minutes*. Every component weight is
configurable (``config/cost_weights.yaml``); nothing here hard-codes a research
assumption. Components: walking, waiting, in-vehicle, transfer wait, transfer
count, crowding, reliability (placeholder), unserved demand.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class CostWeights:
    walking: float = 2.0
    waiting: float = 2.0
    in_vehicle: float = 1.0
    transfer_wait: float = 2.0
    transfer_penalty: float = 10.0
    crowding: float = 1.0
    reliability: float = 0.0
    unserved: float = 60.0

    @classmethod
    def from_config(cls, d: dict) -> "CostWeights":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: float(v) for k, v in d.items() if k in known})


@dataclass(frozen=True)
class TripCostComponents:
    """Per-passenger-trip time components, in raw minutes (unweighted)."""

    walk_min: float = 0.0
    wait_min: float = 0.0
    in_vehicle_min: float = 0.0
    transfer_wait_min: float = 0.0
    n_transfers: float = 0.0
    crowding_excess: float = 0.0   # extra in-vehicle-equivalent min from crowding
    reliability_min: float = 0.0

    def generalized_cost(self, w: CostWeights) -> float:
        """Weighted sum → equivalent in-vehicle minutes."""
        return (
            w.walking * self.walk_min
            + w.waiting * self.wait_min
            + w.in_vehicle * self.in_vehicle_min
            + w.transfer_wait * self.transfer_wait_min
            + w.transfer_penalty * self.n_transfers
            + w.crowding * self.crowding_excess
            + w.reliability * self.reliability_min
        )

    def to_dict(self) -> dict:
        return asdict(self)


def expected_wait_min(headway_min: float, random_arrival_threshold_min: float = 12.0,
                      schedule_coefficient: float = 0.25) -> float:
    """Expected passenger wait given a headway.

    Random arrivals for frequent service (E[wait] = h/2); on infrequent service
    passengers consult the schedule and the marginal wait grows more slowly.

    >>> round(expected_wait_min(10), 3)
    5.0
    >>> round(expected_wait_min(12), 3)
    6.0
    >>> round(expected_wait_min(60), 3)   # 6 + 0.25*48
    18.0
    """
    if headway_min <= 0:
        raise ValueError("headway must be positive")
    t = random_arrival_threshold_min
    if headway_min <= t:
        return headway_min / 2.0
    return t / 2.0 + schedule_coefficient * (headway_min - t)


def demand_retention(headway_min: float, full_min: float = 15.0,
                     zero_min: float = 120.0, floor: float = 0.25) -> float:
    """Fraction of potential demand retained at a given headway.

    Linear from 1.0 at ``full_min`` down to ``floor`` at ``zero_min``.

    >>> demand_retention(10)
    1.0
    >>> round(demand_retention(120), 3)
    0.25
    """
    if headway_min <= full_min:
        return 1.0
    if headway_min >= zero_min:
        return floor
    frac = (headway_min - full_min) / (zero_min - full_min)
    return 1.0 - frac * (1.0 - floor)


def crowding_excess_min(passengers_per_trip: float, capacity: float,
                        in_vehicle_min: float, penalty: float = 1.0) -> float:
    """Extra generalized in-vehicle minutes from crowding above capacity.

    Zero at or below capacity; grows linearly with the excess load factor.

    >>> crowding_excess_min(30, 60, 20)
    0.0
    >>> crowding_excess_min(90, 60, 20, 1.0)   # load factor 1.5 → 0.5*20
    10.0
    """
    if capacity <= 0:
        raise ValueError("capacity must be positive")
    load = passengers_per_trip / capacity
    if load <= 1.0:
        return 0.0
    return penalty * (load - 1.0) * in_vehicle_min


def unserved_cost(n_unserved: float, w: CostWeights, multiplier: float = 1.0) -> float:
    """Penalty for demand that cannot access service."""
    return multiplier * w.unserved * n_unserved
