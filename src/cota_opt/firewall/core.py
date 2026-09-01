"""Deterministic serialization, digests, and semantic field classification.

Everything downstream hashes and compares through here, so two artifacts that
mean the same thing produce the same bytes and two that do not, do not.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from enum import Enum
from typing import Any

SCHEMA_VERSION = "firewall/1"


class Sem(str, Enum):
    """What a field means for the admissibility of a comparison.

    IDENTITY
        What the evaluation *was*: evaluator, objective, envelope, contract,
        state. Two cells being compared must agree unless the contract names
        the field as a treatment dimension.

    OPPORTUNITY
        What the execution actually *got*: which starts were attempted, how
        many restarts completed, whether anything fell back, why it stopped.
        Also compared by default, because two arms with equal nominal effort
        can still receive unequal search opportunity -- which is precisely how
        D27 produced a treatment-correlated optimizer without a single
        configuration field differing.

    OUTCOME
        What the evaluation *found*. Never an admissibility input: this is the
        measurement, and requiring it to match would compare nothing.

    NONE
        Not semantic at all -- wall-clock, pids, timestamps. Declared on the
        type rather than filtered by name in the comparator, so the comparator
        has no list of exceptions to fall out of date.
    """

    IDENTITY = "identity"
    OPPORTUNITY = "opportunity"
    OUTCOME = "outcome"
    NONE = "none"


def semfield(sem: Sem, **kw):
    """A dataclass field that declares what it means for comparability."""
    md = dict(kw.pop("metadata", {}))
    md["sem"] = sem
    return dataclasses.field(metadata=md, **kw)


def _plain(obj: Any) -> Any:
    """Reduce to JSON-able primitives, deterministically."""
    # Enum FIRST: a str-Enum is an instance of str, so a primitive check ahead
    # of this one leaks enum objects into what is supposed to be plain data.
    if isinstance(obj, Enum):
        return obj.value
    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    if isinstance(obj, float):
        # Round-trip stable, and NaN/inf are not valid JSON.
        if obj != obj:
            return "NaN"
        if obj in (float("inf"), float("-inf")):
            return "Infinity" if obj > 0 else "-Infinity"
        return obj
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted(_plain(v) for v in obj)
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in sorted(obj.items(), key=lambda x: str(x[0]))}
    if dataclasses.is_dataclass(obj):
        return {f.name: _plain(getattr(obj, f.name))
                for f in dataclasses.fields(obj)}
    return str(obj)


def canonical_json(obj: Any) -> str:
    return json.dumps(_plain(obj), sort_keys=True, separators=(",", ":"))


def digest(obj: Any, n: int = 16) -> str:
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()[:n]


def fields_by_sem(obj: Any, sem: Sem, prefix: str = "") -> dict[str, Any]:
    """Flatten a dataclass to ``{dotted_name: value}`` for one meaning class.

    Nested dataclasses are walked, and a nested field keeps its own declared
    meaning -- so a policy object embedded in a spec contributes its identity
    fields to the spec's identity map without anything having to list them.

    This walk is why the firewall does not need to know the next bug: a field
    added anywhere in the spec or receipt is compared from the moment it
    exists, and the default for an undeclared difference is refusal.
    """
    out: dict[str, Any] = {}
    if not dataclasses.is_dataclass(obj):
        return out
    for f in dataclasses.fields(obj):
        v = getattr(obj, f.name)
        name = f"{prefix}{f.name}"
        own = f.metadata.get("sem", Sem.IDENTITY)
        if dataclasses.is_dataclass(v) and not isinstance(v, type):
            out.update(fields_by_sem(v, sem, prefix=f"{name}."))
            continue
        if own == sem:
            out[name] = _plain(v)
    return out
