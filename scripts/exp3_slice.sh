#!/usr/bin/env bash
# Run ONE bounded slice of Experiment 3, then commit. Idempotent: run it again
# and it continues from wherever the checkpoint left off.
#
# This shape exists because of what actually kills work here. The sandbox is
# recycled when the session goes idle -- it happened at 20:42:45Z today, taking
# every background worker with it -- so a long-running detached job is not a
# thing this environment supports, whatever setsid says. The disk survives; the
# processes do not. Experiment 2 met the same wall and answered it with a
# supervisor that restarted from checkpoints all night; the supervisor log shows
# it doing exactly that at 21:11, 21:28, 21:56 and 22:10.
#
# So: work happens in slices short enough to finish inside a live tool call,
# every state is fsynced to disk the moment it lands, and every slice ends with
# a commit. The most that can ever be lost is the state in flight.
#
#   bash scripts/exp3_slice.sh [seconds]     # default 480 (8 minutes)
set -u
cd "$(dirname "$0")/.."
SECS="${1:-480}"
OUT=outputs/exp3

# Count UNIQUE states, not lines. The merged file and the shard files hold the
# same records, so `cat ... | wc -l` double-counts and reports progress that did
# not happen -- it claimed 18 states when 9 existed. A progress number that
# overstates is worse than none.
count_states() { python - <<'EOF'
import json, glob
seen = set()
for f in glob.glob("outputs/exp3/stageA_states*.jsonl"):
    for line in open(f):
        if line.strip():
            try: seen.add(json.loads(line)["state"])
            except Exception: pass
print(len(seen))
EOF
}
before=$(count_states)

# Phase A1's states are independent, so both cores run at once. Each shard
# stops cleanly BETWEEN states at the slice deadline -- a shard killed
# mid-state throws away up to 413 seconds of enumeration.
if [ ! -f "$OUT/.a1.done" ]; then
  for i in 0 1; do
    python scripts/exp3_stage_a.py --shard "$i/2" --deadline-seconds "$SECS" \
      >> "$OUT/stageA_shard$i.log" 2>&1 &
  done
  wait
  python scripts/exp3_merge_a1.py > "$OUT/merge.txt" 2>&1
  if grep -q '"complete": true' "$OUT/stageA_A1_merge.json" 2>/dev/null; then
    touch "$OUT/.a1.done"
    echo "PHASE A1 COMPLETE"
  fi
else
  # Phase A2 is a sequential search and is never sharded: its next state
  # depends on the previous one's score.
  python scripts/exp3_stage_a.py --deadline-seconds "$SECS" \
    >> "$OUT/stageA_a2.log" 2>&1
fi

after=$(count_states)
echo "slice: $before -> $after states"

# git is the only store that outlives the container. Commit every slice.
bash scripts/presweep.sh > /dev/null 2>&1
git add -A
git diff --cached --quiet || git commit -q -m "chore: Experiment 3 stage A slice — $after states checkpointed

Committed at the slice boundary because the container is recycled on idle and
the disk is not a durable store. The most a recycle can cost is the state in
flight."
echo "committed: $(git log --oneline -1)"
