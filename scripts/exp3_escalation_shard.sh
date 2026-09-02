#!/usr/bin/env bash
# One §6 escalation worker. 40 restarts, so cells run roughly twice as long as
# Stage B's and the slice budget is doubled -- with Stage B's 760s cell estimate
# the runner would start a cell it cannot finish and the timeout would throw the
# work away.
set -uo pipefail
cd "$(dirname "$0")/.."
SHARD="${1:?usage: exp3_escalation_shard.sh i/n}"
I="${SHARD%%/*}"
OUT=outputs/exp3
TAG="esc$I"
if [ -f "$OUT/$TAG.pid" ]; then
  old=$(cat "$OUT/$TAG.pid" 2>/dev/null || echo)
  case "${old:-}" in (''|*[!0-9]*) old=;; esac
  if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then
    echo "$TAG already running as pid $old" >&2; exit 0
  fi
fi
ONLY=$(python -c "
import json;print(','.join(c['candidate'] for c in json.load(open('outputs/exp3/escalation_manifest.json'))['candidates']))")
case "$ONLY" in (*'#'*) : ;; (*) echo "FATAL: manifest read failed" >&2; exit 4;; esac
echo $$ > "$OUT/$TAG.pid"
echo "$TAG start $(date -u +%FT%TZ) pid=$$" >> "$OUT/$TAG.log"
stall=0
while true; do
  n=$(python scripts/exp3_stage_b.py --escalated --only "$ONLY" --list --shard "$SHARD" 2>/dev/null | grep -cP '\t'); n=${n:-0}
  case "$n" in (''|*[!0-9]*) echo "FATAL: count not a number" >&2; rm -f "$OUT/$TAG.pid"; exit 4;; esac
  printf '{"at":"%s","shard":"%s","remaining":%s,"pid":%s}\n' \
      "$(date -u +%FT%TZ)" "$SHARD" "$n" "$$" > "$OUT/$TAG.heartbeat.json"
  echo "$(date -u +%FT%TZ) remaining=$n" >> "$OUT/$TAG.log"
  [ "$n" -eq 0 ] && break
  timeout 3500 python scripts/exp3_stage_b.py --escalated --only "$ONLY" \
      --shard "$SHARD" --deadline-seconds 3400 --cell-seconds 1650 \
      --cold-extra 500 >> "$OUT/$TAG.run.log" 2>&1
  after=$(python scripts/exp3_stage_b.py --escalated --only "$ONLY" --list --shard "$SHARD" 2>/dev/null | grep -cP '\t'); after=${after:-0}
  case "$after" in (''|*[!0-9]*) echo "FATAL: count not a number" >&2; rm -f "$OUT/$TAG.pid"; exit 4;; esac
  if [ "$after" -eq "$n" ]; then
    stall=$((stall+1))
    [ "$stall" -ge 2 ] && { echo "STALLED" >> "$OUT/$TAG.log"; rm -f "$OUT/$TAG.pid"; exit 3; }
  else stall=0; fi
  git add "$OUT"/stageB_esc*.jsonl "$OUT"/observations_stageB_esc >/dev/null 2>&1
  git diff --cached --quiet || git commit -q -m "chore: Experiment 3 section 6 escalation cells, shard $SHARD

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011QusixhUPcncmLPpuZWqFS" 2>/dev/null || true
done
echo "$TAG done $(date -u +%FT%TZ)" >> "$OUT/$TAG.log"
rm -f "$OUT/$TAG.pid"
