#!/usr/bin/env bash
# One D33-at-Stage-B anchor worker. Stops hard on a digest mismatch: that is a
# reproducibility failure, not a retryable error (OPERATIONS 18).
set -uo pipefail
cd "$(dirname "$0")/.."
SHARD="${1:?usage: exp3_d33_anchor_shard.sh i/n}"
I="${SHARD%%/*}"
OUT=outputs/exp3
TAG="d33anchor$I"
if [ -f "$OUT/$TAG.pid" ]; then
  old=$(cat "$OUT/$TAG.pid" 2>/dev/null || echo)
  case "${old:-}" in (''|*[!0-9]*) old=;; esac
  if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then
    echo "$TAG already running as pid $old" >&2; exit 0
  fi
fi
echo $$ > "$OUT/$TAG.pid"
echo "$TAG start $(date -u +%FT%TZ) pid=$$" >> "$OUT/$TAG.log"
stall=0
while true; do
  n=$(python scripts/exp3_d33_stageb.py --status 2>/dev/null | grep -oP 'anchors \K[0-9]+')
  n=${n:-0}
  case "$n" in (''|*[!0-9]*) echo "FATAL: bad count" >&2; rm -f "$OUT/$TAG.pid"; exit 4;; esac
  [ "$n" -ge 25 ] && break
  timeout 1700 python scripts/exp3_d33_stageb.py --phase anchors \
      --shard "$SHARD" --deadline-seconds 1500 >> "$OUT/$TAG.run.log" 2>&1
  rc=$?
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 124 ]; then
    echo "STOPPED rc=$rc -- see $OUT/$TAG.run.log (digest mismatch stops here)" >> "$OUT/$TAG.log"
    rm -f "$OUT/$TAG.pid"; exit "$rc"
  fi
  after=$(python scripts/exp3_d33_stageb.py --status 2>/dev/null | grep -oP 'anchors \K[0-9]+'); after=${after:-0}
  if [ "$after" -eq "$n" ]; then
    stall=$((stall+1))
    [ "$stall" -ge 2 ] && { echo "STALLED" >> "$OUT/$TAG.log"; rm -f "$OUT/$TAG.pid"; exit 3; }
  else stall=0; fi
  git add outputs/exp3/d33_stageb >/dev/null 2>&1
  git diff --cached --quiet || git commit -q -m "chore: D33 Stage B anchors, shard $SHARD

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011QusixhUPcncmLPpuZWqFS" 2>/dev/null || true
done
echo "$TAG done $(date -u +%FT%TZ)" >> "$OUT/$TAG.log"
rm -f "$OUT/$TAG.pid"
