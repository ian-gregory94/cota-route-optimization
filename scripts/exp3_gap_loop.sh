#!/usr/bin/env bash
# Run optimization-gap benchmark cells until none remain.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=outputs/exp3
guard() {   # a loop whose counter is not a number cannot reach its exit
  case "$1" in (''|*[!0-9]*) echo "FATAL: work count is not a number: $(printf %q "$1")" >&2; exit 4;; esac
}
stall=0
echo "loop start $(date -u +%FT%TZ) pid=$$" >> "$OUT/gap_loop.log"
while true; do
  n=$(python scripts/exp3_gap_benchmark.py --list 2>/dev/null | grep -c .); n=${n:-0}
  guard "$n"
  printf '{"at":"%s","remaining":%s,"pid":%s}\n' "$(date -u +%FT%TZ)" "$n" "$$" > "$OUT/gap_heartbeat.json"
  echo "$(date -u +%FT%TZ) remaining=$n" >> "$OUT/gap_loop.log"
  [ "$n" -eq 0 ] && break
  timeout 1500 python scripts/exp3_gap_benchmark.py --deadline-seconds 1400 \
      >> "$OUT/gap.log" 2>&1
  after=$(python scripts/exp3_gap_benchmark.py --list 2>/dev/null | grep -c .); after=${after:-0}
  guard "$after"
  if [ "$after" -eq "$n" ]; then
    stall=$((stall + 1))
    [ "$stall" -ge 2 ] && { echo "STALLED" >> "$OUT/gap_loop.log"; exit 3; }
  else
    stall=0
  fi
  git add outputs/exp3/gap_benchmark.jsonl outputs/exp3/gap.log data/cache >/dev/null 2>&1
  git diff --cached --quiet || git commit -q -m "chore: optimization-gap benchmark cells

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011QusixhUPcncmLPpuZWqFS" 2>/dev/null || true
done
echo "loop done $(date -u +%FT%TZ)" >> "$OUT/gap_loop.log"
