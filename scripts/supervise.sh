#!/usr/bin/env bash
# Keep the long runs alive, and record how they die.
#
# Every job checkpoints below the cell -- per restart for a solve, per period
# for an enumeration -- so a restart resumes rather than repeats. What they
# cannot survive is dying quietly and being noticed twenty minutes later.
#
# Failure modes already seen, all handled here:
#   * the whole process group going down with a tool-layer outage;
#   * the first version of this script leaking its own debounce lock when the
#     cleanup subshell died with it, blocking every future restart. Locks now
#     carry an mtime and are reaped when stale;
#   * two jobs running the same script with different arguments. Liveness is
#     an EXACT command-line match (pgrep -fx), because a substring match on
#     "scripts/fixpoint.py" reports Model A alive whenever Model B is running
#     and would quietly leave the control job dead for hours.
#
# "Finished" is the script's own closing line, not an exit code, because a
# killed process leaves no exit code behind to read.
set -u
cd "$(dirname "$0")/.."

LOCK_TTL=90            # seconds a debounce lock may live before it is stale

# label | exact command | log | nice
# --max-iterations 8: the default cap of 3 would have stopped the loop while
# the improvable-flow share was still falling fast (9.44% -> 4.52% -> 1.14%),
# and gate 1 requires the last two iterations to be within --tol of each other.
# Hitting the cap mid-descent fails that gate. Raising the cap costs nothing
# when the loop converges sooner, since it exits on the tolerance test.
# certify-* repairs gate 4 and may only run once its model's fixpoint has
# written final|lam cells, so a job is added here when that happens rather
# than up front -- otherwise the supervisor hot-loops on a job that cannot
# start yet.
JOBS=(
  "fixpoint-A|python scripts/fixpoint.py --max-iterations 8|outputs/fixpoint.log|0"
  "fixpoint-B|python scripts/fixpoint.py --common-lines same_route --max-iterations 8|outputs/fixpoint_modelB.log|0"
  "certify-A|python scripts/frontier_certify.py|outputs/certify.log|0"
  "certify-B|python scripts/frontier_certify.py --common-lines same_route|outputs/certify_modelB.log|0"
)

alive()  { pgrep -fx "$1" >/dev/null 2>&1; }
done_()  { tail -5 "$1" 2>/dev/null | grep -q "artifacts:"; }

reap_locks() {
  local now; now=$(date +%s)
  for l in outputs/.lock-*; do
    [ -d "$l" ] || continue
    local age=$(( now - $(stat -c %Y "$l" 2>/dev/null || echo "$now") ))
    [ "$age" -gt "$LOCK_TTL" ] && rmdir "$l" 2>/dev/null
  done
  return 0
}

start() {   # label, command, log, nice
  local lock="outputs/.lock-$(echo "$1" | tr -c 'a-zA-Z0-9' '-')"
  mkdir "$lock" 2>/dev/null || return 0
  local free; free=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
  # the wrapper outlives this loop iteration, so an exit status is recorded
  # even when the supervisor itself is restarted underneath it
  setsid nohup bash -c "
      nice -n $4 $2 >> '$3' 2>&1 < /dev/null
      echo \"\$(date -u +%FT%TZ) supervisor: $1 exited status=\$?\" \
        >> outputs/supervisor.log
    " >/dev/null 2>&1 < /dev/null &
  echo "$(date -u +%FT%TZ) supervisor: started $1 free=${free}MB" \
    >> outputs/supervisor.log
}

log_usage() {
  for pid in $(pgrep -f "[p]ython scripts/"); do
    local rss cmd
    rss=$(awk '/VmRSS/{print int($2/1024)}' "/proc/$pid/status" 2>/dev/null)
    cmd=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | cut -c1-60)
    [ -n "$rss" ] && echo "$(date -u +%FT%TZ) pid=$pid rss=${rss}MB $cmd" \
      >> outputs/memory.log
  done
  return 0
}

while true; do
  reap_locks
  pending=0
  for spec in "${JOBS[@]}"; do
    IFS='|' read -r label cmd log nice_ <<< "$spec"
    if done_ "$log"; then continue; fi
    pending=1
    if ! alive "$cmd"; then
      start "$label" "$cmd" "$log" "$nice_"
      sleep 5
    fi
  done
  if [ "$pending" -eq 0 ]; then
    echo "$(date -u +%FT%TZ) supervisor: all runs complete, exiting" \
      >> outputs/supervisor.log
    exit 0
  fi
  log_usage
  sleep 55
done
