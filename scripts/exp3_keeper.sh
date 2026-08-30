#!/usr/bin/env bash
# Keep Phase A1's two shards alive. Resume is exact, so a restart costs at most
# the state in flight -- but a shard that dies unnoticed costs the whole night,
# which is what this exists to prevent.
#
# It does NOT restart a shard that exits cleanly (status 0): A1 finishing is the
# expected end, not a failure. A shard that dies in under 60 s is treated as
# declining rather than crashing and is held off, so a broken invocation cannot
# spin.
set -u
cd "$(dirname "$0")/.."
LOG=outputs/exp3/keeper.log
echo "$(date -u +%FT%TZ) keeper: started" >> "$LOG"

running() { pgrep -f "exp3_stage_a.py --shard $1/2" > /dev/null; }

while true; do
  alive=0
  for i in 0 1; do
    if running "$i"; then alive=$((alive+1)); continue; fi
    done_marker="outputs/exp3/.shard$i.done"
    [ -f "$done_marker" ] && continue
    if grep -q "phase A1 shard done" "outputs/exp3/stageA_shard$i.log" 2>/dev/null; then
      touch "$done_marker"
      echo "$(date -u +%FT%TZ) keeper: shard $i finished cleanly" >> "$LOG"
      continue
    fi
    echo "$(date -u +%FT%TZ) keeper: restarting shard $i" >> "$LOG"
    # setsid, not bare nohup. A child that stays in this shell's process
    # group dies with it, and that is exactly how the first launch of Phase A1
    # was lost -- three states in, silently, with no traceback. supervise.sh
    # has used setsid since Experiment 2 for the same reason.
    setsid nohup python scripts/exp3_stage_a.py --shard "$i/2" \
      >> "outputs/exp3/stageA_shard$i.log" 2>&1 < /dev/null &
    sleep 60
  done
  if [ -f outputs/exp3/.shard0.done ] && [ -f outputs/exp3/.shard1.done ]; then
    echo "$(date -u +%FT%TZ) keeper: both shards done, exiting" >> "$LOG"
    exit 0
  fi
  sleep 120
done
