#!/usr/bin/env python3
"""Assemble every Experiment 2 number into one place, from the artifacts.

The write-up should not be able to drift from the runs. This reads the
committed artifacts and emits a single JSON plus a markdown block; the
conclusion cites those rather than restating figures by hand, and anything the
runs have not produced yet is reported as **missing** rather than quietly
omitted — a summary that silently drops an unfinished input is how a partial
experiment comes to look complete.

Reads, and says so when it cannot:

  outputs/exp2_candidate_classes.json  the 12 singles and the committed floor
  outputs/exp2_ladder_measured.csv     both ladder orderings
  outputs/exp2_treatments.jsonl        the representation frontier, 12 networks
  outputs/exp2_eval.jsonl              full-effort recheck cells
  outputs/exp2b_subsets.*.jsonl        the 2B subset sweep
  outputs/exp1_baseline_modelB.json    the frozen Experiment 1 baseline
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

OUT = ROOT / "outputs"
FULL_EFFORT = "400000/20/0"
RANK_EFFORT = "60000/2/32"


def _load(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _cells(pattern: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in sorted(OUT.glob(pattern)):
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            out[r["cell"]] = r
    return out


def singles() -> dict:
    d = _load(OUT / "exp2_candidate_classes.json")
    if not d:
        return {"status": "missing", "file": "exp2_candidate_classes.json"}
    return {"status": "ok",
            "noise_floor_pts": d["rule"]["noise_floor_pts"],
            "effort": d["rule"]["effort"],
            "counts": d["rule"]["counts"],
            "best": min(d["candidates"],
                        key=lambda r: r["unserved_vs_noedit_pct_lam2.0"]),
            "harmful": [r for r in d["candidates"] if r["class"] == "harmful"],
            "n_feasible_subsets": 240,
            "candidates": d["candidates"]}


def ladders() -> dict:
    p = OUT / "exp2_ladder_measured.csv"
    if not p.exists():
        return {"status": "missing", "file": p.name}
    d = pd.read_csv(p)
    return {"status": "ok",
            "rows": d[["order", "n_edits", "unserved_vs_0edit_pct",
                       "gc_vs_0edit_pct"]].round(4).to_dict("records")}


def recheck(floor: float) -> dict:
    """D19's falsification test: the two harmful candidates at full effort.

    A verdict needs the zero-edit replicates from the SAME run, because the
    floor at 60,000 iterations is not the floor at 400,000 and carrying the
    cheap one over would be the effort-mismatch confound this project has
    already been burned by.
    """
    c = _cells("exp2_eval.jsonl")
    want = {k: v for k, v in c.items() if FULL_EFFORT in k}
    base = [v for k, v in want.items() if "|0 edits|" in k]
    cands = {k: v for k, v in want.items() if "single:" in k}
    reps = [v for k, v in want.items() if "0 edits seed" in k]
    if not base or len(reps) < 2:
        return {"status": "running",
                "have_baseline": bool(base), "n_replicates": len(reps),
                "n_candidates": len(cands),
                "note": "needs the zero-edit baseline plus at least two "
                        "replicates at this effort before a verdict is "
                        "possible; the cheap floor may not be carried over"}
    b = base[0]["unserved_lam2.0"]
    vals = [b] + [r["unserved_lam2.0"] for r in reps]
    sd = float(np.std(vals, ddof=1)) / b * 100
    full_floor = 3.0 * sd
    out = []
    for k, v in sorted(cands.items()):
        eff = (v["unserved_lam2.0"] / b - 1) * 100
        out.append({
            "candidate": k.split("single:")[1].split("|60")[0].rstrip("|"),
            "unserved_vs_noedit_pct": round(eff, 4),
            "clears_full_effort_floor": bool(abs(eff) >= full_floor),
            "still_harmful": bool(eff >= full_floor)})
    return {"status": "ok", "effort": FULL_EFFORT,
            "n_replicates": len(vals),
            "full_effort_floor_pts": round(full_floor, 4),
            "rank_effort_floor_pts": floor,
            "candidates": out,
            "verdict": ("D19 stands: both remain harmful at full effort"
                        if all(r["still_harmful"] for r in out) else
                        "D19 is qualified: at least one does not remain "
                        "harmful at full effort")}


def frontier() -> dict:
    c = _cells("exp2_treatments.jsonl")
    if not c:
        return {"status": "missing", "file": "exp2_treatments.jsonl"}
    d = pd.DataFrame([{k: v for k, v in r.items() if k != "plan"}
                      for r in c.values()])
    nets = sorted(d["network"].unique())
    done = [n for n in nets
            if len(d[(d["network"] == n)]) >= 6]
    at2 = d[d["lambda"] == 2.0]
    spread = {}
    for t in ("route_level", "path_level"):
        s = at2[at2["treatment"] == t]["unserved_vs_base_pct"]
        if len(s):
            spread[t] = {"min": round(float(s.min()), 4),
                         "max": round(float(s.max()), 4),
                         "range_pts": round(float(s.max() - s.min()), 4),
                         "n_networks": int(len(s))}
    piv = at2.pivot_table(index="network", columns="treatment",
                          values=["unserved_vs_base_pct", "gc_vs_base_pct",
                                  "gc_per_trip_vs_base_pct",
                                  "claim_gap_unserved_pct"])
    return {"status": "ok" if len(done) >= 13 else "running",
            "n_networks_complete": len(done), "n_networks_expected": 13,
            "spread_at_lambda2": spread,
            "table": json.loads(piv.round(4).to_json(orient="index"))}


def subsets() -> dict:
    c = _cells("exp2b_subsets*.jsonl")
    want = {k: v for k, v in c.items() if RANK_EFFORT in k}
    if not want:
        return {"status": "not started", "file": "exp2b_subsets*.jsonl"}
    d = pd.DataFrame([{k: v for k, v in r.items() if k != "plan"}
                      for r in want.values()])
    n = int(d["set_key"].nunique())
    return {"status": "ok" if n >= 240 else "running",
            "n_subsets_solved": n, "n_subsets_expected": 240}


def main() -> int:
    s = singles()
    floor = s.get("noise_floor_pts", 0.288)
    out = {"experiment": "Experiment 2 — route geometry, and Experiment 2B",
           "evaluator": "frozen Model B (same_route common lines)",
           "envelope_veh_hours": 2517.2,
           "singles": s,
           "ladders": ladders(),
           "recheck_D19": recheck(floor),
           "representation_frontier": frontier(),
           "subset_search_2B": subsets()}
    missing = [k for k, v in out.items()
               if isinstance(v, dict) and v.get("status") not in (None, "ok")]
    out["incomplete"] = missing
    (OUT / "exp2_summary.json").write_text(json.dumps(out, indent=2))

    print("=" * 88)
    print("EXPERIMENT 2 — assembled from the artifacts")
    print("=" * 88)
    for k, v in out.items():
        if isinstance(v, dict) and "status" in v:
            extra = ""
            if k == "representation_frontier" and v.get("n_networks_complete"):
                extra = (f"  ({v['n_networks_complete']}/"
                         f"{v['n_networks_expected']} networks)")
            if k == "subset_search_2B" and v.get("n_subsets_solved"):
                extra = (f"  ({v['n_subsets_solved']}/"
                         f"{v['n_subsets_expected']} subsets)")
            print(f"  {k:28s} {v['status']}{extra}")
    if missing:
        print(f"\n  NOT YET COMPLETE: {', '.join(missing)}")
        print("  The conclusion may not be written until these are 'ok', and "
              "a partial run is reported as partial.")
    else:
        print("\n  every input complete — the conclusion may be written")
    f = out["representation_frontier"]
    if f.get("spread_at_lambda2"):
        print("\n  spread of measured unserved demand across networks, λ=2:")
        for t, v in f["spread_at_lambda2"].items():
            print(f"    {t:12s} {v['min']:+7.3f}% .. {v['max']:+7.3f}%  "
                  f"range {v['range_pts']:.3f} pts over {v['n_networks']} rows")
    r = out["recheck_D19"]
    if r.get("status") == "ok":
        print(f"\n  D19 recheck at {r['effort']}, floor "
              f"{r['full_effort_floor_pts']:.3f} pts "
              f"(against {r['rank_effort_floor_pts']:.3f} at ranking effort):")
        for c in r["candidates"]:
            print(f"    {c['candidate']:24s} {c['unserved_vs_noedit_pct']:+7.3f}%  "
                  f"{'still harmful' if c['still_harmful'] else 'NOT harmful'}")
        print(f"    -> {r['verdict']}")
    print(f"\nartifacts: {OUT / 'exp2_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
