#!/usr/bin/env bash
# Where is Experiment 3? One command, no reconstruction from memory.
set -u
cd "$(dirname "$0")/.."
OUT=outputs/exp3
echo "=============================================================="
echo "EXPERIMENT 3 STATUS   $(date -u +%FT%TZ)"
echo "=============================================================="
python - <<'PY'
import json, time
from pathlib import Path
OUT = Path("outputs/exp3")
pool = [m["id"] for m in json.loads((OUT / "mutation_pool.json").read_text())["mutations"]]
have, reps = set(), set()
for p in list(OUT.glob("stageA_states.shard*.jsonl")) + [OUT / "stageA_states.jsonl"]:
    if not p.exists():
        continue
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            k = json.loads(line)["state"]
        except Exception:
            continue
        (reps if k.startswith("<none>|rep") else have).add(k)
singles = have & set(pool)
print(f"  phase A1        {len(singles)}/{len(pool)} singles, {len(reps)}/3 replicates")
print(f"  unique states   {len(have | reps)} of the 420 cap")
print(f"  A1 complete     {(OUT / '.a1.done').exists()}")
b = OUT / "policy_benchmark.json"
print(f"  A2 gate         {'PASS' if b.exists() and json.loads(b.read_text()).get('pass') else 'not passed'}")
hb = OUT / "heartbeat.json"
if hb.exists():
    h = json.loads(hb.read_text())
    age = time.time() - time.mktime(time.strptime(h["at"], "%Y-%m-%dT%H:%M:%SZ"))
    print(f"  heartbeat       {h['at']} ({age/60:.1f} min ago) {h['tag']} {h.get('state','')[:40]}")
else:
    print("  heartbeat       none yet")
PY
# Count workers WITHOUT matching this script's own command line. Experiment
# 2's supervisor had exactly this bug: its pgrep guard matched its own
# launcher, so it refused to start three times while nothing was running.
n=$(ps -eo pid,args | grep '[p]ython scripts/exp3_stage_a.py' | grep -vc "$$")
echo "  processes       ${n:-0} worker(s) running"
echo "  container up    $(awk '{printf "%.0f min", $1/60}' /proc/uptime)"
echo "  last commit     $(git log --oneline -1)"
