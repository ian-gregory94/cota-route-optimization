"""Typed loading of YAML configuration."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .paths import config_dir


def load_yaml(name: str, base: Path | None = None) -> dict[str, Any]:
    p = (base or config_dir()) / name
    if not p.exists():
        raise FileNotFoundError(f"config file not found: {p}")
    return yaml.safe_load(p.read_text()) or {}


def load_assumptions(base: Path | None = None) -> dict[str, Any]:
    return load_yaml("assumptions.yaml", base)


def load_cost_weights(base: Path | None = None) -> dict[str, float]:
    return load_yaml("cost_weights.yaml", base)["weights"]


def load_constraints(base: Path | None = None) -> dict[str, Any]:
    return load_yaml("constraints.yaml", base)


def service_periods(assumptions: dict[str, Any]) -> dict[str, tuple[float, float]]:
    return {k: (float(v[0]), float(v[1]))
            for k, v in assumptions["service_periods"].items()}


def period_of_seconds(sec: float, periods: dict[str, tuple[float, float]]) -> str | None:
    """Map seconds-since-service-midnight to a period name.

    Hours >= 24 wrap for comparison against periods extending past 24 (owl).
    Hours in [0, 4) are treated as 24+h (late-night tail of the service day).
    """
    h = sec / 3600.0
    if h < 4.0:
        h += 24.0
    for name, (a, b) in periods.items():
        if a <= h < b:
            return name
    return None
