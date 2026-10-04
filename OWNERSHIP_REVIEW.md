# Crapper ownership review

Reviewed on October 4, 2026, at commit `9f1bead298b5a9d576bdd6319289fcf426e5b18a` in `bandoyer/crapper`, forked from `unclebob/crapper`.

Crapper's formula and report pipeline are straightforward. The largest ownership risk is attaching an incorrect coverage value or incomplete function list to that formula. Fix coverage freshness, source identity, and extraction before using a CRAP threshold as a release check. These fixes also matter to mutator, which imports crapper's extraction and coverage code.

This is a full repository review at the recorded commit, covering all language readers, coverage formats, tool runners, CLI behavior, packaging, launch scripts, tests, and documentation. This PR changes only this report. One initial review and one evidence/report check were used. No implementation repair pass was needed.

## Verification and limits

- `.venv/bin/python -m pytest -q`: **144 passed, 1 failed in 1.11 seconds**.
- The failure was `test_uml_loader_rejects_a_missing_viewer`. Linux could not launch the tracked executable because its shebang requires `/bin/zsh`, which is absent on this machine. The Python suite otherwise passed. C8 describes the portability issue.
- Environment: Linux, Python 3.14.8, pytest 9.1.1, tree-sitter 0.26.0, tree-sitter-language-pack 1.21.0. A real coverage probe used coverage.py 7.16.2. Pytest and coverage were added to the existing virtual environment.
- The repository contains 19 production Python files with 3,388 lines and 13 test-support/test Python files with 2,294 lines. All production modules and tracked support files were inspected; test inspection focused on behavior and runner boundaries alongside the full suite.
- Ran a real pytest/coverage.py collection and a failing npm coverage script in temporary projects. Reproduced coverage-path collisions, repeated LCOV source records, omitted or misclassified functions, empty-snapshot behavior, and a non-finite threshold.
- Maven/JaCoCo, Go coverage generation, Cargo coverage generation, the Clojure CLI, and the graphical UML viewer were not run end to end. No claim of a complete six-toolchain integration pass is made.

Priorities: **P1** can invalidate a core metric or release check. **P2** is a narrower correctness or compatibility defect. Design and performance proposals are advice unless a measured workload makes them required.

## Act on

These findings are tied to observed results or direct compatibility evidence.

### C1. Exclude stale and failed coverage reports from a fresh run: P1

A failed language command can still yield a successful, fully covered score. A real temporary-project reproduction used:

```json
{"scripts":{"coverage":"false"}}
```

An existing `coverage/lcov.info` marked a one-line TypeScript function as covered. A default crapper run invoked `npm run coverage`, which exited `1`. Stderr said `TypeScript coverage will score 0%.` The report nevertheless showed **100.0% coverage**, CRAP **2.0**, and exit **0**.

`_cover_typescript` prepares `target/coverage/typescript`, while a project coverage script can use `coverage/`. `load_bundle` reads the latter unchanged. Other early-return paths also leave old reports, and per-language `run_coverage` always returns `0`. Even fresh partial output from failing runs is treated inconsistently; Python explicitly retains it.

