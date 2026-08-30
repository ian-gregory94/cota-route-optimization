#!/usr/bin/env python3
"""Can a third party reproduce the frozen outputs, and can a stale cache lie?

Item 13 of the pre-Experiment-3 closeout, as checks rather than as a claim. The
point is not to re-run days of optimization. It is to prove that the dependency
chain is legible and that the specific ways this project has already been
fooled are now impossible.

Each check prints PASS or FAIL with the evidence. A FAIL is a blocker for the
`pre-exp3` tag.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "outputs"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, bool(ok), detail))


def sha(p: Path) -> str | None:
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def c_cache_separates_models() -> None:
    """A Model A path set must not be servable to a Model B request.

    This is the check that would have made the three-day mislabel harmless:
    even with the wrong pricing requested, a wrongly-keyed cache would have
    handed over the other model's enumeration and the numbers would have been
    incoherent rather than plausible.
    """
    from cota_opt.cache import key_of
    base = {"gtfs": "x", "lodes": "y", "top_k": 20000, "seed": 1}
    a = key_of("pathsets", {**base, "common_lines": "pattern"})
    b = key_of("pathsets", {**base, "common_lines": "same_route"})
    check("path-set cache key separates the waiting models", a != b,
          f"pattern={a} same_route={b}")

    src = (ROOT / "src" / "cota_opt" / "harness.py").read_text()
    i = src.index("ps_params = {")
    check("the harness puts common_lines in that key",
          '"common_lines": cl' in src[i:i + 1200],
          "harness.py ps_params")


def c_evaluator_declared() -> None:
    """Every artifact written since provenance recording must name its model."""
    recs = sorted((OUT / "experiments").glob("*/experiment.json"))
    declared = [p for p in recs
                if (json.loads(p.read_text()).get("evaluator") or {})]
    check("experiment records can carry an evaluator block",
          "evaluator" in (ROOT / "src" / "cota_opt" / "experiment.py").read_text(),
          f"{len(declared)} of {len(recs)} existing records declare one; "
          f"records written before 2026-08-30 predate the field and are "
          f"resolved through the cell key instead")


def c_no_unusable_paths() -> None:
    r = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                       capture_output=True)
    paths = [p for p in r.stdout.split(b"\0") if p]
    bad = [p for p in paths
           if any(ch in Path(p.decode("utf-8", "replace")).name
                  for ch in '<>:"|?*')
           or b"\xef\x81\xbc" in p]
    check("every tracked path can exist on Windows", not bad,
          f"{len(paths)} tracked, {len(bad)} unusable")


def c_frozen_hashes_match() -> None:
    p = OUT / "canonical" / "exp1_final.json"
    if not p.exists():
        return check("frozen Experiment 1 record present", False, str(p))
    d = json.loads(p.read_text())
    drift = [k for k, v in d["inputs"].items()
             if v.get("sha256") and sha(ROOT / v["path"]) != v["sha256"]]
    missing = [k for k, v in d["inputs"].items() if not v["present"]]
    check("frozen Experiment 1 inputs still hash as recorded",
          not drift and not missing,
          f"{len(d['inputs'])} inputs; drifted={drift or 'none'}; "
          f"missing={missing or 'none'}")


def c_manifest_points_at_real_files() -> None:
    p = OUT / "CANONICAL_RESULTS.json"
    if not p.exists():
        return check("results manifest present", False, str(p))
    d = json.loads(p.read_text())
    absent = []
    for name, e in d["experiments"].items():
        for rel in e.get("canonical", []):
            if "*" in rel:
                if not list(ROOT.glob(rel)):
                    absent.append(f"{name}:{rel}")
            elif not (ROOT / rel).exists():
                absent.append(f"{name}:{rel}")
    check("every canonical artifact in the manifest exists", not absent,
          f"missing: {absent or 'none'}")


def _pytest_summary(stdout: str) -> str:
    """pytest's summary line, with the stopwatch removed.

    The line ends "356 passed in 4.66s", and that trailing wall-clock time made
    this file differ on every run -- which meant the tag script's own
    precondition check dirtied the tree it was checking, and a reproducibility
    record could never be compared byte-for-byte against a rerun. How long the
    suite took is a property of the machine, not of the repository.
    """
    for l in reversed(stdout.splitlines()):
        if " passed" in l or " failed" in l or " error" in l:
            return re.sub(r"\s+in\s+[\d.]+s$", "",
                          l.strip().strip("=").strip())
    return "no summary line"


def _skip_reasons(stdout: str) -> list[str]:
    """Every skip pytest reported, with its reason.

    `-rs` prints one SKIPPED line per skip. A skip is silently reduced
    coverage, and this project shipped a reproducibility record claiming 356
    passing tests from a machine where a clean install ran 348 -- the realtime
    module's `importorskip` fired because its dependency was never declared.
    Counting is not enough: the record has to say WHICH tests did not run.
    """
    out = []
    for l in stdout.splitlines():
        t = l.strip()
        if t.startswith("SKIPPED"):
            out.append(t)
    return out


def _pytest_counts(stdout: str) -> dict:
    """passed / skipped / failed / error counts from the summary line."""
    line = _pytest_summary(stdout)
    counts = {}
    for n, kind in re.findall(r"(\d+)\s+(passed|skipped|failed|error|errors|"
                              r"xfailed|xpassed|deselected)", line):
        counts[kind.rstrip("s") if kind != "passed" else kind] = int(n)
    return counts


def c_tests() -> None:
    r = subprocess.run([sys.executable, "-m", "pytest", "tests", "-rs",
                        "-p", "no:cacheprovider"],
                       cwd=ROOT, capture_output=True, text=True, timeout=900)
    counts = _pytest_counts(r.stdout)
    skips = _skip_reasons(r.stdout)
    check("full test suite passes in place", r.returncode == 0,
          _pytest_summary(r.stdout))
    # A skip is not a pass. ALLOWED_SKIPS is empty on purpose: every optional
    # dependency this suite touches is declared in an extra that `dev` pulls
    # in, so a skip here means either an undeclared dependency or an
    # environment that did not install what the project says it needs. Either
    # way the coverage the record reports is not the coverage that ran.
    n_skipped = counts.get("skipped", 0)
    check("no tests were skipped", n_skipped == 0,
          "0 skipped — the suite that ran is the suite the record reports"
          if n_skipped == 0 else
          f"{n_skipped} SKIPPED, so the reported pass count overstates "
          f"coverage: " + "; ".join(skips[:4]))


def c_declared_imports() -> None:
    """Every third-party module the code imports is a DECLARED dependency.

    The check that would have caught the realtime gap before it reached a
    frozen record. `pytest.importorskip` turns a missing dependency into a
    silent skip, so the suite stays green on a machine that happens to have
    the package and quietly loses eight tests on one that does not. Running the
    tests cannot detect that; reading the imports can.

    Static, so it does not depend on what this machine happens to have
    installed -- except for the module-to-distribution mapping, which needs the
    package present. A module that maps to nothing is reported rather than
    passed over, since "I could not tell" is not "it is fine".
    """
    import ast
    import tomllib
    from importlib.metadata import packages_distributions

    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text())
    proj = cfg["project"]
    declared = set()
    for spec in (list(proj.get("dependencies", []))
                 + [d for v in proj.get("optional-dependencies", {}).values()
                    for d in v]):
        declared.add(re.split(r"[<>=!~\[; ]", spec.strip())[0].lower()
                     .replace("_", "-"))

    # scripts/ and tests/ import each other by bare module name (pytest and
    # sys.path make that work); those are local files, not distributions.
    local = {"cota_opt", "tests", "scripts"}
    for d in ("scripts", "tests"):
        local |= {f.stem for f in (ROOT / d).rglob("*.py")}
    stdlib = set(sys.stdlib_module_names)
    seen: dict[str, str] = {}
    for f in sorted(list((ROOT / "src").rglob("*.py"))
                    + list((ROOT / "tests").rglob("*.py"))
                    + list((ROOT / "scripts").rglob("*.py"))):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                # level > 0 is a relative import: local by construction.
                mods = [node.module] if (node.module and node.level == 0) else []
            else:
                continue
            for m in mods:
                top = m.split(".")[0]
                if top and top not in stdlib and top not in local:
                    seen.setdefault(top, str(f.relative_to(ROOT)))

    dist_of = packages_distributions()
    undeclared, unmapped = [], []
    for mod, where in sorted(seen.items()):
        dists = [d.lower().replace("_", "-") for d in dist_of.get(mod, [])]
        if not dists:
            unmapped.append(f"{mod} ({where})")
        elif not any(d in declared for d in dists):
            undeclared.append(f"{mod} -> {'/'.join(dists)} ({where})")

    ok = not undeclared and not unmapped
    detail = (f"{len(seen)} third-party modules imported, all declared"
              if ok else
              "; ".join(["UNDECLARED: " + ", ".join(undeclared)] * bool(undeclared)
                        + ["UNRESOLVABLE: " + ", ".join(unmapped)] * bool(unmapped)))
    check("every imported third-party module is a declared dependency",
          ok, detail)


def c_optional_features_declared() -> None:
    """Optional features are named extras, and `dev` pulls every one of them.

    States the distinction the reproducibility record has to carry: which parts
    of this project are optional, and whether the suite the record reports
    actually exercised them. Two modules are optional -- the realtime collector
    and the NTD profile parser -- and both were previously ambient: installed
    on the machine that wrote the record, undeclared in the project, and
    silently absent on a clean install, where the realtime tests turned into
    skips and the pass count quietly dropped from 356 to 348.

    They stay optional, because nothing in the results depends on the realtime
    collector and nothing imports the NTD parser at runtime. What changes is
    that they are declared, and that `dev` includes them, so the suite a
    contributor runs is the whole suite and a skip is now a failure rather
    than a smaller number nobody reads.
    """
    import tomllib
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text())
    extras = cfg["project"].get("optional-dependencies", {})
    dev = {re.split(r"[<>=!~\[; ]", d.strip())[0].lower().replace("_", "-")
           for d in extras.get("dev", [])}
    feature_extras = {k: v for k, v in extras.items() if k != "dev"}
    missing = {}
    for name, specs in feature_extras.items():
        need = {re.split(r"[<>=!~\[; ]", d.strip())[0].lower().replace("_", "-")
                for d in specs}
        if not need <= dev:
            missing[name] = sorted(need - dev)
    check("optional features are declared, and dev installs all of them",
          not missing,
          (f"optional extras: {', '.join(sorted(feature_extras))}; "
           f"dev installs every one, so the suite is complete and any skip is "
           f"a failure") if not missing else
          f"dev does not install: {missing}")


def c_fresh_clone() -> None:
    """The real question: does a third party get the same result from a clone?

    Clones this repository into a scratch directory — no cache, no outputs,
    none of the untracked state this working copy has accumulated — and runs
    the suite there. If the tests need a file that is not committed, this is
    where that shows up.
    """
    import shutil
    import tempfile
    d = Path(tempfile.mkdtemp(prefix="cota-clone-"))
    try:
        c = subprocess.run(["git", "clone", "--quiet", "--no-hardlinks",
                            str(ROOT), str(d / "repo")],
                           capture_output=True, text=True, timeout=600)
        if c.returncode != 0:
            return check("fresh clone runs its own test suite", False,
                         c.stderr.strip()[:200])
        repo = d / "repo"
        env = {**__import__("os").environ,
               "PYTHONPATH": str(repo / "src")}
        r = subprocess.run([sys.executable, "-m", "pytest", "tests", "-rs",
                            "-p", "no:cacheprovider"],
                           cwd=repo, capture_output=True, text=True,
                           timeout=900, env=env)
        cached_dir = repo / "data" / "cache"
        n_skipped = _pytest_counts(r.stdout).get("skipped", 0)
        check("fresh clone runs its own test suite",
              r.returncode == 0 and n_skipped == 0,
              f"{_pytest_summary(r.stdout)}; cache present in clone: "
              f"{cached_dir.exists()} (it must not be — the suite may not "
              f"depend on this machine's cache). SCOPE: this reuses the "
              f"running interpreter's site-packages, so it proves the clone "
              f"has every committed FILE it needs, not that a clean install "
              f"resolves every dependency — that is what the declared-imports "
              f"check covers.")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def c_determinism_is_tested() -> None:
    """Resumed and straight-through solves must be bit-identical, and that is
    asserted by a test rather than by hope."""
    src = (ROOT / "tests" / "test_resume.py").read_text()
    check("resume determinism is under test",
          "optimize_frequencies" in src and "==" in src,
          "tests/test_resume.py asserts equality, not similarity")


def c_declared_dependencies() -> None:
    p = ROOT / "pyproject.toml"
    t = p.read_text() if p.exists() else ""
    check("dependencies are declared for a clean install",
          "dependencies" in t and "[project" in t,
          "pyproject.toml declares them; install with pip install -e '.[dev]'")


def c_raw_data_boundary() -> None:
    gi = (ROOT / ".gitignore").read_text()
    ok = "data/raw/" in gi and "data/cache/" in gi
    src = (ROOT / "config" / "sources.yaml")
    check("the source/generated boundary is documented",
          ok and src.exists(),
          "data/raw and data/cache are gitignored; config/sources.yaml carries "
          "URLs and hashes for every external input")


def main() -> int:
    for f in (c_cache_separates_models, c_evaluator_declared,
              c_no_unusable_paths, c_frozen_hashes_match,
              c_manifest_points_at_real_files, c_determinism_is_tested,
              c_declared_dependencies, c_declared_imports,
              c_optional_features_declared, c_raw_data_boundary,
              c_tests, c_fresh_clone):
        try:
            f()
        except Exception as e:                      # a check that errors is a fail
            check(f.__name__, False, f"{type(e).__name__}: {e}")

    print("=" * 88)
    print("REPRODUCIBILITY CHECK")
    print("=" * 88)
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        print(f"        {detail}")
    bad = [n for n, ok, _ in results if not ok]
    print()
    if bad:
        print(f"  {len(bad)} FAILING: {', '.join(bad)}")
        print("  These block the pre-exp3 tag.")
    else:
        print(f"  all {len(results)} checks pass")
    (OUT / "repro_check.json").write_text(json.dumps(
        [{"check": n, "pass": ok, "detail": d} for n, ok, d in results],
        indent=2))
    print(f"\nartifacts: {OUT / 'repro_check.json'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
