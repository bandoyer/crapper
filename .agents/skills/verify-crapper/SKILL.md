---
name: verify-crapper
description: Drive this checkout's crapper CLI against a scratch project (a built-in TypeScript or Rust fixture, or a clone of a real repo) and capture proof (command, stdout, stderr, exit code, the coverage reports on disk before and after, the .metrics/crap.edn snapshot, and tracked files changed). Use to verify any crapper behaviour the way a user would see it, including which coverage reports a run reads.
---

# Verify crapper

crapper is a command-line CRAP scorer. The only surface is the `./crapper` launcher at the repo root. Run from a project root, it finds source files, runs each language's coverage tool, reads the coverage reports, prints a table worst score first, and writes `.metrics/crap.edn`. A drive never runs against a real project folder: every drive uses a scratch project, because a default run deletes and rewrites coverage reports in the project.

All commands below use the helper at `.agents/skills/verify-crapper/bin/verify-crapper`. Run it from the repo root; call it `vc` for short:

```bash
vc=.agents/skills/verify-crapper/bin/verify-crapper
```

Run every `$vc` command through skillflow's `bin/sandbox` when a caller asks for it (`$SANDBOX $vc doctor`). crapper runs project test commands, and the sandbox keeps a bad signal inside.

## Launch

There is no server and no build. `./crapper` creates `.venv` on first use. In a git worktree, create the worktree's own `.venv` (`python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`); never point it at another checkout's `.venv`, which imports that checkout's source.

It is ready when `$vc doctor` prints `doctor: ok`. Teardown is `$vc cleanup <project>` for each scratch project you made.

## Doctor

```bash
$vc doctor
```

It changes no project file. It fails if the launcher is missing, `./crapper --help` fails, or `.venv` imports `crapper` from anywhere but this checkout's `src/`. On success it prints the Python version, the imported path, the checkout's commit and branch (and whether `src/`, the launcher, or `pyproject.toml` have uncommitted changes), whether `npm` and `cargo-llvm-cov` are on `PATH`, and whether `cargo llvm-cov` runs in a scratch project. When it doesn't and cargo comes from mise, export `MISE_RUST_VERSION` (for example `1.98.0`) before a Rust drive.

## Drive

```bash
project=$($vc project typescript)            # tick in src/clock.ts; `npm run coverage` writes coverage/lcov.info with tick covered
project=$($vc project typescript-failing)    # same package; `npm run coverage` exits 1 and writes nothing
project=$($vc project rust)                  # tick in src/lib.rs, a Cargo package with one passing test in tests/
project=$($vc project ~/Work/bujo)           # or a fresh git clone of a real project (committed files only)
$vc stale "$project" coverage/lcov.info src/clock.ts     # leave an earlier run's report: every line covered, dated 2 days ago
$vc drive "$project" <transcript> [crapper args...]
$vc drive --path /usr/bin:/bin "$project" <transcript>   # hide tools installed outside /usr/bin, such as cargo and cargo-llvm-cov
$vc exec "$project" <transcript> <command> [args...]
```

`drive` runs this checkout's `./crapper <args...>` with the project as the working directory, exactly as a user would type it there. `exec` runs any other command the same way. Both append one block to `<transcript>` and also print it:

- the command, any `PATH` override, the date and time, the crapper commit, and the exit code
- the coverage reports on disk before the run (`lcov.info`, `coverage.out`, `jacoco.xml`, with modification times)
- stdout and stderr
- the coverage reports on disk after the run
- `.metrics/crap.edn`
- tracked files changed in the project (`(none)` when crapper left the source alone)

The features you can drive, and the end state that proves each one, are in [features/README.md](features/README.md).

## Evidence

- Put transcripts where the caller asks, for example `<run folder>/artifacts/verify/round-1/criterion-1.txt`. Never put them inside the scratch project: cleanup removes it.
- Proof is the transcript: the action (command), what the user saw (the table, stderr, exit code), and the side effects (reports before and after, the snapshot, tracked files). Check all three.
- Use the real user path only: the `./crapper` launcher with real arguments. Don't import `crapper` in Python, and don't treat `pytest` as proof.
- Exit codes: `0` analysis finished, `2` the worst CRAP score is above `--threshold`, `1` a usage error. A git failure under `--changed` exits with git's status.

## Cleanup

```bash
$vc cleanup "$project"
```

This removes only a scratch folder that `$vc project` created (`$TMPDIR/crapper-verify.*` or `/tmp/crapper-verify.*`), given as the project or the scratch folder itself, after resolving `..` and symlinks. It refuses any other path, including a folder inside the project. `drive`, `exec`, and `stale` likewise refuse a project outside a scratch folder, so a real checkout can't be driven by mistake. Transcripts stay where you wrote them.

## Helpers

`bin/verify-crapper` subcommands: `doctor`, `project typescript | typescript-failing | rust | <git repo>`, `stale <project> <report> <source>`, `drive [--path <PATH>] <project> <transcript> [crapper args...]`, `exec <project> <transcript> <command> [args...]`, `cleanup <project>`. Running it with no arguments prints usage.
