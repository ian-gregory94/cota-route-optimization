#!/usr/bin/env bash
# Rename any output whose filename Windows cannot hold, before it is committed.
#
# Run this before `git add -A` while a job is still running. The evaluation
# script's own naming was fixed, but a job that started before the fix holds
# the old code in memory for its whole life and keeps writing pipe-separated
# candidate keys into filenames. Twice now one of those has been swept into a
# commit by `git add -A`, and each time the result was a history that cannot be
# checked out on Windows -- which surfaces as `error: invalid path` mid-merge,
# after the merge has already started.
set -u
cd "$(dirname "$0")/.."
n=0
while IFS= read -r f; do
  [ -n "$f" ] || continue
  d=$(dirname "$f"); b=$(basename "$f")
  nb=$(printf '%s' "$b" | tr '<>:"|?*' '-------' | sed 's/^single_splice-/single-splice-/')
  [ "$b" = "$nb" ] && continue
  if [ -e "$d/$nb" ]; then
    echo "presweep: $d/$nb already exists; leaving $f for a human" >&2
    continue
  fi
  if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
    git mv "$f" "$d/$nb"
  else
    mv "$f" "$d/$nb"
  fi
  echo "presweep: $f -> $d/$nb"
  n=$((n + 1))
done < <(find outputs config scripts src tests -type f -name '*[<>:"|?*]*' 2>/dev/null)
echo "presweep: $n renamed"
