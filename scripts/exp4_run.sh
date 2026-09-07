#!/usr/bin/env bash
# Start the Experiment 4 run if it is not already running. Idempotent.
#
# OPERATIONS 25: a pidfile, never a process-name pattern. A `pgrep -f` on this
# script's own name matches the shell that ran the pgrep, which is how a keeper
# kills the thing it is keeping.
#
# OPERATIONS 28: this container dies of SESSION idleness. Processes do not
# survive a reclaim, disk does. So this script is designed to be run again and
# again -- every stage is resumable from artifacts on disk.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$ROOT/outputs/exp4/run/exp4.pid"
LOG="$ROOT/outputs/exp4/run/exp4.log"
MAXH="${1:-6}"

mkdir -p "$(dirname "$PIDFILE")"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; then
  echo "ALREADY RUNNING pid=$(cat "$PIDFILE")"
  exit 0
fi

cd "$ROOT" || exit 1
nohup python scripts/exp4_launch.py --max-hours "$MAXH" >> "$LOG" 2>&1 &
echo $! > "$PIDFILE"
echo "STARTED pid=$(cat "$PIDFILE") log=$LOG"
