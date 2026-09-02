#!/usr/bin/env bash
# One-shot health check for a long escalation run. Everything that has silently
# cost hours on this project, checked in one place (OPERATIONS 18, 21, 24-29).
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=outputs/exp3
say() { printf '%-34s %s\n' "$1" "$2"; }

n=$(ls "$OUT/observations_stageB_esc" 2>/dev/null | wc -l)
say "escalation cells" "$n/170"
for i in 0 1; do
  p=$(cat "$OUT/esc$i.pid" 2>/dev/null || echo)
  case "${p:-}" in (''|*[!0-9]*) p=;; esac
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then say "shard $i" "alive (pid $p)"
  else say "shard $i" "DEAD"; fi
done

# rule 24: the evaluation path must not drift mid-batch
cur=$(python -c "
import sys;sys.path.insert(0,'src');sys.path.insert(0,'scripts')
from cota_opt.exp3_cell import code_version;print(code_version())" 2>/dev/null)
frz=$(cat "$OUT/EVAL_PATH_FROZEN" 2>/dev/null)
[ "$cur" = "$frz" ] && say "eval path digest" "MATCH ($cur)" \
                    || say "eval path digest" "*** DRIFT *** $cur vs $frz"

# a refused cell can never complete, so the loop would spin forever
r=$(grep -c -iE 'REFUSED|INADMISSIBLE' "$OUT"/esc*.run.log 2>/dev/null | awk -F: '{s+=$2} END{print s+0}')
say "firewall refusals" "$r"
t=$(grep -c 'Traceback' "$OUT"/esc*.run.log 2>/dev/null | awk -F: '{s+=$2} END{print s+0}')
say "tracebacks" "$t"

say "disk free" "$(df -h / | awk 'NR==2{print $4}')"
say "memory available" "$(free -m | awk 'NR==2{print $7" MB"}')"
say "container uptime" "$(uptime -p)"
say "checked at" "$(date -u +%FT%TZ)"
[ "$r" -gt 0 ] || [ "$t" -gt 0 ] || [ "$cur" != "$frz" ] && exit 1
exit 0
