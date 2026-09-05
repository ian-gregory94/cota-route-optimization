"""Experiment 4's network representation — selection, not mutation.

Experiments 1-3 asked "what happens if I change COTA's network like *this*",
and a state was a `Sequence[GeometryEdit]` applied to the legacy network.
Experiment 4 asks a different question: **which complete network, drawn from a
frozen pool of synthetic lines, is best?** A selection of 41 pool lines is not
expressible as edits to the legacy network, and encoding one as fake edits to
reach `score_state` would hide the change of abstraction inside a type that
lies about what it holds.

So the interface changes, explicitly:

    Exp 1-3   Sequence[GeometryEdit]  ->  apply_edits  ->  (network, tstats)
    Exp 4     Exp4Selection           ->  assemble     ->  (network, tstats)

Everything downstream of `(network, tstats)` is shared. That boundary is the
whole design: the assignment model, RAPTOR semantics, the waiting model,
vehicle-hour and peak-vehicle accounting and the envelope are reused unchanged,
because a greenfield network must be scored on the same yardstick as the
incumbent it claims to beat or the comparison means nothing.

Service activation
------------------
`ACCEPTANCE.md` gate 4-5: a synthetic route-period may be OFF, consuming no
vehicle-hours and no peak vehicles and contributing no frequency. Two distinct
things can put a route-period out of service and they are kept separate:

* **not selected** — the line is not in the network at all. It has no
  route-periods, no patterns, no stops of its own.
* **selected but pinned OFF** — the line exists structurally and this
  (line, period) is fixed to :data:`frequency.OFF`. Used to state a network
  precisely, and by the known-optimum benchmark to construct cases the search
  must find.

Anything not pinned is a *decision*: the optimizer chooses its headway from a
ladder built with ``allow_off=True``, so OFF is a rung it may select. A pinned
OFF is a constraint; an optimizer-chosen OFF is a result. Conflating them would
make it impossible to say which one produced a given network.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .firewall import digest


class Exp4SelectionError(ValueError):
    """A selection that cannot be assembled into a network."""


@dataclass(frozen=True)
class Exp4Selection:
    """Which pool lines run, and which of their route-periods are pinned OFF.

    Frozen and hashable so it can key a cache, and validated at construction so
    a malformed selection fails where it is written rather than deep inside an
    assembler. Nothing here is repaired: a selection naming a line the pool does
    not contain is an error, not an invitation to guess.
    """

    pool_version: str
    lines: frozenset[str]
    pinned_off: frozenset[tuple[str, str]] = frozenset()

    def __post_init__(self) -> None:
        if not self.pool_version:
            raise Exp4SelectionError(
                "a selection must name the pool version it was drawn from; "
                "two selections from different pools are not comparable")
        if not isinstance(self.lines, frozenset):
            object.__setattr__(self, "lines", frozenset(self.lines))
        if not isinstance(self.pinned_off, frozenset):
            object.__setattr__(self, "pinned_off", frozenset(self.pinned_off))
        if not self.lines:
            raise Exp4SelectionError(
                "an empty network is not a comparable cell: it has no "
                "route-periods to optimize and no service to price")
        for entry in self.pinned_off:
            if (not isinstance(entry, tuple)) or len(entry) != 2:
                raise Exp4SelectionError(
                    f"pinned_off entries must be (line_id, period) pairs, got "
                    f"{entry!r}")
            rid, period = entry
            if rid not in self.lines:
                raise Exp4SelectionError(
                    f"cannot pin {rid!r} OFF in period {period!r}: that line is "
                    f"not selected. A line that does not run has no "
                    f"route-periods to switch off, and accepting this would let "
                    f"two different selections describe the same network")

    # -- identity ----------------------------------------------------------
    @property
    def state_key(self) -> str:
        """Human-readable, stable, and short enough to log."""
        n_off = len(self.pinned_off)
        return (f"exp4|{self.pool_version}|{len(self.lines)}lines"
                + (f"|{n_off}off" if n_off else "")
                + f"#{self.state_digest[:12]}")

    @property
    def state_digest(self) -> str:
        """Content digest. Order-independent, because a set has no order."""
        return digest({
            "pool_version": self.pool_version,
            "lines": sorted(self.lines),
            "pinned_off": sorted(map(list, self.pinned_off)),
        })

    @property
    def cardinality(self) -> int:
        return len(self.lines)

    @property
    def members(self) -> list[str]:
        return sorted(self.lines)

    def is_pinned_off(self, line_id: str, period: str) -> bool:
        return (line_id, period) in self.pinned_off

    # -- construction helpers ----------------------------------------------
    @classmethod
    def of(cls, pool_version: str, lines: Iterable[str],
           pinned_off: Iterable[tuple[str, str]] = ()) -> "Exp4Selection":
        return cls(pool_version, frozenset(lines), frozenset(pinned_off))

    def validate_against_pool(self, pool_rids: Mapping[str, object] | Iterable[str],
                              pool_version: str) -> None:
        """Fail closed against the actual pool. Never repairs.

        Called by the assembler before any work. A selection that names an
        unknown line, or that was drawn from a different pool version, is a
        broken selection and is refused -- silently dropping the unknown line
        would score a different network than the one asked for, under the name
        of the one asked for.
        """
        if pool_version != self.pool_version:
            raise Exp4SelectionError(
                f"selection is from pool {self.pool_version!r} but the pool "
                f"supplied is {pool_version!r}; a network is only meaningful "
                f"relative to the pool it was drawn from")
        known = set(pool_rids)
        missing = sorted(self.lines - known)
        if missing:
            raise Exp4SelectionError(
                f"{len(missing)} selected line(s) are not in the pool: "
                f"{missing[:5]}{'...' if len(missing) > 5 else ''}")
