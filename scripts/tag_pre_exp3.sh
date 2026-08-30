#!/usr/bin/env bash
# Create a pre-exp3 tag, or refuse and say why.
#
# The tag marks the end of the conservative-network era: Experiments 1, 2 and 2B
# frozen, the baseline Experiment 3 must beat fixed and hashed, and the rules
# Experiment 3 will run under committed before it has seen anything. After the
# tag the Experiment 1-2 record is not edited except to correct a discovered
# error.
#
# Every precondition is checked here rather than remembered. A tag that can be
# created while an input is still moving is not a freeze.
#
# The checks are not read-only: repro_check.py and build_exp3_baseline.py both
# WRITE their artifacts. So the tree is checked twice -- once before, and once
# after the generators have run. If running the checks changed a tracked file,
# the tag would point at a commit that does not contain the records its own
# preconditions just produced, and it is refused. That is the second check's
# whole job, and it caught this exact hazard on v1.
set -u
cd "$(dirname "$0")/.."
TAG="${1:-pre-exp3-v2}"
VERSION="${2:-v2}"
BASELINE="outputs/canonical/pre_exp3_baseline_${VERSION}.json"
fail=0

say() { printf '%-52s %s\n' "$1" "$2"; }

echo "=============================================================================="
echo "PRE-EXPERIMENT-3 TAG: $TAG   (baseline $VERSION)"
echo "=============================================================================="

if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  say "tag does not already exist" "FAIL — $TAG is taken"
  fail=1
else
  say "tag does not already exist" "ok"
fi

if [ -z "$(git status --porcelain)" ]; then
  say "working tree clean (before checks)" "ok"
else
  say "working tree clean (before checks)" "FAIL — commit or stash first"
  git status --porcelain | head -5 | sed 's/^/      /'
  fail=1
fi

# Snapshot every tracked file's content id, so the after-check can name exactly
# which ones the generators rewrote rather than just reporting "dirty".
BEFORE="$(git ls-files -s | git hash-object --stdin 2>/dev/null || echo none)"

echo
echo "--- reproducibility ---"
if python3 scripts/repro_check.py > /tmp/repro.txt 2>&1; then
  say "all reproducibility checks pass" "ok"
  grep -E "^  all [0-9]+ checks" /tmp/repro.txt | sed 's/^/      /'
else
  say "all reproducibility checks pass" "FAIL"
  grep -E "^  FAIL" /tmp/repro.txt | sed 's/^/      /'
  fail=1
fi

echo
echo "--- frozen records ---"
python3 scripts/freeze_records.py > /tmp/freeze.txt 2>&1 \
  && say "canonical records regenerate" "ok" \
  || { say "canonical records regenerate" "FAIL"; tail -5 /tmp/freeze.txt | sed 's/^/      /'; fail=1; }

python3 scripts/build_exp3_baseline.py --version "$VERSION" > /tmp/base.txt 2>&1
if grep -q "BLOCKERS" /tmp/base.txt; then
  say "pre_exp3_baseline_${VERSION} has no blockers" "FAIL"
  sed -n '/BLOCKERS/,$p' /tmp/base.txt | sed 's/^/      /' | head -8
  fail=1
else
  say "pre_exp3_baseline_${VERSION} has no blockers" "ok"
fi

echo
echo "--- required documents ---"
for f in ACCEPTANCE.md EXPERIMENT3_CONTRACT.md DISCOVERIES.md HANDOFF.md \
         README.md EXPERIMENT2_CLOSEOUT.md EXPERIMENT3_PREFLIGHT.md \
         outputs/CANONICAL_RESULTS.json outputs/SUPERSEDED.md \
         outputs/canonical/exp1_final.json "$BASELINE" \
         outputs/exp2_promotion.json outputs/exp2b_certification.json \
         outputs/repro_check.json; do
  if [ -s "$f" ]; then say "$f" "ok"; else say "$f" "FAIL — missing or empty"; fail=1; fi
done

echo
echo "--- the tree, after the checks wrote their artifacts ---"
AFTER="$(git ls-files -s | git hash-object --stdin 2>/dev/null || echo none)"
DIRTY="$(git status --porcelain)"
if [ -z "$DIRTY" ] && [ "$BEFORE" = "$AFTER" ]; then
  say "checks left tracked files untouched" "ok"
else
  say "checks left tracked files untouched" "FAIL — regenerated records differ"
  echo "      Running the preconditions rewrote tracked files, so this tag would"
  echo "      point at a commit that does NOT contain the records that just"
  echo "      passed. Commit these and re-run:"
  echo "$DIRTY" | head -8 | sed 's/^/        /'
  fail=1
fi

echo
if [ "$fail" -ne 0 ]; then
  echo "REFUSING to tag: $fail precondition(s) failed."
  echo "A tag that can be created while an input is still moving is not a freeze."
  exit 1
fi

git tag -a "$TAG" -m "$(cat <<MSG
The conservative-network era, frozen.

Experiments 1, 2 and 2B are closed. This tag is what Experiment 3 reports
against, and after it the Experiment 1-2 record is not edited except to correct
a discovered error.

  Experiment 1  outputs/canonical/exp1_final.json
  Experiment 2  outputs/exp2_promotion.json (nothing promoted)
  Experiment 2B outputs/exp2b_certification.json (certified null)
  closeout      EXPERIMENT2_CLOSEOUT.md
  baseline      $BASELINE
  gates         ACCEPTANCE.md
  Exp 3 rules   EXPERIMENT3_CONTRACT.md
  Exp 3 preflight EXPERIMENT3_PREFLIGHT.md
  what matters  outputs/CANONICAL_RESULTS.json
  what does not outputs/SUPERSEDED.md
  reproducible  outputs/repro_check.json
MSG
)"
echo "tagged $TAG at $(git rev-parse --short HEAD)"
echo "push it with: git push origin $TAG"
