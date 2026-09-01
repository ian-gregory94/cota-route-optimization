#!/usr/bin/env bash
# One keep-alive beat: revive any dead Stage B shard worker, then report.
#
# Exists because of OPERATIONS 28 -- the container dies of SESSION idleness at
# roughly fifteen minutes and busy workers do not prevent it, so something has
# to touch this session on a shorter cycle than that. Called from a foreground
# loop, and from the self-bound `send_later` wake that carries the chain when
# no turn is running.
#
# Liveness is read from the pidfile, never from a process-name pattern
# (OPERATIONS 17, 25), and every count is asserted numeric before it is used in
# an arithmetic test (OPERATIONS 21).
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=outputs/exp3

for i in 0 1; do
  p=$(cat "$OUT/stageB$i.pid" 2>/dev/null || echo)
  case "${p:-}" in (''|*[!0-9]*) p=;; esac
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
    echo "shard$i pid $p alive"
    continue
  fi
  left=$(python scripts/exp3_stage_b.py --list --shard "$i/2" 2>/dev/null | grep -cP '\t')
  left=${left:-0}
  case "$left" in (''|*[!0-9]*)
      echo "shard$i FATAL: remaining count not a number: $(printf %q "$left")" >&2
      continue;;
  esac
  if [ "$left" -eq 0 ]; then
    echo "shard$i complete"
  else
    rm -f "$OUT/stageB$i.pid"
    setsid nohup bash scripts/exp3_stage_b_shard.sh "$i/2" >/dev/null 2>&1 </dev/null &
    echo "shard$i RELAUNCHED ($left cells left)"
  fi
done

n=$(ls "$OUT/observations_stageB" 2>/dev/null | wc -l)
echo "cells $n/200   up $(uptime -p)   $(date -u +%FT%TZ)"
