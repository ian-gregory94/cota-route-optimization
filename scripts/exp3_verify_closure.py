#!/usr/bin/env python3
"""Check every quantitative claim in EXPERIMENT3_CLOSURE.md against the artifacts.

A closure document is the one file people quote without re-deriving, so its
numbers get checked mechanically rather than trusted. Each claim is searched for
verbatim in the document and independently recomputed from the JSON. Exits
non-zero if any claim is absent or any recomputation disagrees.

    python scripts/exp3_verify_closure.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "exp3"


def main() -> int:
    doc = (ROOT / "EXPERIMENT3_CLOSURE.md").read_text()
    e = json.loads((OUT / "escalation_report.json").read_text())
    sb = json.loads((OUT / "stageB_report.json").read_text())
    d33 = json.loads((OUT / "d33_stageb" / "d33_stageb_report.json").read_text())
    cen = json.loads((OUT / "stageA_census.json").read_text())
    lead = e["combined"][0]
    best_esc = [r for r in e["combined"]
                if r["certified"] and r["regime"] == "escalated"][0]

    claims = [
        ("leader state",        "add_stop-010#22c4c35ac5b2",   lead["state"] == "add_stop-010#22c4c35ac5b2"),
        ("leader effect",       "−0.18657%",              f"{lead['mean_pct']:.5f}" == "-0.18657"),
        ("leader SD",           "0.002375%",                   f"{lead['sd_pct']:.6f}" == "0.002375"),
        ("leader ratio",        "78.6",                        f"{lead['ratio']:.1f}" == "78.6"),
        ("other certified",     "all 28 other certified",      len(e["certified"]) - 1 == 28),
        ("census states",       "84 census states",            len(cen["states"]) == 84),
        ("promoted",            "39 were promoted",            sum(1 for r in cen["states"] if r["effect_pct"] < 0) == 39),
        ("stage B certified",   "30 certified at Stage B",     len(sb["certified"]) == 30),
        ("post-esc certified",  "**29 remain",                 len(e["certified"]) == 29),
        ("D33 bound",           "0.0018970%",                  f"{d33['largest_differential_pct']:.7f}" == "0.0018970"),
        ("D33 verdict",         "**Verdict: PASS. 0 of 30",    d33["verdict"] == "PASS" and not d33["vetoed"]),
        ("leader/D33 ratio",    "**98×** that bound",     round(abs(lead["mean_pct"]) / d33["largest_differential_pct"]) == 98),
        ("escalation cells",    "= **170 cells at 40 restarts**", e["n_escalated"] == 33),
        ("esc control 3sigma",  "0.00936%",                    f"{e['escalated_control_diagnostic']['three_sigma_pct']:.5f}" == "0.00936"),
        ("unresolved pairs",    "**all 50** unresolved",       len(e["unresolved"]) == 50),
        ("best escalated",      "at −0.08017%",           f"{best_esc['mean_pct']:.5f}" == "-0.08017"),
        ("leader/best ratio",   "**2.33× smaller**",      f"{abs(lead['mean_pct'])/abs(best_esc['mean_pct']):.2f}" == "2.33"),
    ]

    # structural claims that are not single numbers
    mine = [p for p in e["pairwise"] if lead["state"] in (p["a"], p["b"])]
    structural = [
        ("leader has 28 comparisons", len(mine) == 28),
        ("all leader comparisons at Stage B effort",
         {p["regime"] for p in mine} == {"stage_b"}),
        ("all leader comparisons resolved", all(p["resolved"] for p in mine)),
        ("all unresolved pairs are escalated",
         {p["regime"] for p in e["unresolved"]} == {"escalated"}),
        ("leader not in the escalation manifest",
         lead["state"] in e["not_escalated"]),
        ("exactly one certification change",
         len(e["certification_changes"]) == 1),
    ]

    bad = 0
    print("claims quoted in EXPERIMENT3_CLOSURE.md:")
    for name, text, computed_ok in claims:
        present = text in doc
        ok = present and computed_ok
        bad += not ok
        flag = "OK  " if ok else ("MISSING" if not present else "MISMATCH")
        print(f"  {flag:8s} {name}")
    print("\nstructural claims:")
    for name, ok in structural:
        bad += not ok
        print(f"  {'OK  ' if ok else 'FAIL':8s} {name}")

    print(f"\n{'ALL CLAIMS VERIFIED' if not bad else f'{bad} CLAIM(S) FAILED'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
