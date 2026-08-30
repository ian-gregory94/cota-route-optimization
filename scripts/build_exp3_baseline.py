#!/usr/bin/env python3
"""Build `pre_exp3_baseline_v1` — the object Experiment 3 must beat.

Experiment 3 changes route structure. Every number it produces has to be
reported against one immutable comparison object, chosen and hashed before the
first mutation exists, or the baseline quietly becomes "whatever the repository
happened to contain when the run started" and no one can tell later whether a
gain was real or was measured against a moving reference.

The package carries two reference points, and Experiment 3's margin is over the
second:

* the **raw baseline** — COTA's published network and schedule;
* the **conservative incumbent** — that network with Experiment 1's certified
  frequency redistribution and Experiment 2/2B's promoted geometry, with
  frequencies re-optimized on the edited network.

Beating the raw baseline is not a result: Experiments 1 and 2 already do that.

This refuses to write a v1 while any input is unsettled. A baseline assembled
from a running experiment would be a baseline that changes, which is the one
thing it must not be.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "outputs"
CANON = OUT / "canonical"
BASELINE_ID = "pre_exp3_baseline_v1"


def sha(p: Path) -> str | None:
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


#: Paths this script itself rewrites. A freeze record that calls the tree dirty
#: because it is in the middle of writing itself is reporting on its own
#: execution, not on the state of the repository, and it can never be made to
#: say anything else -- committing the file changes it again on the next run.
SELF_OUTPUTS = ("outputs/canonical/pre_exp3_baseline_v1.json",)


def commit() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                           capture_output=True, text=True, timeout=30)
        d = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                           capture_output=True, text=True, timeout=60)
        other = [ln for ln in d.stdout.splitlines()
                 if ln.strip() and not any(ln.endswith(s) for s in SELF_OUTPUTS)]
        return r.stdout.strip() + ("-dirty" if other else "")
    except Exception:
        return "UNKNOWN"


def hashed(rel: str) -> dict:
    p = ROOT / rel
    return {"path": rel, "sha256": sha(p), "present": p.exists(),
            "bytes": p.stat().st_size if p.exists() else None}


def load(rel: str):
    try:
        return json.loads((ROOT / rel).read_text())
    except Exception:
        return None


def blockers() -> list[str]:
    """Everything that must be settled before a v1 can honestly be written."""
    out = []
    s = load("outputs/exp2_summary.json") or {}
    if s.get("subset_search_2B", {}).get("status") != "ok":
        n = s.get("subset_search_2B", {}).get("n_subsets_solved", 0)
        out.append(f"Experiment 2B stage A is not complete ({n}/240 subsets) — "
                   f"the geometry incumbent is not decided")
    g = s.get("gate_2B8_cross_check", {})
    if g.get("status") != "ok":
        out.append("gate 2B-8 has not fully passed — the subset sweep has not "
                   "yet reproduced all three ladder rungs it replaces")
    p = load("outputs/exp2_promotion.json")
    if p is None:
        out.append("the promotion decision between splice|011|034|WESHIGW and "
                   "splice|033|034|WESHIGW is not recorded — run the "
                   "full-effort confirmation and gate 9, and write the verdict")
    if not (CANON / "exp1_final.json").exists():
        out.append("Experiment 1 is not frozen")
    if not (ROOT / "outputs" / "exp2b_certification.json").exists():
        out.append("Experiment 2B stage C has not certified or nulled a "
                   "subset — the geometry component of the incumbent is not "
                   "settled")
    return out


def main() -> int:
    stop = blockers()
    CANON.mkdir(parents=True, exist_ok=True)

    pkg = {
        "id": BASELINE_ID,
        "status": "DRAFT — not yet valid" if stop else "FROZEN",
        "commit": commit(),
        "what_this_is":
            "The immutable object Experiment 3 reports against. Experiment 3's "
            "margin is over the conservative incumbent, not over the raw "
            "baseline: Experiments 1 and 2 already beat the raw baseline, and "
            "re-reporting that as an Experiment 3 result would be counting the "
            "same gain twice.",
        "blockers": stop,
        "evaluator": {
            "waiting_model": "same_route (Model B)",
            "asserted_by": "Experiment.declare_evaluator, which reads the "
                           "value out of the setup that scored the plans and "
                           "raises if it disagrees with what the run asked for",
            "cache_separation": "the path-set cache key includes common_lines, "
                                "so a Model A enumeration cannot be served to "
                                "a Model B request (scripts/repro_check.py)",
        },
        "reference_points": {
            "raw_baseline": {
                "what": "COTA's published network and schedule",
                "weekday_revenue_veh_hours": 2517.2,
                "peak_vehicles": 197.0,
                "artifact": hashed("outputs/exp1_baseline_modelB.json"),
            },
            "exp1_certified": {
                "what": "frequency redistribution, geometry unchanged, "
                        "certified λ≥2",
                "unserved_change_pct": -6.652,
                "served_change_pct": 3.299,
                "gc_change_pct": 0.878,
                "gc_per_trip_change_pct": -2.344,
                "weekday_revenue_veh_hours": 2516.5,
                "peak_vehicles": 197.0,
                "artifact": hashed("outputs/canonical/exp1_final.json"),
            },
            "conservative_incumbent": {
                "what": "the best defensible performance available WITHOUT "
                        "materially changing route structure — the number "
                        "Experiment 3 must beat",
                "geometry": "UNCHANGED. Experiment 2 promoted nothing: at the "
                            "effort Experiment 1 is certified at, no candidate "
                            "produces a measurable improvement and six produce "
                            "measurable harm (D24, outputs/exp2_promotion.json). "
                            "Experiment 2B may still find a subset that clears "
                            "the floor where no single does — that would be a "
                            "real interaction — and until stage C says so the "
                            "incumbent geometry is COTA's own.",
                "equals": "exp1_certified, on the published geometry",
                "artifacts": [hashed("outputs/exp2_promotion.json"),
                              hashed("outputs/exp2b_certification.json")],
            },
        },
        "inputs": {k: hashed(v) for k, v in {
            "assumptions": "config/assumptions.yaml",
            "cost_weights": "config/cost_weights.yaml",
            "constraints": "config/constraints.yaml",
            "sources": "config/sources.yaml",
            "exp2_include": "config/exp2_include.txt",
            "exp2_promote": "config/exp2_promote.txt",
            "exp2_recheck": "config/exp2_recheck.txt",
            "exp3_contract": "EXPERIMENT3_CONTRACT.md",
            "gates": "ACCEPTANCE.md",
            "exp1_frozen": "outputs/canonical/exp1_final.json",
            "exp2_classes": "outputs/exp2_candidate_classes.json",
            "exp2_ladders": "outputs/exp2_ladder_measured.csv",
            "exp2_treatments": "outputs/exp2_treatments.jsonl",
            "exp2b_stageA": "outputs/exp2b_stageA.csv",
            "stop_price_diagnosis": "outputs/exp3_stopprice_diagnosis.json",
            "runtime_validation": "outputs/runtime_validation.json",
            "manifest": "outputs/CANONICAL_RESULTS.json",
        }.items()},
        "generation_parameters": {
            "note": "the enumeration and search settings any Experiment 3 "
                    "comparison must match; taken from the frozen Experiment 1 "
                    "record rather than restated",
            "from": "outputs/canonical/exp1_final.json -> search",
        },
        "rules_that_travel_with_it": {
            "quoting": "the certified frontier begins at λ=2; the "
                       "cost-favouring λ≤1 corner is uncertified on both models",
            "identification": "the claim is the aggregate effect, never an "
                              "individual route headway — independent seeds "
                              "disagree on 19% of route-periods while scoring "
                              "within 0.064 points",
            "stop_penalty": "no runtime saving may be credited for serving "
                            "fewer stops on the same alignment; this feed "
                            "cannot price a stop",
            "contract": "EXPERIMENT3_CONTRACT.md",
        },
    }

    e1 = load("outputs/canonical/exp1_final.json")
    if e1:
        pkg["generation_parameters"].update(e1.get("search", {}))

    path = CANON / f"{BASELINE_ID}.json"
    path.write_text(json.dumps(pkg, indent=2))

    print("=" * 84)
    print(f"{BASELINE_ID}: {pkg['status']}")
    print("=" * 84)
    missing = [k for k, v in pkg["inputs"].items() if not v["present"]]
    print(f"  {len(pkg['inputs'])} inputs hashed, {len(missing)} missing"
          + (f": {', '.join(missing)}" if missing else ""))
    if stop:
        print("\n  BLOCKERS — this is a draft and may not be tagged:")
        for b in stop:
            print(f"    - {b}")
    else:
        print("\n  no blockers; the baseline is frozen and Experiment 3 may "
              "report against it")
    print(f"\nartifacts: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
