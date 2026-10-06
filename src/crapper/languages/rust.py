"""Rust functions and cyclomatic complexity.

Decision points are `if` / `if let`, `for`, `while` / `while let`, `loop`,
each `match` arm, `?`, and `&&` / `||`. Free functions are namespaced by the
module path (`crate::foo::bar`). Methods are namespaced by the self type
(`crate::foo::Widget`) so uml-viewer can join them to that type.

Test code is not scored: bodies inside `mod tests`, and a function that has a
test attribute or sits in a `mod` or `impl` that has one. A test attribute is
one whose path ends in `test` (`#[test]`, `#[tokio::test]`), one of `#[rstest]`,
`#[test_case]`, `#[test_matrix]`, `#[proptest]`, `#[property_test]`,
`#[wasm_bindgen_test]`, and `#[quickcheck]` (bare or with a path), or a `cfg`
that holds only in a test build (`test`, or `all(...)` with such a part). An
inner `#![cfg(test)]` marks the file or `mod` body it starts.

A module declared with `mod x;` keeps its body in another file, so crapper
follows the crate's module tree from its roots (`src/lib.rs`, `src/main.rs`,
`src/bin/...`) by rustc's rules, and skips a file that every root reaches only
through test code. A bare `mod tests;` counts as test code by its name, as an
inline `mod tests { }` does, although rustc compiles it in a normal build.
"""

import re
from pathlib import Path

from crapper.languages.treesitter import (
    absolute_path as _absolute,
    binary_logic,
    child_of_type,
    complexity,
    descendants,
    end_line,
    node_text,
    parse,
    start_line,
)
from crapper.model import Function

_DECISIONS = {
    "if_expression",
    "for_expression",
    "while_expression",
    "loop_expression",
    "match_arm",
    "try_expression",
}
_TEST_ATTRIBUTES = {
    "test",
    "rstest",
    "test_case",
    "test_matrix",
    "proptest",
    "property_test",
    "wasm_bindgen_test",
    "quickcheck",
}
_BEFORE_ITEM = {"attribute_item", "line_comment", "block_comment"}
_BODIES = {"source_file", "declaration_list"}
_PACKAGE_BLOCK = re.compile(r"(?ms)^\[package\](.*?)(?:^\[|\Z)")
_NAME = re.compile(r'(?m)^name\s*=\s*"([^"]+)"')


def _is_decision(node) -> bool:
    return node.type in _DECISIONS or binary_logic(node)


def _skip(_node) -> bool:
    return False


def _has_block(node) -> bool:
    return child_of_type(node, "block") is not None


def _ancestor_mods(data: bytes, node) -> list[str]:
    names: list[str] = []
    current = node.parent
    while current is not None:
        if current.type == "mod_item":
            ident = child_of_type(current, "identifier")
            if ident is not None:
                names.append(node_text(data, ident))
        current = current.parent
    names.reverse()
    return names


def _in_mod_named(data: bytes, node, name: str) -> bool:
    return name in _ancestor_mods(data, node)


def _predicates(data: bytes, predicates):
    """Each predicate in a `cfg` list, `(...)`, as its name and its own list, or None."""

    items = predicates.children
    for item, following in zip(items, [*items[1:], None]):
        if item.type == "identifier":
            nested = following if following is not None and following.type == "token_tree" else None
            yield node_text(data, item), nested


def _test_only(data: bytes, predicates) -> bool:
    """A `cfg` predicate list that holds only in a test build: `test`, or `all(...)` with such a part."""

    for name, nested in _predicates(data, predicates):
        if name == "test" and nested is None:
            return True
        if name == "all" and nested is not None and _test_only(data, nested):
            return True
    return False


def _is_test_attribute(data: bytes, attribute) -> bool:
    path = "".join(node_text(data, attribute.children[0]).split())
    if path == "cfg":
        predicates = child_of_type(attribute, "token_tree")
        return predicates is not None and _test_only(data, predicates)
    return path.split("::")[-1] in _TEST_ATTRIBUTES


