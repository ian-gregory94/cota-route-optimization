#!/usr/bin/env python3
"""Freeze the finished experiments into records a third party can verify.

Two artifacts, both regenerable and both content-addressed:

``outputs/canonical/exp1_final.json``
    Experiment 1 as one immutable record — every input hash, every setting,
    every headline number, every gate verdict, and the commit it was written
    at. Experiment 1 is closed; this is what "closed" means operationally.

``outputs/CANONICAL_RESULTS.json``
    Which five files matter among the hundreds. For each experiment: the
    canonical artifact, its status, the commit, the evaluator that produced it,
    whether it is certified, what it supersedes, the headline, and the known
    limitations.

The manifest exists because of a specific failure. The Experiment 2 evaluator
scored under Model A for three days while reporting Model B, so an artifact can
look entirely legitimate and contain the wrong model. Nothing is deleted —
superseded outputs stay on disk as the record of what was run — but a reader
must be able to tell in one place which ones are load-bearing.
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


def sha(p: Path) -> str | None:
    if not p.exists() or not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


#: Paths this script itself rewrites. A record that calls the tree dirty because
#: it is in the middle of writing itself reports on its own execution rather
#: than on the repository, and can never be made to say anything else --
#: committing the file changes it again on the next run.
SELF_OUTPUTS = ("outputs/canonical/exp1_final.json",
                "outputs/CANONICAL_RESULTS.json",
                "outputs/SUPERSEDED.md")


def commit() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                           capture_output=True, text=True, timeout=30)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                               capture_output=True, text=True, timeout=60)
        other = [ln for ln in dirty.stdout.splitlines()
                 if ln.strip() and not any(ln.endswith(s)
                                           for s in SELF_OUTPUTS)]
        return r.stdout.strip() + ("-dirty" if other else "")
    except Exception:
        return "UNKNOWN"


def _exp2b_headline() -> str:
    """Experiment 2B's headline, read from the certification artifact.

    Written rather than typed, because a manifest whose headline is a string
    literal drifts from the artifact it describes the moment either is
    regenerated — and this manifest exists precisely because an artifact that
    looks legitimate can contain a number nobody re-derived. If the
    certification is missing the manifest says so instead of quoting a value it
    cannot see.
    """
    p = OUT / "exp2b_certification.json"
    if not p.exists():
        return ("UNAVAILABLE — outputs/exp2b_certification.json is missing, so "
                "no 2B headline can be stated")
    c = json.loads(p.read_text())
    return (
        f"NULL. All 240 structurally feasible subsets solved at 60,000/2/32; "
        f"the leader `{c['set']}` re-solved at {c['effort']} under "
        f"{len(c['seeds'])} seeds scores {c['effect_pct']:+.4f}% unserved "
        f"against a {c['floor_pts']}-point floor — {c['floors']} floors. Not "
        f"one of the 227 multi-edit sets beats the best single, and at λ≥2 all "
        f"227 substitute. Best-set identity and cardinality monotonicity hold "
        f"at λ ∈ {{1, 2, 4}}. Gate 12 fired on its own: the effect moved "
        f"{c['gate_12_shift_pts']} points between discovery and certification "
        f"effort.")


def hashes(paths: dict[str, str]) -> dict[str, dict]:
    out = {}
    for label, rel in paths.items():
        p = ROOT / rel
        out[label] = {"path": rel, "sha256": sha(p),
                      "bytes": p.stat().st_size if p.exists() else None,
                      "present": p.exists()}
    return out


def load(rel: str):
    p = ROOT / rel
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def exp1_record() -> dict:
    base = load("outputs/exp1_baseline_modelB.json") or {}
    seed = load("outputs/seedcheck_modelB.json") or {}
    fleet = load("outputs/fleet_check.json") or load("outputs/model_diagnostics_modelB.json") or {}
    st = seed.get("stats", {})

    def m(k):
        v = st.get(k, {})
        return {"mean_pct": v.get("mean"), "sd_pct": v.get("sd"),
                "sigmas": v.get("sigmas")}

    return {
        "id": "exp1_final_v1",
        "status": "CLOSED — immutable. Reopen only for a falsification result, "
                  "not for tuning.",
        "question": "Holding route geometry fixed, how should COTA redistribute "
                    "service frequency inside its existing resource envelope?",
        "commit": commit(),
        "evaluator": {
            "waiting_model": "same_route (Model B)",
            "why": "Model A prices a ride leg at the chosen pattern's own "
                   "headway and so undervalues frequent trunk service; Model B "
                   "prices it on the combined frequency of every same-route "
                   "pattern that can carry the movement. Model A is the "
                   "one-pattern special case.",
            "verified": "harness.setup() passes common_lines explicitly; this "
                        "path is not the one that was mislabelled in "
                        "Experiment 2.",
        },
        "search": {
            "lambda": seed.get("lambda"),
            "effort": seed.get("effort"),
            "seeds": seed.get("seeds"),
            "n_paths": seed.get("n_paths"),
            "enumeration_tag": seed.get("enumeration_tag"),
            "candidate_set": seed.get("set"),
        },
        "resources": {
            "weekday_revenue_veh_hours_baseline": 2517.2,
            "weekday_revenue_veh_hours_optimized": 2516.5,
            "peak_vehicles_baseline": 197.0,
            "peak_vehicles_optimized": 197.0,
            "fleet_proxy_note": "block-derived; reconstructing COTA's blocks "
                                "from the feed gives 197 peak vehicles against "
                                "NTD's independently reported VOMS of 198, so "
                                "the proxy is not tuned to the answer.",
        },
        "headline": {
            "unserved_demand": m("unserved_change_pct"),
            "trips_served": m("served_change_pct"),
            "generalized_cost": m("gc_change_pct"),
            "cost_per_trip_served": m("gc_per_trip_change_pct"),
        },
        "the_claim": "The AGGREGATE effect, not any one headway plan. "
                     "Independent seeds at top effort on one shared candidate "
                     "set produce plans differing on 19.1% of route-periods by "
                     "a mean of 6.9 minutes while scoring within 0.064 points "
                     "of each other: the optimum is flat and no individual "
                     "route headway is identified (gate 7, D17).",
        "boundary_condition": "The certified frontier begins at λ=2. The "
                              "cost-favouring λ≤1 portion fails adequacy on "
                              "both models and is reported as uncertified "
                              "(gate 4, D15).",
        "plan_disagreement": seed.get("plan_disagreement"),
        "gates": {
            "1 fixpoint converges": "PASS on both models, on the tolerance "
                                    "test rather than the iteration cap",
            "4 adequacy of L4 plans": "PARTIAL — λ≥2 certified on both models, "
                                      "λ≤1 uncertified on both",
            "7 seed stability": "effect PASS (104σ Model B, 55σ Model A); "
                                "plan FAIL (19.7% / 26.0% route-period "
                                "disagreement against a 10% line)",
            "9 legible as a transit proposal": "PASS on the promoted geometry "
                                               "candidate (Experiment 2)",
            "10 same-route valuation": "PASS — residual 4.301% → −3.0e-18%",
            "11 Model B discovery adequacy": "PASS — Case C closed by a "
                                             "route-level search scenario",
            "11 follow-up does it change the answer": "PASS — max gap 0.057% "
                                                      "gc against a 0.25% line",
            "fleet": "197.0 vs 197.0 peak vehicles, no additional buses",
        },
        "inputs": hashes({
            "assumptions": "config/assumptions.yaml",
            "cost_weights": "config/cost_weights.yaml",
            "constraints": "config/constraints.yaml",
            "sources": "config/sources.yaml",
            "frozen_baseline": "outputs/exp1_baseline_modelB.json",
            "seed_check": "outputs/seedcheck_modelB.json",
            "certified_frontier": "outputs/certify_frontier_modelB.csv",
            "fixpoint_frontier": "outputs/fixpoint_frontier_modelB.csv",
        }),
        "frontier": base.get("frontier"),
        "quoting_rule": base.get("quoting_rule"),
        "identification_rule": base.get("identification_rule"),
    }


def manifest() -> dict:
    return {
        "generated_commit": commit(),
        "why_this_exists":
            "The Experiment 2 evaluator scored every plan under Model A for "
            "three days while reporting Model B, so an artifact can look "
            "entirely legitimate and contain the wrong model. Nothing here is "
            "deleted — superseded outputs are the record of what was run — but "
            "a reader must be able to tell which files are load-bearing "
            "without reconstructing the history.",
        "how_to_check_an_artifact":
            "Open its experiment.json and read `evaluator`. "
            "`common_lines: same_route` with `source: explicit` is Model B, "
            "declared. `null` means the run predates provenance recording and "
            "the model must be established another way — for Experiment 2 that "
            "means checking whether the cell key carries |same_route|.",
        "experiments": {
            "exp1": {
                "title": "Frequency redistribution inside the existing "
                         "geometry and envelope",
                "status": "CLOSED, certified λ≥2",
                "canonical": ["outputs/canonical/exp1_final.json",
                              "outputs/exp1_baseline_modelB.json",
                              "outputs/seedcheck_modelB.json",
                              "outputs/certify_frontier_modelB.csv"],
                "evaluator": "same_route (Model B), via harness.setup()",
                "certified": True,
                "headline": "−6.65% ± 0.06 unserved demand, +3.30% ± 0.03 "
                            "trips served, +0.88% ± 0.04 generalized cost, "
                            "−2.34% ± 0.01 cost per trip served, at 2,516.5 of "
                            "2,517.2 vehicle-hours and 197.0 of 197.0 peak "
                            "vehicles",
                "superseded": ["outputs/model_A/*",
                               "outputs/fixpoint_frontier.csv",
                               "outputs/certify_frontier.csv",
                               "outputs/seedcheck.json"],
                "superseded_why": "Model A — kept as the control and as the "
                                  "record of the pre-correction result",
                "limitations": ["λ≤1 uncertified on both models",
                                "no individual route headway is identified",
                                "commute-only LODES demand"],
            },
            "exp2": {
                "title": "Route geometry — twelve splice candidates, "
                         "evaluated individually",
                "status": "CLOSED — no candidate promoted",
                "canonical": ["outputs/exp2_promotion.json",
                              "outputs/exp2_candidate_classes.json",
                              "outputs/exp2_ladder_measured.csv",
                              "outputs/exp2_treatments.jsonl",
                              "outputs/exp2_modelA_vs_modelB_singles.csv",
                              "outputs/exp2_summary.json"],
                "evaluator": "same_route (Model B) — cells carrying "
                             "|same_route| in the key only",
                "certified": False,
                "headline": "NO supportable geometry claim. At the effort "
                            "Experiment 1 is certified at, six of twelve "
                            "candidates do measurable harm and none does "
                            "measurable good; the two leaders land inside the "
                            "0.287-point floor at +0.060% and +0.160%. The "
                            "−0.5% through-routing claim was withdrawn "
                            "2026-08-30 (D24): the unedited network was the "
                            "under-optimized one at ranking effort.",
                "superseded": ["every exp2_eval cell whose key has NO pricing "
                               "segment", "outputs/exp2_eval_modelB.log",
                               "outputs/exp2_recheck.log",
                               "outputs/exp2_ladder.csv"],
                "superseded_why": "produced by the mislabelled evaluator — "
                                  "Model A numbers under a Model B label",
                "limitations": ["every 60,000/2/32 number is discovery-stage "
                                "under gate 12 and orders candidates rather "
                                "than concluding anything",
                                "only splices were ever evaluated",
                                "the representation-stability observation is "
                                "exploratory and uncontaminated confirmation "
                                "is still owed"],
                "closeout": "EXPERIMENT2_CLOSEOUT.md",
            },
            "exp2b": {
                "title": "Joint search over geometry edit subsets — all 240 "
                         "structurally feasible combinations",
                "status": "CLOSED — certified NULL",
                "canonical": ["outputs/exp2b_certification.json",
                              "outputs/exp2b_stageA.csv",
                              "outputs/exp2b_stageB.csv",
                              "outputs/exp2b_stageA_gaps.json",
                              "outputs/exp2b_subsets.shard*.jsonl"],
                "evaluator": "same_route (Model B), passed explicitly — "
                             "verified by reading the call site in "
                             "exp2b_subsets.py and by the `evaluator` block in "
                             "each stage's experiment.json, and this is one of "
                             "the two pipelines whose disagreement exposed the "
                             "defect",
                "certified": True,
                "headline": _exp2b_headline(),
                "superseded": [],
                "limitations": [
                    "every 60,000/2/32 number is discovery-stage under gate 12 "
                    "— it orders sets, it does not size effects",
                    "λ=1 and λ=4 ran one seed each, so no noise floor exists "
                    "at those weights and no headline may be drawn from them",
                    "the universal-substitution claim is λ≥2; at λ=1 the sign "
                    "inverts (D25)",
                    "only splices were ever in the candidate space",
                    "interaction terms at λ≠2 exist only for sets all of whose "
                    "members were promoted"],
                "closeout": "EXPERIMENT2_CLOSEOUT.md",
            },
            "exp3": {
                "title": "Route mutation — search over network states under a "
                         "committed treatment contract",
                "status": "NOT STARTED — contract committed, gates committed",
                "canonical": [],
                "evaluator": "same_route (Model B), required by gate 3-6 and "
                             "asserted by the state validator rather than "
                             "requested and hoped for",
                "certified": False,
                "headline": "n/a — nothing scored yet. The conservative "
                            "incumbent Experiment 3 must beat is Experiment "
                            "1's certified frequency plan on COTA's UNCHANGED "
                            "geometry, because Experiment 2B certified the "
                            "null and promoted no geometry edit.",
                "superseded": [],
                "contract": "EXPERIMENT3_CONTRACT.md",
                "limitations": [
                    "the stop-service penalty is not measurable from this "
                    "feed, so no mutation may claim a runtime benefit from "
                    "serving fewer stops on the same alignment; see "
                    "outputs/exp3_stopprice_diagnosis.json",
                    "stop consolidation is a DEFERRED question, not this "
                    "experiment — its gates are marked conditional in "
                    "ACCEPTANCE.md",
                    "the search is heuristic and must recover the known "
                    "optimum on the exhaustively enumerated 2B space before "
                    "it is trusted on the mutation space"],
            },
        },
    }


def main() -> int:
    CANON.mkdir(parents=True, exist_ok=True)
    r = exp1_record()
    (CANON / "exp1_final.json").write_text(json.dumps(r, indent=2))
    m = manifest()
    (OUT / "CANONICAL_RESULTS.json").write_text(json.dumps(m, indent=2))

    print("=" * 84)
    print("FROZEN RECORDS")
    print("=" * 84)
    print(f"  commit {r['commit']}")
    h = r["headline"]
    for k, v in h.items():
        if v.get("mean_pct") is not None:
            print(f"  {k:26s} {v['mean_pct']:+7.3f}% ± {v['sd_pct']:.3f}  "
                  f"({v['sigmas']:.0f}σ)")
    missing = [k for k, v in r["inputs"].items() if not v["present"]]
    if missing:
        print(f"\n  MISSING INPUTS: {', '.join(missing)}")
    print(f"\n  {len(m['experiments'])} experiments in the manifest")
    for k, v in m["experiments"].items():
        print(f"    {k:6s} {v['status']}")
    # A human-readable index of what is no longer current. The manifest is the
    # machine-readable record; this is what someone reads when they open an
    # outputs directory of several hundred files and need to know which of
    # them will mislead them. Nothing is deleted -- a superseded artifact is
    # the record of what was actually run, and the whole difficulty is that it
    # looks entirely legitimate from the inside.
    lines = ["# Superseded outputs", "",
             "Generated by `scripts/freeze_records.py`. **Nothing here is "
             "deleted.** These files are the record of what was actually run "
             "and several of them look completely legitimate — that is exactly "
             "the problem they document.", ""]
    for name, e in m["experiments"].items():
        sup = e.get("superseded") or []
        if not sup:
            continue
        lines += [f"## {name} — {e['title']}", "",
                  f"*{e.get('superseded_why', 'superseded')}*", ""]
        for rel in sup:
            lines.append(f"- `{rel}`")
        lines += ["", f"**Current instead:** "
                  + ", ".join(f"`{c}`" for c in e.get("canonical", [])), ""]
    lines += ["## How to tell, for any artifact", "",
              m["how_to_check_an_artifact"], ""]
    (OUT / "SUPERSEDED.md").write_text("\n".join(lines))

    print(f"\nartifacts: {CANON / 'exp1_final.json'}")
    print(f"           {OUT / 'CANONICAL_RESULTS.json'}")
    print(f"           {OUT / 'SUPERSEDED.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
