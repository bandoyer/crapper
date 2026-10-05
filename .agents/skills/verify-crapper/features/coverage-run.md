# Score with fresh coverage

A default `crapper` run measures coverage for each language it finds, reads the reports, and prints each function's coverage and CRAP score. Each collector clears the reports it writes before it runs (for TypeScript, also root `coverage/**/lcov.info` and each package's own `coverage/**/lcov.info`), and the run then reads only the LCOV, Go, and JaCoCo reports its collectors wrote. So when a collection writes nothing (its command fails, writes no report, or its tool is missing), that language scores 0%. A report the collectors don't write, such as a hand-made root `coverage.out` or a leftover `coverage/lcov.info` in a Rust package, is ignored and left on disk. A relative `SF:` path resolves against the module (Cargo package, Python project, or npm package) whose collector wrote the report. Each source file is matched to its report by its path under the project root (`--root`), never under the folder the user runs crapper from.

## Sub-features

- `coverage-fresh` reads the report this run's coverage command wrote.
- `coverage-stale-failed` scores 0% when the coverage command fails and an earlier run's report is on disk.
- `coverage-stale-missing-tool` scores 0% when the language's coverage tool is missing and an earlier run's report is on disk.
- `coverage-leftover` ignores a report the collectors don't write: a leftover `coverage/lcov.info` in a Rust package doesn't override cargo-llvm-cov's fresh report, and stays on disk.
- `coverage-root-from-member` scores the same from a member crate's folder with `--root ..` as from the workspace root: each crate gets its own report's lines.
- `coverage-python-root` measures a Python file at the project root, alone or beside a package folder: crapper passes coverage.py `--source=.` for it, never the file's name.
- `coverage-root-sibling-report` picks the right file from a report that names a sibling crate's `src/lib.rs` at the same depth, run from outside `--root`.

## How to get to it (user POV)

- Run `crapper` with no options from the project root, or `crapper --root <project>` from another folder.

## Driving it with verify-crapper

Preconditions:

- `$vc doctor` prints `doctor: ok`.
- `T` is the transcript path for the feature.

- **coverage-fresh.** `project=$($vc project typescript)`, then `$vc stale "$project" coverage/lcov.info src/clock.ts`, then `$vc drive "$project" "$T"`. Exit code `0`. stdout shows `> sh coverage.sh` and the row `tick  clock  1 100.0%  1.0`. Reports after lists `./coverage/lcov.info` with today's time, not the stale report's date two days ago.
- **coverage-stale-failed.** `project=$($vc project typescript-failing)`, then `$vc stale "$project" coverage/lcov.info src/clock.ts`, then `$vc drive "$project" "$T"`. stderr has `TypeScript coverage exited 1 in … TypeScript coverage will score 0%.` The row reads `tick  clock  1   0.0%  2.0`, and `.metrics/crap.edn` has `:coverage 0.0, :crap 2.0`. Reports after does not list the stale `./coverage/lcov.info`.
- **coverage-stale-missing-tool.** `project=$($vc project rust)`, then `$vc stale "$project" target/coverage/rust/lcov.info src/lib.rs`, then `$vc drive --path /usr/bin:/bin "$project" "$T"`. stderr has `Neither cargo-llvm-cov nor cargo-tarpaulin is installed`, `Coverage command failed to start`, and `Rust coverage will score 0%.` The row reads `tick  clock  1   0.0%  2.0`.
- **coverage-leftover.** Needs a real `cargo llvm-cov` (doctor's `rust:` line; export `MISE_RUST_VERSION` if it says so). `project=$($vc project rust-untested)`, then `$vc stale "$project" coverage/lcov.info src/lib.rs`, then `$vc drive "$project" "$T"`. Exit code `0`. The rows read `tick  clock  1 100.0%  1.0` and `tock  clock  1   0.0%  2.0`. Reports after lists `./coverage/lcov.info` with its two-days-ago time, and a fresh `./target/coverage/rust/lcov.info`.

- **coverage-root-from-member.** Needs a real `cargo llvm-cov`. `project=$($vc project rust-workspace)`, then `$vc drive "$project/gears" "$T" --root ..`. Exit code `0`. The rows read `tick  clock  1 100.0%  1.0`, `tock  clock  1   0.0%  2.0`, `idle  gears  1   0.0%  2.0`, and `spin  gears  1 100.0%  1.0`, the same as `$vc drive "$project" "$T"` from the root. `.metrics/crap.edn` (the workspace root's, listed first) has the same four scores.
- **coverage-root-sibling-report.** Needs a real `cargo llvm-cov`. `project=$($vc project rust-siblings)`, then `$vc drive "$project" "$T" --root clock --coverage-command 'mkdir -p target/coverage/rust && cargo llvm-cov --workspace --lcov --output-path "$PWD/target/coverage/rust/lcov.info"'`. Exit code `0`. The report under `clock/target/coverage/rust/` names both `clock/src/lib.rs` and `gears/src/lib.rs`. The rows read `tick  clock  1 100.0%  1.0` and `tock  clock  1   0.0%  2.0`, and the snapshot headed `(./clock/.metrics/crap.edn)` has `:coverage 100.0` for `tick` and `:coverage 0.0` for `tock`.
- **coverage-python-root.** Needs a `python3` with coverage.py and pytest (the fixture's `.venv` uses its packages). `project=$($vc project python-flat)`, then `$vc drive "$project" "$T"`. Exit code `0`. stderr shows the `coverage run` command with `--source=.`, and has no `never imported` warning and no `Python coverage will score 0%.` The rows read `tick  demo  1 100.0%  1.0`, `tock  demo  1  50.0%  1.1` (only its `def` line runs, at import), and `unused  extra  1   0.0%  2.0`. Reports after lists `./target/coverage/python/lcov.info`. Then `project=$($vc project python-mixed)` and the same drive: `--source=.,gears`, the same three rows, and `spin  gears.spin  1 100.0%  1.0`. The bug (#3) shows as `--source=demo.py,extra.py`, `coverage lcov exited 1`, and `tick` at `0.0%`.

## Gotchas

- Go and Java collectors write only into module folders they find (`<module>/target/coverage/go/coverage.out`, `<module>/target/site/jacoco/jacoco.xml`). With no `go.mod` or `pom.xml`, a default run reads no Go or Java report, and a root `coverage.out` or `target/site/jacoco/jacoco.xml` is ignored and kept. `--use-existing-coverage` and `--coverage-command` still read them.
- `--path /usr/bin:/bin` hides cargo, rustup, and cargo-llvm-cov on this machine (they live under mise). Without it, crapper finds or installs cargo-llvm-cov, and a real `cargo llvm-cov` run on the Rust fixture compiles for about a minute.
- crapper installs missing coverage tools: `@vitest/coverage-v8` into `node_modules`, `coverage` and `pytest` into the project's Python, and `cargo-llvm-cov` with `cargo install`. The TypeScript fixtures avoid all of these: their `coverage` script is plain `sh`.
- With `--source=.`, coverage.py also measures a Python project's test files, so its `lcov.info` names `test_demo.py` too. crapper scores only the files it analyzes, so those records change no row.
- npm prints `> coverage` and `> sh coverage.sh` to stdout above the table.
