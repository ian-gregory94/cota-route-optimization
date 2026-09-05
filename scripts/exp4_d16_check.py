"""D16, executed against its own literal criterion.

EXPERIMENT4_DESIGN.md section 9 item 16, verbatim:

    An `ExperimentContract` for Experiment 4 exists, with every declared
    treatment difference carrying a written justification, and refuses at
    construction if any is missing.

Three claims, not one. The readiness script tested the first and reported MET,
which is the same shape of error as D21 passing on half its own text. Each is
executed here:

  16a  an ExperimentContract for exp4 exists AND is reachable from `firewall/`
       (a contract in a module that says "not in force" is a design artifact)
  16b  EVERY declared treatment difference carries a non-empty justification,
       checked entry by entry against the whitelist, not by trusting the
       constructor
  16c  construction REFUSES when a justification is missing -- demonstrated by
       constructing one and catching the error, because a guard nobody has
       fired is a guard nobody has tested

Plus the precondition the draft set for itself, which is not part of item 16
but without which promotion would be premature:

  16-pre  Gen1 is frozen AND the Gen1->Gen2 bridge suite has run with a
          non-BROKEN verdict

D16 is NOT closed by D21b closing. It is closed by these four checks passing.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import cota_opt.firewall as fw                                    # noqa: E402
from cota_opt.firewall.contract import (ContractError,            # noqa: E402
                                        ExperimentContract)

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")


print("D16 -- Experiment 4 ExperimentContract, against its own criterion\n")

# --- 16-pre ---------------------------------------------------------------
freeze = ROOT / "outputs" / "GEN1_FREEZE_MANIFEST.json"
gen1_frozen = freeze.exists() and (ROOT / "GEN1_FREEZE.md").exists()
bridge_path = ROOT / "outputs" / "exp4" / "gen_bridge.json"
bridge = json.loads(bridge_path.read_text()) if bridge_path.exists() else {}
verdict = bridge.get("verdict", "<not run>")
check("16-pre gen1 frozen", gen1_frozen,
      f"GEN1_FREEZE.md + manifest present={gen1_frozen}")
check("16-pre bridge suite run", verdict in ("CONFIRMED", "SUPERSEDED"),
      f"gen_bridge.json verdict={verdict}")

# --- 16a ------------------------------------------------------------------
in_force = {n: getattr(fw, n) for n in dir(fw)
            if isinstance(getattr(fw, n, None), ExperimentContract)
            and getattr(fw, n).experiment == "exp4"}
check("16a exp4 contract exists and is exported from firewall/",
      bool(in_force),
      f"{sorted(in_force) or 'none'}")

draft_src = (ROOT / "src/cota_opt/firewall/exp4_draft.py").read_text()
promoted_src = (ROOT / "src/cota_opt/firewall/exp4.py").read_text()
check("16a in-force module does not disclaim itself",
      "not yet in force" not in promoted_src and "not in force" not in
      promoted_src,
      "exp4.py carries no 'not in force' disclaimer; exp4_draft.py still "
      f"does ({'not yet in force' in draft_src}) and is not exported")

# --- 16b ------------------------------------------------------------------
for name, c in sorted(in_force.items()):
    missing = sorted(d for d in c.allowed_treatment_differences
                     if not c.justifications.get(d, "").strip())
    check(f"16b {name}: every declared difference justified",
          not missing,
          f"{len(c.allowed_treatment_differences)} declared, "
          f"{len(missing)} unjustified"
          + (f": {missing}" if missing else ""))
    # A justification that is a placeholder is not a written reason.
    thin = sorted(d for d in c.allowed_treatment_differences
                  if len(c.justifications.get(d, "").split()) < 4)
    check(f"16b {name}: no placeholder justifications", not thin,
          f"shortest reason is {min((len(c.justifications[d].split()) for d in c.allowed_treatment_differences), default=0)} words"
          + (f"; too thin: {thin}" if thin else ""))

# --- 16c ------------------------------------------------------------------
# Fire the guard. Take a real in-force contract, remove one justification, and
# require ContractError. Done for EVERY declared dimension in turn, so the
# guard is shown to cover the whole whitelist rather than one lucky entry.
import dataclasses                                                # noqa: E402

for name, c in sorted(in_force.items()):
    fired: list[str] = []
    silent: list[str] = []
    for d in sorted(c.allowed_treatment_differences):
        j = {k: v for k, v in c.justifications.items() if k != d}
        try:
            dataclasses.replace(c, justifications=j)
        except ContractError:
            fired.append(d)
        else:
            silent.append(d)
    check(f"16c {name}: refuses at construction for every dimension",
          not silent,
          f"{len(fired)}/{len(c.allowed_treatment_differences)} dimensions "
          f"raise ContractError when their justification is removed"
          + (f"; SILENT: {silent}" if silent else ""))
    # And an empty-string justification is not a justification either.
    try:
        dataclasses.replace(
            c, justifications={**c.justifications,
                               sorted(c.allowed_treatment_differences)[0]: "  "})
    except ContractError:
        check(f"16c {name}: whitespace is not a justification", True,
              "a whitespace-only reason raises ContractError")
    else:
        check(f"16c {name}: whitespace is not a justification", False,
              "a whitespace-only reason was ACCEPTED")

# --- verdict --------------------------------------------------------------
npass = sum(1 for _, ok, _ in results if ok)
allok = npass == len(results)
print(f"\n  {npass}/{len(results)} checks pass")
print(f"  D16: {'MET' if allok else 'OPEN'}")

out = ROOT / "outputs" / "exp4" / "d16_check.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({
    "item": "D16",
    "criterion": ("An ExperimentContract for Experiment 4 exists, with every "
                  "declared treatment difference carrying a written "
                  "justification, and refuses at construction if any is "
                  "missing."),
    "checks": [{"name": n, "pass": ok, "detail": d} for n, ok, d in results],
    "passed": npass, "total": len(results),
    "contracts": {n: {"digest": c.digest, "stage": c.stage,
                      "version": c.version,
                      "declared": sorted(c.allowed_treatment_differences)}
                  for n, c in sorted(in_force.items())},
    "bridge_verdict": verdict,
    "verdict": "MET" if allok else "OPEN",
}, indent=2) + "\n")
print(f"  wrote {out.relative_to(ROOT)}")
sys.exit(0 if allok else 1)
