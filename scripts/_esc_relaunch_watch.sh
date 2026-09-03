#!/usr/bin/env bash
# One-shot, self-terminating: wait for each orphaned escalation slice to finish,
# then relaunch that shard's wrapper so it picks up the re-sized slice budget.
# Not part of code_version; touches no experimental parameter.
set -uo pipefail
cd "$(dirname "$0")/.."
LOG=outputs/exp3/relaunch.log
declare -A PY=( [0]="$1" [1]="$2" )
done0=0; done1=0
echo "$(date -u +%FT%TZ) watcher start py0=${PY[0]} py1=${PY[1]}" >> "$LOG"
for _ in $(seq 1 720); do
  for i in 0 1; do
    v=done$i; [ "${!v}" -eq 1 ] && continue
    if ! kill -0 "${PY[$i]}" 2>/dev/null; then
      rm -f "outputs/exp3/esc$i.pid"
      nohup bash scripts/exp3_escalation_shard.sh "$i/2" > /dev/null 2>&1 &
      echo "$(date -u +%FT%TZ) relaunched shard $i as $!" >> "$LOG"
      printf -v "$v" 1; eval "$v=1"
    fi
  done
  [ "$done0" -eq 1 ] && [ "$done1" -eq 1 ] && break
  sleep 15
done
echo "$(date -u +%FT%TZ) watcher exit done0=$done0 done1=$done1" >> "$LOG"
