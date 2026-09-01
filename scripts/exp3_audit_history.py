#!/usr/bin/env python3
"""Run the firewall retrospectively over Phase A1/A2 as it was actually recorded.

This is the integration test that matters: not a constructed scenario, but the
131 states this project already scored, replayed through the admissibility
gate. If the firewall works, it refuses the contaminated census without being
told what went wrong.

The pre-firewall rows carry no receipts, so start behaviour is RECONSTRUCTED
from the solve logs and the receipts are stamped as such. That is exactly the
dependency the firewall exists to remove -- it is acceptable for a retrospective
audit of artifacts that predate it, and for nothing else.

    python scripts/exp3_audit_history.py
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cota_opt.firewall import (EXP3_STAGE_A, EventType,  # noqa: E402
                               ExecutionEvent, ExecutionReceipt, StartPolicy,
                               StopRule, build_spec, compare, digest,
                               health_report)

OUT = ROOT / "outputs" / "exp3"
NULL_KEY = "<none>"


def fallback_states() -> set[str]:
    """Which solves rejected their incumbent, read out of the logs.

    Log parsing, declared as such. The whole point of ExecutionReceipt is that
    nothing after this script ever has to do it again.
    """
    out = set()
    for f in sorted(glob.glob(str(OUT / "stageA_*.log"))):
        buf: list[str] = []
        for line in open(f, errors="replace"):
            buf.append(line)
            if " obj=" in line and " unserved=" in line and " vh=" in line:
                if "incumbent plan is infeasible" in "".join(buf[-40:]):
                    out.add(line.split(" obj=")[0].split()[-1])
                buf = []
    return out


def rows() -> dict[str, dict]:
    out = {}
    for f in glob.glob(str(OUT / "stageA_rows*.jsonl")):
        for line in open(f):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            out[r.get("state_key", "")] = r
    return out


def reconstruct(r: dict, fell_back: bool) -> ExecutionReceipt:
    C = EXP3_STAGE_A
    spec = build_spec(C, state_digest=r.get("state_digest", ""),
                      state_key=r.get("state_key", ""),
                      cardinality=int(r.get("cardinality", 0)),
                      members=[m for m in (r.get("members") or "").split("|") if m],
                      envelope_digest=digest(round(2517.1833333333334, 6)),
                      config_digest="historical", code_version="pre-firewall",
                      seed=int(r.get("seed", 20260825)))
    events, rejected, reasons = [], (), ()
    if fell_back:
        starts = ("greedy",)
        rejected = ("incumbent",)
        reasons = ("ladder-snapped incumbent exceeds the envelope",)
        events = [ExecutionEvent(EventType.START_REJECTED, reasons[0],
                                 "frequency.optimize_frequencies"),
                  ExecutionEvent(EventType.START_FALLBACK,
                                 "greedy build substituted for the requested policy",
                                 "frequency.optimize_frequencies")]
    else:
        starts = ("incumbent",)
    return ExecutionReceipt(
        spec=spec, evaluator_used=r.get("waiting_model", "same_route"),
        objective_used=C.objective, envelope_used_vh=2517.1833333333334,
        pathset_digest=f"historical-{r.get('state_digest','')[:8]}",
        code_version="pre-firewall", schema_version="firewall/1-reconstructed",
        start_policy_requested=StartPolicy.INCUMBENT_ONLY,
        starts_attempted=starts, starts_rejected=rejected,
        rejection_reasons=reasons, winning_start=starts[-1],
        fallback_occurred=fell_back, restarts_requested=2, restarts_completed=2,
        evaluations_performed=0, termination=StopRule.NO_IMPROVING_MOVE,
        converged=True, objective=float(r["objective"]),
        metrics={k: float(v) for k, v in r.items()
                 if isinstance(v, (int, float)) and k != "objective"},
        plan_digest=f"historical-{r.get('state_digest','')[:8]}",
        feasible=True, events=tuple(events))


def kind(rec: ExecutionReceipt) -> str:
    k = rec.spec.state_key
    if k in ("", NULL_KEY) or k.startswith(NULL_KEY):
        return "control"
    if rec.spec.cardinality > 1:
        return f"k={rec.spec.cardinality}"
    return k.split("-")[0]


def main() -> int:
    fb, rs = fallback_states(), rows()

    def fell(key: str) -> bool:
        return key in fb or any(key.startswith(s[:50]) for s in fb)

    receipts = {k: reconstruct(r, fell(k)) for k, r in rs.items() if k}
    control = receipts.get(NULL_KEY) or receipts.get("")
    if control is None:
        print("no zero-edit control row found")
        return 2

    comps = [compare(control, t, EXP3_STAGE_A)
             for k, t in receipts.items() if t is not control]
    rep = health_report(list(receipts.values()), EXP3_STAGE_A, kind, comps)

    print(rep.text())
    print()
    admitted = sum(1 for c in comps if c)
    print(f"census comparisons attempted : {len(comps)}")
    print(f"                    admitted : {admitted}")
    print(f"                    refused  : {len(comps) - admitted}")
    if admitted == 0:
        print("\nEvery Phase A1/A2 effect in the recorded census is inadmissible.")
        print("The firewall reached that verdict from the receipts alone.")
    example = next((c for c in comps if not c), None)
    if example is not None:
        print("\n--- one refusal, in full ---")
        print(example)
    (OUT / "history_audit.json").write_text(json.dumps(
        {**rep.as_dict(), "comparisons_attempted": len(comps),
         "comparisons_admitted": admitted}, indent=2))
    print(f"\nwrote {OUT / 'history_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
