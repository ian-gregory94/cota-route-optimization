"""Durable, content-addressed cache for expensive build artifacts.

Every experiment rebuilds the same things: the GTFS baseline, the RAPTOR
network, the zone system, the OD table, and — most expensively — the per-period
candidate path sets (~9 minutes). Rebuilding those on each run made long,
properly-searched experiments impractical, which is how an under-powered search
ended up being compared against a well-powered one.

Cache entries live in ``data/cache/`` (inside the repo, so they survive a
scratch-space wipe) and are keyed by a hash of the inputs that actually affect
the artifact. Change a relevant config value and the key changes, so a stale
entry can never be silently reused.
"""
from __future__ import annotations

import hashlib
import json
import logging
import pickle
import time
from pathlib import Path
from typing import Any, Callable

from .paths import repo_root

log = logging.getLogger(__name__)


def cache_dir() -> Path:
    d = repo_root() / "data" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def key_of(name: str, params: dict[str, Any]) -> str:
    """Stable hash of a builder name plus the inputs that determine its output."""
    blob = json.dumps({"name": name, "params": params}, sort_keys=True,
                      default=str).encode()
    return f"{name}-{hashlib.sha256(blob).hexdigest()[:16]}"


def cached(name: str, params: dict[str, Any], build: Callable[[], Any],
           enabled: bool = True) -> Any:
    """Return a cached artifact, building and storing it on a miss."""
    if not enabled:
        return build()
    k = key_of(name, params)
    p = cache_dir() / f"{k}.pkl"
    if p.exists():
        try:
            t = time.time()
            obj = pickle.loads(p.read_bytes())
            log.info("cache hit  %s (%.1f MB, %.1fs)", k,
                     p.stat().st_size / 1e6, time.time() - t)
            return obj
        except Exception as e:      # a corrupt entry must never be fatal
            log.warning("cache entry %s unreadable (%s), rebuilding", k, e)
            p.unlink(missing_ok=True)
    t = time.time()
    obj = build()
    build_s = time.time() - t
    try:
        p.write_bytes(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))
        log.info("cache store %s (%.1f MB, built in %.0fs)", k,
                 p.stat().st_size / 1e6, build_s)
    except Exception as e:
        log.warning("could not cache %s: %s", k, e)
    return obj


def clear(prefix: str | None = None) -> int:
    n = 0
    for p in cache_dir().glob("*.pkl"):
        if prefix is None or p.name.startswith(prefix):
            p.unlink()
            n += 1
    return n


def summary() -> list[dict[str, Any]]:
    return sorted(
        ({"entry": p.stem, "mb": round(p.stat().st_size / 1e6, 1)}
         for p in cache_dir().glob("*.pkl")),
        key=lambda d: -d["mb"])


# ---------------------------------------------------------------------------
# Checkpointed result store: one row per solved cell, resumable
# ---------------------------------------------------------------------------

class ResultStore:
    """Append-only JSONL of solved cells so a long run can resume where it died."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._done: dict[str, dict] = {}
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    self._done[rec["cell"]] = rec
                except json.JSONDecodeError:
                    continue
            log.info("result store: %d cells already solved", len(self._done))

    def has(self, cell: str) -> bool:
        return cell in self._done

    def get(self, cell: str) -> dict | None:
        return self._done.get(cell)

    def put(self, cell: str, record: dict) -> None:
        rec = {"cell": cell, **record}
        with open(self.path, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        self._done[cell] = rec

    def rows(self) -> list[dict]:
        return list(self._done.values())
