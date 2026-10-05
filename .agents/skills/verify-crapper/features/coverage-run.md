# Score with fresh coverage

A default `crapper` run measures coverage for each language it finds, reads the reports, and prints each function's coverage and CRAP score. Each collector clears the reports it writes before it runs (for TypeScript, also root `coverage/**/lcov.info` and each package's own `coverage/**/lcov.info`), and the run then reads only the LCOV, Go, and JaCoCo reports its collectors wrote. So when a collection writes nothing (its command fails, writes no report, or its tool is missing), that language scores 0%. A report the collectors don't write, such as a hand-made root `coverage.out` or a leftover `coverage/lcov.info` in a Rust package, is ignored and left on disk. A relative `SF:` path resolves against the module (Cargo package, Python project, or npm package) whose collector wrote the report.

## Sub-features

- `coverage-fresh` reads the report this run's coverage command wrote.
- `coverage-stale-failed` scores 0% when the coverage command fails and an earlier run's report is on disk.
- `coverage-stale-missing-tool` scores 0% when the language's coverage tool is missing and an earlier run's report is on disk.
- `coverage-leftover` ignores a report the collectors don't write: a leftover `coverage/lcov.info` in a Rust package doesn't override cargo-llvm-cov's fresh report, and stays on disk.

## How to get to it (user POV)

- Run `crapper` with no options from the project root.

## Driving it with verify-crapper

Preconditions:

- `$vc doctor` prints `doctor: ok`.
- `T` is the transcript path for the feature.

- **coverage-fresh.** `project=$($vc project typescript)`, then `$vc stale "$project" coverage/lcov.info src/clock.ts`, then `$vc drive "$project" "$T"`. Exit code `0`. stdout shows `> sh coverage.sh` and the row `tick  clock  1 100.0%  1.0`. Reports after lists `./coverage/lcov.info` with today's time, not the stale report's date two days ago.
- **coverage-stale-failed.** `project=$($vc project typescript-failing)`, then `$vc stale "$project" coverage/lcov.info src/clock.ts`, then `$vc drive "$project" "$T"`. stderr has `TypeScript coverage exited 1 in … TypeScript coverage will score 0%.` The row reads `tick  clock  1   0.0%  2.0`, and `.metrics/crap.edn` has `:coverage 0.0, :crap 2.0`. Reports after does not list the stale `./coverage/lcov.info`.
- **coverage-stale-missing-tool.** `project=$($vc project rust)`, then `$vc stale "$project" target/coverage/rust/lcov.info src/lib.rs`, then `$vc drive --path /usr/bin:/bin "$project" "$T"`. stderr has `Neither cargo-llvm-cov nor cargo-tarpaulin is installed`, `Coverage command failed to start`, and `Rust coverage will score 0%.` The row reads `tick  clock  1   0.0%  2.0`.
- **coverage-leftover.** Needs a real `cargo llvm-cov` (doctor's `rust:` line; export `MISE_RUST_VERSION` if it says so). `project=$($vc project rust-untested)`, then `$vc stale "$project" coverage/lcov.info src/lib.rs`, then `$vc drive "$project" "$T"`. Exit code `0`. The rows read `tick  clock  1 100.0%  1.0` and `tock  clock  1   0.0%  2.0`. Reports after lists `./coverage/lcov.info` with its two-days-ago time, and a fresh `./target/coverage/rust/lcov.info`.

## Gotchas

- Go and Java collectors write only into module folders they find (`<module>/target/coverage/go/coverage.out`, `<module>/target/site/jacoco/jacoco.xml`). With no `go.mod` or `pom.xml`, a default run reads no Go or Java report, and a root `coverage.out` or `target/site/jacoco/jacoco.xml` is ignored and kept. `--use-existing-coverage` and `--coverage-command` still read them.
- `--path /usr/bin:/bin` hides cargo, rustup, and cargo-llvm-cov on this machine (they live under mise). Without it, crapper finds or installs cargo-llvm-cov, and a real `cargo llvm-cov` run on the Rust fixture compiles for about a minute.
- crapper installs missing coverage tools: `@vitest/coverage-v8` into `node_modules`, `coverage` and `pytest` into the project's Python, and `cargo-llvm-cov` with `cargo install`. The TypeScript fixtures avoid all of these: their `coverage` script is plain `sh`.
- npm prints `> coverage` and `> sh coverage.sh` to stdout above the table.
