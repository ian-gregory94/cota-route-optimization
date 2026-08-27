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

So the sandbox cannot push. What it *can* do is put the commits in the local
clone, fast-forward, and leave one button.

## The working loop

Local clone (kept current by the sandbox):

    C:\Users\ianjg\OneDrive\Documents\GitHub\cota-route-optimization

1. **Commit in the sandbox** as normal.
2. **Bundle the history** — one file, every ref, verifiable:

       git bundle create /mnt/user-data/outputs/cota.bundle --all
       git bundle verify /mnt/user-data/outputs/cota.bundle

3. **Deliver it** with `SendUserFile`, then `device_commit_files` the returned
   `file_uuid` to `C:\Users\ianjg\Downloads\cota.bundle`.
4. **Fast-forward the clone** over the device bridge:

       cd "$HOME/mnt/cota-route-optimization"
       git fetch "$HOME/mnt/Downloads/cota.bundle" \
           'refs/heads/master:refs/remotes/bundle/master'
       git merge --ff-only bundle/master

   Fetch into a *remote-tracking* ref, not into `master` itself: git refuses
   `refs/heads/master:refs/heads/master` on a non-bare repo with the checked-out
   branch, and the accompanying `Already up to date` from the merge makes it look
   like a no-op succeeded. On the very first import, where `HEAD` is unborn, use
   `git fetch ... 'refs/heads/master:refs/heads/master'` (legal while the branch
   does not exist), then `git symbolic-ref HEAD refs/heads/master` and
   `git reset --hard master`.

5. **Ian clicks Push** in GitHub Desktop. The credentials are his and never
   pass through the sandbox.

## Two gotchas that cost an hour each

**The mount forbids `unlink` by default**, so git cannot create or clear its
`.lock` files and fetch dies with `could not lock config file`. Grant deletion
for the folder (`device_request_delete_permission`) before any git write.
Watch for stale locks too — an eleven-hour-old zero-byte `.git/index.lock` was
blocking a fast-forward that otherwise computed fine.

**GitHub Desktop caches repository state** and will not notice a fast-forward
made underneath it. Clicking into the window refreshes it; switching repos in
the dropdown and back always does. In this session it was also granted in
*background app mode*, where synthetic clicks and keystrokes go to whatever is
actually focused — visible, not drivable.

## What the bundle does not carry

Only committed history. `data/raw/` (GTFS, LODES, CenPop, NTD — 38 MB) and
`data/cache/` (1.1 GB of pickled path sets) are gitignored. The cache is
rebuildable from the raw inputs; the raw inputs are re-downloadable from the
URLs and hashes in `config/sources.yaml`, and were also delivered as three
archives split under the 30 MiB upload cap.

## Next session

Attach the repository when the session is created, not after, and install the
Claude GitHub App at github.com/settings/installations with explicit access to
it. OAuth alone leaves private repos invisible even when settings read
"Connected".
