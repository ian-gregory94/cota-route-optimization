"""Experiment 5 — frontier validation, traversal, marginals and transitions.

The §18 half that does not depend on which network Experiment 4 selects. It
operates on a generic result record, so the machinery can be proved on a toy
network now and bound to the real one later without changing.

THE FOUR THINGS THIS FILE IS FOR
--------------------------------
1. **Monotonicity (E5-5).** Resource limits are CAPS. Loosening a cap cannot
   shrink the feasible set, so a looser cell cannot have a worse optimum. When
   one does, that is a search or certification failure and is treated as one --
   a non-monotone frontier is never published as a transit finding.

2. **Traversal invariance (E5-7).** Adjacent cells make good warm starts, which
   is exactly what makes the frontier vulnerable to path dependence. Ascending
   and descending sweeps must agree on the certified objective. If the PLANS
   differ while the SCORES agree, the solution set is flat and is reported that
   way rather than one schedule being crowned.

3. **Marginals (§12).** What each increment of allowed resource actually
   bought, separated from what the optimum chose to spend.

4. **Structural response (§14).** Which route-periods switched on, off, or
   changed headway, as a matrix a heatmap can consume.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .firewall.core import digest

#: A headway change smaller than this is not a "material" service change. One
#: ladder step is the smallest change the representation can express, so the
#: threshold is a fraction of a step rather than a number chosen for taste.
MATERIAL_HEADWAY_REL = 0.05

#: Objective agreement tolerance between traversal orders. Relative, because
#: the objective is ~3.6e6 and an absolute epsilon would be meaningless at that
#: scale.
TRAVERSAL_TOL_REL = 1e-9

#: How much worse a looser cell may be before monotonicity is called violated.
#: Not a tolerance for real regressions -- it exists only to absorb float noise
#: in a comparison of two independently computed sums.
MONOTONE_TOL_REL = 1e-9


@dataclass(frozen=True)
class CellResult:
    """One certified resource cell. Generic: no Experiment 4 types appear.

    `objective` and `fitness` are EXACT-stage values. Experiment 5 inherits
    Experiment 4's rule that proposal scores decide nothing, and inherits its
    certification language too: if the certificate is block-local, `guarantee`
    says so and nothing here relabels it an exact optimum.
    """

    cell_id: str
    stage: str
    hours_pct: float
    fleet_pct: float
    objective: float
    fitness: Mapping[str, float]
    usage: Mapping[str, Any]
    plan: Mapping[str, float]          # "route|period" -> headway (OFF = inf)
    certification: Mapping[str, Any] = field(default_factory=dict)
    network_digest: str = ""
    evaluator_digest: str = ""
    envelope_digest: str = ""
    seed: int = 0
    traversal: str = ""

    @property
    def guarantee(self) -> str:
        return str(self.certification.get("guarantee", "UNSTATED"))

    def payload(self) -> dict:
        return {"cell_id": self.cell_id, "stage": self.stage,
                "hours_pct": self.hours_pct, "fleet_pct": self.fleet_pct,
                "objective_EXACT": self.objective,
                "fitness_EXACT": dict(self.fitness),
                "usage": dict(self.usage),
                "certification": dict(self.certification),
                "guarantee": self.guarantee,
                "network_digest": self.network_digest,
                "evaluator_digest": self.evaluator_digest,
                "envelope_digest": self.envelope_digest,
                "seed": self.seed, "traversal": self.traversal,
                "n_route_periods": len(self.plan),
                "plan_digest": digest({k: (None if _off(v) else round(v, 9))
                                       for k, v in sorted(self.plan.items())})}


def _off(h: float) -> bool:
    return (not math.isfinite(h)) or h >= 1e5


# ---------------------------------------------------------------------------
# E5-1 / E5-2 / E5-3 — the treatment really is the envelope and nothing else
# ---------------------------------------------------------------------------

def treatment_isolation(cells: Sequence[CellResult]) -> tuple[bool, list[str]]:
    """Only the resource caps may differ between cells."""
    bad: list[str] = []
    if not cells:
        return True, []
    nets = {c.network_digest for c in cells}
    evals = {c.evaluator_digest for c in cells}
    seeds = {c.seed for c in cells}
    if len(nets) > 1:
        bad.append(f"E5-1 network topology differs across cells: {sorted(nets)}")
    if len(evals) > 1:
        bad.append(f"E5-2 evaluator/model differs across cells: {sorted(evals)}")
    if len(seeds) > 1:
        bad.append(f"E5-3 seed differs across cells: {sorted(seeds)} -- the "
                   f"treatment is the envelope, so the seed may not move with it")
    envs = {c.envelope_digest for c in cells}
    if len(envs) != len({c.cell_id for c in cells}):
        bad.append("E5-3 two cells share an envelope digest, so they are not "
                   "distinct treatments")
    return (not bad), bad


# ---------------------------------------------------------------------------
# E5-5 — monotonicity
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MonotonicityReport:
    ok: bool
    violations: list[dict]
    comparisons: int

    def payload(self) -> dict:
        return {"invariant": "E5-5", "ok": self.ok,
                "comparisons": self.comparisons,
                "violations": self.violations,
                "rule": ("resource limits are CAPS, so a cell whose caps "
                         "dominate another's cannot have a materially worse "
                         "certified optimum under the same minimized "
                         "objective"),
                "on_failure": ("investigate search/certification first; a "
                               "non-monotone frontier is not a transit result "
                               "and must not be published as one")}


def monotone(cells: Sequence[CellResult],
             tol_rel: float = MONOTONE_TOL_REL) -> MonotonicityReport:
    """A looser pair of caps must not certify worse. Lower objective is better."""
    viol: list[dict] = []
    n = 0
    for a in cells:
        for b in cells:
            if a.cell_id == b.cell_id:
                continue
            # a dominates b in BOTH resources
            if a.hours_pct >= b.hours_pct and a.fleet_pct >= b.fleet_pct:
                n += 1
                slack = abs(b.objective) * tol_rel
                if a.objective > b.objective + slack:
                    viol.append({
                        "looser": a.cell_id, "tighter": b.cell_id,
                        "looser_objective": a.objective,
                        "tighter_objective": b.objective,
                        "regression": a.objective - b.objective,
                        "regression_rel": (a.objective - b.objective)
                                          / abs(b.objective),
                        "note": (f"{a.cell_id} has caps at least {b.cell_id}'s "
                                 f"in both resources yet certifies worse; the "
                                 f"tighter cell's own plan is feasible here, so "
                                 f"the search failed to find at least it")})
    return MonotonicityReport(not viol, viol, n)


# ---------------------------------------------------------------------------
# E5-4 — feasibility nesting, checked on realised usage
# ---------------------------------------------------------------------------

def feasible_under(result: CellResult, envelope_payload: Mapping[str, Any]
                   ) -> tuple[bool, list[str]]:
    """Would this cell's realised plan satisfy another cell's caps?

    Uses USED resources, not caps: the question is whether the plan a tighter
    envelope produced would still be admissible under a looser one, which is
    what makes the frontier's nesting checkable without re-solving.
    """
    bad: list[str] = []
    u = result.usage
    cap_h = float(envelope_payload["revenue_veh_hours_cap"])
    if float(u["hours_used"]) > cap_h + 1e-6:
        bad.append(f"{result.cell_id} uses {u['hours_used']:.6f} vh, above "
                   f"{cap_h:.6f}")
    caps = envelope_payload["peak_by_period_cap"]
    for p, used in sorted(dict(u["peak_used_by_period"]).items()):
        if p in caps and float(used) > float(caps[p]) + 1e-6:
            bad.append(f"{result.cell_id} uses {used:.6f} peak in {p}, above "
                       f"{float(caps[p]):.6f}")
    return (not bad), bad


# ---------------------------------------------------------------------------
# E5-7 — traversal invariance
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TraversalReport:
    ok: bool
    rows: list[dict]

    def payload(self) -> dict:
        flat = [r["cell_id"] for r in self.rows if r.get("plans_differ")
                and r.get("objectives_agree")]
        return {"invariant": "E5-7", "ok": self.ok, "cells": self.rows,
                "flat_or_non_identified": flat,
                "rule": ("ascending and descending sweeps must agree on the "
                         "certified objective within tolerance"),
                "plan_instability_note": (
                    "where objectives agree and plans differ, the solution set "
                    "is flat: several schedules reach the same certified value "
                    "and none of them is 'the' optimum. That is reported as "
                    "non-identification, not as objective instability")}


def traversal_invariant(ascending: Sequence[CellResult],
                        descending: Sequence[CellResult],
                        tol_rel: float = TRAVERSAL_TOL_REL) -> TraversalReport:
    up = {c.cell_id: c for c in ascending}
    down = {c.cell_id: c for c in descending}
    rows: list[dict] = []
    ok = True
    for cid in sorted(set(up) | set(down)):
        a, b = up.get(cid), down.get(cid)
        if a is None or b is None:
            rows.append({"cell_id": cid, "present_ascending": a is not None,
                         "present_descending": b is not None,
                         "objectives_agree": False})
            ok = False
            continue
        d = abs(a.objective - b.objective)
        rel = d / max(abs(a.objective), 1e-12)
        agree = rel <= tol_rel
        pa = a.payload()["plan_digest"]
        pb = b.payload()["plan_digest"]
        rows.append({"cell_id": cid,
                     "objective_ascending": a.objective,
                     "objective_descending": b.objective,
                     "abs_diff": d, "rel_diff": rel,
                     "objectives_agree": agree,
                     "plans_differ": pa != pb,
                     "plan_digest_ascending": pa,
                     "plan_digest_descending": pb})
        ok &= agree
    return TraversalReport(ok, rows)


# ---------------------------------------------------------------------------
# §12 — marginal resource analysis
# ---------------------------------------------------------------------------

def marginals(cells: Sequence[CellResult],
              fields: Sequence[str] = ("generalized_cost", "unserved_demand",
                                       "served_demand")) -> list[dict]:
    """Finite differences between adjacent preregistered levels.

    Reports change per *allowed* additional resource and, separately, how much
    additional resource was actually consumed -- §12's distinction, kept in the
    schema so a reader cannot conflate them by accident.
    """
    ordered = sorted(cells, key=lambda c: (c.hours_pct, c.fleet_pct))
    out: list[dict] = []
    for lo, hi in zip(ordered, ordered[1:]):
        d_obj = hi.objective - lo.objective
        allowed_vh = (float(hi.usage["hours_cap"])
                      - float(lo.usage["hours_cap"]))
        used_vh = (float(hi.usage["hours_used"])
                   - float(lo.usage["hours_used"]))
        peak_cap_hi = max(dict(hi.usage["peak_cap_by_period"]).values(),
                          default=0.0)
        peak_cap_lo = max(dict(lo.usage["peak_cap_by_period"]).values(),
                          default=0.0)
        allowed_peak = peak_cap_hi - peak_cap_lo
        used_peak = (max(dict(hi.usage["peak_used_by_period"]).values(),
                         default=0.0)
                     - max(dict(lo.usage["peak_used_by_period"]).values(),
                           default=0.0))
        row = {"from": lo.cell_id, "to": hi.cell_id,
               "d_objective": d_obj,
               "d_objective_rel": d_obj / abs(lo.objective) if lo.objective else None,
               "allowed_additional_veh_hours": allowed_vh,
               "actually_used_additional_veh_hours": used_vh,
               "allowed_additional_peak": allowed_peak,
               "actually_used_additional_peak": used_peak,
               "unused_share_of_new_hours": (
                   None if abs(allowed_vh) < 1e-9
                   else 1.0 - used_vh / allowed_vh),
               "hours_binding_at_to": bool(hi.usage["hours_binding"]),
               "peak_binding_at_to": bool(hi.usage["any_peak_binding"])}
        for f in fields:
            a, b = float(lo.fitness.get(f, float("nan"))), \
                float(hi.fitness.get(f, float("nan")))
            row[f"d_{f}"] = b - a
            row[f"d_{f}_per_allowed_veh_hour"] = (
                (b - a) / allowed_vh if abs(allowed_vh) > 1e-9 else None)
            row[f"d_{f}_per_allowed_peak_vehicle"] = (
                (b - a) / allowed_peak if abs(allowed_peak) > 1e-9 else None)
        out.append(row)
    return out


def diminishing_returns(marg: Sequence[Mapping[str, Any]],
                        field_name: str = "d_generalized_cost_per_allowed_veh_hour",
                        flat_rel: float = 0.05) -> dict:
    """Describe where marginal gains shrink. Deliberately does NOT find a knee.

    §13 forbids interpolating a saturation point that was never evaluated, so
    this reports the measured per-interval marginals and names the FIRST TESTED
    interval whose gain falls below `flat_rel` of the largest observed gain.
    That is a statement about tested points, not a fitted curve.
    """
    vals = [(m["from"], m["to"], m.get(field_name)) for m in marg]
    live = [(a, b, v) for a, b, v in vals if v is not None and math.isfinite(v)]
    if not live:
        return {"measured": vals, "first_flat_interval": None,
                "note": "no finite marginals to describe"}
    biggest = max(abs(v) for _, _, v in live)
    first_flat = None
    for a, b, v in live:
        if biggest > 0 and abs(v) < flat_rel * biggest:
            first_flat = f"{a}->{b}"
            break
    return {"field": field_name,
            "measured": [{"interval": f"{a}->{b}", "value": v}
                         for a, b, v in vals],
            "largest_absolute_marginal": biggest,
            "flat_threshold_rel": flat_rel,
            "first_flat_interval": first_flat,
            "interpretation_rule": (
                "this names the first TESTED interval whose marginal gain is "
                "below the threshold. It is not an interpolated knee and no "
                "saturation point between tested levels is claimed")}


# ---------------------------------------------------------------------------
# §14 — structural response
# ---------------------------------------------------------------------------

def transitions(lo: CellResult, hi: CellResult,
                material_rel: float = MATERIAL_HEADWAY_REL) -> dict:
    """How the network spends -- or gives up -- marginal resource."""
    keys = sorted(set(lo.plan) | set(hi.plan))
    on, off, faster, slower, unchanged, absent = [], [], [], [], [], []
    rows = []
    for k in keys:
        a = lo.plan.get(k)
        b = hi.plan.get(k)
        if a is None or b is None:
            absent.append(k)
            continue
        ao, bo = _off(a), _off(b)
        if ao and not bo:
            on.append(k)
            kind = "switched_on"
        elif bo and not ao:
            off.append(k)
            kind = "switched_off"
        elif ao and bo:
            unchanged.append(k)
            kind = "off_both"
        else:
            rel = (a - b) / a if a else 0.0
            if rel > material_rel:
                faster.append(k)
                kind = "headway_decreased"       # shorter headway = more service
            elif rel < -material_rel:
                slower.append(k)
                kind = "headway_increased"
            else:
                unchanged.append(k)
                kind = "unchanged"
        rows.append({"route_period": k,
                     "headway_from": None if a is None or _off(a) else a,
                     "headway_to": None if b is None or _off(b) else b,
                     "off_from": bool(a is not None and _off(a)),
                     "off_to": bool(b is not None and _off(b)),
                     "kind": kind})
    return {"from": lo.cell_id, "to": hi.cell_id,
            "material_headway_rel": material_rel,
            "n_switched_on": len(on), "n_switched_off": len(off),
            "n_headway_decreased": len(faster),
            "n_headway_increased": len(slower),
            "n_unchanged": len(unchanged),
            "n_absent_from_one_plan": len(absent),
            "switched_on": on, "switched_off": off,
            "headway_decreased": faster, "headway_increased": slower,
            "rows": rows,
            "note": ("descriptive only. §14: no political or desirability "
                     "reading belongs here")}


def transition_matrix(cells: Sequence[CellResult]) -> dict:
    """Resource level x route-period, for a heatmap. Service, not headway.

    Emits 1/headway so that "more service" is a larger number and OFF is zero,
    which is what a heatmap needs; the raw headways stay in `plans`.
    """
    ordered = sorted(cells, key=lambda c: (c.hours_pct, c.fleet_pct))
    keys = sorted({k for c in ordered for k in c.plan})
    return {"cell_ids": [c.cell_id for c in ordered],
            "route_periods": keys,
            "service_per_hour": [[0.0 if k not in c.plan or _off(c.plan[k])
                                  else 60.0 / c.plan[k] for k in keys]
                                 for c in ordered],
            "plans": {c.cell_id: {k: (None if k not in c.plan
                                      or _off(c.plan[k]) else c.plan[k])
                                  for k in keys} for c in ordered},
            "units": "vehicles per hour; 0 means OFF"}
