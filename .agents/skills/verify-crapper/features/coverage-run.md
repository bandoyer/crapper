# Score with fresh coverage

A default `crapper` run measures coverage for each language it finds, reads the reports, and prints each function's coverage and CRAP score. A report this run did not write is not this run's coverage: when a language's collection writes nothing (its command fails, writes no report, or its tool is missing), that language scores 0%.

## Sub-features

- `coverage-fresh` reads the report this run's coverage command wrote.
- `coverage-stale-failed` scores 0% when the coverage command fails and an earlier run's report is on disk.
- `coverage-stale-missing-tool` scores 0% when the language's coverage tool is missing and an earlier run's report is on disk.

## How to get to it (user POV)

- Run `crapper` with no options from the project root.

## Driving it with verify-crapper

Preconditions:

- `$vc doctor` prints `doctor: ok`.
- `T` is the transcript path for the feature.

- **coverage-fresh.** `project=$($vc project typescript)`, then `$vc stale "$project" coverage/lcov.info src/clock.ts`, then `$vc drive "$project" "$T"`. Exit code `0`. stdout shows `> sh coverage.sh` and the row `tick  clock  1 100.0%  1.0`. Reports after lists `./coverage/lcov.info` with today's time, not the stale report's date two days ago.
- **coverage-stale-failed.** `project=$($vc project typescript-failing)`, then `$vc stale "$project" coverage/lcov.info src/clock.ts`, then `$vc drive "$project" "$T"`. stderr has `TypeScript coverage exited 1 in … TypeScript coverage will score 0%.` The row reads `tick  clock  1   0.0%  2.0`, and `.metrics/crap.edn` has `:coverage 0.0, :crap 2.0`. Reports after does not list the stale `./coverage/lcov.info`.
- **coverage-stale-missing-tool.** `project=$($vc project rust)`, then `$vc stale "$project" target/coverage/rust/lcov.info src/lib.rs`, then `$vc drive --path /usr/bin:/bin "$project" "$T"`. stderr has `Neither cargo-llvm-cov nor cargo-tarpaulin is installed`, `Coverage command failed to start`, and `Rust coverage will score 0%.` The row reads `tick  clock  1   0.0%  2.0`.

## Gotchas

- `--path /usr/bin:/bin` hides cargo, rustup, and cargo-llvm-cov on this machine (they live under mise). Without it, crapper finds or installs cargo-llvm-cov, and a real `cargo llvm-cov` run on the Rust fixture compiles for about a minute.
- crapper installs missing coverage tools: `@vitest/coverage-v8` into `node_modules`, `coverage` and `pytest` into the project's Python, and `cargo-llvm-cov` with `cargo install`. The TypeScript fixtures avoid all of these: their `coverage` script is plain `sh`.
- npm prints `> coverage` and `> sh coverage.sh` to stdout above the table.
