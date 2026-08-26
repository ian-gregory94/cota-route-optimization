#!/usr/bin/env bash
# Keep the long runs alive.
#
# Both jobs checkpoint per cell, so a restart resumes rather than repeats. What
# they cannot survive is dying quietly at 17:14 and being noticed at 17:23,
# which is what happened when memory-hungry diagnostics were run alongside them
# on an 8 GB box. This watches every 60 s and restarts anything that is neither
# running nor finished.
#
# "Finished" is the script's own closing line, not an exit code, because a
# killed process leaves no exit code behind to read.
set -u
cd "$(dirname "$0")/.."
ROOT=$(pwd)

alive() { pgrep -f "[p]ython $1" >/dev/null 2>&1; }
done_() { tail -5 "$2" 2>/dev/null | grep -q "artifacts:"; }

# One instance per job, enforced by a lock directory rather than by trusting
# pgrep to have caught up: a restart racing its own previous attempt would put
# two copies of the same run on an 8 GB box, which is how both jobs died once.
start() {   # name, script+args, log, nice
  local lock="outputs/.lock-$(echo "$1" | tr -c 'a-zA-Z0-9' '-')"
  mkdir "$lock" 2>/dev/null || return 0
  setsid nohup nice -n "$4" python $2 >> "$3" 2>&1 < /dev/null &
  local pid=$!
  echo "$(date -u +%FT%TZ) supervisor: started $1 pid=$pid free=$(awk '/MemAvailable/{print int($2/1024)"MB"}' /proc/meminfo)" \
    >> outputs/supervisor.log
  ( sleep 90; rmdir "$lock" 2>/dev/null ) &
}

log_usage() {
  for pat in "scripts/fixpoint.py" "scripts/run_exp2_screen.py"; do
    for pid in $(pgrep -f "[p]ython $pat"); do
      local rss=$(awk '/VmRSS/{print int($2/1024)}' /proc/$pid/status 2>/dev/null)
      [ -n "$rss" ] && echo "$(date -u +%FT%TZ) $pat pid=$pid rss=${rss}MB" \
        >> outputs/memory.log
    done
  done
}

while true; do
  if done_ "scripts/fixpoint.py" outputs/fixpoint.log \
     && done_ "scripts/run_exp2_screen.py" outputs/exp2_screen.log; then
    echo "$(date -u +%FT%TZ) supervisor: both runs complete, exiting" \
      >> outputs/supervisor.log
    exit 0
  fi
  if ! alive "scripts/fixpoint.py" && ! done_ "scripts/fixpoint.py" outputs/fixpoint.log; then
    start "fixpoint" "scripts/fixpoint.py" outputs/fixpoint.log 0
  fi
  sleep 5
  if ! alive "scripts/run_exp2_screen.py" \
     && ! done_ "scripts/run_exp2_screen.py" outputs/exp2_screen.log; then
    start "exp2 screen" \
      "scripts/run_exp2_screen.py --per-kind 12 --origin-sample 400" \
      outputs/exp2_screen.log 15
  fi
  log_usage
  sleep 55
done
