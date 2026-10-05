# Rust test code is not scored

crapper scores only the code under test. In Rust it skips a function that is test code: a function with a test attribute, or one inside an item marked test-only. A test attribute is one whose path ends in `test` (`#[test]`, `#[tokio::test]`, `#[async_std::test]`), or `#[rstest]`. An item is test-only when it, or a `mod` or `impl` around it, has `#[cfg(test)]`, or a `cfg` whose `all(…)` includes `test`. Functions in `mod tests` are skipped by name, as before. Integration tests under `tests/` aren't scanned at all.

## Sub-features

- `test-code-attributes` skips top-level and stacked `#[test]` functions and `#[cfg(test)]` code, and still scores functions whose attributes aren't test-only.
- `test-code-macros` skips `#[tokio::test]` and `#[rstest]` functions, and still scores a function with `test` only inside its attribute's path.

## How to get to it (user POV)

- Run `crapper` from a Cargo package whose `src/` holds test functions.

## Driving it with verify-crapper

Preconditions:

- `$vc doctor` prints `doctor: ok`.
- `T` is the transcript path for the feature.

- **test-code-attributes.** Needs a real `cargo llvm-cov`. `project=$($vc project rust-test-fns)`, then `$vc drive "$project" "$T"`. Exit code `0`, and stderr has no `error`. The table has rows for `tick` (`100.0%`), `tock`, `kept` (`#[must_use]`), `real` (`#[cfg(not(test))]`), and `either` (`#[cfg(any(test, feature = "x"))]`). It has no row for `ticks` (`#[test]`), `panics` (`#[should_panic]` above `#[test]`), `helper` (`#[cfg(test)]`), `probe` (in `#[cfg(test)] mod checks`), `turn` (in `#[cfg(test)] impl Dial`), or `gated` (`#[cfg(all(test, feature = "x"))]`). `.metrics/crap.edn` lists the same five names.
- **test-code-macros.** `project=$($vc project rust-test-macros)`, then `$vc drive "$project" "$T" --no-coverage`. Exit code `0`. The table has rows for `tick`, `tock`, and `assisted` (`#[testing::helper]`), and no row for `served` (`#[tokio::test]`) or `cases` (`#[rstest]`).

## Gotchas

- `rust-test-macros` uses attributes from crates the fixture doesn't depend on, so it doesn't compile. Drive it with `--no-coverage`; a default run would score every row 0% after a failed `cargo llvm-cov`.
- mutator lists functions through crapper, so it doesn't mutate the functions this feature skips.
