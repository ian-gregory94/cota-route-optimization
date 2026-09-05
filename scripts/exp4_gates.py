#!/usr/bin/env python3
"""C15 — the 15 Experiment 4 acceptance gates, as executable checks.

`ACCEPTANCE.md` writes the gates down. Written is not implemented, and this
project's own rule is that a mechanism which looks like it is working is not
evidence that it ran (OPERATIONS 24/26/27). So each gate gets a state:

  MET    satisfied now, by an artifact or by code, and re-checked on every run.
  ARMED  the gate is written AND the machinery that will fire it exists, but it
         applies to a PROMOTED NETWORK and so cannot be satisfied before the
         search. Recorded as armed, never as met.
  OPEN   neither satisfied nor armed. Work remains.

ARMED is the honest state for eight of the fifteen. A gate that says "every
promoted network reruns the diagnostic" has nothing to check until a network is
promoted, and marking it MET now would be a lie that survives until it matters.

    python scripts/exp4_gates.py
    python scripts/exp4_gates.py --json outputs/exp4/gates.json
"""
from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "outputs" / "exp4"

MET, ARMED, OPEN = "MET", "ARMED", "OPEN"


def _j(name: str):
    p = OUT / name
    return json.loads(p.read_text()) if p.exists() else None


def _src(rel: str) -> str:
    p = ROOT / rel
    return p.read_text() if p.exists() else ""


