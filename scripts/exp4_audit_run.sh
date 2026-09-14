#!/usr/bin/env bash
# Start the Experiment 4 out-of-band audit if it is not already running.
# Idempotent, same shape as scripts/exp4_run.sh (OPERATIONS 25, 28).
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$ROOT/outputs/exp4_audit/audit.pid"
LOG="$ROOT/outputs/exp4_audit/audit.log"
MAXH="${1:-6}"

mkdir -p "$(dirname "$PIDFILE")"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; then
  echo "ALREADY RUNNING pid=$(cat "$PIDFILE")"
  exit 0
fi

cd "$ROOT" || exit 1
nohup python scripts/exp4_audit_launch.py --max-hours "$MAXH" >> "$LOG" 2>&1 &
echo $! > "$PIDFILE"
echo "STARTED pid=$(cat "$PIDFILE") log=$LOG"
