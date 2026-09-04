#!/usr/bin/env bash
# One Stage B certification worker. Two of these use both cores; the shards
# partition a canonically sorted cell list (OPERATIONS 12) and the report checks
# the union.
set -uo pipefail
cd "$(dirname "$0")/.."
SHARD="${1:?usage: exp3_stage_b_shard.sh i/n [--escalated]}"
shift || true
EXTRA="${*:-}"
I="${SHARD%%/*}"
TAG="stageB${EXTRA:+_esc}$I"
OUT=outputs/exp3
# Refuse to start when a live worker already owns this shard. After a container
# recycle two keepers can fire close together; without this the second one
# doubles the workers and oversubscribes both cores (OPERATIONS 25).
if [ -f "$OUT/$TAG.pid" ]; then
  old=$(cat "$OUT/$TAG.pid" 2>/dev/null || echo)
  case "${old:-}" in (''|*[!0-9]*) old=;; esac
  if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then
    echo "$TAG already running as pid $old; not starting a second" >&2
    exit 0
  fi
fi
guard() { case "$1" in (''|*[!0-9]*) echo "FATAL: count not a number: $(printf %q "$1")" >&2; exit 4;; esac; }
stall=0
echo "$TAG start $(date -u +%FT%TZ) pid=$$" >> "$OUT/$TAG.log"
# A pidfile, never a process-name pattern: a pattern that appears in your own
# command line kills your own tool call (OPERATIONS 17, 25).
python -c "import sys;sys.path.insert(0,'src');from cota_opt.exp3_cell import code_version;print(code_version())" > "$OUT/BATCH_IN_FLIGHT"
trap 'rm -f "$OUT/BATCH_IN_FLIGHT"' EXIT
echo $$ > "$OUT/$TAG.pid"
while true; do
  n=$(python scripts/exp3_stage_b.py --list --shard "$SHARD" $EXTRA 2>/dev/null | grep -cP '\t'); n=${n:-0}
  guard "$n"
  printf '{"at":"%s","shard":"%s","remaining":%s,"pid":%s}\n' \
      "$(date -u +%FT%TZ)" "$SHARD" "$n" "$$" > "$OUT/$TAG.heartbeat.json"
  echo "$(date -u +%FT%TZ) remaining=$n" >> "$OUT/$TAG.log"
  [ "$n" -eq 0 ] && break
  timeout 1700 python scripts/exp3_stage_b.py --deadline-seconds 1600 \
      --shard "$SHARD" $EXTRA >> "$OUT/$TAG.run.log" 2>&1
  after=$(python scripts/exp3_stage_b.py --list --shard "$SHARD" $EXTRA 2>/dev/null | grep -cP '\t'); after=${after:-0}
  guard "$after"
  if [ "$after" -eq "$n" ]; then
    stall=$((stall+1))
    if [ "$stall" -ge 2 ]; then
      echo "STALLED: two consecutive slices made no progress" >> "$OUT/$TAG.log"
      rm -f "$OUT/$TAG.pid"; exit 3
    fi
  else
    stall=0
  fi
  # Artifacts only, never the log (OPERATIONS 23).
  git add "$OUT"/stageB*.jsonl "$OUT"/observations_stageB* >/dev/null 2>&1
  git diff --cached --quiet || git commit -q -m "chore: Experiment 3 Stage B cells, shard $SHARD

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011QusixhUPcncmLPpuZWqFS" 2>/dev/null || true
done
echo "$TAG done $(date -u +%FT%TZ)" >> "$OUT/$TAG.log"
rm -f "$OUT/$TAG.pid"
