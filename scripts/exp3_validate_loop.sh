#!/usr/bin/env bash
# Run validation slices back to back until none remain. Launched under setsid so
# it outlives the tool call that started it (OPERATIONS 13: a plain `nohup &`
# dies with the tool call's process group -- this project lost a run to that).
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=outputs/exp3
mkdir -p "$OUT"
echo "loop start $(date -u +%FT%TZ) pid=$$" >> "$OUT/validate_loop.log"
guard() {   # a loop whose counter is not a number cannot reach its exit
  case "$1" in (''|*[!0-9]*) echo "FATAL: work count is not a number: $(printf %q "$1")" >&2; exit 4;; esac
}
while true; do
  n=$(python scripts/exp3_validate_fallback.py --list 2>/dev/null | grep -c .); n=${n:-0}
  echo "$(date -u +%FT%TZ) remaining=$n" >> "$OUT/validate_loop.log"
  printf '{"at":"%s","remaining":%s,"pid":%s}\n' "$(date -u +%FT%TZ)" "$n" "$$" > "$OUT/validate_heartbeat.json"
  [ "$n" -eq 0 ] && break
  timeout 900 bash scripts/exp3_validate_slice.sh 840 >> "$OUT/validate_loop.log" 2>&1
done
echo "loop done $(date -u +%FT%TZ)" >> "$OUT/validate_loop.log"
