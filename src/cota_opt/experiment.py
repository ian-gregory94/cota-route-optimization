"""Experiment framework: reproducible, provenance-stamped runs.

Every experiment persists experiment_id, timestamp, git commit, input dataset
checksums, a config snapshot, the random seed, algorithm name, metrics and
output paths. Reruns with identical inputs and seed are deterministic.
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import config_dir, outputs_dir
from .registry import Registry

log = logging.getLogger(__name__)


def git_commit(repo: Path | None = None) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo or Path.cwd(),
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:  # pragma: no cover - environment dependent
        pass
    return "UNKNOWN"


@dataclass
class ExperimentRecord:
    experiment_id: str
    name: str
    timestamp: str
    git_commit: str
    seed: int
    algorithm: str
    input_checksums: dict[str, str] = field(default_factory=dict)
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    output_paths: list[str] = field(default_factory=list)
    #: The waiting model the EVALUATOR used, taken from the setup that did the
    #: scoring rather than from whatever the launcher was asked for. Those were
    #: different for three days: run_exp2_eval.py set the harness to Model B,
    #: logged "waiting model: same_route", and scored every plan under Model A,
    #: and no artifact recorded it. `None` means the run never declared one and
    #: its numbers cannot be attributed to a model at all.
    evaluator: dict[str, Any] | None = None
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Experiment:
    """Context for one experiment run."""

    def __init__(self, name: str, seed: int, algorithm: str,
                 config_files: list[str] | None = None,
                 registry: Registry | None = None,
                 root: Path | None = None) -> None:
        ts = datetime.now(timezone.utc)
        self.experiment_id = f"{name}_{ts.strftime('%Y%m%dT%H%M%SZ')}"
        self.dir = (root or outputs_dir()) / "experiments" / self.experiment_id
        self.dir.mkdir(parents=True, exist_ok=True)
        reg = registry or Registry()
        checksums = {k: v.sha256 for k, v in reg.all_records().items()}
        snapshot: dict[str, Any] = {}
        for cf in (config_files or []):
            p = config_dir() / cf
            if p.exists():
                snapshot[cf] = p.read_text()
        self.record = ExperimentRecord(
            experiment_id=self.experiment_id, name=name,
            timestamp=ts.isoformat(), git_commit=git_commit(),
            seed=seed, algorithm=algorithm,
            input_checksums=checksums, config_snapshot=snapshot)

    def artifact_path(self, filename: str) -> Path:
        p = self.dir / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        self.record.output_paths.append(str(p))
        return p

    def log_metrics(self, **metrics: Any) -> None:
        self.record.metrics.update(metrics)

    def declare_evaluator(self, setup: Any, expected: str | None = None) -> None:
        """Record what the evaluator actually is, from the evaluator itself.

        ``setup`` is anything carrying a ``checks`` mapping — an Exp2Setup. The
        value is read out of it rather than passed in, because the whole point
        is that what a caller intended and what it got were not the same thing.

        ``expected`` is what the run was launched to do. If it disagrees with
        what the setup came back with, this raises: a run that cannot say which
        model scored its plans should produce no artifact at all.
        """
        checks = dict(getattr(setup, "checks", {}) or {})
        got = checks.get("common_lines")
        if got is None:
            raise ValueError(
                "the setup does not report common_lines, so this run cannot "
                "state which waiting model scored its plans")
        if expected is not None and str(got) != str(expected):
            raise ValueError(
                f"evaluator pricing is {got!r} but the run asked for "
                f"{expected!r}; refusing to write an artifact that would be "
                f"labelled with a model it did not use")
        self.record.evaluator = {
            "common_lines": str(got),
            "source": checks.get("common_lines_source", "unknown"),
            "with_crowding": checks.get("with_crowding"),
            "locked_route_periods": checks.get("locked_route_periods"),
            "requested": expected,
        }

    def save(self) -> Path:
        if self.record.evaluator is None:
            log.warning(
                "experiment %s is being saved with NO evaluator declared. Its "
                "numbers cannot be attributed to a waiting model. Call "
                "declare_evaluator() from the run that does the scoring.",
                self.experiment_id)
        p = self.dir / "experiment.json"
        p.write_text(json.dumps(self.record.to_dict(), indent=2, default=str))
        log.info("experiment saved: %s", p)
        return p


#: Every artifact the freeze scripts regenerate. Shared so that a script does
#: not call the tree dirty because a SIBLING generator is mid-write -- they run
#: together as one freeze, and each seeing the others' output as foreign made
#: every record stamp itself "-dirty" forever.
GENERATED_RECORDS = (
    "outputs/canonical/exp1_final.json",
    "outputs/canonical/pre_exp3_baseline_v1.json",
    "outputs/canonical/pre_exp3_baseline_v2.json",
    "outputs/CANONICAL_RESULTS.json",
    "outputs/SUPERSEDED.md",
    "outputs/repro_check.json",
)


def provenance_commit(root, paths) -> str:
    """The last commit that changed any of `paths` — not HEAD.

    HEAD cannot work here and the reason is structural, not cosmetic. A record
    that stamps HEAD is committed *after* the commit it names, so regenerating
    it writes a different value, which dirties the tree, which means the next
    regeneration writes a different value again. It never converges, and a tag
    script that requires its own checks to leave the tree clean can therefore
    never pass.

    The commit that last touched an input is stable: it moves only when an
    input actually moves, so regenerating an unchanged freeze is a byte-for-byte
    no-op. It is also the provenance a reader actually wants — "this record
    describes the tree as of commit X" — rather than "the file happened to be
    written while HEAD was here".
    """
    import subprocess
    try:
        r = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", *paths],
            cwd=root, capture_output=True, text=True, timeout=60)
        commit = r.stdout.strip()
        if not commit:
            return "UNKNOWN"
        d = subprocess.run(["git", "status", "--porcelain", "--", *paths],
                           cwd=root, capture_output=True, text=True, timeout=60)
        return commit + ("-dirty" if d.stdout.strip() else "")
    except Exception:
        return "UNKNOWN"
