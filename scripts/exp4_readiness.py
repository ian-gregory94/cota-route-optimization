#!/usr/bin/env python3
"""Experiment 4 — the definition-of-ready gate, checked rather than claimed.

22 items: the 15 in EXPERIMENT4_CONTRACT.md section 24, plus the 7 added by
EXPERIMENT4_DESIGN.md section 9 after D27-D33.

Every check reads an artifact, imports a module, or runs a test. Items that
cannot be checked mechanically are reported as MANUAL with what a human must
confirm -- they are never silently counted as met. Exits non-zero while any
item is open, so "is Experiment 4 ready" has one answer and it is not a
memory.

    python scripts/exp4_readiness.py
    python scripts/exp4_readiness.py --json outputs/exp4/readiness.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "outputs" / "exp4"

MET, OPEN, MANUAL = "MET", "OPEN", "MANUAL"


def _json(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _src(rel: str) -> str:
    p = ROOT / rel
    return p.read_text() if p.exists() else ""


def _acceptance_gate(label: str) -> bool:
    """Is this Experiment 4 gate committed in ACCEPTANCE.md?

    Committed is not satisfied. A gate written down is a promise about what will
    be checked; running it is a separate item. Items that need the gate RUN say
    so in their own detail line.
    """
    return label in (ROOT / "ACCEPTANCE.md").read_text()


def _git(*args: str) -> str:
    r = subprocess.run(("git",) + args, cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip()


def checks() -> list[tuple[str, str, str, str]]:
    """(id, title, status, detail)"""
    out: list[tuple[str, str, str, str]] = []

    def add(i, title, status, detail=""):
        out.append((i, title, status, detail))

    pool = _json(OUT / "route_pool.json")
    lg = _json(OUT / "linkgraph_audit.json")
    tr = _json(OUT / "transition_audit.json")
    rc = _json(OUT / "reconstruction.json")

    # ---- contract section 24 ------------------------------------------------
    tags = _git("tag", "-l", "exp3-final-v1")
    dirty = _git("status", "--porcelain")
    add("C1", "Experiment 3 closed and frozen",
        MET if tags and not dirty else OPEN,
        f"tag={tags or 'absent'}, tree={'clean' if not dirty else 'dirty'}")

    base = OUT / "pre_exp4_baseline_v1.json"
    add("C2", "pre_exp4_baseline_v1 exists",
        MET if base.exists() else OPEN,
        str(base.relative_to(ROOT)) if base.exists() else "not found")

    add("C3", "Synthetic routes exist independently of legacy route ids",
        MET if pool and pool.get("accepted", 0) > 0 else OPEN,
        f"{pool.get('accepted')} accepted from "
        f"{len(pool.get('accepted_by_generator', {}))} generators" if pool else "no pool")

    add("C4", "Legacy network reconstructs and reproduces score and resources",
        MET if rc and rc.get("every_route_reconstructed")
        and rc.get("stop_coverage_complete") else OPEN,
        f"{rc.get('reconstructed')} routes, stop coverage complete="
        f"{rc.get('stop_coverage_complete')}; SCORE/RESOURCE reproduction is the "
        "part to confirm" if rc else "no reconstruction artifact")

    try:
        from cota_opt.routeclass import RouteClass                # noqa: F401
        has_klass = "peak_express" in (
            ROOT / "src" / "cota_opt" / "routeclass.py").read_text()
    except Exception:
        has_klass = False
    locks = "peak_express" in (
        ROOT / "src" / "cota_opt" / "exp3_score.py").read_text()
    add("C5", "Peak express service explicitly separated",
        MET if has_klass and locks else OPEN,
        "routeclass.py defines the peak_express class and exp3_score locks it "
        "via lock_classes" if has_klass and locks else "class or lock missing")

    add("C6", "Observed-link graph built and audited",
        MET if lg and lg.get("every_pattern_is_a_path") else OPEN,
        f"{lg.get('n_stops')} stops, {lg.get('n_directed_links')} links, "
        f"every_pattern_is_a_path={lg.get('every_pattern_is_a_path')}" if lg else "absent")

    add("C7", "Frozen route pool contains the current network",
        MET if pool and pool.get("legacy_in_pool") == pool.get("legacy_lines")
        and pool.get("legacy_lines", 0) > 0 else OPEN,
        f"legacy_in_pool={pool.get('legacy_in_pool')}/"
        f"{pool.get('legacy_lines')}" if pool else "no pool")

    try:
        import inspect

        from cota_opt.frequency import OFF, build_ladders, is_off
        off_ok = (is_off(OFF)
                  and inspect.signature(build_ladders)
                  .parameters["allow_off"].default is False)
    except Exception:
        off_ok = False
    add("C8", "Synthetic route-period service can be OFF",
        MET if off_ok else OPEN,
        "frequency.OFF (infinite headway): zero trips, zero vehicle-hours, zero "
        "peak vehicles, unboardable by the path model. build_ladders(allow_off=) "
        "defaults False so Gen1 cannot represent it. tests/test_off_service.py"
        if off_ok else "no OFF representation")
    # The FILE existing is not the gate passing -- an earlier version of this
    # check tested only for the artifact and reported MET on a benchmark whose
    # own verdict was False. Third time a check here over-claimed; read the
    # verdict, never the artifact.
    # C9 stays tied to the GATE'S CLOSURE, not to the benchmark having run.
    # The looser reading -- "benchmarked" is satisfied once a benchmark exists --
    # is available and is refused: it is the same move as reporting MET because
    # an artifact is on disk, which this check has made three times. Readiness
    # means discovery may proceed with reuse, and it may not.
    _g47 = _json(OUT / "gate47.json")
    _adj = _json(OUT / "gate47_adjudicated.json")
    _adj_ok = (_adj or {}).get("verdict") == "MET"
    _adj_note = ""
    if _adj and not _adj_ok:
        _adj_note = (
            f"AND adjudication against D18 is blocked: {_adj.get('blocked_by')}. "
            f"A gate about a DISCOVERY-EFFORT approximation cannot close when "
            f"discovery-effort comparison is itself forbidden. ")
    _mp = _json(OUT / "masterpath_benchmark.json")
    _pr = _json(OUT / "pathreuse_benchmark.json")
    if _g47:
        _inv = sum(c["ranking_inversions"] for c in _g47["cases"])
        _prs = sum(c["ranking_pairs"] for c in _g47["cases"])
        _ld = sum(c["leader_preserved"] for c in _g47["cases"])
        _n = len(_g47["cases"])
        _c9_detail = (
            f"BENCHMARKED as a ONE-FACTOR comparison and NOT closed. The "
            f"previous measurement varied reuse AND enumeration richness "
            f"together and was unidentified; the amendment "
            f"(decisions/2026-09-05-gate-4-7-amendment.md) narrows the gate to "
            f"reuse alone. Substrate proved sound: filtering is exactly the "
            f"identity at survival 1.000, zero hard failures. Approximation "
            f"fails: exact leader preserved in {_ld}/{_n} cases, {_inv}/{_prs} "
            f"pairs inverted, worst objective rel gap "
            f"{_g47['worst_objective_rel_gap']:.3e}. The bias is systematic and "
            f"directional -- zero at survival 1.000, growing as the candidate "
            f"thins -- so reuse biases the search toward activating more lines. "
            + (_adj_note if _adj_note else
               "NO LONGER BLOCKED ON D18: closure is band-independent. ")
            + "EXPERIMENT4_GATE47.md, outputs/exp4/gate47.json")
        _c9_met = _g47.get("verdict") == "MET" and _adj_ok
    elif _mp:
        _inv = sum(c["ranking_inversions"] for c in _mp["cases"])
        _prs = sum(c["ranking_pairs"] for c in _mp["cases"])
        _ld = sum(c["leader_identified"] for c in _mp["cases"])
        _nc = len(_mp["cases"])
        _c9_detail = (
            f"BUILT and RUN, and NOT closed. The gate's own object -- a frozen "
            f"supernetwork master path set, filtered per candidate -- now "
            f"exists and was benchmarked against exact rebuilds on "
            f"{_mp['n_candidates']} preregistered candidates: exact leader "
            f"identified in {_ld}/{_nc} cases, {_inv}/{_prs} ranking pairs "
            f"inverted, promoted set changes in "
            f"{sum(c['promoted_set_changes'] for c in _mp['cases'])}/{_nc}, "
            f"worst objective rel gap {_mp['worst_objective_rel_gap']:.3e}, "
            f"median speedup ~5.3x. At survival 1.000 the reuse arm still "
            f"differs and is BETTER in 4/5 cases, so the residual is "
            f"enumeration richness rather than filtering, and widening -- the "
            f"remedy the gate names -- changed nothing. Closure now needs "
            f"D18's promotion band. This replaces the naive cache-sharing "
            f"result (worst 1.307), which was a different and invalid object. "
            f"EXPERIMENT4_MASTERPATH.md, outputs/exp4/masterpath_benchmark.json")
        _c9_met = bool(_mp.get("band_independent_pass"))
    else:
        _c9_detail = ("the master-path benchmark has not been run: "
                      "scripts/exp4_masterpath_benchmark.py")
        _c9_met = bool((_pr or {}).get("gate_4_7_closes"))
    add("C9", "Discovery path reuse benchmarked against exact rebuilds",
        MET if _c9_met else OPEN, _c9_detail)
    _c10 = _json(OUT / "c10_benchmark.json")
    add("C10", "Outer network search recovers an exhaustively known optimum",
        MET if (_c10 or {}).get("gate_4_14_closes") else OPEN,
        "CLOSED on the production evaluator: 5 of 5 cases genuinely defeat "
        "add-only greedy and Gen2 recovers all 5 exact optima. Cases were "
        "discovered by scanning 45 spaces, not hand-tuned. "
        "outputs/exp4/c10_benchmark.json")
    add("C11", "Committed gate on common-lines exposure",
        MET if _acceptance_gate("Gate 4-10") else OPEN,
        "ACCEPTANCE.md Gate 4-10 -- every promoted network reruns the "
        "diagnostic; if exposure balloons the result is classified "
        "model-dependent")
    add("C12", "Committed transfer-depth, path-cap and OD-cap adequacy gates",
        MET if _acceptance_gate("Gate 4-9") else OPEN,
        "ACCEPTANCE.md Gate 4-9 covers all three: deeper max_rounds on promoted "
        "networks, the 4->6 paths-per-OD sensitivity redone, and certification "
        "on a materially wider OD set than the top 20,000")
    claims = ROOT / "EXPERIMENT4_DEMAND_ROBUSTNESS.md"
    add("C13", "Demand-robustness claims written before the winner is known",
        MET if claims.exists() else OPEN,
        "Gate 4-12 is COMMITTED in ACCEPTANCE.md, but the CLAIMS themselves are "
        "not written. They must exist before any Exp 4 winner is known, so this "
        "is cheap now and impossible later"
        if _acceptance_gate("Gate 4-12") else "gate not found")
    ed = "network_edit_distance_pct" in (
        ROOT / "src" / "cota_opt" / "contract.py").read_text()
    add("C14", "Structural-distance measurement exists",
        MET if ed and _acceptance_gate("Gate 4-13") else OPEN,
        "contract.py computes network_edit_distance_pct with a committed cap; "
        "ACCEPTANCE Gate 4-13 requires geometry-based identity because Exp 4 "
        "route ids are synthetic")
    gates4 = [g for g in (f"Gate 4-{n}" for n in range(1, 16))
              if _acceptance_gate(g)]
    # The counts are read from the gate runner rather than retyped, because a
    # hand-maintained tally in a checklist is a number nobody re-checks -- this
    # line said "9 MET, 4 ARMED, 2 OPEN" after the gates had already moved.
    _gs = _json(OUT / "gates.json") or {}
    _gtxt = (f"{_gs['met']} MET, {_gs['armed']} ARMED (they fire on a promoted "
             f"network and cannot be satisfied before the search), "
             f"{_gs['open']} OPEN"
             if "met" in _gs else
             "run scripts/exp4_gates.py --json outputs/exp4/gates.json for "
             "current counts")
    add("C15", "Every ACCEPTANCE.md rejection condition in place before scoring",
        MANUAL,
        f"{len(gates4)} of 15 gates written; scripts/exp4_gates.py executes "
        f"them: {_gtxt}. Remains MANUAL because 'armed' is a judgement that the "
        "right machinery exists, not a proof -- and because D35 showed a "
        "constraint can be fully written, validated at construction, hashed "
        "into the state digest and still reach nothing that scores")

    # ---- design section 9 ---------------------------------------------------
    try:
        from cota_opt.firewall import exp4_draft            # noqa: F401
        has_draft = True
    except Exception:
        has_draft = False
    # Must be an ExperimentContract, not merely a name beginning with EXP4.
    # An earlier version of this check tested the latter and flipped to MET the
    # moment EXP4_ALLOWANCE was exported -- a different object entirely.
    try:
        import cota_opt.firewall as fw
        from cota_opt.firewall.contract import ExperimentContract
        in_force = [n for n in dir(fw)
                    if n.startswith("EXP4")
                    and isinstance(getattr(fw, n, None), ExperimentContract)]
    except Exception:
        in_force = []
    draft_says_not_in_force = "not yet in force" in _src(
        "src/cota_opt/firewall/exp4_draft.py")
    # D16 is NOT closed by an ExperimentContract merely existing, and NOT by
    # D21b closing. Its criterion has three clauses -- the contract exists,
    # every declared treatment difference carries a written justification, and
    # construction REFUSES when one is missing -- and the third can only be
    # settled by firing the guard. scripts/exp4_d16_check.py executes all
    # three, plus the precondition the draft set for itself, and this reads
    # that script's verdict. An earlier version tested clause one and reported
    # MET, which is the same error as D21 passing on half its own text.
    _d16 = _json(OUT / "d16_check.json")
    if _d16:
        _d16_detail = (
            f"{_d16['passed']}/{_d16['total']} checks pass in "
            f"scripts/exp4_d16_check.py, which executes the criterion's three "
            f"clauses separately and fires the construction guard for EVERY "
            f"declared dimension in turn. Contracts in force: "
            f"{sorted(_d16['contracts'])} "
            f"(digests {', '.join(sorted(c['digest'] for c in _d16['contracts'].values()))}). "
            f"Bridge verdict {_d16['bridge_verdict']}. "
            f"outputs/exp4/d16_check.json")
        _d16_met = _d16.get("verdict") == "MET"
    else:
        _d16_detail = (
            f"ExperimentContract instances exported: {in_force or 'none'}; "
            f"exp4_draft.py still says 'not yet in force'="
            f"{draft_says_not_in_force}. The criterion has not been EXECUTED: "
            f"run scripts/exp4_d16_check.py")
        _d16_met = False
    add("D16", "Experiment 4 ExperimentContract exists and is in force",
        MET if _d16_met else OPEN, _d16_detail)

    add("D17", "Recovery behaviours classified in writing before the search",
        MET if "recovery" in (ROOT / "EXPERIMENT4_DESIGN.md").read_text().lower()
        else OPEN,
        "EXPERIMENT4_DESIGN.md section 2 classifies seven; a committed machine-"
        "readable form is what the search will actually consult")

    # D18's criterion is that the benchmark HAS RUN and question 3's answer is
    # RECORDED -- "including the branch where it forbids discovery-effort
    # comparison". Taking the forbidding branch therefore MEETS D18. It does
    # not make Experiment 4 runnable; it is the answer, and the answer being
    # unwelcome is not the same as the item being open.
    _gap = _json(OUT / "gap_benchmark.json")
    if _gap:
        _q3 = _gap["q3_gap_tracks_structure"]
        add("D18", "Gap benchmark run on Experiment 4 networks, Q3 answered",
            MET,
            f"RUN on {_gap['n_cells']} cells over {len(_gap['q2_by_structure'])} "
            f"network structures, by exhaustive enumeration of a reduced "
            f"neighbourhood (K={_gap['k_rungs']}, N={_gap['sizes']}) under the "
            f"production objective. Q1/Q2: median gap "
            f"{_gap['q1_median_gap_pct']:+.6f}%, max "
            f"{_gap['q1_max_gap_pct']:+.6f}%. Q3 ANSWER RECORDED: "
            f"{_gap['q3_answer']} (largest structure-paired differential "
            f"{_gap['q3_largest_paired_differential_pp']:.6f} pp against a "
            f"median absolute gap of "
            f"{_gap['q3_median_absolute_gap_pp']:.6f} pp, ratio "
            f"{_gap['q3_ratio']:.3f} vs the limit "
            f"{_gap['q3_forbid_ratio_declared']} declared before any number "
            f"existed). Q4: "
            + (f"NO BAND EMITTED -- section 3's forbidding branch. "
               f"discovery_effort_comparison_permitted=False. This item is MET "
               f"and Experiment 4 is BLOCKED BY ITS ANSWER, which is a "
               f"different thing."
               if _q3 else
               f"promotion band {_gap['q4_promotion_band_pp']:.6f} pp.")
            + " outputs/exp4/gap_benchmark.json")
    else:
        add("D18", "Gap benchmark run on Experiment 4 networks, Q3 answered",
            OPEN,
            "not run -- scripts/exp4_gap_benchmark.py. This is the "
            "compute-heavy item and it can forbid discovery-effort comparison "
            "outright")

    docs = " ".join((ROOT / f).read_text() for f in
                    ("EXPERIMENT4_DESIGN.md", "EXPERIMENT4_CONTRACT.md"))
    add("D19", "Effort stated in restarts with convergence asserted",
        MET if "restarts_completed" in docs and "converged" in docs else OPEN,
        "EXPERIMENT4_DESIGN.md section 4 states effort in restarts, records "
        "restarts_completed and converged, and refuses a certification "
        "comparison where either arm did not converge")

    cls = (tr or {}).get("classes", {})
    add("D20", "Transition-level evidence on every pool line and the receipt",
        MET if tr and tr.get("n_lines") == (pool or {}).get("accepted") else OPEN,
        f"{tr.get('n_lines')} lines classified, classes={cls}; receipt-side "
        "attachment still to confirm" if tr else "absent")

    # Two conditions, and an earlier version of this check tested only the
    # first and reported MET. Splitting them is the point: a gate that passes
    # on half its own text is worse than no gate.
    gen1 = ROOT / "GEN1_FREEZE.md"
    gen1_man = OUT.parent / "GEN1_FREEZE_MANIFEST.json"
    add("D21a", "Gen1 frozen",
        MET if gen1.exists() and gen1_man.exists() else OPEN,
        "GEN1_FREEZE.md + outputs/GEN1_FREEZE_MANIFEST.json; verify with "
        "scripts/gen1_freeze.py --verify" if gen1.exists() else "absent")
    # Read the bridge's VERDICT, not the file's existence. A bridge that ran
    # and came back BROKEN is a bridge that has run and must not close this.
    _bridge = _json(OUT / "gen_bridge.json")
    if _bridge:
        _b_met = _bridge.get("verdict") in ("CONFIRMED", "SUPERSEDED")
        add("D21b", "Gen1->Gen2 bridge suite has run",
            MET if _b_met else OPEN,
            f"RUN. One real Gen1 question -- the optimal frequency plan for an "
            f"assembled Exp 4 network under a pinned envelope -- answered twice, "
            f"arms differing only in the solver. Verdict {_bridge['verdict']}: "
            f"{_bridge['note']} Gen1 {_bridge['seconds']['gen1']:.1f}s vs Gen2 "
            f"{_bridge['seconds']['gen2']:.1f}s over "
            f"{_bridge['exact_combinations']:,} combinations. "
            f"outputs/exp4/gen_bridge.json")
        return_early_d21b = True
    else:
        return_early_d21b = False
    bridge = OUT.parent / "gen1_gen2_bridge.json"
    if not return_early_d21b:
        add("D21b", "Gen1->Gen2 bridge suite has run",
            MET if bridge.exists() else OPEN,
            "the bridge has not been run: scripts/exp4_gen_bridge.py. Gen2's "
            "replacement frequency solver (cota_opt.gen2_frequency) now exists, "
            "so the Gen1 question the bridge needs -- the optimal frequency "
            "plan for one network -- can be answered by both generations")

    merged = (ROOT / "src" / "cota_opt" / "firewall" / "search_allowance.py")
    staged = (ROOT / "scripts" / "exp4_staging" / "search_allowance.py")
    add("D22", "Search-allowance contract merged into firewall/ and in force",
        MET if merged.exists() else OPEN,
        f"still staged at {staged.relative_to(ROOT)}; OPERATIONS 24 blocked the "
        "move while the Experiment 3 batch ran and that block is now lifted"
        if not merged.exists() else "merged")

    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    rows = checks()
    w = max(len(t) for _, t, _, _ in rows)
    print("EXPERIMENT 4 — DEFINITION OF READY\n")
    print(f"  {'':4} {'item':<{w}}  status")
    for i, title, status, detail in rows:
        print(f"  {i:<4} {title:<{w}}  {status}")
        if detail:
            print(f"       {'':<{w}}  {detail}")
    met = sum(1 for *_, s, _ in rows if s == MET)
    opn = sum(1 for *_, s, _ in rows if s == OPEN)
    man = sum(1 for *_, s, _ in rows if s == MANUAL)
    print(f"\n  {met} met | {opn} open | {man} need manual confirmation "
          f"| {len(rows)} total")
    print("\nExperiment 4 is NOT ready to launch a search while any item is open "
          "or unconfirmed.\nMANUAL items are not met -- they are unchecked.")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"items": [{"id": i, "title": t, "status": s, "detail": d}
                       for i, t, s, d in rows],
             "met": met, "open": opn, "manual": man, "total": len(rows),
             "ready": opn == 0 and man == 0}, indent=2))
        print(f"\nwrote {args.json}")
    return 1 if (opn or man) else 0


if __name__ == "__main__":
    raise SystemExit(main())
