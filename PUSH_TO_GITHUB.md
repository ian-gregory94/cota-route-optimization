# Getting commits from the sandbox onto GitHub

The research runs in an ephemeral cloud sandbox. Its git history has to reach
`github.com/ian-gregory94/cota-route-optimization`, and there is no direct path:

* **The session's GitHub token is bound to repositories configured when the
  session was created.** Nothing can be added mid-session — no picker, no
  setting, no `add_repo` tool (the proxy's own 403 text suggests one; it does
  not exist in the session's tool registry). Every call for this repo returns
  `GitHub access to this repository is not enabled for this session`.
* **That token is an API token, not a git credential.** `git push` with it
  returns `Password authentication is not supported for Git operations`.
* **The device bridge's Linux VM can reach GitHub** — `git ls-remote` against a
  public repo succeeds — **but holds no credentials**, and a push there ends at
  `could not read Username for 'https://github.com'`.

So the sandbox cannot push. The loop below routes around it entirely.

## The loop that works — established 2026-08-29

Nothing in the sandbox and nothing behind the folder bridge holds a git
credential, so neither can push. **GitHub Desktop has its own token and can.**
Every step below has been run end to end.

1. **Commit in the sandbox** as normal.
2. **Bundle only what the clone is missing** — incremental, so it is kilobytes
   rather than megabytes:

       git bundle create /home/claude/cota-<sha>.bundle <their-head>..HEAD --branches
       git bundle verify  /home/claude/cota-<sha>.bundle

3. **Deliver it**: `SendUserFile`, then `device_commit_files` the returned
   `file_uuid` to `C:\Users\ianjg\Downloads\cota-<sha>.bundle`.
4. **Fetch it into a local branch** over the bridge — refs and objects only, no
   index, no working tree, so the mount's `unlink` refusal does not bite:

       cd "$HOME/mnt/repos/cota-route-optimization"
       git fetch "$HOME/mnt/Downloads/cota-<sha>.bundle" \
           'refs/heads/master:refs/remotes/bundle/master'
       git branch -f frombundle refs/remotes/bundle/master

5. **Clear the stale locks the bridge leaves behind** — every git command run
   over the mount creates `.git/index.lock` and cannot remove it, and the next
   command then dies on `A lock file already exists`. Move them, do not try to
   delete them:

       mkdir -p .git/_stale
       for f in .git/*.lock; do [ -e "$f" ] && mv "$f" ".git/_stale/$(basename $f).$(date +%s%N)"; done

   Run this as the **last** bridge command before touching Desktop; any git
   command after it recreates the lock.
6. **In GitHub Desktop**: `Ctrl+Shift+M` → `frombundle` → merge. It fast-forwards
   (Desktop labels the button "Create a merge commit" regardless). Desktop's git
   runs natively on Windows and is not subject to the mount's restrictions.
7. **Push origin.** Done.

The clone Desktop uses is

    C:\Users\ianjg\source\repos\cota-route-optimization

added to Desktop with `Ctrl+O`. The OneDrive clone at
`Documents\GitHub\cota-route-optimization` is abandoned at `8dc11e1` —
OneDrive's file locking fought git for the `.git` directory. Do not resume it.

### Things that look like failures and are not

* **`git push` from Git Bash returns `Repository not found`.** That shell's
  credential cannot see the repo, and GitHub answers 404 rather than 403 for a
  private repo. It is not evidence the repository is missing. Use Desktop.
* **A clone built from a bundle has no `origin/*` refs at all.** That means it
  has never talked to GitHub — not that GitHub has nothing. Check
  `git ls-remote` or Desktop's fetch before concluding anything.
* **The bridge's `git status` prints `unable to unlink .git/index.lock` and
  still exits 0.** Reads work; writes to the working tree do not.

### What the bundle does not carry

Only committed history. `data/raw/` (GTFS, LODES, CenPop, NTD — 38 MB) and
`data/cache/` (pickled path sets, now ~2 GB) are gitignored. The cache is
rebuildable from the raw inputs; the raw inputs are re-downloadable from the
URLs and hashes in `config/sources.yaml`.

## Next session

Attach the repository when the session is created, not after, and install the
Claude GitHub App at github.com/settings/installations with explicit access to
it. OAuth alone leaves private repos invisible even when settings read
"Connected".

---

## Amendment, 2026-09-21 — two traps found during the Exp 4 audit push

**Use the right clone.** There are two on the machine and earlier versions of
this document named the wrong one:

* `C:\Users\ianjg\OneDrive\Documents\GitHub\cota-route-optimization` — **current,
  use this one.**
* `C:\Users\ianjg\source\repos\cota-route-optimization` — **stale**, 350 commits
  behind `origin/exp3-clean` as of 2026-09-21.

Both point at the same `origin`. Pushing from the stale one pushes nothing
useful and quietly succeeds.

**The bridge VM cannot delete files.** `rm`, `rmdir` and `unlink` return
`Operation not permitted` on anything under a mounted folder. Git does not care
that it lacks permission — it creates `.git/index.lock`, fails to remove it, and
prints only a warning:

    warning: unable to unlink '.git/index.lock': Operation not permitted

The command appears to succeed. **Every subsequent GitHub Desktop operation then
reports the repository as locked**, which is what "its locked" means when it
comes back from the machine. `git fetch` also strands
`.git/objects/pack/tmp_pack_*` and `tmp_idx_*` files the same way; 26 had
accumulated before anyone noticed.

The fix, since deletion is unavailable:

    mkdir -p _to_delete/gitlocks
    mv .git/index.lock .git/objects/maintenance.lock _to_delete/gitlocks/
    for f in .git/objects/pack/tmp_*; do mv "$f" _to_delete/gitlocks/; done

`mv` is a rename and **is** permitted. Then `git fsck --connectivity-only` to
confirm nothing was harmed, and tell Ian the `_to_delete/` folder is his to
remove. `device_request_delete_permission` exists and would prompt him for real
deletion rights, but `mv` costs him nothing and answers the same need.

**A fast-forward push does not need a checkout.** Fetch the bundle into a
tracking ref, move the local branch, let Desktop push:

    git fetch <bundle> 'refs/heads/exp3-clean:refs/remotes/cloud/exp3-clean'
    git merge-base --is-ancestor exp3-clean refs/remotes/cloud/exp3-clean   # verify FF
    git branch -f exp3-clean refs/remotes/cloud/exp3-clean
    git branch --set-upstream-to=origin/exp3-clean exp3-clean

This never touches the index or the working tree, so the 23 CRLF-noise files
stay untouched and no `index.lock` is needed for the branch move itself.
