# A run with no source files

A successful run that selects no source files prints `No source files to analyze.`, exits 0, and replaces `.metrics/crap.edn` with an empty snapshot, `{:entries []}`. That holds for a full scan of a project with no sources, a filter that matches nothing, and `--changed` with nothing changed. A failed run, such as `--changed` outside a git repo, keeps the old snapshot.

## Sub-features

- `empty-full` the last source file is deleted; a full scan empties the snapshot.
- `empty-filter` a filter that matches no file empties the snapshot.
- `empty-changed` `--changed` with nothing changed empties the snapshot.
- `empty-git-error` `--changed` outside a git repo exits 128 and keeps the old snapshot.

## How to get to it (user POV)

- Run `crapper`, `crapper <filter>`, or `crapper --changed` in a project where it selects no source file.

## Driving it with verify-crapper

Preconditions:

- `$vc doctor` prints `doctor: ok`.
- `project=$($vc project typescript)`. `T` is the transcript path for the feature.
- Before each sub-feature, fill the snapshot with a real run: `$vc drive "$project" "$T" --no-coverage`. Its transcript shows `.metrics/crap.edn` naming `tick`.

- **empty-filter.** Run `$vc drive "$project" "$T" no-such-path`. Pass: exit `0`, stdout is `No source files to analyze.`, and the transcript's `.metrics/crap.edn` is `{:entries []}`.
- **empty-changed.** Run `$vc drive "$project" "$T" --changed`. Pass: the same as empty-filter.
- **empty-full.** Run `$vc exec "$project" "$T" git rm -q src/clock.ts`, then `$vc drive "$project" "$T"`. Pass: the same as empty-filter.
- **empty-git-error.** Run `$vc exec "$project" "$T" git checkout -q HEAD -- src/clock.ts`, fill the snapshot, then `$vc exec "$project" "$T" rm -rf .git` and `$vc drive "$project" "$T" --changed`. Pass: exit `128`, `not a git repository` on stderr, and `.metrics/crap.edn` still names `tick`.

## Gotchas

- The fixture's `.gitignore` lists `.metrics/` and `coverage/`, so the run's own output never counts as a change for `--changed`.
- An empty run stops before coverage, so no coverage command runs and the reports on disk are untouched.
