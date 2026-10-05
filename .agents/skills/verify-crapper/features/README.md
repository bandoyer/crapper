# crapper verification map

This folder is the maintained source for verifying what a crapper user sees. Read this index before driving the CLI, then use the matching feature file as the recipe.

## Baseline preconditions

- `$vc doctor` prints `doctor: ok` for the commit under test (`vc=.agents/skills/verify-crapper/bin/verify-crapper`), and its `imports:` line names this checkout's `src/`.
- Each recipe starts from a fresh scratch project from `$vc project`.
- No real project folder is driven. A real project is cloned first.

## Driving conventions

- Run every crapper command through `$vc drive <project> <transcript> <args...>`, and every other project command through `$vc exec`. The one exception is [install-minimum](./install-minimum.md), which runs crapper from another environment through `exec`.
- Leave an earlier run's report with `$vc stale`, never by editing files by hand, so the transcript's "reports before" section shows it.
- Treat every command as literal. Keep quoted text unchanged.
- A default run deletes and rewrites coverage reports, so a recipe that needs a report from an earlier run makes it right before the drive.

## Proof and skip reporting

- CLI proof is the transcript: command, exit code, reports before, stdout, stderr, reports after, `.metrics/crap.edn`, and tracked files changed.
- Read the score from both the table (`Cov%`, `CRAP`) and `.metrics/crap.edn` (`:coverage`, `:crap`).
- Record the feature ID with every transcript.
- Report an unreachable path with the attempted command and the unmet precondition.

## Features

- [Score with fresh coverage](./coverage-run.md) covers a default run: it measures coverage, clears an earlier run's reports first, reads only the reports its collectors wrote, and scores a language 0% when its collection wrote nothing.
- [Score with a custom coverage command](./coverage-command.md) covers `--coverage-command`: crapper runs the given command, then reads the reports on disk, combining reports that name the same file.
- [Score with existing coverage](./existing-coverage.md) covers `--use-existing-coverage`: it reads the reports already on disk, runs no coverage command, and deletes nothing.
- [Complexity only](./no-coverage.md) covers `--no-coverage`: coverage and CRAP are `N/A`.
- [Threshold](./threshold.md) covers `--threshold`: exit 2 when the worst score is above it.
- [A run with no source files](./empty-run.md) covers a full scan, a filter, or `--changed` that selects nothing: the snapshot becomes `{:entries []}`, and a failed run keeps it.
- [Install with the lowest dependencies](./install-minimum.md) covers running crapper with every direct dependency at the lowest version `pyproject.toml` allows.
