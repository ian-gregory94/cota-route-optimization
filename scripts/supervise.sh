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

start() {   # name, script+args, log
  echo "$(date -u +%FT%TZ) supervisor: starting $1" >> outputs/supervisor.log
  setsid nohup nice -n "$4" python $2 >> "$3" 2>&1 < /dev/null &
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
  sleep 55
done
