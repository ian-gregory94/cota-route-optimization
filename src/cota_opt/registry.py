"""Data source registry and provenance subsystem.

Every external dataset enters the project through this module:

- source definitions load from ``config/sources.yaml``;
- raw files are immutable once registered (chmod a-w + checksum guard);
- SHA-256 checksums, retrieval timestamps and version metadata are persisted to
  ``data/raw/_provenance.json``;
- errors are explicit — missing sources or checksum drift raise, never warn.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .paths import config_dir, data_raw

log = logging.getLogger(__name__)


class RegistryError(RuntimeError):
    """Raised for any provenance violation (missing source, checksum drift)."""


@dataclass
class SourceDef:
    """A declared external data source (from config/sources.yaml)."""

    key: str
    name: str
    publisher: str = "UNKNOWN"
    url: str = "UNKNOWN"
    data_type: str = "UNKNOWN"
    coverage: str = "UNKNOWN"
    license: str = "UNKNOWN"
    download_method: str = "UNKNOWN"
    status: str = "UNKNOWN"
    notes: str = ""


@dataclass
class ProvenanceRecord:
    """Provenance for one registered raw file."""

    source_key: str
    path: str                      # relative to data/raw
    sha256: str
    size_bytes: int
    retrieved_at: str              # ISO 8601 UTC
    origin: str                    # URL or human description of how it arrived
    version: str = "UNKNOWN"
    extra: dict[str, Any] = field(default_factory=dict)


def load_sources(path: Path | None = None) -> dict[str, SourceDef]:
    """Load source definitions from configuration."""
    p = path or (config_dir() / "sources.yaml")
    if not p.exists():
        raise RegistryError(f"sources config not found: {p}")
    raw = yaml.safe_load(p.read_text())
    out: dict[str, SourceDef] = {}
    for key, rec in (raw.get("sources") or {}).items():
        known = {f for f in SourceDef.__dataclass_fields__ if f != "key"}
        out[key] = SourceDef(key=key, **{k: v for k, v in rec.items()
                                         if k in known and v is not None})
    return out


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while blob := f.read(chunk):
            h.update(blob)
    return h.hexdigest()


class Registry:
    """Provenance-aware raw data store rooted at ``data/raw``."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or data_raw()
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / "_provenance.json"

    # -- index ------------------------------------------------------------
    def _load_index(self) -> dict[str, dict[str, Any]]:
        if self._index_path.exists():
            return json.loads(self._index_path.read_text())
        return {}

    def _save_index(self, idx: dict[str, dict[str, Any]]) -> None:
        self._index_path.write_text(json.dumps(idx, indent=2, sort_keys=True))

    # -- API --------------------------------------------------------------
    def register_file(
        self,
        source_key: str,
        file_path: Path,
        origin: str,
        version: str = "UNKNOWN",
        move: bool = False,
        extra: dict[str, Any] | None = None,
    ) -> ProvenanceRecord:
        """Copy (or move) a file into the immutable raw store and record it."""
        file_path = Path(file_path)
        if not file_path.exists():
            raise RegistryError(f"cannot register missing file: {file_path}")
        dest_dir = self.root / source_key
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / file_path.name
        if dest.exists():
            existing = self.get(source_key)
            if existing and existing.sha256 == sha256_file(dest):
                new_hash = sha256_file(file_path)
                if new_hash == existing.sha256:
                    log.info("identical file already registered: %s", dest)
                    return existing
            raise RegistryError(
                f"{dest} already registered; refusing to overwrite immutable raw "
                f"data. Use a new source_key or explicitly remove the old record."
            )
        if move:
            shutil.move(str(file_path), dest)
        else:
            shutil.copy2(file_path, dest)
        os.chmod(dest, 0o444)
        rec = ProvenanceRecord(
            source_key=source_key,
            path=str(dest.relative_to(self.root)),
            sha256=sha256_file(dest),
            size_bytes=dest.stat().st_size,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            origin=origin,
            version=version,
            extra=extra or {},
        )
        idx = self._load_index()
        idx[source_key] = asdict(rec)
        self._save_index(idx)
        log.info("registered %s (%d bytes, sha256=%s...)",
                 rec.path, rec.size_bytes, rec.sha256[:12])
        return rec

    def get(self, source_key: str) -> ProvenanceRecord | None:
        rec = self._load_index().get(source_key)
        return ProvenanceRecord(**rec) if rec else None

    def path_for(self, source_key: str, verify: bool = True) -> Path:
        """Absolute path of a registered raw file; verifies checksum by default."""
        rec = self.get(source_key)
        if rec is None:
            raise RegistryError(f"source not registered: {source_key}")
        p = self.root / rec.path
        if not p.exists():
            raise RegistryError(f"registered file missing on disk: {p}")
        if verify and sha256_file(p) != rec.sha256:
            raise RegistryError(f"checksum drift for {source_key}: {p}")
        return p

    def all_records(self) -> dict[str, ProvenanceRecord]:
        return {k: ProvenanceRecord(**v) for k, v in self._load_index().items()}
