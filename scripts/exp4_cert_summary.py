#!/usr/bin/env python3
"""Read-only summary of the certification stage so far.

Reads outputs/exp4/run/certified/*.json and prints counts, the objective range,
and convergence health. It DECIDES NOTHING: the ordering that matters is
`exp4_inference.rank_certified`, applied to the complete set under the frozen
tie-break, and a sort printed here is a progress readout, not a ranking. It
says so on every run for the same reason `ProposalScore` refuses comparison --
a number that looks like a leaderboard gets cited as one.

Touches no instrument and imports nothing from cota_opt, so it is safe to run
against a batch in flight (OPERATIONS 24).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CERT = ROOT / "outputs/exp4/run/certified"
N_PROMOTED = 200


def main() -> int:
    if not CERT.exists():
        print("no certified/ directory yet")
        return 1

    ok, err = [], []
    for f in sorted(CERT.glob("*.json")):
        try:
            r = json.loads(f.read_text())
        except json.JSONDecodeError:
            err.append({"state_key": f.name, "error": "unreadable/partial"})
            continue
        (err if "error" in r else ok).append(r)

    done = len(ok) + len(err)
    print(f"certified {done}/{N_PROMOTED}   ok {len(ok)}   errors {len(err)}")
    for e in err:
        print(f"  ERROR {e.get('state_key')}: {str(e.get('error'))[:100]}")
    if not ok:
        return 0

    ok.sort(key=lambda r: r["objective_EXACT"])
    best, worst = ok[0], ok[-1]
    spread = worst["objective_EXACT"] - best["objective_EXACT"]

    print(f"  best  {best['objective_EXACT']:>16,.4f}  "
          f"...{best['state_key'][-12:]}  rounds {best['rounds']}")
    print(f"  worst {worst['objective_EXACT']:>16,.4f}  "
          f"...{worst['state_key'][-12:]}  rounds {worst['rounds']}")
    print(f"  spread{spread:>16,.4f}  "
          f"({100 * spread / best['objective_EXACT']:.3f}%)")

    rounds = [r["rounds"] for r in ok]
    secs = [r["seconds"] for r in ok]
    unconverged = [r for r in ok if not r["converged"]]
    print(f"  rounds {min(rounds)}-{max(rounds)}   "
          f"mean {sum(secs) / len(secs):.0f}s   "
          f"remaining ~{(N_PROMOTED - done) * (sum(secs) / len(secs)) / 3600:.1f}h")
    if unconverged:
        print(f"  NOT CONVERGED: {len(unconverged)} -- these hit the round cap "
              f"and are recorded as unconverged, not as certified optima")

    print("  (progress readout only -- rank_certified decides ordering, on the "
          "complete set)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        # Piping into `head` closes stdout early. That is a normal way to call
        # this from a keeper beat, and a traceback there reads like a run
        # failure when nothing is wrong.
        try:
            sys.stdout.close()
        finally:
            sys.exit(0)
