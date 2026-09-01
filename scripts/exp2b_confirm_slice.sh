#!/usr/bin/env bash
# One bounded, idempotent cell of the Experiment 2B matched-start confirmation.
set -uo pipefail
cd "$(dirname "$0")/.."
SECS="${1:-540}"
remaining() { python scripts/exp2b_confirm.py --list 2>/dev/null | grep -cP '\t' || true; }
before=$(remaining)
python scripts/exp2b_confirm.py --deadline-seconds "$SECS" >> outputs/exp2b_confirm.log 2>&1
after=$(remaining)
echo "slice: $before -> $after cells remaining"
git add -A >/dev/null 2>&1
if ! git diff --cached --quiet; then
  git commit -q -m "chore: Experiment 2B matched-start confirmation — $((before-after)) cells done, $after of 6 remaining

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011QusixhUPcncmLPpuZWqFS"
  echo "committed: $(git log --oneline -1)"
fi
