#!/usr/bin/env bash
# One bounded, idempotent re-score slice. Commits at the boundary (OPERATIONS 4).
set -uo pipefail
cd "$(dirname "$0")/.."
SECS="${1:-470}"
OUT=outputs/exp3
mkdir -p "$OUT"

remaining() { python scripts/exp3_rescore.py --list 2>/dev/null | grep -c . || true; }

before=$(remaining)
python scripts/exp3_rescore.py --deadline-seconds "$SECS" >> "$OUT/rescore.log" 2>&1
after=$(remaining)
echo "slice: $before -> $after states remaining"

git add -A >/dev/null 2>&1
if ! git diff --cached --quiet; then
  git commit -q -m "chore: Experiment 3 A1 re-score slice — $after of $(python scripts/exp3_rescore.py --list </dev/null | wc -l) states remaining

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_011QusixhUPcncmLPpuZWqFS"
  echo "committed: $(git log --oneline -1)"
fi
