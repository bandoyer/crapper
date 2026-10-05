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
