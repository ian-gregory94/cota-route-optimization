"""Execution-path balance audit and the per-stage health report.

Section 14 of the corrective plan, and the thing whose absence let D27 run for
four experiments: nobody was asking whether execution behaviour was ASSOCIATED
with treatment identity. One receipt looked fine. All of them together did not.

Nothing here is specialised to start fallbacks. It sweeps every event type and
every opportunity field in the receipt, so a failure mode invented next year is
audited the day its field exists.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .contract import ExperimentContract
from .core import Sem, fields_by_sem
from .events import ExecutionEvent
from .receipt import ExecutionReceipt


@dataclass(frozen=True)
class Imbalance:
    dimension: str
    kind: str                      # "event" | "opportunity"
    by_class: dict[str, object]
    spread: float

    def __str__(self) -> str:
        cells = "  ".join(f"{k}={v}" for k, v in sorted(self.by_class.items()))
        return f"{self.dimension} ({self.kind}): {cells}"


def balance_audit(receipts, classify, *, threshold: float = 0.10
                  ) -> list[Imbalance]:
    """Find execution dimensions associated with the experimental class.

    ``classify(receipt) -> str``. ``threshold`` is the share-point spread above
    which a categorical dimension counts as treatment-correlated (0.10 = ten
    percentage points).

    A dimension that is constant across classes is not reported, however
    unusual its value: the question is association with treatment, not
    rarity.
    """
    groups: dict[str, list[ExecutionReceipt]] = defaultdict(list)
    for r in receipts:
        groups[classify(r)].append(r)
    if len(groups) < 2:
        return []
    out: list[Imbalance] = []

    types = {e.type.value for r in receipts for e in r.events}
    for t in sorted(types):
        share = {g: sum(1 for r in rs if any(e.type.value == t for e in r.events)) / len(rs)
                 for g, rs in groups.items()}
        spread = max(share.values()) - min(share.values())
        if spread > threshold:
            out.append(Imbalance(t, "event",
                                 {g: f"{100*v:.0f}%" for g, v in sorted(share.items())},
                                 spread))

    names = sorted({k for r in receipts
                    for k in fields_by_sem(r, Sem.OPPORTUNITY)})
    for name in names:
        vals = {g: [fields_by_sem(r, Sem.OPPORTUNITY).get(name) for r in rs]
                for g, rs in groups.items()}
        flat = [v for vs in vals.values() for v in vs]
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in flat):
            means = {g: sum(vs) / len(vs) for g, vs in vals.items()}
            lo, hi = min(means.values()), max(means.values())
            scale = max(abs(lo), abs(hi), 1.0)
            spread = (hi - lo) / scale
            if spread > threshold:
                out.append(Imbalance(name, "opportunity",
                                     {g: round(m, 3) for g, m in sorted(means.items())},
                                     spread))
        else:
            share = {g: Counter(str(v) for v in vs).most_common(1)[0][0]
                     for g, vs in vals.items()}
            if len(set(share.values())) > 1:
                out.append(Imbalance(name, "opportunity", dict(sorted(share.items())), 1.0))
    return sorted(out, key=lambda i: -i.spread)


@dataclass
class HealthReport:
    stage: str
    contract_digest: str
    raw: int = 0
    admissible: int = 0
    inadmissible: int = 0
    inadmissible_reasons: Counter = field(default_factory=Counter)
    comparisons: int = 0
    refused: int = 0
    refusal_dimensions: Counter = field(default_factory=Counter)
    events: Counter = field(default_factory=Counter)
    event_rates: dict = field(default_factory=dict)
    imbalances: list = field(default_factory=list)
    cache_hits: int = 0
    resumed: int = 0
    converged: int = 0
    seeds: Counter = field(default_factory=Counter)
    schema_versions: Counter = field(default_factory=Counter)

    def as_dict(self) -> dict:
        return {"stage": self.stage, "contract": self.contract_digest,
                "raw": self.raw, "admissible": self.admissible,
                "inadmissible": self.inadmissible,
                "inadmissible_reasons": dict(self.inadmissible_reasons),
                "comparisons": self.comparisons, "refused": self.refused,
                "refusal_dimensions": dict(self.refusal_dimensions),
                "events": dict(self.events), "event_rates": self.event_rates,
                "imbalances": [{"dimension": i.dimension, "kind": i.kind,
                                "by_class": i.by_class, "spread": round(i.spread, 3)}
                               for i in self.imbalances],
                "cache_hits": self.cache_hits, "resumed": self.resumed,
                "converged": self.converged, "seeds": dict(self.seeds),
                "schema_versions": dict(self.schema_versions)}

    def text(self) -> str:
        L = [f"EXPERIMENT HEALTH — {self.stage} (contract {self.contract_digest})",
             f"  evaluations   {self.raw} raw, {self.admissible} admissible, "
             f"{self.inadmissible} inadmissible",
             f"  comparisons   {self.comparisons} admitted, {self.refused} refused",
             f"  execution     {self.cache_hits} cache hits, {self.resumed} resumed, "
             f"{self.converged} converged"]
        if self.inadmissible_reasons:
            L.append("  why inadmissible:")
            L += [f"      {n:4d}  {r}" for r, n in self.inadmissible_reasons.most_common()]
        if self.refusal_dimensions:
            L.append("  refused on:")
            L += [f"      {n:4d}  {d}" for d, n in self.refusal_dimensions.most_common()]
        if self.event_rates:
            L.append("  event rates by class:")
            for t, by in sorted(self.event_rates.items()):
                L.append(f"      {t:22s} " +
                         "  ".join(f"{g}={v}%" for g, v in sorted(by.items())))
        if self.imbalances:
            L.append("  TREATMENT-CORRELATED EXECUTION (fail closed):")
            L += [f"      {i}" for i in self.imbalances]
        else:
            L.append("  no treatment-correlated execution differences found")
        return "\n".join(L)

    @property
    def healthy(self) -> bool:
        return not self.imbalances and self.inadmissible == 0 and self.refused == 0


def health_report(receipts, contract: ExperimentContract, classify,
                  comparisons=(), *, threshold: float = 0.10) -> HealthReport:
    from .observation import Inadmissible, admit
    rep = HealthReport(stage=contract.stage, contract_digest=contract.digest)
    for r in receipts:
        rep.raw += 1
        rep.cache_hits += int(r.cache_hit)
        rep.resumed += int(r.resumed)
        rep.converged += int(r.converged)
        rep.seeds[str(r.spec.seed)] += 1
        rep.schema_versions[r.schema_version] += 1
        for e in r.events:
            rep.events[e.type.value] += 1
        a = admit(r, contract)
        if isinstance(a, Inadmissible):
            rep.inadmissible += 1
            for why in a.reasons:
                rep.inadmissible_reasons[why.split(";")[0][:80]] += 1
        else:
            rep.admissible += 1
    from .events import event_rates
    rep.event_rates = event_rates(list(receipts), classify) if receipts else {}
    rep.imbalances = balance_audit(list(receipts), classify, threshold=threshold)
    for c in comparisons:
        if c:
            rep.comparisons += 1
        else:
            rep.refused += 1
            for d in getattr(c, "undeclared", ()):
                rep.refusal_dimensions[d.dimension] += 1
    return rep
