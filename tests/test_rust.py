import inspect
import sys
from pathlib import Path

import pytest

from crapper.languages.rust import _file_modules, functions_in_source

SOURCE = """
pub fn choose(x: i32) -> i32 {
    if x > 0 && x < 10 {
        return 1;
    }
    match x {
        1 => 1,
        2 => 2,
        _ => 0,
    }
}

impl Sample {
    pub fn run(&self) -> i32 {
        if self.ok { 1 } else { 0 }
    }
}

impl Trait for Sample {
    fn draw(&mut self) {}
}

mod tests {
    fn hidden() {
        if true {}
    }
}

fn outer() {
    fn inner() {
        if true {}
    }
}
"""


def test_functions_methods_and_skipped_tests(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "demo-game"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    path = tmp_path / "src" / "lib.rs"
    path.parent.mkdir()
    path.write_text(SOURCE, encoding="utf-8")
    functions = functions_in_source(SOURCE, "src/lib.rs", str(tmp_path))
    assert [(fn.namespace, fn.name, fn.complexity) for fn in functions] == [
        ("demo_game", "choose", 6),
        ("demo_game::Sample", "run", 2),
        ("demo_game::Sample", "draw", 1),
        ("demo_game", "outer", 2),
    ]


def test_impl_for_a_nested_generic_type(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "demo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    source = "impl Trait for Vec<crate::Sample> {\n    fn draw(&self) {}\n}\n"
    functions = functions_in_source(source, str(tmp_path / "src" / "lib.rs"), str(tmp_path))
    assert functions[0].name == "draw"
    assert functions[0].namespace.endswith("Vec") or "Sample" in functions[0].namespace


def test_module_paths_outside_the_usual_layout(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "demo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    mod = "pub fn open() {}\n"
    binary = "pub fn main_ok() {}\n"
    functions_in_source(mod, str(tmp_path / "src" / "game" / "mod.rs"), str(tmp_path))
    functions = functions_in_source(binary, str(tmp_path / "src" / "bin" / "tool.rs"), str(tmp_path))
    assert functions[0].namespace == "tool"
    outside = functions_in_source("pub fn loose() {}\n", "/tmp/loose.rs", str(tmp_path))
    assert outside[0].name == "loose"
    bare = functions_in_source("pub fn bare() {}\n", str(tmp_path / "notes.rs"), None)
    assert bare[0].name == "bare"


def test_a_file_outside_the_crate_root_uses_the_crate_name():
    assert _file_modules("/tmp/loose.rs", "demo", Path("/projects/demo")) == ["demo"]


def test_nested_module_path(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "demo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    path = tmp_path / "src" / "game" / "board.rs"
    path.parent.mkdir(parents=True)
    source = "pub fn place() -> i32 { if ready { 1 } else { 0 } }\n"
    path.write_text(source, encoding="utf-8")
    functions = functions_in_source(source, "src/game/board.rs", str(tmp_path))
    assert [(fn.namespace, fn.name, fn.complexity) for fn in functions] == [
        ("demo::game::board", "place", 2)
    ]


@pytest.mark.parametrize(
    "item",
    [
        "#[test]\nfn hidden() {}",
        "#[should_panic]\n#[test]\nfn hidden() {}",
        "#[test]\n#[should_panic]\nfn hidden() {}",
        "/// Checks the dial.\n#[test]\n// keep\nfn hidden() {}",
        "#[tokio::test]\nasync fn hidden() {}",
        "#[async_std::test]\nasync fn hidden() {}",
        "#[rstest]\nfn hidden() {}",
        "#[cfg(test)]\nfn hidden() {}",
        "#[cfg(all(test, feature = \"x\"))]\nfn hidden() {}",
        "#[cfg(all(unix, all(test, feature = \"x\")))]\nfn hidden() {}",
        "#[cfg(test)]\nmod checks {\n    fn hidden() {}\n}",
        "#[cfg(test)]\nimpl Dial {\n    fn hidden(&self) {}\n}",
        "mod checks {\n    #![cfg(test)]\n    fn hidden() {}\n}",
    ],
)
def test_rust_test_code_is_not_scored(item):
    """#23: a test function, or one in test-only code, is not a scored function."""

    source = f"pub fn kept() {{}}\n\n{item}\n"
    assert [fn.name for fn in functions_in_source(source, "/tmp/lib.rs")] == ["kept"]


@pytest.mark.parametrize(
    "item",
    [
        "#[test_case(1)]\nfn hidden(n: i32) {}",
        "#[test_case::test_case(2)]\nfn hidden(n: i32) {}",
        "#[test_case(1)]\n#[test_case(2)]\nfn hidden(n: i32) {}",
        "#[test_matrix([1, 2])]\nfn hidden(n: i32) {}",
        "#[proptest]\nfn hidden(n: u8) {}",
        "#[property_test]\nfn hidden(n: u8) {}",
        "#[wasm_bindgen_test]\nfn hidden() {}",
        "#[wasm_bindgen_test::wasm_bindgen_test]\nfn hidden() {}",
        "#[quickcheck]\nfn hidden(n: u8) -> bool {\n    n > 0\n}",
        "#[quickcheck_macros::quickcheck]\nfn hidden(n: u8) -> bool {\n    n > 0\n}",
    ],
)
def test_rust_functions_with_other_test_attributes_are_not_scored(item):
    """#42: test-case, proptest, wasm-bindgen-test, and quickcheck tests are test code."""

    source = f"pub fn kept() {{}}\n\n{item}\n"
    assert [fn.name for fn in functions_in_source(source, "/tmp/lib.rs")] == ["kept"]


def test_functions_in_a_test_macro_body_are_not_listed():
    source = (
        "pub fn kept() {}\n\n"
        "proptest! {\n    #[test]\n    fn hidden(n in 0..10u8) {\n        if n > 1 {}\n    }\n}\n\n"
        "quickcheck! {\n    fn also_hidden(n: u8) -> bool {\n        n > 0\n    }\n}\n"
    )
    assert [fn.name for fn in functions_in_source(source, "/tmp/lib.rs")] == ["kept"]


@pytest.mark.parametrize(
    "attribute",
    [
        "#[must_use]",
        "#[inline]",
        "#[cfg(not(test))]",
        "#[cfg(any(test, feature = \"x\"))]",
        "#[cfg(feature = \"x\")]",
        "#[cfg(all(unix, feature = \"x\"))]",
        "#[testing::helper]",
        "#[attest]",
        "#[test_helper]",
        "#[wasm_bindgen]",
        "#[test_cases]",
        "#[quickcheck_helper]",
    ],
)
def test_rust_functions_with_other_attributes_are_scored(attribute):
    source = f"{attribute}\npub fn kept() {{}}\n"
    assert [fn.name for fn in functions_in_source(source, "/tmp/lib.rs")] == ["kept"]


def test_a_rust_file_marked_test_only_scores_nothing():
    assert functions_in_source("#![cfg(test)]\n\npub fn helper() {}\n", "/tmp/lib.rs") == []


def test_other_inner_attributes_keep_a_rust_function_scored():
    source = "#![allow(dead_code)]\n\nmod gears {\n    #![allow(unused)]\n    pub fn kept() {}\n}\n"
    assert [fn.name for fn in functions_in_source(source, "/tmp/lib.rs")] == ["kept"]


# #45: a crate whose test-only modules are declared with `mod x;` and kept in
# their own files. Each module file holds one function. rustc compiles the
# TEST_ONLY files only in a test build; it compiles the CODE files in a normal
# build, except tests.rs (crapper skips a `mod tests` by its name) and
# orphan.rs, which no module declares.
TREE = {
    "Cargo.toml": '[package]\nname = "tree"\nversion = "0.1.0"\nedition = "2021"\n',
    "src/lib.rs": """pub fn tick() -> i32 {
    1
}

pub mod outer;
mod util;

#[cfg(test)]
mod checks;

#[cfg(test)]
mod fixtures;

#[cfg(test)]
mod inline {
    mod leaf;
}

#[cfg(test)]
#[path = "support/helpers.rs"]
mod helpers;

#[cfg(all(test, feature = "x"))]
mod gated;

mod tests;

#[cfg(not(test))]
mod real;

#[cfg(test)]
mod shared;
""",
    "src/main.rs": "fn main() {}\n\nmod shared;\n\n#[cfg(test)]\nmod cli_checks;\n",
    "src/checks.rs": "mod deeper;\n\nfn checks_sample() -> i32 {\n    1\n}\n",
    "src/checks/deeper.rs": "fn deeper_probe() {}\n",
    "src/fixtures/mod.rs": "fn fixtures_probe() {}\n",
    "src/outer.rs": "pub fn outer_fn() {}\n\n#[cfg(test)]\nmod inner;\n",
    "src/outer/inner.rs": "fn inner_probe() {}\n",
    "src/inline/leaf.rs": "fn leaf_probe() {}\n",
    "src/support/helpers.rs": "fn helpers_probe() {}\n",
    "src/gated.rs": "fn gated_probe() {}\n",
    "src/tests.rs": "fn tests_probe() {}\n",
    "src/cli_checks.rs": "fn cli_probe() {}\n",
    "src/util.rs": "pub fn util_fn() {}\n",
    "src/real.rs": "pub fn real_fn() {}\n",
    "src/shared.rs": "pub fn shared_fn() {}\n",
    "src/orphan.rs": "pub fn orphan_fn() {}\n",
}

TEST_ONLY = [
    "src/checks.rs",
    "src/fixtures/mod.rs",
    "src/outer/inner.rs",
    "src/checks/deeper.rs",
    "src/inline/leaf.rs",
    "src/support/helpers.rs",
    "src/gated.rs",
    "src/tests.rs",
    "src/cli_checks.rs",
]

CODE = {
    "src/lib.rs": ["tick"],
    "src/main.rs": ["main"],
    "src/outer.rs": ["outer_fn"],
    "src/util.rs": ["util_fn"],
    "src/real.rs": ["real_fn"],
    "src/shared.rs": ["shared_fn"],
    "src/orphan.rs": ["orphan_fn"],
}


def _write_crate(root: Path, files: dict[str, str]) -> Path:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _listed(root: Path, relative: str, caller: str) -> list[str]:
    """Function names as crapper lists them (a root-relative path) or as mutator does (an absolute path)."""

    source = (root / relative).read_text(encoding="utf-8")
    path = relative if caller == "crapper" else (root / relative).as_posix()
    return [fn.name for fn in functions_in_source(source, path, str(root))]


@pytest.mark.parametrize("caller", ["crapper", "mutator"])
@pytest.mark.parametrize("relative", TEST_ONLY)
def test_a_test_only_module_in_its_own_file_is_not_scored(tmp_path, monkeypatch, relative, caller):
    """#45: the module tree, not the file alone, says the file is test code."""

    crate = _write_crate(tmp_path / "tree", TREE)
    monkeypatch.chdir(tmp_path)
    assert _listed(crate, relative, caller) == []


@pytest.mark.parametrize("caller", ["crapper", "mutator"])
@pytest.mark.parametrize("relative", sorted(CODE))
def test_a_module_file_a_crate_root_compiles_is_scored(tmp_path, monkeypatch, relative, caller):
    crate = _write_crate(tmp_path / "tree", TREE)
    monkeypatch.chdir(tmp_path)
    assert _listed(crate, relative, caller) == CODE[relative]


def test_a_missing_module_file_or_a_module_that_loads_itself_ends_the_walk(tmp_path):
    crate = _write_crate(
        tmp_path / "loops",
        {
            "Cargo.toml": '[package]\nname = "loops"\nversion = "0.1.0"\n',
            "src/lib.rs": (
                '#[cfg(test)]\nmod gone;\n\n#[path = "lib.rs"]\nmod again;\n\n'
                '#[path = "lost/missing.rs"]\nmod lost;\n\npub fn tick() {}\n'
            ),
            "src/stray.rs": "pub fn stray() {}\n",
            "src/lost/stray.rs": "pub fn lost_stray() {}\n",
        },
    )
    assert _listed(crate, "src/lib.rs", "crapper") == ["tick"]
    assert _listed(crate, "src/stray.rs", "crapper") == ["stray"]
    assert _listed(crate, "src/lost/stray.rs", "crapper") == ["lost_stray"]


CARGO = '[package]\nname = "edges"\nversion = "0.1.0"\n'


@pytest.mark.parametrize(
    "files, relative, names",
    [
        pytest.param(
            {"src/bin/tool/main.rs": "fn main() {}\n\n#[cfg(test)]\nmod checks;\n", "src/bin/tool/checks.rs": "fn hidden() {}\n"},
            "src/bin/tool/checks.rs",
            [],
            id="a binary root's test-only module",
        ),
        pytest.param(
            {"src/lib.rs": '#[cfg(test)]\n#[path = "../testsupport/helpers.rs"]\nmod helpers;\n', "testsupport/helpers.rs": "fn hidden() {}\n"},
            "testsupport/helpers.rs",
            [],
            id="a #[path] from a root out of src",
        ),
        pytest.param(
            {"src/lib.rs": "pub mod outer;\n", "src/outer.rs": '#[cfg(test)]\n#[path = "outer/impl_checks.rs"]\nmod checks;\n', "src/outer/impl_checks.rs": "fn hidden() {}\n"},
            "src/outer/impl_checks.rs",
            [],
            id="a #[path] in a plain module file, inside its folder",
        ),
        pytest.param(
            {"src/lib.rs": '#[cfg(test)]\nmod inline {\n    #[path = "p.rs"]\n    mod q;\n}\n', "src/inline/p.rs": "fn hidden() {}\n"},
            "src/inline/p.rs",
            [],
            id="a #[path] inside an inline module",
        ),
        pytest.param(
            {"src/lib.rs": '#[cfg(test)]\n#[path = "support/helpers.rs"]\nmod helpers;\n', "src/support/helpers.rs": "mod sub;\n", "src/support/sub.rs": "fn hidden() {}\n"},
            "src/support/sub.rs",
            [],
            id="a #[path] file's own module resolves beside it",
        ),
        pytest.param(
            {"src/lib.rs": "pub mod outer;\n", "src/outer.rs": '#[cfg(test)]\n#[path = "sibling.rs"]\nmod checks;\n', "src/sibling.rs": "pub fn kept() {}\n"},
            "src/sibling.rs",
            ["kept"],
            id="a #[path] out of a plain module's folder is not followed",
        ),
        pytest.param(
            {"src/lib.rs": "#[cfg(test)]\nmod helpers {\n    fn inside() {}\n}\n", "src/helpers.rs": "pub fn kept() {}\n"},
            "src/helpers.rs",
            ["kept"],
            id="an inline module loads no file of its name",
        ),
        pytest.param(
            {"src/lib.rs": "#[cfg(test)]\nmod checks;\n", "src/checks.rs": "pub fn kept() {}\n", "src/bin/checks.rs": "fn main() {}\n"},
            "src/bin/checks.rs",
            ["main"],
            id="a binary root of the same name is scored",
        ),
    ],
)
def test_module_tree_edges(tmp_path, files, relative, names):
    crate = _write_crate(tmp_path / "edges", {"Cargo.toml": CARGO, **files})
    assert _listed(crate, relative, "mutator") == names


def test_the_module_walk_does_not_deepen_the_stack_per_module(tmp_path):
    """A chain of 150 nested modules is walked with fewer than 100 spare stack frames."""

    depth = 150
    files = {"Cargo.toml": CARGO, "src/lib.rs": "#[cfg(test)]\nmod m;\n"}
    for level in range(1, depth):
        files["src/" + "m/" * (level - 1) + "m.rs"] = "mod m;\n"
    deepest = "src/" + "m/" * (depth - 1) + "m.rs"
    files[deepest] = "fn hidden() {}\n"
    crate = _write_crate(tmp_path / "deep", files)
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(len(inspect.stack()) + 100)
    try:
        listed = _listed(crate, deepest, "crapper")
    finally:
        sys.setrecursionlimit(limit)
    assert listed == []
