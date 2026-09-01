#!/usr/bin/env bash
# Run 2B confirmation cells back to back until none remain.
#
# A certification cell is ~20 restarts at ~25s plus its initial search, so it
# does not fit the ~10 minute ceiling a foreground tool call has. It fits here,
# under setsid, where the only limit is the one this script sets.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=outputs
mkdir -p "$OUT"
echo "loop start $(date -u +%FT%TZ) pid=$$" >> "$OUT/exp2b_confirm_loop.log"
while true; do
  n=$(python scripts/exp2b_confirm.py --list 2>/dev/null | grep -cP '\t' || echo 0)
  printf '{"at":"%s","remaining":%s,"pid":%s}\n' "$(date -u +%FT%TZ)" "$n" "$$" > "$OUT/exp2b_confirm_heartbeat.json"
  echo "$(date -u +%FT%TZ) remaining=$n" >> "$OUT/exp2b_confirm_loop.log"
  [ "$n" -eq 0 ] && break
  timeout 1500 python scripts/exp2b_confirm.py --deadline-seconds 1400 \
      >> "$OUT/exp2b_confirm.log" 2>&1
  git add -A >/dev/null 2>&1
  git diff --cached --quiet || git commit -q -m "chore: Experiment 2B matched-start confirmation cell

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011QusixhUPcncmLPpuZWqFS"
done
echo "loop done $(date -u +%FT%TZ)" >> "$OUT/exp2b_confirm_loop.log"
