#!/usr/bin/env python3
"""Experiment 4 OUT-OF-BAND CERTIFICATION AUDIT.

Certifies the 200 proposals frozen in `outputs/exp4_audit/audit_sample.json`
-- a stratified random sample of discovery ranks 201-2000, none of which was
promoted or certified by Experiment 4.

THE PIPELINE IS NOT MODIFIED. This script reproduces the certify loop of
`scripts/exp4_launch.py` verbatim. It differs in exactly two places:

  1. the candidate list comes from the frozen audit sample instead of from
     `promote()`;
  2. results are written to `outputs/exp4_audit/certified/` instead of
     `outputs/exp4/run/certified/`.

Everything that could change a number is shared with the production launcher:
LAM, SEED, POOL_VERSION, the canonical envelope, ContractLimits, the same
`assemble(...)`, the same `certify(...)` under CERTIFICATION_DIGEST, the same
per-candidate error handling, the same write-the-instant-it-exists, the same
resume-by-file-existence, and the same shard bound checked at the TOP of each
candidate. `src/cota_opt` is untouched.

DOES NOT alter the Exp 4 incumbent, and does not read or write anything under
`outputs/exp4/run/` except `proposals.json`, read-only, for provenance.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

RUN = ROOT / "outputs" / "exp4" / "run"          # read-only here
OUT = ROOT / "outputs" / "exp4_audit"
SAMPLE = OUT / "audit_sample.json"

CANONICAL_ENVELOPE = ROOT / "outputs" / "CANONICAL_ENVELOPE.json"

# Identical to scripts/exp4_launch.py. Not re-derived, not re-tuned.
LAM = 2.0
SEED = 20260825

INCUMBENT_KEY = "exp4|exp4-pool-v1|65lines#ecb2ffc4bcce"
INCUMBENT_OBJ = 3511184.5657525407


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-hours", type=float, default=6.0)
    a = ap.parse_args()

    from cota_opt.configs import load_constraints
    from cota_opt.contract import ContractLimits
    from cota_opt.exp4_assemble import assemble
    from cota_opt.exp4_certify import CERTIFICATION_DIGEST, certify
    from cota_opt.exp4_network import Exp4Selection
    from cota_opt.firewall.core import digest
    from exp4_c10_fixtures import (POOL_VERSION, _BY_RID, _boot,
                                   _first_dep_by_period)

    if not SAMPLE.exists():
        print(f"FATAL: {SAMPLE} is missing. The sample is frozen before "
              f"execution and this script does not generate one.")
        return 2
    spec = json.loads(SAMPLE.read_text())
    selected = spec["selected"]
    if len(selected) != 200:
        print(f"FATAL: sample has {len(selected)} entries, expected 200.")
        return 2
    if spec["incumbent"]["state_key"] != INCUMBENT_KEY:
        print("FATAL: sample names a different incumbent.")
        return 2

    # lines come from the proposal record, read-only, so the audit assembles
    # exactly what discovery proposed.
    prop = json.loads((RUN / "proposals.json").read_text())["proposals"]
    lines_of = {p["state_key"]: p["lines"] for p in prop}
    missing = [s["state_key"] for s in selected if s["state_key"] not in lines_of]
    if missing:
        print(f"FATAL: {len(missing)} sampled keys absent from proposals.json")
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    cert_dir = OUT / "certified"
    cert_dir.mkdir(exist_ok=True)

    t_start = time.time()
    deadline = t_start + a.max_hours * 3600

    st = _boot()
    H, sg, graph = st["H"], st["sg"], st["graph"]
    first_dep = _first_dep_by_period()

    if not CANONICAL_ENVELOPE.exists():
        print("FATAL: outputs/CANONICAL_ENVELOPE.json is missing.")
        return 2
    env = json.loads(CANONICAL_ENVELOPE.read_text())
    VEH_HOURS = float(env["weekday_revenue_vehicle_hours"])
    ENVELOPE_DIGEST = str(env["envelope_digest"])

    _c = load_constraints()
    cons = {**_c, "resource": {**_c["resource"],
                               "weekday_revenue_vehicle_hours": VEH_HOURS}}
    assert cons["resource"]["peak_fleet_by_period"] == "baseline"

    # Constructed for parity with the production launcher. Certification does
    # not read it, but building it here means a future divergence in
    # ContractLimits shows up in this script too rather than silently not.
    _limits = ContractLimits(veh_hour_budget=VEH_HOURS,
                             peak_vehicle_budget=None,
                             required_waiting_model="same_route")

    todo = [s for s in selected
            if not (cert_dir / f"{digest(s['state_key'])}.json").exists()]
    print(f"AUDIT exp4-audit-v1  seed {spec['sample_seed']}  "
          f"envelope {ENVELOPE_DIGEST}  lam {LAM}  seed(cert) {SEED}")
    print(f"incumbent to beat: {INCUMBENT_OBJ:,.4f}  ({INCUMBENT_KEY[-12:]})")
    print(f"certification: {len(selected) - len(todo)} done, "
          f"{len(todo)} remaining of {len(selected)}")

    for i, s in enumerate(todo, 1):
        if time.time() > deadline:
            print(f"  shard bound reached ({a.max_hours}h); "
                  f"{len(todo) - i + 1} candidates remain. Re-run to resume.")
            break
        k = s["state_key"]
        sel = Exp4Selection(POOL_VERSION, frozenset(lines_of[k]), frozenset())
        built = assemble(sel, _BY_RID, graph, H.baseline.network.stops,
                         pool_version=POOL_VERSION,
                         first_dep_sec_by_period=first_dep)
        t0 = time.time()
        try:
            cr = certify(built.network, built.tstats, state_key=k,
                         state_digest=sel.state_digest, harness=H,
                         stops_gdf=sg, lam=LAM, seed=SEED,
                         constraints=cons, contract_digest=CERTIFICATION_DIGEST)
        except Exception as e:
            (cert_dir / f"{digest(k)}.json").write_text(json.dumps(
                {"state_key": k, "error": f"{type(e).__name__}: {e}"[:200],
                 "discovery_rank": s["discovery_rank"],
                 "stratum": s["stratum"]}, indent=1))
            print(f"  [{i}/{len(todo)}] {k} FAILED {type(e).__name__}")
            continue
        # written the instant it exists -- OPERATIONS 31
        (cert_dir / f"{digest(k)}.json").write_text(json.dumps(
            {**cr.payload(), "lines": lines_of[k],
             "discovery_rank": s["discovery_rank"],
             "objective_APPROXIMATE": s["objective_APPROXIMATE"],
             "stratum": s["stratum"]}, indent=1))
        beat = " ** BEATS INCUMBENT **" if cr.objective < INCUMBENT_OBJ else ""
        print(f"  [{i}/{len(todo)}] r{s['discovery_rank']:<5d} {k[-12:]} "
              f"obj {cr.objective:,.4f} rounds {cr.rounds} "
              f"converged {cr.converged} ({time.time() - t0:.0f}s){beat}")

    done = sorted(cert_dir.glob("*.json"))
    ok = [p for p in done
          if "error" not in json.loads(p.read_text())]
    print(f"audit: {len(done)}/{len(selected)} written, {len(ok)} ok, "
          f"{len(done) - len(ok)} errors")
    (OUT / "audit_status.json").write_text(json.dumps({
        "audit": "exp4-audit-v1",
        "n_selected": len(selected),
        "n_written": len(done),
        "n_ok": len(ok),
        "n_errors": len(done) - len(ok),
        "complete": len(done) == len(selected),
        "incumbent": {"state_key": INCUMBENT_KEY,
                      "objective_EXACT": INCUMBENT_OBJ,
                      "note": "NOT ALTERED BY THIS AUDIT"},
        "lam": LAM, "seed": SEED, "envelope_digest": ENVELOPE_DIGEST,
        "certification_digest": CERTIFICATION_DIGEST,
        "pipeline": ("identical to scripts/exp4_launch.py certify stage; "
                     "candidate list and output directory differ, nothing else"),
        "scope_of_claim": ("population behaviour of discovery ranks 201-2000 "
                           "under stratified sampling. Certifies no individual "
                           "candidate outside the sample. No fleet claim."),
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
