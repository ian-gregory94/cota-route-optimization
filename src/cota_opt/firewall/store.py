"""Cache complete scientific observations, not scores.

A cache entry is only usable if the evaluation that produced it satisfies the
contract asking for it. Keying on a state name is how an entry built under one
evaluator, envelope or objective comes back to answer a question posed under
another -- and the answer looks perfectly ordinary, because a float is a float.

So this store keys on the FULL `EvaluationSpec` digest, and revalidates on
load: spec identity, schema version, and the contract itself. A rejected entry
is not silently rebuilt behind the caller's back; the miss is reported with a
`CACHE_INVALIDATED` event so it appears in the health report.
"""
from __future__ import annotations

import os
import pickle
from dataclasses import dataclass
from pathlib import Path

from .contract import ExperimentContract
from .core import CELL_PREFIX, SCHEMA_VERSION
from .events import EventType, ExecutionEvent, Severity
from .observation import Inadmissible, admit
from .receipt import ExecutionReceipt
from .spec import EvaluationSpec

#: Only the firewall may name files in the observation store. A runner that
#: builds its own path here has, by definition, its own cache identity.
PREFIX = CELL_PREFIX


@dataclass
class CacheMiss:
    reason: str
    event: ExecutionEvent | None = None

    def __bool__(self) -> bool:
        return False


class ObservationStore:
    """Content-addressed store of `ExecutionReceipt`, keyed by spec digest."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, spec: EvaluationSpec) -> Path:
        return self.root / f"{spec.cache_key}.pkl"

    def get(self, spec: EvaluationSpec, contract: ExperimentContract
            ) -> ExecutionReceipt | CacheMiss:
        p = self._path(spec)
        if not p.exists():
            return CacheMiss("no entry")
        try:
            rec = pickle.loads(p.read_bytes())
        except Exception as e:
            return CacheMiss(f"unreadable ({e})", ExecutionEvent(
                EventType.CACHE_INVALIDATED, f"unreadable entry: {e}",
                "firewall.store", changes_opportunity=False,
                changes_semantics=False, severity=Severity.INFO))
        if not isinstance(rec, ExecutionReceipt):
            return CacheMiss("entry is not a receipt")

        # A filename that matches is not a match.
        if rec.spec.digest != spec.digest:
            return CacheMiss("spec digest mismatch", ExecutionEvent(
                EventType.CACHE_INVALIDATED,
                "stored spec does not match the requested one",
                "firewall.store", before=rec.spec.digest, after=spec.digest))
        if rec.schema_version != SCHEMA_VERSION:
            return CacheMiss(f"schema {rec.schema_version}", ExecutionEvent(
                EventType.CACHE_INVALIDATED,
                f"entry written under schema {rec.schema_version}, "
                f"this is {SCHEMA_VERSION}", "firewall.store"))
        verdict = admit(rec, contract)
        if isinstance(verdict, Inadmissible):
            return CacheMiss("inadmissible under this contract: " +
                             "; ".join(verdict.reasons),
                             ExecutionEvent(
                                 EventType.CACHE_INVALIDATED,
                                 "; ".join(verdict.reasons), "firewall.store"))
        return rec

    def put(self, receipt: ExecutionReceipt) -> Path:
        p = self._path(receipt.spec)
        tmp = p.with_suffix(".tmp")
        with tmp.open("wb") as f:
            f.write(pickle.dumps(receipt, protocol=pickle.HIGHEST_PROTOCOL))
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(p)
        return p

    def all(self) -> list[ExecutionReceipt]:
        out = []
        for p in sorted(self.root.glob(f"{PREFIX}*.pkl")):
            try:
                r = pickle.loads(p.read_bytes())
            except Exception:
                continue
            if isinstance(r, ExecutionReceipt):
                out.append(r)
        return out
