#!/usr/bin/env bash
# One-shot health check for the Phase 5b symmetric escalation.
# Counts cells from the observation STORE under the escalated contract, not by
# listing a directory -- an `ls | wc -l` caught the directory mid-write during
# the section 6 batch and reported 169 when 170 were present.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=outputs/exp3
say() { printf '%-34s %s\n' "$1" "$2"; }

python - <<'PY'
import sys, collections
sys.path.insert(0,'src')
from pathlib import Path
from cota_opt.firewall import ObservationStore, EXP3_STAGE_B_ESCALATED as E, EXP3_STAGE_B as B
OUT=Path('outputs/exp3')
frozen=(OUT/'EVAL_PATH_FROZEN').read_text().strip()
recs=[r for r in ObservationStore(OUT/'observations_stageB_esc').all()]
ok=[r for r in recs if r.spec.contract_digest==E.digest and r.code_version==frozen]
print(f"{'escalated store (contract+path)':<34} {len(ok)}/200")
other_contract=len([r for r in recs if r.spec.contract_digest!=E.digest])
other_path=len([r for r in recs if r.code_version!=frozen])
print(f"{'stage B receipts in this store':<34} "
      f"{len([r for r in recs if r.spec.contract_digest==B.digest])}")
print(f"{'other contract / other path':<34} {other_contract} / {other_path}")
rs=collections.Counter(getattr(r,'restarts_completed',None) for r in ok)
print(f"{'restarts_completed':<34} {dict(rs)}")
keys=[(r.spec.state_key or '<none>', r.spec.seed) for r in ok]
dupes=[k for k,c in collections.Counter(keys).items() if c>1]
print(f"{'duplicate (state,seed) keys':<34} {len(dupes)}")
PY

for i in 0 1; do
  p=$(cat "$OUT/esc5b$i.pid" 2>/dev/null || echo)
  case "${p:-}" in (''|*[!0-9]*) p=;; esac
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then say "shard $i" "alive (pid $p)"
  else say "shard $i" "not running"; fi
done
say "eval path digest" "$(cat "$OUT/EVAL_PATH_FROZEN" 2>/dev/null)"
say "firewall refusals" "$(grep -c 'REFUSED' "$OUT"/esc5b*.run.log 2>/dev/null | awk -F: '{s+=$2} END{print s+0}')"
say "tracebacks" "$(grep -c 'Traceback' "$OUT"/esc5b*.run.log 2>/dev/null | awk -F: '{s+=$2} END{print s+0}')"
say "disk free" "$(df -h . | tail -1 | awk '{print $4}')"
say "memory available" "$(free -m | awk '/Mem:/{print $7" MB"}')"
say "container uptime" "$(uptime -p)"
say "checked at" "$(date -u +%FT%TZ)"
