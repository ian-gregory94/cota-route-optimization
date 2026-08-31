#!/usr/bin/env bash
# Run Experiment 3 rescore slices back to back until the locked set is done.
# Launched under setsid so it outlives the tool call that starts it.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=outputs/exp3
mkdir -p "$OUT"
echo "loop start $(date -u +%FT%TZ) pid=$$" >> "$OUT/rescore_loop.log"
while true; do
  n=$(python scripts/exp3_rescore.py --list 2>/dev/null | grep -c . || echo 0)
  printf '{"at":"%s","remaining":%s,"pid":%s}\n' "$(date -u +%FT%TZ)" "$n" "$$" > "$OUT/rescore_heartbeat.json"
  echo "$(date -u +%FT%TZ) remaining=$n" >> "$OUT/rescore_loop.log"
  [ "$n" -eq 0 ] && break
  timeout 1500 bash scripts/exp3_rescore_slice.sh 1400 >> "$OUT/rescore_loop.log" 2>&1
done
echo "loop done $(date -u +%FT%TZ)" >> "$OUT/rescore_loop.log"
