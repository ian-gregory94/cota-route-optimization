"""Reproducible downloaders for external data.

In an unrestricted environment ``download_gtfs`` fetches COTA's official feed
directly. In the current sandbox (egress limited to package registries) the
canonical path is ``ingest_local_gtfs``: the file is retrieved on the user's
machine, staged into the workspace, then registered with full provenance.
Either path produces the same immutable raw artifact.
"""
from __future__ import annotations

import logging
import tempfile
import zipfile
from pathlib import Path

import requests

from .registry import Registry, RegistryError, load_sources
from .paths import data_interim

log = logging.getLogger(__name__)

GTFS_SOURCE_KEY = "cota_gtfs_static"


def download_gtfs(registry: Registry | None = None, refresh: bool = False) -> Path:
    """Download the official COTA GTFS zip and register it. Returns raw path."""
    reg = registry or Registry()
    if not refresh:
        try:
            return reg.path_for(GTFS_SOURCE_KEY)
        except RegistryError:
            pass
    src = load_sources()[GTFS_SOURCE_KEY]
    log.info("downloading %s", src.url)
    resp = requests.get(src.url, timeout=120,
                        headers={"User-Agent": "cota-opt-research/0.1"})
    resp.raise_for_status()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "cota.gtfs.zip"
        tmp.write_bytes(resp.content)
        _assert_valid_zip(tmp)
        rec = reg.register_file(GTFS_SOURCE_KEY, tmp, origin=src.url)
    return reg.root / rec.path


def ingest_local_gtfs(zip_path: Path, origin: str,
                      registry: Registry | None = None) -> Path:
    """Register an externally retrieved GTFS zip (user-mediated download)."""
    reg = registry or Registry()
    zip_path = Path(zip_path)
    _assert_valid_zip(zip_path)
    rec = reg.register_file(GTFS_SOURCE_KEY, zip_path, origin=origin)
    return reg.root / rec.path


def _assert_valid_zip(path: Path) -> None:
    if not zipfile.is_zipfile(path):
        raise RegistryError(f"not a valid zip archive: {path}")
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
    required = {"stops.txt", "routes.txt", "trips.txt", "stop_times.txt"}
    missing = required - names
    if missing:
        raise RegistryError(f"GTFS zip missing required files: {sorted(missing)}")


def unpack_gtfs(registry: Registry | None = None) -> Path:
    """Unpack the registered GTFS zip into data/interim/gtfs (idempotent)."""
    reg = registry or Registry()
    zpath = reg.path_for(GTFS_SOURCE_KEY)
    dest = data_interim() / "gtfs"
    marker = dest / ".sha256"
    rec = reg.get(GTFS_SOURCE_KEY)
    assert rec is not None
    if marker.exists() and marker.read_text().strip() == rec.sha256:
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(dest)
    marker.write_text(rec.sha256)
    log.info("unpacked GTFS to %s", dest)
    return dest
