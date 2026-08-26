# Pushing this repo to your GitHub

The repo already has full git history (11 commits, clean tree). I can't push it
myself — this session's GitHub token is scoped to pre-configured repos only, and
the machine bridge has no SSH key or credential helper, so a push would mean
handling a personal access token, which I don't do.

Three commands from you and it's up.

## 1. Create the empty repo

Either on github.com (New repository -> name it `columbus-transit-opt`, **do not**
add a README, .gitignore, or license — the repo already has them), or with the
GitHub CLI:

```bash
gh repo create columbus-transit-opt --private --source=. --remote=origin --push
```

If you use `gh` that's the whole job — skip to step 3 to verify.

## 2. Point this repo at it and push

```bash
cd columbus-transit-opt
git remote add origin https://github.com/<your-username>/columbus-transit-opt.git
git push -u origin main
```

## 3. Verify

```bash
git log --oneline
gh repo view --web    # or just open the URL
```

## What is and isn't in the repo

Tracked: all source (`src/`), tests (`tests/`, 127 passing), scripts, configs,
docs, and the small committed outputs.

Deliberately untracked (see `.gitignore`): `data/raw/`, `data/interim/`,
`data/processed/`, `data/cache/` (123 MB of memoised RAPTOR path sets), and
per-experiment artifact directories. Everything under `data/` is reproducible —
`scripts/fetch_gtfs.py` and `config/sources.yaml` record where each input came
from, and the cache rebuilds itself on first run. This is intentional: the
provenance rule in `AGENTS.md` is that inputs are re-fetched from their recorded
source rather than committed as opaque blobs.

The two LEHD LODES files and the NTD profile PDF you downloaded manually are
also untracked, for the same reason — `config/sources.yaml` has their URLs.
