# Rust test code is not scored

crapper scores only the code under test. In Rust it skips a function that is test code: a function with a test attribute, or one inside an item marked test-only. A test attribute is one whose path ends in `test` (`#[test]`, `#[tokio::test]`, `#[async_std::test]`), or one of `#[rstest]`, `#[test_case]`, `#[test_matrix]`, `#[proptest]`, `#[property_test]`, `#[wasm_bindgen_test]`, and `#[quickcheck]` (bare or with a path, such as `#[quickcheck_macros::quickcheck]`). An item is test-only when it, or a `mod` or `impl` around it, has `#[cfg(test)]`, or a `cfg` whose `all(…)` includes `test`. Functions in `mod tests` are skipped by name, as before. A module declared with `mod x;` follows the same rules, and its file is skipped when every crate root (`src/lib.rs`, `src/main.rs`, `src/bin/…`) reaches it only through test code. Integration tests under `tests/` aren't scanned at all.

## Sub-features

- `test-code-attributes` skips top-level and stacked `#[test]` functions and `#[cfg(test)]` code, and still scores functions whose attributes aren't test-only.
- `test-code-macros` skips `#[tokio::test]`, `#[rstest]`, `#[test_case]`, `#[test_matrix]`, `#[proptest]`, `#[property_test]`, `#[wasm_bindgen_test]`, and `#[quickcheck]` functions, and still scores a function with `test` only inside its attribute's path, a `#[wasm_bindgen]` export, and attributes whose names only resemble a test attribute.
- `test-code-module-files` skips the functions in a module declared test-only with `mod x;` whose body is in its own file (`x.rs`, `x/mod.rs`, nested, inherited, under an inline module, by `#[path]`, a bare `mod tests;`, and one declared in `main.rs`), and still scores production modules, a file one root uses plainly, and a file no module declares.

## How to get to it (user POV)

- Run `crapper` from a Cargo package whose `src/` holds test functions.

## Driving it with verify-crapper

Preconditions:

- `$vc doctor` prints `doctor: ok`.
- `T` is the transcript path for the feature.

- **test-code-attributes.** Needs a real `cargo llvm-cov`. `project=$($vc project rust-test-fns)`, then `$vc drive "$project" "$T"`. Exit code `0`, and stderr has no `error`. The table has rows for `tick` (`100.0%`), `tock`, `kept` (`#[must_use]`), `real` (`#[cfg(not(test))]`), and `either` (`#[cfg(any(test, feature = "x"))]`). It has no row for `ticks` (`#[test]`), `panics` (`#[should_panic]` above `#[test]`), `helper` (`#[cfg(test)]`), `probe` (in `#[cfg(test)] mod checks`), `turn` (in `#[cfg(test)] impl Dial`), or `gated` (`#[cfg(all(test, feature = "x"))]`). `.metrics/crap.edn` lists the same five names.
- **test-code-macros.** `project=$($vc project rust-test-macros)`, then `$vc drive "$project" "$T" --no-coverage`. Exit code `0`. The table has rows for `tick`, `tock`, `assisted` (`#[testing::helper]`), `greet` (`#[wasm_bindgen]`), `plural` (`#[test_cases]`), and `aided` (`#[quickcheck_helper]`), and no others. It has no row for `served` (`#[tokio::test]`), `cases` (`#[rstest]`), `cased` (`#[test_case(1)]`), `cased_path` (`#[test_case::test_case(2)]`), `matrixed` (`#[test_matrix]`), `proped` (`#[proptest]`), `property` (`#[property_test]`), `in_browser` (`#[wasm_bindgen_test]`), `in_browser_path` (`#[wasm_bindgen_test::wasm_bindgen_test]`), `checked` (`#[quickcheck]`), `checked_path` (`#[quickcheck_macros::quickcheck]`), or `in_proptest_body` (inside `proptest! { }`). `.metrics/crap.edn` lists the same six names.
- **test-code-module-files.** Needs a real `cargo llvm-cov`. `project=$($vc project rust-test-modules)`, then `$vc drive "$project" "$T"`. Exit code `0`, and stderr has no `error`. The table has rows for `tick` (`100.0%`), `main`, `outer_fn`, `util_fn`, `real_fn` (`#[cfg(not(test))] mod real;`), `shared_fn` (lib.rs declares `#[cfg(test)] mod shared;`, main.rs `mod shared;`), and `orphan_fn` (no module declares `orphan.rs`), and no others. It has no row for `checks_sample` (`#[cfg(test)] mod checks;` in `checks.rs`), `checks_test`, `deeper_probe` (`mod deeper;` inside `checks.rs`), `fixtures_probe` (`fixtures/mod.rs`), `inner_probe` (`#[cfg(test)] mod inner;` in the production `outer.rs`), `leaf_probe` (`#[cfg(test)] mod inline { mod leaf; }`), `helpers_probe` (`#[path = "support/helpers.rs"]`), `gated_probe` (`#[cfg(all(test, feature = "x"))]`), `tests_probe` (a bare `mod tests;`), or `cli_probe` (`#[cfg(test)] mod cli_checks;` in `main.rs`). `.metrics/crap.edn` lists the same seven names. Then `$vc drive "$project/src" "$T" --root .. --no-coverage` lists the same seven names: the lookup reads the module tree from `--root`, not the folder crapper runs in.

## Gotchas

- `rust-test-macros` uses attributes from crates the fixture doesn't depend on, so it doesn't compile. Drive it with `--no-coverage`; a default run would score every row 0% after a failed `cargo llvm-cov`.
- mutator lists functions through crapper, so it doesn't mutate the functions this feature skips.
- A bare `mod tests;` is skipped by its name, like an inline `mod tests { }`, though rustc compiles it in a normal build. A `#[path]` deeper in the tree that leads out of its module's folder isn't followed, so that file is still scored.
