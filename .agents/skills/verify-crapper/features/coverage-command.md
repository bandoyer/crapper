# Score with a custom coverage command

`crapper --coverage-command '<command>'` runs that command in a shell from the project root instead of crapper's own collectors, then reads the reports on disk. When the command exits non-zero, crapper reads no reports and every function scores 0%.

## Sub-features

- `command-split-reports` combines two reports that name the same source file: a line counts as hit when either report hits it.

## How to get to it (user POV)

- Run `crapper --coverage-command '<command>'` from the project root.

## Driving it with verify-crapper

Preconditions:

- `$vc doctor` prints `doctor: ok`, and `cargo-llvm-cov` is found.
- `project=$($vc project rust-split)`. `T` is the transcript path for the feature.

- **command-split-reports.** Run `$vc drive "$project" "$T" --coverage-command 'mkdir -p target/coverage/rust/unit target/coverage/rust/integration && cargo llvm-cov --lib --lcov --output-path target/coverage/rust/unit/lcov.info && cargo llvm-cov --test clock --lcov --output-path target/coverage/rust/integration/lcov.info'`. Exit code `0`. Reports after lists both `./target/coverage/rust/unit/lcov.info` and `./target/coverage/rust/integration/lcov.info`. Both rows read `100.0%` and `1.0`: `tick  clock  1 100.0%  1.0` and `tock  clock  1 100.0%  1.0`. Each report on its own covers only one of them: `$vc exec "$project" "$T" grep -H -E '^(SF|DA)' target/coverage/rust/unit/lcov.info target/coverage/rust/integration/lcov.info` shows `tock`'s lines (5 to 7) hit only in `unit` and `tick`'s lines (1 to 3) hit only in `integration`.

## Gotchas

- cargo is a mise shim on this machine. A scratch project has no `mise.toml`, so set the toolchain in the environment: `MISE_RUST_VERSION=1.98.0 $vc drive …`. Without it, cargo fails with `No version is set for shim: cargo`.
- Each `cargo llvm-cov` run compiles the package, so the drive takes about a minute.