def gates() -> list[dict]:
    pool = _j("route_pool.json") or {}
    tr = _j("transition_audit.json") or {}
    lg = _j("linkgraph_audit.json") or {}
    rec = _j("reconstruction.json") or {}
    acc = _src("ACCEPTANCE.md")
    # normalised: the gate text wraps across lines, so a raw substring search
    # fails on phrases that happen to straddle a newline.
    acc_flat = " ".join(acc.split())
    out: list[dict] = []

    def g(gid, title, state, detail):
        out.append({"gate": gid, "title": title, "state": state,
                    "detail": detail})

    # --- 4-1 evidence class -------------------------------------------------
    classes = tr.get("classes", {})
    every_classified = tr.get("n_lines") == pool.get("accepted")
    g("4-1", "Primary evidence class is the observed-link graph",
      MET if every_classified and classes else OPEN,
      f"all {tr.get('n_lines')} pool lines carry an evidence class "
      f"{classes}; no line uses an unobserved link (class 3 count "
      f"{classes.get('modelled_geometry', 0)}). The headline restriction to "
      f"observed-link networks binds on a RESULT and is enforced by gate 4-15")

    # --- 4-2 peak express frozen -------------------------------------------
    has_class = "peak_express" in _src("src/cota_opt/routeclass.py")
    locked = "peak_express" in _src("src/cota_opt/exp3_score.py")
    g("4-2", "Peak-express layer frozen and excluded from the graph",
      MET if has_class and locked else OPEN,
      "routeclass.py defines the peak_express class; exp3_score locks it via "
      "lock_classes. Exclusion of express links from the observed-link graph "
      "is asserted by the pool build, not re-derived here")

    # --- 4-3 stop universe fixed -------------------------------------------
    covered = rec.get("stops_covered")
    g("4-3", "Stop universe is fixed; no stop created or moved",
      MET if covered and covered == lg.get("n_stops") else OPEN,
      f"reconstruction covers {covered} stops against the link graph's "
      f"{lg.get('n_stops')}; stops_missed={rec.get('stops_missed')}")

    # --- 4-4 pool contains the current network ------------------------------
    g("4-4", "Frozen pool contains the current network",
      MET if pool.get("legacy_in_pool") == pool.get("legacy_lines")
      and pool.get("legacy_lines") else OPEN,
      f"{pool.get('legacy_in_pool')}/{pool.get('legacy_lines')} legacy lines in "
      f"the pool; {rec.get('reconstructed')} reconstructed, "
      f"{rec.get('failed')} failed, stop coverage complete="
      f"{rec.get('stop_coverage_complete')}")

    # --- 4-5 service activation is a real decision --------------------------
    try:
        from cota_opt.frequency import OFF, build_ladders, is_off
        off_ok = is_off(OFF) and (
            inspect.signature(build_ladders).parameters["allow_off"].default
            is False)
    except Exception:
        off_ok = False
    g("4-5", "Service activation is a real decision (OFF is representable)",
      MET if off_ok else OPEN,
      "frequency.OFF is an infinite headway: zero trips, zero vehicle-hours, "
      "zero peak vehicles, unboardable by the path model. build_ladders("
      "allow_off=) is opt-in so Gen1 cannot represent it. The second half -- no "
      "synthetic route may be given a copied baseline headway -- binds when the "
      "Exp 4 FrequencyModel is built and is armed by gate 4-15's review"
      if off_ok else "no OFF representation")

    # --- 4-6 search bounds proved inactive ----------------------------------
    om = pool.get("oneway_minutes") or {}
    rm = rec.get("oneway_minutes") or {}
    inside = (rm.get("min", 0) >= 10 and rm.get("max", 999) <= 120
              and not rec.get("outside_search_bounds"))
    g("4-6", "Search bounds proved inactive on the incumbent",
      MET if inside else OPEN,
      f"today's local routes run {rm.get('min')}-{rm.get('max')} min one way, "
      f"inside the 10-120 bound, and outside_search_bounds is empty. "
      f"NOTE: {pool.get('on_length_bound')} POOL line sits on the bound "
      f"(pool range {om.get('min')}-{om.get('max')}), so if that line wins, "
      f"gate 4-6 censors the result")

    # --- 4-7 discovery approximation benchmarked ----------------------------
    g("4-7", "Discovery approximation benchmarked, buys no conclusions",
      MET if (OUT / "pathreuse_benchmark.json").exists() else OPEN,
      "needs outputs/exp4/pathreuse_benchmark.json with objective gap, "
      "unserved gap, ranking stability, omitted and improvable flow, and "
      "whether the promoted set changes")

    # --- 4-8 what the optimizer abandons is reported ------------------------
    g("4-8", "What the optimizer abandons is reported", ARMED,
      "applies to a promoted network: stops losing service, demand losing "
      "access, one-seat rides lost, transfer burden created. Nothing to "
      "compute before a network is promoted")

    # --- 4-9 path-model adequacy re-established -----------------------------
    has_adequacy = "def adequacy" in _src("src/cota_opt/adequacy.py")
    g("4-9", "Path-model adequacy re-established, not inherited",
      ARMED if has_adequacy else OPEN,
      "adequacy() exists and measures cached-set cost against fresh RAPTOR. "
      "The gate requires it rerun on PROMOTED networks with a deeper "
      "max_rounds, the 4->6 paths-per-OD sensitivity redone, and certification "
      "on a wider OD set than the top 20,000")

    # --- 4-10 common-lines exposure re-measured -----------------------------
    has_cl = "common_lines" in _src("src/cota_opt/exp2.py")
    g("4-10", "Common-lines exposure re-measured on promoted networks",
      ARMED if has_cl else OPEN,
      "the diagnostic exists and reported 0.516% cross-route today; the gate "
      "reruns it per promoted network and classifies the result "
      "model-dependent if exposure balloons")

    # --- 4-11 crowding re-checked -------------------------------------------
    has_crowd = (ROOT / "src" / "cota_opt" / "crowding.py").exists()
    g("4-11", "Crowding re-checked on promoted networks",
      ARMED if has_crowd else OPEN,
      "crowding.py exists; it did not bind on the existing network and a "
      "greenfield optimizer may concentrate load onto few trunks")

    # --- 4-12 demand robustness preregistered -------------------------------
    claims = ROOT / "EXPERIMENT4_DEMAND_ROBUSTNESS.md"
    g("4-12", "Demand robustness preregistered before the winner is known",
      MET if claims.exists() else OPEN,
      "EXPERIMENT4_DEMAND_ROBUSTNESS.md must exist BEFORE any Exp 4 result. "
      "Cheap now, impossible later")

    # --- 4-13 structural identity uses geometry -----------------------------
    ed = "network_edit_distance_pct" in _src("src/cota_opt/contract.py")
    g("4-13", "Structural identity uses geometry, not route ids",
      MET if ed else OPEN,
      "contract.py computes network_edit_distance_pct with a committed cap; "
      "Exp 4 route ids are synthetic so id disagreement is meaningless")

    # --- 4-14 search benchmarked on a space that can defeat it --------------
    g("4-14", "Search benchmarked on a space that can defeat it",
      MET if (OUT / "known_optimum_recovery.json").exists() else OPEN,
      "needs an enumerated envelope and recovery of the true optimum from "
      "incumbent, random and deceptive starts, including a drop-a-good-route "
      "case, a non-nested optimum, a required swap, and an optimal incumbent. "
      "Passing the 2B benchmark is explicitly insufficient")

    # --- 4-15 what Experiment 4 may conclude --------------------------------
    g("4-15", "Conclusion language is bounded and the null is precommitted",
      MET if "Gate 4-15" in acc_flat
      and "null is precommitted as a fine result" in acc_flat else OPEN,
      "ACCEPTANCE.md bounds the admissible claim and precommits the null as a "
      "fine result. Binds on the write-up, enforced by review")

    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    rows = gates()
    w = max(len(r["title"]) for r in rows)
    print("EXPERIMENT 4 — ACCEPTANCE GATES\n")
    for r in rows:
        print(f"  {r['gate']:<5} {r['title']:<{w}}  {r['state']}")
        print(f"        {'':<{w}}  {r['detail']}")
    met = sum(1 for r in rows if r["state"] == MET)
    armed = sum(1 for r in rows if r["state"] == ARMED)
    opn = sum(1 for r in rows if r["state"] == OPEN)
    print(f"\n  {met} met | {armed} armed (fire on a promoted network) | "
          f"{opn} open | {len(rows)} total")
    print("\nARMED is not MET. A gate that applies to a promoted network cannot "
          "be satisfied\nbefore the search, and marking it met now would be a "
          "lie that survives until it matters.")
    if a.json:
        Path(a.json).write_text(json.dumps(
            {"gates": rows, "met": met, "armed": armed, "open": opn,
             "total": len(rows),
             "all_pre_search_gates_met": opn == 0}, indent=2))
        print(f"\nwrote {a.json}")
    return 1 if opn else 0


if __name__ == "__main__":
    raise SystemExit(main())