def _attribute_items(node):
    """A node's attribute items: inner `#![...]` ones when it is a file or a `mod`
    body, and outer ones written before it, with any comments between them."""

    if node.type in _BODIES:
        yield from (child for child in node.children if child.type == "inner_attribute_item")
    current = node.prev_sibling
    while current is not None and current.type in _BEFORE_ITEM:
        yield current
        current = current.prev_sibling


def _attributes(node):
    for item in _attribute_items(node):
        attribute = child_of_type(item, "attribute")
        if attribute is not None:
            yield attribute


def _in_test_code(data: bytes, node) -> bool:
    """The function, or a `mod`, `impl`, or file around it, has a test attribute."""

    current = node
    while current is not None:
        if any(_is_test_attribute(data, attribute) for attribute in _attributes(current)):
            return True
        current = current.parent
    return False


def _is_test_item(data: bytes, node) -> bool:
    """The item sits in a `mod tests`, or it, or a `mod`, `impl`, or file around it, has a test attribute."""

    return _in_mod_named(data, node, "tests") or _in_test_code(data, node)


def _path_attribute(data: bytes, node) -> str | None:
    """The file a `#[path = "..."]` on the item names, or None."""

    for attribute in _attributes(node):
        if node_text(data, attribute.children[0]) != "path":
            continue
        for item in descendants(attribute):
            if item.type == "string_content":
                return node_text(data, item)
    return None


def _declarations(data: bytes, tree):
    """Each `mod x;` in a parsed file (a `mod` with no body here), with its name
    as a file name: `mod r#type;` loads `type.rs`."""

    for node in descendants(tree.root_node):
        if node.type == "mod_item" and child_of_type(node, "declaration_list") is None:
            ident = child_of_type(node, "identifier")
            if ident is not None:
                yield node, node_text(data, ident).removeprefix("r#")


def _module_files(module: Path, folder: Path):
    """Each `mod x;` in a module file, by rustc's rules: the file it loads, the
    folder where that file's own declarations resolve, and whether the
    declaration is test code. `folder` is where this file's declarations
    resolve: beside a crate root, `mod.rs`, or `#[path]` file, and under
    `a/x/` for a plain module file `a/x.rs`. Only a regular file is yielded,
    so the walk never reads a FIFO or a device a `#[path]` names."""

    try:
        data, tree = parse(module.read_text(encoding="utf-8", errors="replace"), "rust")
    except OSError:
        return
    for node, name in _declarations(data, tree):
        inline = [part.removeprefix("r#") for part in _ancestor_mods(data, node)]
        base = folder.joinpath(*inline)
        test = name == "tests" or _is_test_item(data, node)
        path = _path_attribute(data, node)
        if path is not None:
            loaded = ((base if inline else module.parent) / path).resolve()
            candidates = [(loaded, loaded.parent)]
        else:
            candidates = [(base / f"{name}.rs", base / name), (base / name / "mod.rs", base / name)]
        for loaded, below in candidates:
            if loaded.is_file():
                yield loaded.resolve(), below.resolve(), test
                break


def _crate_roots(crate_root: Path) -> list[Path]:
    src = crate_root / "src"
    found = [src / "lib.rs", src / "main.rs", *(src / "bin").glob("*.rs"), *(src / "bin").glob("*/main.rs")]
    return [root.resolve() for root in found if root.is_file()]


def _ways_to(target: Path, roots: list[Path]):
    """Whether each declaration that loads `target` is reached through test code,
    walking the module tree down from the crate roots. Below the roots, the walk
    opens only a module whose folder holds `target`, and each module once per
    test-code state, so a `#[path]` cycle ends."""

    walk = [(root, root.parent, False) for root in roots]
    seen = set(walk)
    while walk:
        module, folder, test = walk.pop()
        for loaded, below, declared_test in _module_files(module, folder):
            through_test = test or declared_test
            if loaded == target:
                yield through_test
            elif target.is_relative_to(below) and (loaded, below, through_test) not in seen:
                seen.add((loaded, below, through_test))
                walk.append((loaded, below, through_test))


