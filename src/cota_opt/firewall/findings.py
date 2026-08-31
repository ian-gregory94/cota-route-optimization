"""Findings that know what they rest on.

Section 22. A canonical claim cites the comparisons behind it, so that when an
upstream observation is later marked superseded -- as 131 of them just were --
the claims that depended on it can be *named* rather than left standing on a
slide looking current.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .core import SCHEMA_VERSION, digest


@dataclass(frozen=True)
class Finding:
    """One claim, with its evidence attached."""

    id: str
    claim: str
    experiment: str
    stage: str
    contract_digest: str
    comparison_ids: tuple[str, ...]
    observation_digests: tuple[str, ...]
    code_version: str = ""
    schema_version: str = SCHEMA_VERSION
    methodology_generation: str = "gen1"
    superseded: str = ""

    @property
    def live(self) -> bool:
        return not self.superseded

    def as_dict(self) -> dict:
        return {"id": self.id, "claim": self.claim,
                "experiment": self.experiment, "stage": self.stage,
                "contract": self.contract_digest,
                "comparisons": list(self.comparison_ids),
                "observations": list(self.observation_digests),
                "code_version": self.code_version,
                "schema_version": self.schema_version,
                "methodology_generation": self.methodology_generation,
                "superseded": self.superseded}


def finding(claim: str, comparisons, *, experiment: str, stage: str,
            code_version: str = "") -> Finding:
    """Build a finding from the comparisons that support it.

    Refuses to build one from a refused comparison: a claim whose evidence was
    inadmissible is not a weaker claim, it is not a claim.
    """
    comps = list(comparisons)
    bad = [c for c in comps if not c]
    if bad:
        raise ValueError(
            f"{len(bad)} of {len(comps)} supporting comparisons were refused; "
            f"a finding cannot rest on evidence the firewall would not admit")
    if not comps:
        raise ValueError("a finding with no supporting comparison is an opinion")
    cids = tuple(c.id for c in comps)
    obs = tuple(sorted({c.control.receipt.digest for c in comps} |
                       {c.treatment.receipt.digest for c in comps}))
    return Finding(id=f"find-{digest((claim, cids))}", claim=claim,
                   experiment=experiment, stage=stage,
                   contract_digest=comps[0].contract.digest,
                   comparison_ids=cids, observation_digests=obs,
                   code_version=code_version,
                   methodology_generation=comps[0].contract.methodology_generation)


@dataclass
class FindingLog:
    path: Path
    findings: list[Finding] = field(default_factory=list)

    def load(self) -> "FindingLog":
        if self.path.exists():
            self.findings = [
                Finding(id=d["id"], claim=d["claim"],
                        experiment=d["experiment"], stage=d["stage"],
                        contract_digest=d["contract"],
                        comparison_ids=tuple(d["comparisons"]),
                        observation_digests=tuple(d["observations"]),
                        code_version=d.get("code_version", ""),
                        schema_version=d.get("schema_version", SCHEMA_VERSION),
                        methodology_generation=d.get("methodology_generation",
                                                     "gen1"),
                        superseded=d.get("superseded", ""))
                for d in json.loads(self.path.read_text())]
        return self

    def save(self) -> None:
        self.path.write_text(json.dumps([f.as_dict() for f in self.findings],
                                        indent=2) + "\n")

    def add(self, f: Finding) -> None:
        self.findings = [x for x in self.findings if x.id != f.id] + [f]

    def dependents(self, observation_digests) -> list[Finding]:
        """Which live findings rest on any of these observations."""
        bad = set(observation_digests)
        return [f for f in self.findings
                if f.live and bad & set(f.observation_digests)]

    def supersede(self, observation_digests, reason: str) -> list[Finding]:
        hit = self.dependents(observation_digests)
        import dataclasses
        for f in hit:
            self.findings[self.findings.index(f)] = dataclasses.replace(
                f, superseded=reason)
        return hit
