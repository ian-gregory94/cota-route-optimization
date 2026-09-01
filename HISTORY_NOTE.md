# Experiment 3 — freeze and history condensation

*Written outside the frozen tree on purpose. Adding it to `exp3-clean` would
make that branch's tree differ from `exp3`, and tree identity takes priority.
Place it on `master`, outside the frozen equivalence boundary.*

## The branches and what each one is for

| ref | commit | what it is |
|---|---|---|
| `exp3-frozen-v1` | `80221f75` | **The immutable scientific freeze point.** Not moved, not rewritten. |
| `exp3` | `e162d24b` | **The archival research history** — 2,698 commits since `b014c26c`, every slice of every batch. The audit trail. |
| `exp3-clean` | `c875fa66` | **The condensed representation** — 94 commits since the same base. Human-facing, and the branch to merge forward. |

Experiment 3 was **frozen before** the history was condensed. Nothing about the
condensation could reach the science, and the artifacts prove it rather than
asserting it.

## The final tree is byte-identical

```
exp3^{tree}        2c26132d4782522b4e5c13909e8a850911896869
exp3-clean^{tree}  2c26132d4782522b4e5c13909e8a850911896869
git diff --exit-code exp3 exp3-clean   ->  0
```

Every commit id since the base changed; **zero** ids are shared between the two
branches. The trees are the same object.

That is true by construction, not by luck: the collapse reuses the *original
tree objects* via `git commit-tree` rather than checking files out and
re-committing them, which would have introduced another way for content to
change.

## The freeze is verified independently of git

`outputs/exp3/FREEZE_MANIFEST.json` records **content hashes, not commit ids** —
precisely so a history rewrite cannot invalidate it and cannot be laundered
through it. `python scripts/exp3_freeze.py --verify` re-checks, from
`exp3-clean`:

* source digest `src-74b02d24b77f`
* contract digest `00c0953c95a96ffd`
* 20 / 20 frozen artifact SHA-256 hashes
* 87 / 87 receipt digests

All pass. The verifier was deliberately proven able to fail — appending one
newline to `gap_report.json` makes it report the change and refuse — before it
was relied on.

The full test suite is green from `exp3-clean`, and the working tree is clean
after running it.

## The one expected difference from the tag

`git diff --stat exp3-frozen-v1..exp3` shows exactly one file:

```
scripts/exp3_freeze.py | 55 ++++++++++++++++++++++++++++++
```

That is commit `e162d24b`, **post-freeze verification infrastructure**. It
touches no frozen artifact and sits outside the `code_version` hashed path, so
the source digest is unchanged. It exists to verify the freeze at `80221f75`,
and it is preserved as its own commit in the condensed history rather than
absorbed into a checkpoint — stranding the verifier on the archival branch
would have made the human-facing branch less auditable for no scientific gain.

## The history map

`EXP3_HISTORY_MAP.json` links every condensed commit to the original commit or
span it represents: new SHA, original first and last SHA, how many commits were
collapsed, and whether it is a preserved substantive commit (56) or a
checkpoint (38). Two entries carry notes — the frozen state, and the
post-freeze verifier.

It is provenance only. **No frozen artifact was modified to record the new
ids**; the freeze uses content hashes exactly so it stays independent of them.

## What was collapsed, and what was not

Runs of consecutive `chore:` loop commits became one checkpoint each — the
largest absorbing 892 commits, which were re-score slices differing only in one
more state having been scored. Every substantive commit stayed individually
addressable: the discoveries, the decisions, the contract changes, the
operations rules.

The condensed history is meant to explain the research, not merely to be
smaller.