def _test_only_file(file: Path, crate_root: Path) -> bool:
    """At least one crate root reaches the file, and only through test code."""

    target = file.resolve()
    roots = _crate_roots(crate_root)
    if target in roots:
        return False
    reached = False
    for through_test in _ways_to(target, roots):
        if not through_test:
            return False
        reached = True
    return reached


def _first_type_name(data: bytes, node) -> str | None:
    if node.type == "type_identifier":
        return node_text(data, node)
    for item in descendants(node):
        if item.type == "type_identifier":
            return node_text(data, item)
    return None


def _impl_type(data: bytes, impl) -> str | None:
    saw_for = False
    chosen = None
    for child in impl.children:
        if child.type == "for":
            saw_for = True
            chosen = None
            continue
        if child.type in {"type_identifier", "generic_type", "scoped_type_identifier"}:
            chosen = _first_type_name(data, child)
            if saw_for:
                return chosen
    return chosen


def _crate_name(path: str) -> tuple[str, Path | None]:
    current = Path(path).resolve().parent
    while True:
        cargo = current / "Cargo.toml"
        if cargo.is_file():
            text = cargo.read_text(encoding="utf-8")
            block = _PACKAGE_BLOCK.search(text)
            if block:
                match = _NAME.search(block.group(1))
                name = match.group(1) if match else current.name
                return name.replace("-", "_"), current
        if current.parent == current:
            break
        current = current.parent
    return "crate", None


def _rs_parts(relative: str) -> list[str]:
    parts = relative.split("/")
    if parts[-1] == "mod.rs":
        return parts[:-1]
    if parts[-1].endswith(".rs"):
        parts[-1] = parts[-1][:-3]
    return parts


def _with_crate(crate_name: str, parts: list[str]) -> list[str]:
    if parts[:1] == ["bin"] and len(parts) >= 2:
        return parts[1:]
    return [crate_name, *parts]


def _file_modules(path: str, crate_name: str, crate_root: Path | None) -> list[str]:
    file_path = Path(path).resolve()
    if crate_root is None:
        if file_path.stem in {"lib", "main"}:
            return [crate_name]
        return [crate_name, file_path.stem]
    try:
        relative = file_path.relative_to(crate_root).as_posix()
    except ValueError:
        return [crate_name]
    if relative.startswith("src/"):
        relative = relative[4:]
    if relative in {"lib.rs", "main.rs"}:
        return [crate_name]
    return _with_crate(crate_name, _rs_parts(relative))


def _namespace(modules: list[str], extra: list[str], type_name: str | None) -> str:
    parts = [*modules, *extra]
    if type_name:
        parts.append(type_name)
    return "::".join(part for part in parts if part)


def _impl_owner(data: bytes, node):
    parent = node.parent
    if parent is None or parent.type != "declaration_list":
        return None
    owner = parent.parent
    if owner is None or owner.type != "impl_item":
        return None
    return _impl_type(data, owner)


def _record_function(data: bytes, node, modules: list[str], path: str) -> Function | None:
    if node.type != "function_item" or not _has_block(node):
        return None
    if node.parent is not None and node.parent.type == "block":
        return None
    if _is_test_item(data, node):
        return None
    ident = child_of_type(node, "identifier")
    if ident is None:
        return None
    return Function(
        name=node_text(data, ident),
        namespace=_namespace(modules, _ancestor_mods(data, node), _impl_owner(data, node)),
        complexity=complexity(node, _is_decision, _skip),
        start_line=start_line(node),
        end_line=end_line(node),
        path=path,
        language="rust",
    )


def functions_in_source(
    source: str, path: str, project_root: str | None = None
) -> list[Function]:
    located = _absolute(path, project_root)
    crate_name, crate_root = _crate_name(located)
    if crate_root is not None and _test_only_file(Path(located), crate_root):
        return []
    data, tree = parse(source, "rust")
    modules = _file_modules(located, crate_name, crate_root)
    found: list[Function] = []
    for node in descendants(tree.root_node):
        recorded = _record_function(data, node, modules, path)
        if recorded is not None:
            found.append(recorded)
    return found