Evidence: [_cover_typescript](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/runners.py#L471), [_cover_python](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/runners.py#L523), [run_coverage](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/runners.py#L557), [report discovery](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/coverage.py#L493), and [_coverage_bundle](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/cli.py#L283).

Smallest repair: have collectors return exact report paths, package roots, and collection status. Read only reports associated with the current successful measurement, except under explicit `--use-existing-coverage`. Define a consistent policy for useful coverage from failing tests, and report that state truthfully. A stale report must never become current coverage just because it is on disk.

Regression checks should include an old 100% report plus a failing command, a missing tool, a missing test script, and a successful command that produces no report. Carry the status through to mutator rather than returning unconditional success.

### C2. Use valid coverage.py source targets for flat Python layouts: P1

For a project containing `demo.py` at its root, `python_sources` returns `demo.py`. The generated command uses `--source=demo.py`, but coverage.py expects directories or importable module/package names.

The actual generated command ran a passing test that imports and calls `demo.f()`. It then warned:

```text
Module demo.py was never imported.
No data was collected.
```

`coverage lcov` exited `1` with `No data to report.` Crapper therefore reports 0% for exercised code, and mutator can skip its mutation sites as uncovered.

Evidence: [python_sources](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/runners.py#L351) and [python_coverage_commands](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/runners.py#L368). The [coverage.py source-selection documentation](https://coverage.readthedocs.io/en/7.16.2/source.html) specifies directories or importable names.

Smallest repair: use `.` for a flat project with an appropriate include/omit policy, or use importable module names such as `demo` where unambiguous. Keep the current `src` directory case working. Test real collection for flat modules, packages, mixed layouts, and files never imported by tests.

### C3. Preserve report origin and merge LCOV records deliberately: P1

The loader discards the location of each report before indexing its source records. This loses package identity and coverage contributions.

Verified cases:

| Case | Observed result |
| --- | --- |
| `one/src/core.py` and `two/src/core.py`, with package reports both using `SF:src/core.py`; one report has hits and the other does not | Both analyzed functions score 0%. One dictionary slot remains, and source matching cannot identify its owner. |
| One LCOV file has two records for `SF:x.py`, the first hitting line 2 and the second hitting line 3 | The parsed result retains only line 3. |

There are also direct collection/lookup mismatches. A package's own coverage script can write `packages/app/coverage/lcov.info`, but `_lcov_paths` searches only root `coverage` and root `target/coverage`. Go and JaCoCo lookup are hard-coded to at most two nested module directories, even though collectors discover modules deeper in the tree.

Evidence: [_store_lcov](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/coverage.py#L245), [_lcov_paths](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/coverage.py#L493), [_merge_lcov](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/coverage.py#L513), [_merge_go](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/coverage.py#L520), [_merge_jacoco](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/coverage.py#L535), and [per-module report locations](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/runners.py#L281).

Smallest repair: retain a report's generating module root and resolve relative source paths there before merging. Use the collectors' exact output list instead of fixed-depth glob guesses. Merge repeated line hits and branch identities according to a defined aggregation rule, rather than overwriting a source record. Test identical filenames across two packages, nested package-local output, modules deeper than two levels, and multiple test-name records for one source.

### C4. Use reader-aware Clojure structure for complexity and extraction: P1

The current text scanner removes literals before counting top-level forms, and recognizes only textually top-level `defn` forms. These probes demonstrate incorrect metrics or missing functions:

| Source | Observed | Required behavior |
| --- | --- | --- |
| `(defn f [x y] (cond x "a" y "b" :else "c"))` | Complexity 2 | Complexity 4 under the documented rule of one base point plus each of the three clauses. |
| `(defn f [] '(if true 1 0))` | Complexity 2 | Quoted data should not add an executed decision. |
| `#?(:clj (defn f [x] (if x 1 0)))` in a `.cljc` file | No functions | Include the selected platform definition, or report an explicit unsupported construct. |

Replacing string bodies with whitespace erases the fact that each string is a result form. Reader conditionals put `defn` inside another pair of parentheses, so `_extract_top_level_defns` misses it. Clojure quote and conditional syntax are described in the [reader reference](https://clojure.org/reference/reader).

Evidence: [without_strings_and_comments](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/languages/clojure.py#L119), [_count_top_level_forms](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/languages/clojure.py#L181), [cyclomatic_complexity](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/languages/clojure.py#L232), and [_extract_top_level_defns](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/languages/clojure.py#L372).

Smallest immediate repair: preserve a literal placeholder when counting forms, distinguish quoted/discarded forms, and handle reader-conditional branches explicitly. Longer term, use one tested reader/token model for extraction and complexity. Dryer's reader is a useful comparison but has its own documented bugs; do not copy it without conformance tests. Add each example above and verify that mutator discovers the same retained functions.

### C5. Complete the supported JavaScript function extraction cases: P2

A class containing `#f(x) { return x > 0; }` and ordinary `g(x) { return x > 0; }` reports only `g`. `_append_method` accepts ordinary identifier nodes but not `private_property_identifier`.

Likewise, `var f = x => x > 0;` produces no function entry. The dispatcher visits `lexical_declaration` for `const` and `let` but not `variable_declaration` for `var`. Both are valid supported JavaScript/TypeScript forms. Mutator's README explicitly discusses `#` private names, yet it cannot create sites for these omitted methods.

Evidence: [_append_method](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/languages/typescript.py#L289), [_append_arrows](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/languages/typescript.py#L309), and [functions_in_source](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/languages/typescript.py#L381).

Smallest repair: accept private property identifiers and variable declarations, retaining byte spans and privacy information. Add JavaScript and TypeScript fixtures. Make unsupported class-field arrow functions or generator forms explicit in the language matrix instead of implying that every function spelling is covered.

### C6. Do not attach anonymous Java field-initializer methods to the outer class: P2

This source produces a method named `run` in namespace `A`, complexity 2:

```java
class A {
  Runnable r = new Runnable() {
    public void run() { if (true) return; }
  };
}
```

The README excludes anonymous-class methods. The current check excludes methods inside another executable, which misses field initializers. If retained, the method also needs the anonymous binary class identity for JaCoCo; using `A` is incorrect.

Evidence: [_inside_executable](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/languages/java.py#L50), [_type_chain](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/languages/java.py#L68), and [functions_in_source](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/languages/java.py#L88).

Smallest repair: recognize anonymous ownership and exclude it consistently with the documented scope. Test fields and initializer blocks alongside the existing anonymous-class-inside-method case. Apply the equivalent fixture to dryer.

### C7. Correct the declared parser dependency minimum: P2

The manifest allows tree-sitter-language-pack 0.7.0. `parser_for` requires its `download` API. Inspection of the downloaded 0.7.0 wheel confirmed that the module has no such function; its exports are the supported-language type and the three `get_*` helpers.

A dependency resolver can therefore produce an installation allowed by the metadata that fails when a tree-sitter language is first parsed. The existing suite used 1.21.0; this finding comes from the older wheel's API, not an asserted full test run with that wheel.

Evidence: [dependencies](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/pyproject.toml#L9) and [parser_for](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/languages/treesitter.py#L8). Mutator calls this same implementation.

Smallest repair: establish the true minimum compatible parser-pack version or explicitly support its older API. Test minimum and current dependencies. Document parser download/cache requirements and fail with a useful diagnostic when provisioning is unavailable.

### C8. Make the UML launcher portable or declare its shell prerequisite: P2

The tracked `uml` file starts with `#!/bin/zsh` and uses zsh-specific syntax such as `*.edn(N)` and `${f:t}`. This Linux environment has no `/bin/zsh`. The existing test expecting a useful missing-viewer error instead receives a process-launch `FileNotFoundError`.

Evidence: [launcher](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/uml#L1) and [CLI tests](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/tests/test_cli.py#L381). The exact failing test is `test_uml_loader_rejects_a_missing_viewer`.

Smallest repair: use the existing portable shell/Python baseline for path selection and process launching, or explicitly declare and check the zsh prerequisite. Do not merely skip the failing test if the launcher is intended to work on supported Linux machines. Verify help, missing-viewer handling, and paths containing spaces. A real GUI launch remains a separate integration check.

### C9. Clear the project snapshot after a successful empty full scan: P2

If the final source file is deleted, a full run exits `0` before writing metrics. The previous `.metrics/crap.edn` remains and can display functions that no longer exist. A temporary reproduction left a sentinel report unchanged.

Evidence: [run](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/cli.py#L307) and [write_metrics](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/metrics.py#L55).

Smallest repair: write an empty `{:entries []}` for a successful full scan with no sources. Define partial-run semantics separately. Test from a populated prior snapshot through deleting the final source file.

### C10. Reject non-finite CRAP thresholds: P2

`--threshold nan` is accepted by `float`. Comparisons against NaN are false, so no finite score exceeds it. A real CLI probe with uncovered branching code exited **0** under `--threshold nan`.

Evidence: [argument parsing](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/cli.py#L111) and [_threshold_status](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/cli.py#L294).

Smallest repair: require a finite, non-negative threshold and issue a usage error for NaN, infinities, and invalid values. Add boundary tests around the intended equality rule, which currently triggers only when the score is strictly greater than the threshold.

## Consider

These changes would improve maintenance or operational behavior, but do not all require immediate redesign.

### C11. Make file identity and source spans part of the shared contract

Python and TypeScript namespace helpers strip everything through the first `src/`. Distinct packages can consequently produce the same displayed namespace and name. Java overloads also share those display keys. The snapshot discards `Entry.path`, leaving a viewer unable to distinguish some collisions.

Most language extractors leave `Function.start_byte` and `end_byte` at `-1`. Mutator demonstrably misassigns same-line Java sites as a result; its review records M6. The shared API should carry source identity and byte ranges for every function, separately from the viewer's display name.

Evidence: [Function](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/model.py#L5), [Entry](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/model.py#L23), [serialized fields](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/metrics.py#L30), and [source-root stripping](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/languages/python.py#L54).

Add backward-compatible source and identity fields where possible, then validate the actual viewer join before changing existing namespace keys. Keep viewer compatibility work bounded; do not invent a cross-project identity system for this repair.

### C12. Avoid rebuilding coverage lookup state for every function

Every `percent_for` call normalizes all report keys and searches suffix candidates again. Ambiguity checks scan the source list during matching. On projects with many functions and coverage entries, this repeats work that depends only on the source file.

Evidence: [_select_key](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/coverage.py#L137), [CoverageBundle](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/coverage.py#L422), and [analysis loop](https://github.com/bandoyer/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/analyze.py#L35). This is a source-traced scaling concern; no whole-project bottleneck measurement was made for crapper.

Resolve each canonical source path to its coverage record once after C3 is fixed. Pre-index exact normalized keys. Profile a representative report before adding more elaborate suffix indexes. Keep ambiguity rejection instead of optimizing toward a faster wrong match.

### C13. Give external tool execution an explicit operating policy

Coverage collection can install Python modules, an npm coverage provider, and a global Cargo tool. Some commands have no timeout. These behaviors are documented in part, but a metrics command changing an environment is a substantial ownership decision.

Offer explicit bootstrap/installation behavior and a mode that only uses installed tools. Pin or constrain tool versions where compatibility requires it, while preserving supported project versions. Report collection status separately from a measured 0% result. Add timeouts and cancellation handling for language coverage commands.

Preserve the current generated argument vectors and manifest restoration tests. Review project settings before bypassing scripts: direct Vitest invocation can skip environment setup or flags in the project's test script. Test one project whose script supplies required configuration.

### C14. Improve error and snapshot handling

Malformed Go or JaCoCo reports can raise through `load_bundle`, including when they belong to another language in the same project. Catch errors at the report boundary, name the bad report, and apply an explicit incomplete-analysis policy. Tree-sitter recovery currently has no parse-error diagnostic, so partially parsed code can look like complete successful analysis.

Write `.metrics/crap.edn` using a temporary file plus atomic replacement. Clarify that a filtered or `--changed` run currently replaces the full snapshot with only selected functions. That replacement is documented behavior, so changing it to merge results needs a deliberate contract and deletion handling.

The report rounds coverage before applying the formula and rounds CRAP before checking the threshold. Preserve raw values for computation if exact threshold comparisons matter, then round only for presentation. Add an edge case near a threshold before changing this policy.

### C15. Reduce maintenance duplication without optimizing for a metric score

Crapper contains a handwritten option parser, a handwritten Clojure scanner, and repeated namespace/discovery logic shared conceptually with the other two tools. There are 244 production function definitions, including methods; 85 occupy at most five physical lines. That count does not establish bad design, but many wrappers add navigation to already simple rules.

Simplify the CLI with a standard parser if exit behavior can be preserved. Consolidate Clojure parsing around tested syntax, as C4 requires. Establish shared fixtures for discovery and namespaces before extracting code. Retain language-specific complexity rules as explicit policy.

The core formula, dataclasses, report formatting, and direct runtime dependency list are small. There is no need for a framework or a general plugin engine. Keep the useful stack-based traversal for deep syntax trees.

### C16. Add release checks that cover the actual integration risks

The tracked tree has no CI workflow. Add Python 3.11/current and parser minimum/current jobs, Linux launcher checks, and an isolated wheel-install smoke test. Test the sibling mutator contract when changing function extraction or coverage APIs.

The test suite contains useful exact formula, complexity, branch-coverage, path-ambiguity, shell-argument, and manifest-preservation assertions. However, `tests/conftest.py` globally replaces CLI `run_coverage`, and most language-runner tests inspect command vectors or mock execution. They cannot prove generated commands produce coverage that maps back to the correct functions.

Keep the global safety fixture for ordinary unit tests. Add separate opt-in integration fixtures that actually generate and reload coverage in each supported language, starting with the flat and multi-package Python cases. Include stale reports, missing tools, failed tests, and nested module roots.

Add fork-specific project/release URLs, supported-platform documentation, and release notes while preserving upstream attribution. The bootstrap script checks only for an existing virtualenv interpreter. Make it recover from an incomplete first installation instead of leaving a permanently broken launcher.

## Noted

These properties are sound or intentional, with practical limits.

- The CRAP formula is directly implemented and has meaningful expected-value tests. Coverage provenance and function extraction are the weak points, not a need to replace the formula.
- `--no-coverage` deliberately writes `nil` coverage and CRAP. Missing requested coverage deliberately scores 0%. A failed collection still needs a distinct diagnostic and status; a measured zero and an unknown measurement are different facts.
- Different languages use instruction, statement, branch, line, or form coverage. Their scores are useful within those conventions but should not be presented as an exact cross-language ranking without explaining the measurement basis.
- Constructors, some nested functions, and Rust `mod tests` are deliberately excluded. Preserve those documented choices unless expanding the product's scope.
- Express route detection is heuristic: a method named `get`, `post`, or `use` with a callback is treated as a route without proving the receiver is Express. Treat labels accordingly or offer a configurable route policy if false classifications occur in target projects.
- Source-controlled examples and the optional viewer launcher are small integration aids. They are not a significant storage burden. The larger maintenance cost is supporting six collectors and their external tools.

## Dismissed

These are not warranted default changes.

- Lowering every function's own CRAP score is not an acceptance criterion for this ownership work. A low score does not show that coverage was mapped correctly or that all functions were found.
- Rewriting the tool or adding a database would not address the concrete measurement errors above.
- The zsh failure is not evidence that the Python package cannot run on Linux. It identifies one launcher prerequisite and one failing test precisely.

## Proposed order

1. Fix C1–C3 and add real coverage-generation/reload tests. These changes also unblock reliable coverage-guided mutation testing.
2. Fix C4–C6 and supply byte spans for all language extractors. Run mutator's ownership fixtures against the resulting shared API.
3. Fix C7–C10 and add clean-install, launcher, and compatibility CI before releasing the maintained fork.
4. Define source identity and partial-snapshot behavior with the viewer. Preserve existing display fields while adding evidence needed to disambiguate them.
5. Profile repeated lookup and collector work, then make the bounded efficiency changes that measurements justify. Keep automatic installation and failure policies explicit in the release documentation.
