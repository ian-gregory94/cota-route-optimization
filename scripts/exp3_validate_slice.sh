#!/usr/bin/env bash
# One bounded, idempotent validation slice (corrective plan, section 2).
set -uo pipefail
cd "$(dirname "$0")/.."
SECS="${1:-470}"
OUT=outputs/exp3
remaining() { python scripts/exp3_validate_fallback.py --list 2>/dev/null | grep -c . || true; }
before=$(remaining)
python scripts/exp3_validate_fallback.py --deadline-seconds "$SECS" >> "$OUT/validate.log" 2>&1
after=$(remaining)
echo "slice: $before -> $after cells remaining"
git add outputs/exp3/validation_fallback.jsonl outputs/exp3/validate.log \
        outputs/exp3/validation_plans data/cache >/dev/null 2>&1
if ! git diff --cached --quiet; then
  git commit -q -m "chore: fallback greedy-vs-both validation — $((before-after)) cells done, $after remaining

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011QusixhUPcncmLPpuZWqFS"
  echo "committed: $(git log --oneline -1)"
fi
