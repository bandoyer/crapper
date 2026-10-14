"""C# methods and constructors, and their cyclomatic complexity.

A method or constructor with a body is an entry. One with no body (abstract,
interface, extern, a partial declaration) is not. Local functions and lambdas
belong to the member that holds them. The namespace is the C# namespace plus
the enclosing types, without type parameters (`Demo.Clock.Ticker.Gear`), and a
constructor is named by its class, as C# spells it.

Decisions follow crap4java (`if`, loops, `catch`, `?:`, each `case` and
`default` label, `&&` and `||`), plus each switch-expression arm, and `??` and
`?.` as the TypeScript reader counts them. A `when` guard and the `and` and
`or` patterns are not decisions, as Java's guards are not.
"""

from crapper.languages.treesitter import (
    binary_logic,
    child_of_type,
    complexity,
    end_line,
    node_text,
    parse,
    start_line,
)
from crapper.model import Function

_MEMBERS = {"method_declaration", "constructor_declaration"}
_SCOPES = {
    "namespace_declaration",
    "class_declaration",
    "struct_declaration",
    "record_declaration",
    "interface_declaration",
}
_DECISIONS = {
    "if_statement",
    "for_statement",
    "foreach_statement",
    "while_statement",
    "do_statement",
    "catch_clause",
    "conditional_expression",
    "switch_expression_arm",
    "conditional_access_expression",
}


def _is_decision(node) -> bool:
    if node.type in _DECISIONS or binary_logic(node):
        return True
    if node.type in {"case", "default"}:
        return node.parent is not None and node.parent.type == "switch_section"
    return node.type == "binary_expression" and any(child.type == "??" for child in node.children)


def _name(data: bytes, node) -> str:
    return node_text(data, node.child_by_field_name("name"))


def _namespace(data: bytes, node, file_namespace: str | None) -> str:
    """The file-scoped namespace, then each enclosing block namespace and type, outermost first."""

    names: list[str] = []
    current = node.parent
    while current is not None:
        if current.type in _SCOPES:
            names.append(_name(data, current))
        current = current.parent
    if file_namespace:
        names.append(file_namespace)
    return ".".join(reversed(names))


def _file_namespace(data: bytes, root) -> str | None:
    found = child_of_type(root, "file_scoped_namespace_declaration")
    return _name(data, found) if found is not None else None


def functions_in_source(
    source: str, path: str, project_root: str | None = None
) -> list[Function]:
    del project_root
    data, tree = parse(source, "csharp")
    file_namespace = _file_namespace(data, tree.root_node)
    found: list[Function] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type in _MEMBERS:
            if child_of_type(node, "block", "arrow_expression_clause") is not None:
                found.append(
                    Function(
                        name=_name(data, node),
                        namespace=_namespace(data, node, file_namespace),
                        complexity=complexity(node, _is_decision, lambda _node: False),
                        start_line=start_line(node),
                        end_line=end_line(node),
                        path=path,
                        language="csharp",
                    )
                )
            continue
        stack.extend(reversed(node.children))
    return found
