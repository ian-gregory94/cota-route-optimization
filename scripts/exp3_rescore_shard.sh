#!/usr/bin/env bash
# One sharded re-score worker. Two of these use both cores; the shards are a
# partition of a canonically sorted list, so they never collide (OPERATIONS 12),
# and the freeze checks the union.
set -uo pipefail
cd "$(dirname "$0")/.."
SHARD="${1:?usage: exp3_rescore_shard.sh i/n}"
I="${SHARD%%/*}"
OUT=outputs/exp3
guard() { case "$1" in (''|*[!0-9]*) echo "FATAL: count not a number: $(printf %q "$1")" >&2; exit 4;; esac; }
stall=0
echo "shard $SHARD start $(date -u +%FT%TZ) pid=$$" >> "$OUT/rescore_shard$I.log"
# Record the pid where a supervisor can find it. Killing by pattern is how a
# tool call kills itself when its own command text mentions the script
# (OPERATIONS 17) -- a pidfile has no such failure mode.
echo $$ > "$OUT/rescore_shard$I.pid"
while true; do
  n=$(python scripts/exp3_rescore.py --list --shard "$SHARD" 2>/dev/null | grep -c .); n=${n:-0}
  guard "$n"
  printf '{"at":"%s","shard":"%s","remaining":%s,"pid":%s}\n' \
      "$(date -u +%FT%TZ)" "$SHARD" "$n" "$$" > "$OUT/rescore_shard$I.heartbeat.json"
  echo "$(date -u +%FT%TZ) remaining=$n" >> "$OUT/rescore_shard$I.log"
  [ "$n" -eq 0 ] && break
  timeout 1500 python scripts/exp3_rescore.py --deadline-seconds 1400 \
      --shard "$SHARD" >> "$OUT/rescore_shard$I.run.log" 2>&1
  after=$(python scripts/exp3_rescore.py --list --shard "$SHARD" 2>/dev/null | grep -c .); after=${after:-0}
  guard "$after"
  if [ "$after" -eq "$n" ]; then
    stall=$((stall+1))
    [ "$stall" -ge 2 ] && { echo "STALLED" >> "$OUT/rescore_shard$I.log"; rm -f "$OUT/rescore_shard$I.pid"; exit 3; }
  else
    stall=0
  fi
  git add outputs/exp3/stageA_rescored.shard$I.jsonl outputs/exp3/observations >/dev/null 2>&1
  git diff --cached --quiet || git commit -q -m "chore: Experiment 3 re-score shard $SHARD

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011QusixhUPcncmLPpuZWqFS" 2>/dev/null || true
done
echo "shard $SHARD done $(date -u +%FT%TZ)" >> "$OUT/rescore_shard$I.log"
rm -f "$OUT/rescore_shard$I.pid"
