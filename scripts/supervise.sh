#!/usr/bin/env bash
# Keep the long runs alive, and record how they die.
#
# Both jobs checkpoint per cell, so a restart resumes rather than repeats. What
# they cannot survive is dying quietly and being noticed twenty minutes later.
#
# Two failure modes have already been seen and are handled here:
#   * the whole process group going down with a tool-layer outage;
#   * the first version of this script leaking its own debounce lock when the
#     cleanup subshell died with it, which then blocked every future restart.
#     Locks now carry an mtime and are reaped when stale.
#
# "Finished" is the script's own closing line, not an exit code, because a
# killed process leaves no exit code behind to read.
set -u
cd "$(dirname "$0")/.."

LOCK_TTL=90            # seconds a debounce lock may live before it is stale

alive()  { pgrep -f "[p]ython $1" >/dev/null 2>&1; }
done_()  { tail -5 "$1" 2>/dev/null | grep -q "artifacts:"; }

reap_locks() {
  local now; now=$(date +%s)
  for l in outputs/.lock-*; do
    [ -d "$l" ] || continue
    local age=$(( now - $(stat -c %Y "$l" 2>/dev/null || echo "$now") ))
    [ "$age" -gt "$LOCK_TTL" ] && rmdir "$l" 2>/dev/null
  done
}

start() {   # label, script+args, log, nice
  local lock="outputs/.lock-$(echo "$1" | tr -c 'a-zA-Z0-9' '-')"
  mkdir "$lock" 2>/dev/null || return 0
  local free; free=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
  # the wrapper outlives this loop iteration, so an exit status is recorded
  # even when the supervisor itself is restarted underneath it
  setsid nohup bash -c "
      nice -n $4 python $2 >> '$3' 2>&1 < /dev/null
      echo \"\$(date -u +%FT%TZ) supervisor: $1 exited status=\$?\" \
        >> outputs/supervisor.log
    " >/dev/null 2>&1 < /dev/null &
  echo "$(date -u +%FT%TZ) supervisor: started $1 free=${free}MB" \
    >> outputs/supervisor.log
}

log_usage() {
  for pat in "scripts/fixpoint.py" "scripts/run_exp2_screen.py"; do
    for pid in $(pgrep -f "[p]ython $pat"); do
      local rss; rss=$(awk '/VmRSS/{print int($2/1024)}' "/proc/$pid/status" 2>/dev/null)
      [ -n "$rss" ] && echo "$(date -u +%FT%TZ) $pat pid=$pid rss=${rss}MB" \
        >> outputs/memory.log
    done
  done
}

while true; do
  reap_locks
  if done_ outputs/fixpoint.log \
     && { [ ! -f outputs/exp2_screen.log ] || done_ outputs/exp2_screen.log; }; then
    echo "$(date -u +%FT%TZ) supervisor: all runs complete, exiting" \
      >> outputs/supervisor.log
    exit 0
  fi
  if ! alive "scripts/fixpoint.py" && ! done_ outputs/fixpoint.log; then
    start "fixpoint" "scripts/fixpoint.py" outputs/fixpoint.log 0
  fi
  sleep 5
  if [ -f outputs/exp2_screen.log ] \
     && ! alive "scripts/run_exp2_screen.py" && ! done_ outputs/exp2_screen.log; then
    start "exp2-screen" \
      "scripts/run_exp2_screen.py --per-kind 12 --origin-sample 400" \
      outputs/exp2_screen.log 15
  fi
  log_usage
  sleep 55
done
