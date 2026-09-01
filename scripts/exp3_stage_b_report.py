#!/usr/bin/env python3
"""Experiment 3 Stage B — the analysis.

Written before any Stage B result existed, for the same reason the criterion was
preregistered: analysis code written while the numbers are visible is analysis
code shaped by the numbers.

**This script does not decide anything.** Every rule it applies is fixed in
`EXPERIMENT3_STAGE_B_PREREGISTRATION.md` and is transcribed here, not chosen
here. Where the preregistration is silent on a purely numerical convention, the
script computes the verdict under *both* readings and escalates any candidate
whose answer depends on which one is used (see `--help` on `ddof`).

Refuses to emit verdicts on an incomplete run. A partial certification batch is
exactly the shape of evidence that looks like an answer and is not one, and this
project has been bitten by that specific thing more than once (OPERATIONS 18,
24, 27).

    python scripts/exp3_stage_b_report.py --structure-only   # safe while running
    python scripts/exp3_stage_b_report.py                    # only when 200/200
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cota_opt.firewall import (EXP3_STAGE_B, EXP3_STAGE_B_ESCALATED,  # noqa: E402
                               InadmissibleComparison, ObservationStore,
                               compare)

OUT = ROOT / "outputs" / "exp3"
NULL = "<none>"

# §4: the reference point for the control-spread DIAGNOSTIC. 2B's matched-start
# confirmation gave 3sigma = 0.00657%. A Stage B control spread more than 3x
# that is flagged for investigation of the WHOLE RUN.
#
# This number is a solver-stability trigger. It is never compared against a
# candidate's effect and nothing certifies or fails to certify because of it.
CONTROL_SPREAD_REFERENCE_3SIGMA_PCT = 0.00657
CONTROL_SPREAD_FLAG_MULTIPLE = 3.0

# §4: the criterion. Fixed. Do not parameterise this.
K_SIGMA = 3.0


@dataclass
class Candidate:
    state: str
    effects_pct: dict[int, float]          # seed -> paired effect, percent
    effects_abs: dict[int, float]          # seed -> paired effect, objective units
    refusals: dict[int, str]               # seed -> why the pair was refused

    @property
    def complete(self) -> bool:
        return not self.refusals


def _sd(xs: list[float], ddof: int) -> float:
    if len(xs) - ddof < 1:
        return float("nan")
    return statistics.stdev(xs) if ddof == 1 else statistics.pstdev(xs)


def verdict(effects: list[float], ddof: int) -> tuple[bool, float, float]:
    """§4: certified iff |mean| > 3*SD and mean < 0. Returns (certified, mean, sd).

    Unit-invariant: scaling every effect by a constant scales mean and SD
    alike, so percent and absolute objective units give the same answer. The
    caller asserts that.
    """
    m = statistics.fmean(effects)
    sd = _sd(effects, ddof)
    return (m < 0 and abs(m) > K_SIGMA * sd), m, sd


def load(escalated: bool) -> tuple[dict, object]:
    """Receipts, keyed (state, seed). The observation store is the evidence.

    Not the .jsonl rows: a row is something the runner wrote about the work,
    and a receipt is the work. Reading rows and treating a missing field as
    fine is the exact bug that made `done()` report cells it had never seen.
    """
    contract = EXP3_STAGE_B_ESCALATED if escalated else EXP3_STAGE_B
    frozen_f = OUT / "EVAL_PATH_FROZEN"
    frozen = frozen_f.read_text().strip() if frozen_f.exists() else None
    store = ObservationStore(OUT / ("observations_stageB_esc" if escalated
                                    else "observations_stageB"))
    out: dict[tuple[str, int], object] = {}
    skipped_contract = skipped_code = 0
    for r in store.all():
        if r.spec.contract_digest != contract.digest:
            skipped_contract += 1
            continue
        if frozen and r.code_version != frozen:
            skipped_code += 1
            continue
        key = (r.spec.state_key or NULL, r.spec.seed)
        if key in out:
            raise SystemExit(
                f"two receipts for {key} under one contract and code version; "
                "the store is ambiguous and nothing may be computed from it")
        out[key] = r
    if skipped_contract or skipped_code:
        print(f"  ignored {skipped_contract} receipts from another contract, "
              f"{skipped_code} from another evaluation path", file=sys.stderr)
    return out, contract


def build(receipts: dict, contract, states: list[str], seeds: list[int]
          ) -> list[Candidate]:
    """§3: every comparison goes through firewall.compare() on the receipts.

    A pair whose execution differed in any undeclared way yields NO effect for
    that seed rather than a suspect one.
    """
    cands: list[Candidate] = []
    for state in states:
        pct: dict[int, float] = {}
        absol: dict[int, float] = {}
        refused: dict[int, str] = {}
        for s in seeds:
            ctl, trt = receipts.get((NULL, s)), receipts.get((state, s))
            if ctl is None or trt is None:
                refused[s] = "cell missing"
                continue
            r = compare(ctl, trt, contract)
            if isinstance(r, InadmissibleComparison) or not r:
                refused[s] = str(r).replace("\n", " ")[:300]
                continue
            pct[s] = r.effect_pct
            absol[s] = r.effect
        cands.append(Candidate(state, pct, absol, refused))
    return cands


def control_diagnostic(receipts: dict, seeds: list[int]) -> dict:
    """§4: a run-level solver-stability measure. NOT a gate on any candidate."""
    objs = [receipts[(NULL, s)].objective for s in seeds if (NULL, s) in receipts]
    if len(objs) < 2:
        return {"available": False}
    mean = statistics.fmean(objs)
    sd = statistics.stdev(objs)
    three_sigma_pct = 100.0 * K_SIGMA * sd / abs(mean) if mean else float("nan")
    trigger = CONTROL_SPREAD_FLAG_MULTIPLE * CONTROL_SPREAD_REFERENCE_3SIGMA_PCT
    return {"available": True, "n": len(objs), "objectives": objs,
            "mean": mean, "sd": sd, "three_sigma_pct": three_sigma_pct,
            "reference_3sigma_pct": CONTROL_SPREAD_REFERENCE_3SIGMA_PCT,
            "flag_threshold_pct": trigger,
            "flagged": three_sigma_pct > trigger,
            "role": "run-level solver-stability diagnostic; never a "
                    "materiality threshold and never compared to a candidate"}


def analyse(cands: list[Candidate]) -> dict:
    usable = [c for c in cands if c.complete]
    rows = []
    sds = []
    for c in usable:
        e_pct = [c.effects_pct[s] for s in sorted(c.effects_pct)]
        e_abs = [c.effects_abs[s] for s in sorted(c.effects_abs)]
        cert1, m1, sd1 = verdict(e_pct, ddof=1)
        cert0, m0, sd0 = verdict(e_pct, ddof=0)
        # Unit invariance self-check: the verdict must not depend on units.
        cert1_abs, _, _ = verdict(e_abs, ddof=1)
        if cert1_abs != cert1:
            raise SystemExit(f"{c.state}: verdict changed with units; "
                             "the arithmetic is wrong, stop")
        rows.append({"state": c.state, "effects_pct": e_pct,
                     "mean_pct": m1, "sd_pct": sd1,
                     "ratio": abs(m1) / sd1 if sd1 else float("inf"),
                     "certified": cert1,
                     "certified_ddof0": cert0, "sd_pct_ddof0": sd0,
                     "ddof_sensitive": cert1 != cert0})
        sds.append(sd1)
    median_sd = statistics.median(sds) if sds else float("nan")
    for r in rows:
        # §6: escalate on failure, or on an unstable paired spread.
        unstable = r["sd_pct"] > 3.0 * median_sd if sds else False
        r["spread_unstable"] = unstable
        r["escalate"] = (not r["certified"]) or unstable or r["ddof_sensitive"]
        r["escalate_because"] = [x for x, y in (
            ("failed paired criterion at 20 restarts", not r["certified"]),
            ("paired spread > 3x median SD across candidates", unstable),
            ("verdict depends on the SD convention", r["ddof_sensitive"]),
        ) if y]
    rows.sort(key=lambda r: r["mean_pct"])
    return {"rows": rows, "median_sd_pct": median_sd,
            "refused": [{"state": c.state, "seeds": c.refusals}
                        for c in cands if not c.complete]}


def pairwise(cands: list[Candidate], certified: list[str]) -> list[dict]:
    """§5: certified candidates compared to each other on the SAME observations."""
    by = {c.state: c for c in cands}
    out = []
    for i, a in enumerate(certified):
        for b in certified[i + 1:]:
            ca, cb = by[a], by[b]
            seeds = sorted(set(ca.effects_abs) & set(cb.effects_abs))
            if len(seeds) < 2:
                out.append({"a": a, "b": b, "resolved": False,
                            "why": "too few shared seeds"})
                continue
            d = [ca.effects_abs[s] - cb.effects_abs[s] for s in seeds]
            sep, m, sd = verdict(d, ddof=1)
            distinguishable = abs(m) > K_SIGMA * sd if sd else True
            out.append({"a": a, "b": b, "seeds": seeds, "mean": m, "sd": sd,
                        "distinguishable": distinguishable,
                        "better": (a if m < 0 else b) if distinguishable else None,
                        "resolved": distinguishable})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="ddof: the preregistration says 'the standard deviation of the "
               "candidate's own five paired differences' without naming a "
               "convention. The sample SD (ddof=1) is used, and any candidate "
               "whose verdict would flip under the population SD (ddof=0) is "
               "reported as ddof-sensitive and escalated rather than resolved "
               "by picking a convention after seeing the data.")
    ap.add_argument("--escalated", action="store_true")
    ap.add_argument("--structure-only", action="store_true",
                    help="check completeness and comparison admissibility "
                         "WITHOUT reporting any effect. Safe to run mid-batch.")
    ap.add_argument("--json", default="", help="write the full result here")
    args = ap.parse_args()

    receipts, contract = load(args.escalated)
    seeds = list(contract.solver.seeds)
    census = json.loads((OUT / "stageA_census.json").read_text())
    promoted = sorted(r["state"] for r in census["states"] if r["effect_pct"] < 0)
    expected = [(s, seed) for s in [NULL] + promoted for seed in seeds]
    missing = [k for k in expected if k not in receipts]

    print(f"Stage B {'(escalated) ' if args.escalated else ''}"
          f"contract {contract.digest}")
    print(f"  {len(expected) - len(missing)} of {len(expected)} cells present")

    if args.structure_only:
        cands = build(receipts, contract, promoted, seeds)
        ok = sum(len(c.effects_pct) for c in cands)
        bad = [(c.state, s, why) for c in cands for s, why in c.refusals.items()
               if why != "cell missing"]
        print(f"  {ok} admissible pairwise comparisons")
        print(f"  {len([1 for c in cands for w in c.refusals.values() if w == 'cell missing'])}"
              " pairs not yet runnable (a cell is missing)")
        if bad:
            print(f"  {len(bad)} REFUSED by the firewall:")
            for st, s, why in bad[:20]:
                print(f"    {st} seed {s}: {why}")
        else:
            print("  0 refused by the firewall")
        print("\nNo effects reported: --structure-only.")
        return 0

    if missing:
        print(f"\nREFUSING to report: {len(missing)} cells are missing.",
              file=sys.stderr)
        for k in missing[:10]:
            print(f"    {k[0]} seed {k[1]}", file=sys.stderr)
        if len(missing) > 10:
            print(f"    ... and {len(missing) - 10} more", file=sys.stderr)
        print("\nThe criterion is preregistered over the complete design. A "
              "partial run is not a small version of the answer.", file=sys.stderr)
        return 2

    cands = build(receipts, contract, promoted, seeds)
    res = analyse(cands)
    ctl = control_diagnostic(receipts, seeds)
    certified = [r["state"] for r in res["rows"] if r["certified"]]
    pw = pairwise(cands, certified)

    print(f"\nControl spread (run-level diagnostic, NOT a gate):")
    if ctl["available"]:
        print(f"  3sigma = {ctl['three_sigma_pct']:.5f}%  "
              f"(flag above {ctl['flag_threshold_pct']:.5f}%) "
              f"-> {'FLAGGED, investigate the run' if ctl['flagged'] else 'normal'}")

    print(f"\nCandidates ({len(res['rows'])} analysable, "
          f"median SD {res['median_sd_pct']:.6f}%):\n")
    print(f"  {'state':<44} {'mean%':>10} {'SD%':>10} {'|m|/SD':>8}  verdict")
    for r in res["rows"]:
        v = "CERTIFIED" if r["certified"] else "not certified"
        if r["ddof_sensitive"]:
            v += " (ddof-sensitive)"
        print(f"  {r['state']:<44} {r['mean_pct']:>10.5f} {r['sd_pct']:>10.6f} "
              f"{r['ratio']:>8.2f}  {v}")

    if res["refused"]:
        print(f"\n{len(res['refused'])} candidates produced NO effect "
              "(firewall refused a pair):")
        for x in res["refused"]:
            print(f"  {x['state']}: {list(x['seeds'])}")

    esc = [r["state"] for r in res["rows"] if r["escalate"]]
    unresolved = [p for p in pw if not p["resolved"]]
    for p in unresolved:
        for st in (p["a"], p["b"]):
            if st not in esc:
                esc.append(st)

    print(f"\nOutcome: ", end="")
    if not certified:
        print("(3) EFFECTIVELY NULL after certification — none of the 39 "
              "corrected-negative states survives.\n  Precommitted as a result, "
              "not a failure (§8).")
    elif len(certified) == 1:
        print(f"(1) ONE CERTIFIED CANDIDATE: {certified[0]}")
    elif all(p["resolved"] for p in pw):
        print(f"(1) A LEADER among {len(certified)} certified: "
              f"{res['rows'][0]['state']}")
    else:
        print(f"(2) {len(certified)} CERTIFIED, NOT ALL DISTINGUISHABLE — "
              "reported as a set, no leader named (§8).")

    if esc:
        print(f"\nEscalate to 40 restarts x the same 5 seeds ({len(esc)}):")
        for r in res["rows"]:
            if r["state"] in esc:
                print(f"  {r['state']}: {'; '.join(r['escalate_because']) or 'pairwise unresolved'}")

    print("\nCertified means distinguishable from solver variance at this "
          "effort, and nothing more (§9). D33 is re-measured at Stage B effort "
          "as a veto diagnostic and is not part of this threshold (§7).")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"contract": contract.digest, "escalated": args.escalated,
             "control_diagnostic": ctl, "candidates": res["rows"],
             "median_sd_pct": res["median_sd_pct"], "refused": res["refused"],
             "certified": certified, "pairwise": pw, "escalate": esc},
            indent=2, default=str))
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
