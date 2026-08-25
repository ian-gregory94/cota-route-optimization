"""Canonical repository paths."""
from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """Repository root, overridable via COTA_OPT_ROOT for tests."""
    env = os.environ.get("COTA_OPT_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2]


def data_raw() -> Path:
    return repo_root() / "data" / "raw"


def data_interim() -> Path:
    return repo_root() / "data" / "interim"


def data_processed() -> Path:
    return repo_root() / "data" / "processed"


def outputs_dir() -> Path:
    return repo_root() / "outputs"


def config_dir() -> Path:
    return repo_root() / "config"
