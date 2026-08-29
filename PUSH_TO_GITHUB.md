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

## Current state — 2026-08-29

Commit **`2ac3b1d`** ("Experiment 2B — enumerate the geometry subset space
instead of composing it") is committed in the sandbox, bundled, delivered, and
**already fetched into the local clone** at

    C:\Users\ianjg\source\repos\cota-route-optimization

as `refs/remotes/bundle/master`. `master` there is still at its parent
`2875f93`, because the fast-forward needs to replace tracked files and the
mount refuses `unlink` (see the gotcha below); the delete-permission request
that would fix it was declined by the session's permission layer, so it stays
declined rather than being worked around.

**None of that blocks the push.** Pushing a fetched ref never touches the index
or the working tree, so from a terminal where your credentials work:

    cd C:\Users\ianjg\source\repos\cota-route-optimization
    git push origin bundle/master:master

That puts `2ac3b1d` on GitHub. Bring the local checkout along afterwards, at
your convenience:

    git reset --hard bundle/master

If `git reset` also trips the unlink error, the clone's working tree is stale
but its history is not, and GitHub has the commit either way.

## The working loop

Local clone (kept current by the sandbox):

    C:\Users\ianjg\source\repos\cota-route-optimization

(The OneDrive clone at `Documents\GitHub\cota-route-optimization` is
abandoned at `8dc11e1` — OneDrive's file locking fought git for the `.git`
directory. Do not resume it.)

1. **Commit in the sandbox** as normal.
2. **Bundle the history** — one file, every ref, verifiable:

       git bundle create /mnt/user-data/outputs/cota.bundle --all
       git bundle verify /mnt/user-data/outputs/cota.bundle

3. **Deliver it** with `SendUserFile`, then `device_commit_files` the returned
   `file_uuid` to `C:\Users\ianjg\Downloads\cota.bundle`.
4. **Fast-forward the clone** over the device bridge:

       cd "$HOME/mnt/repos/cota-route-optimization"
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

5. **Ian pushes.** `git push origin bundle/master:master` from a terminal, or
   the Push button in GitHub Desktop. The credentials are his and never pass
   through the sandbox. Step 4 is a convenience; step 5 works without it,
   because `bundle/master` is a real ref as soon as the fetch lands.

## Two gotchas that cost an hour each

**The mount forbids `unlink`.** Git cannot clear its `.lock` files, and every
command that reads the index leaves a fresh zero-byte `.git/index.lock` behind
— which then blocks the next command that writes one. `git fetch` and
`git push` survive it (they touch refs and objects, not the index); `git merge`,
`git checkout` and `git reset` do not, and fail with `unable to unlink old
<path>` for each tracked file they need to replace. `device_request_delete_permission`
on the folder is the fix and needs a human to approve it; when it is declined,
push from the fetched ref instead of fast-forwarding first, and move stray
locks aside with `mv .git/index.lock .git/_stale/` rather than trying to delete
them.

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
