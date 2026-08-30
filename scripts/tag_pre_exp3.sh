#!/usr/bin/env bash
# Create the pre-exp3 tag, or refuse and say why.
#
# The tag marks the end of the conservative-network era: Experiments 1, 2 and 2B
# frozen, the baseline Experiment 3 must beat fixed and hashed, and the rules
# Experiment 3 will run under committed before it has seen anything. After this
# tag the Experiment 1-2 record is not edited except to correct a discovered
# error.
#
# Every precondition is checked here rather than remembered. A tag that can be
# created while an input is still moving is not a freeze.
set -u
cd "$(dirname "$0")/.."
TAG="${1:-pre-exp3-v1}"
fail=0

say() { printf '%-52s %s\n' "$1" "$2"; }

echo "=============================================================================="
echo "PRE-EXPERIMENT-3 TAG: $TAG"
echo "=============================================================================="

if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  say "tag does not already exist" "FAIL — $TAG is taken"
  fail=1
else
  say "tag does not already exist" "ok"
fi

if [ -z "$(git status --porcelain)" ]; then
  say "working tree clean" "ok"
else
  say "working tree clean" "FAIL — commit or stash first"
  git status --porcelain | head -5 | sed 's/^/      /'
  fail=1
fi

echo
echo "--- reproducibility ---"
if python3 scripts/repro_check.py > /tmp/repro.txt 2>&1; then
  say "all reproducibility checks pass" "ok"
else
  say "all reproducibility checks pass" "FAIL"
  grep -E "^  FAIL" /tmp/repro.txt | sed 's/^/      /'
  fail=1
fi

echo
echo "--- frozen baseline ---"
python3 scripts/build_exp3_baseline.py > /tmp/base.txt 2>&1
if grep -q "BLOCKERS" /tmp/base.txt; then
  say "pre_exp3_baseline_v1 has no blockers" "FAIL"
  sed -n '/BLOCKERS/,$p' /tmp/base.txt | sed 's/^/      /' | head -8
  fail=1
else
  say "pre_exp3_baseline_v1 has no blockers" "ok"
fi

echo
echo "--- required documents ---"
for f in ACCEPTANCE.md EXPERIMENT3_CONTRACT.md DISCOVERIES.md HANDOFF.md \
         README.md outputs/CANONICAL_RESULTS.json outputs/SUPERSEDED.md \
         outputs/canonical/exp1_final.json \
         outputs/canonical/pre_exp3_baseline_v1.json \
         outputs/exp2_promotion.json outputs/repro_check.json; do
  if [ -s "$f" ]; then say "$f" "ok"; else say "$f" "FAIL — missing or empty"; fail=1; fi
done

echo
if [ "$fail" -ne 0 ]; then
  echo "REFUSING to tag: $fail precondition(s) failed."
  echo "A tag that can be created while an input is still moving is not a freeze."
  exit 1
fi

git tag -a "$TAG" -m "$(cat <<'MSG'
The conservative-network era, frozen.

Experiments 1, 2 and 2B are closed. This tag is what Experiment 3 reports
against, and after it the Experiment 1-2 record is not edited except to correct
a discovered error.

  Experiment 1  outputs/canonical/exp1_final.json
  Experiment 2  outputs/exp2_promotion.json (nothing promoted)
  Experiment 2B outputs/exp2b_certification.json
  baseline      outputs/canonical/pre_exp3_baseline_v1.json
  gates         ACCEPTANCE.md
  Exp 3 rules   EXPERIMENT3_CONTRACT.md
  what matters  outputs/CANONICAL_RESULTS.json
  what does not outputs/SUPERSEDED.md
  reproducible  outputs/repro_check.json
MSG
)"
echo "tagged $TAG at $(git rev-parse --short HEAD)"
echo "push it with: git push origin $TAG"
