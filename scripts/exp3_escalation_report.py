#!/usr/bin/env python3
"""Phase 5 — recompute after the literal §6 escalation.

Written and committed BEFORE any escalated effect was read. Every statistical
rule is *imported* from `exp3_stage_b_report`, not transcribed here, so the
criterion, the SD convention, the unit-invariance self-check, the control
diagnostic and the pairwise test are the same code objects that produced the
Stage B table. This script adds exactly one thing: regime bookkeeping.

The rules it applies are fixed in `EXPERIMENT3_PHASE5_DESIGN.md`:

  * the 33 manifest candidates are recomputed at the escalated effort;
    that verdict
    supersedes their 20-restart verdict.
  * the 6 candidates §6 did not trigger keep their Stage B verdict; no
    higher-effort measurement of them exists and their certification was never
    a triggering decision.
  * a pairwise comparison is computed WITHIN ONE REGIME OR NOT AT ALL. Both
    members escalated -> escalated effort. Otherwise -> Stage B effort,
    labelled. The two efforts are read from the contracts, not hardcoded.
  * §8 is then evaluated over the resulting certified set using those
    within-regime comparisons.

Nothing is averaged across regimes. Refuses to report on an incomplete batch.

    python scripts/exp3_escalation_report.py --structure-only   # safe while running
    python scripts/exp3_escalation_report.py --json outputs/exp3/escalation_report.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cota_opt.firewall import (EXP3_STAGE_B,                  # noqa: E402
                               EXP3_STAGE_B_ESCALATED)
from exp3_stage_b_report import (NULL, OUT, K_SIGMA,          # noqa: E402
                                 Candidate, analyse, build,
                                 control_diagnostic, load, pairwise, verdict)

# Read from the contracts, never hardcoded: a wrong literal here would mislabel
# every row's regime while the arithmetic stayed correct, which is the worst
# kind of error because it looks fine.
STAGE_B_RESTARTS = EXP3_STAGE_B.solver.restarts            # 20
ESC_RESTARTS = EXP3_STAGE_B_ESCALATED.solver.restarts      # 40


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--structure-only", action="store_true",
                    help="completeness and admissibility only; reports NO "
                         "effect. Safe to run mid-batch.")
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    man = json.loads((OUT / "escalation_manifest.json").read_text())
    esc_states = [c["candidate"] for c in man["candidates"]]
    if len(esc_states) != man["n_candidates"]:
        raise SystemExit("manifest is internally inconsistent; stop")

    stage_b = json.loads((OUT / "stageB_report.json").read_text())
    sb_rows = {r["state"]: r for r in stage_b["candidates"]}
    sb_certified = set(stage_b["certified"])

    # ---- escalated regime -------------------------------------------------
    receipts, contract = load(escalated=True)
    seeds = list(contract.solver.seeds)
    expected = [(s, seed) for s in [NULL] + esc_states for seed in seeds]
    missing = [k for k in expected if k not in receipts]

    print(f"ESCALATION (§6) contract {contract.digest}")
    print(f"  regime: {contract.solver.restarts} restarts x {len(seeds)} seeds")
    print(f"  design: {len(esc_states)} candidates + control = {len(expected)} cells")
    print(f"  {len(expected) - len(missing)} of {len(expected)} present")

    esc_cands = build(receipts, contract, esc_states, seeds)

    if args.structure_only:
        ok = sum(len(c.effects_pct) for c in esc_cands)
        bad = [(c.state, s, w) for c in esc_cands for s, w in c.refusals.items()
               if w != "cell missing"]
        print(f"  {ok} admissible pairwise comparisons")
        print(f"  {sum(1 for c in esc_cands for w in c.refusals.values() if w == 'cell missing')}"
              " pairs not yet runnable")
        print(f"  {len(bad)} REFUSED by the firewall")
        for st, s, w in bad[:20]:
            print(f"    {st} seed {s}: {w}")
        print("\nNo effects reported: --structure-only.")
        return 0

    if missing:
        print(f"\nREFUSING to report: {len(missing)} of {len(expected)} cells "
              "missing.", file=sys.stderr)
        for k in missing[:10]:
            print(f"    {k[0]} seed {k[1]}", file=sys.stderr)
        if len(missing) > 10:
            print(f"    ... and {len(missing) - 10} more", file=sys.stderr)
        return 2

    esc_res = analyse(esc_cands)
    esc_ctl = control_diagnostic(receipts, seeds)
    esc_rows = {r["state"]: r for r in esc_res["rows"]}

    # ---- Stage B regime, for the 6 §6 never triggered ----------------------
    sb_receipts, sb_contract = load(escalated=False)
    sb_seeds = list(sb_contract.solver.seeds)
    promoted = sorted(sb_rows)
    sb_cands = {c.state: c for c in build(sb_receipts, sb_contract, promoted, sb_seeds)}
    not_escalated = [s for s in promoted if s not in set(esc_states)]

    # ---- the combined table ------------------------------------------------
    combined = []
    for s in promoted:
        if s in esc_rows:
            r = dict(esc_rows[s]); r["regime"] = "escalated"
            r["restarts"] = ESC_RESTARTS
            r["superseded_stage_b"] = True
            r["stage_b_mean_pct"] = sb_rows[s]["mean_pct"]
            r["stage_b_sd_pct"] = sb_rows[s]["sd_pct"]
            r["stage_b_certified"] = sb_rows[s]["certified"]
            r["escalation_triggers"] = next(
                c["trigger_reasons"] for c in man["candidates"] if c["candidate"] == s)
        else:
            r = dict(sb_rows[s]); r["regime"] = "stage_b"
            r["restarts"] = STAGE_B_RESTARTS
            r["superseded_stage_b"] = False
            r["escalation_triggers"] = []
            r["not_escalated_because"] = ("§6 did not trigger: certified, "
                                          "stable spread, ddof-insensitive, "
                                          "all pairwise relations resolved")
        combined.append(r)
    combined.sort(key=lambda r: r["mean_pct"])
    certified = [r["state"] for r in combined if r["certified"]]

    # ---- pairwise, within one regime or not at all -------------------------
    esc_set = set(esc_states)
    cert_esc = [s for s in certified if s in esc_set]
    cert_sb = [s for s in certified if s not in esc_set]

    pw_esc = pairwise([c for c in esc_cands if c.state in cert_esc], cert_esc)
    for p in pw_esc:
        p["regime"] = "escalated"; p["restarts"] = ESC_RESTARTS

    # every pair with at least one non-escalated member: Stage B regime.
    cross = [s for s in certified]
    pw_sb_all = pairwise([sb_cands[s] for s in cross], cross)
    pw_sb = []
    for p in pw_sb_all:
        if p["a"] in esc_set and p["b"] in esc_set:
            continue                      # superseded by the escalated pair
        p["regime"] = "stage_b"; p["restarts"] = STAGE_B_RESTARTS
        p["why_this_regime"] = (f"at least one member has no "
                                f"{ESC_RESTARTS}-restart measurement; a "
                                "cross-regime difference is not computed")
        pw_sb.append(p)
    pw = pw_esc + pw_sb

    # ---- report ------------------------------------------------------------
    print(f"\nEscalated control spread (diagnostic, NOT a gate):")
    if esc_ctl["available"]:
        print(f"  3sigma = {esc_ctl['three_sigma_pct']:.5f}%  "
              f"(flag above {esc_ctl['flag_threshold_pct']:.5f}%) -> "
              f"{'FLAGGED' if esc_ctl['flagged'] else 'normal'}")

    print(f"\nCOMBINED TABLE  ({len(combined)} candidates; "
          f"{len(esc_rows)} at {ESC_RESTARTS} restarts, "
          f"{len(not_escalated)} at {STAGE_B_RESTARTS})\n")
    print(f"  {'state':<44} {'mean%':>10} {'SD%':>10} {'|m|/SD':>8} {'reg':>4}  verdict")
    for r in combined:
        v = "CERTIFIED" if r["certified"] else "not certified"
        if r["regime"] == "escalated" and r["certified"] != r["stage_b_certified"]:
            v += "  <-- CHANGED by escalation"
        print(f"  {r['state']:<44} {r['mean_pct']:>10.5f} {r['sd_pct']:>10.6f} "
              f"{r['ratio']:>8.2f} {ESC_RESTARTS if r['regime']=='escalated' else STAGE_B_RESTARTS:>4}  {v}")

    flips = [r for r in combined if r["regime"] == "escalated"
             and r["certified"] != r["stage_b_certified"]]
    print(f"\nCertification changes from escalation: {len(flips)}")
    for r in flips:
        print(f"  {r['state']}: {'not certified' if r['stage_b_certified'] else 'certified'}"
              f" -> {'CERTIFIED' if r['certified'] else 'not certified'}"
              f"  (Stage B mean {r['stage_b_mean_pct']:+.5f}% SD {r['stage_b_sd_pct']:.6f}%"
              f" -> {r['mean_pct']:+.5f}% SD {r['sd_pct']:.6f}%)")

    unres = [p for p in pw if not p["resolved"]]
    print(f"\nPairwise: {len(pw)} comparisons among {len(certified)} certified")
    print(f"  {len(pw_esc)} at {ESC_RESTARTS} restarts (both members escalated)")
    print(f"  {len(pw_sb)} at {STAGE_B_RESTARTS} restarts (at least one member "
          "not escalated)")
    print(f"  {len(unres)} unresolved")

    def separates_from_all(state: str) -> bool:
        mine = [q for q in pw if state in (q["a"], q["b"])]
        return bool(mine) and all(q["resolved"] for q in mine)

    leaders = [r["state"] for r in combined
               if r["certified"] and separates_from_all(r["state"])]

    print("\n§8 outcome: ", end="")
    if not certified:
        print("(3) EFFECTIVELY NULL after certification.")
    elif len(certified) == 1:
        print(f"(1) ONE CERTIFIED CANDIDATE: {certified[0]}")
    elif leaders and leaders[0] == combined[0]["state"]:
        lead = combined[0]
        print(f"(1) A CERTIFIED LEADER: {leaders[0]}")
        print(f"  certified against the control and distinguishable from all "
              f"{len(certified) - 1} other certified candidates.")
        print(f"  {len(unres)} of {len(pw)} pairs elsewhere remain unresolved; "
              "none involves the leader.")
        print(f"  MEASURED AT {lead['restarts']} RESTARTS"
              + ("" if lead["regime"] == "escalated" else
                 f" -- §6 did not trigger on it, so its margin is UNCONFIRMED "
                 f"at {ESC_RESTARTS} restarts while some rivals have been "
                 "tested there."))
    else:
        print(f"(2) {len(certified)} CERTIFIED, NOT ALL DISTINGUISHABLE — "
              "reported as a set, no leader named (§8).")
        if combined[0]["state"] not in leaders:
            bad = [q for q in pw if combined[0]["state"] in (q["a"], q["b"])
                   and not q["resolved"]]
            print(f"  the Stage B leader {combined[0]['state']} no longer "
                  f"separates: {len(bad)} unresolved comparison(s), "
                  f"regime(s) {sorted({q['regime'] for q in bad})}")

    print("\nCertified means distinguishable from solver variance at the effort "
          "stated in its row, and nothing more (§9). Rows measured at different "
          "efforts are never differenced against each other "
          "(EXPERIMENT3_PHASE5_DESIGN.md).")

    if args.json:
        Path(args.json).write_text(json.dumps({
            "escalation_contract": contract.digest,
            "stage_b_contract": sb_contract.digest,
            "escalated_restarts": ESC_RESTARTS,
            "stage_b_restarts": STAGE_B_RESTARTS,
            "n_escalated": len(esc_states),
            "not_escalated": not_escalated,
            "escalated_control_diagnostic": esc_ctl,
            "combined": combined,
            "certified": certified,
            "certification_changes": [r["state"] for r in flips],
            "pairwise": pw,
            "unresolved": [{"a": p["a"], "b": p["b"], "regime": p["regime"]}
                           for p in unres],
            "leaders": leaders,
            "escalated_only_report": esc_res,
        }, indent=2, default=str))
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
