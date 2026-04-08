from __future__ import annotations

from tree_sitter import Node, Tree
from tree_sitter_language_pack import get_parser

from core.types import Diagnostic, DiagnosticSpan

_TS_PARSER = get_parser("typescript")


def parse_eslint_messages(
    messages: list[dict],
    source_code: str | None = None,
    ast_tree: Tree | None = None,
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    tree = ast_tree if ast_tree is not None else _parse_ts(source_code)
    for message in messages:
        rule_id = message["ruleId"]
        severity = "error" if message["severity"] == 2 else "warning"
        diagnostics.append(
            Diagnostic(
                message=message["message"],
                severity=severity,
                spans=(DiagnosticSpan(
                    line=message["line"],
                    col=message["column"],
                    is_primary=True,
                ),),
                error_code=rule_id,
                hints=_build_hints(rule_id, message, source_code, tree),
            )
        )
    return tuple(diagnostics)


def has_errors(diagnostics: tuple[Diagnostic, ...]) -> bool:
    return any(diag.severity == "error" for diag in diagnostics)


def filter_post_prefix_diagnostics(
    diagnostics: tuple[Diagnostic, ...],
    prefix: str,
) -> tuple[Diagnostic, ...]:
    prefix_end = _prefix_end_span(prefix)
    return tuple(
        diag for diag in diagnostics
        if not _has_primary_span(diag) or _primary_starts_before(diag, prefix_end)
    )


def _has_primary_span(diag: Diagnostic) -> bool:
    return any(s.is_primary for s in diag.spans)


def _primary_starts_before(diag: Diagnostic, limit: tuple[int, int]) -> bool:
    primary = next((s for s in diag.spans if s.is_primary), None)
    if primary is None:
        return True
    limit_line, limit_column = limit
    if primary.line != limit_line:
        return primary.line < limit_line
    return primary.col < limit_column


def _prefix_end_span(prefix: str) -> tuple[int, int]:
    line = 1
    column = 1
    for ch in prefix:
        if ch == "\n":
            line += 1
            column = 1
            continue
        column += 1
    return (line, column)


def _parse_ts(source_code: str | None) -> Tree | None:
    if source_code is None:
        return None
    return _TS_PARSER.parse(source_code.encode("utf-8"))


def _build_hints(
    rule_id: str | None,
    message: dict,
    source_code: str | None,
    ast_tree: Tree | None,
) -> tuple[str, ...]:
    if rule_id != "@typescript-eslint/typedef":
        return ()
    snippet = _build_typedef_variable_snippet(message, source_code, ast_tree)
    if snippet is None:
        return ()
    return (f"Add an explicit type annotation, for example: `{snippet}`",)


def _build_typedef_variable_snippet(
    message: dict,
    source_code: str | None,
    ast_tree: Tree | None,
) -> str | None:
    if source_code is None or ast_tree is None:
        return None
    source_bytes = source_code.encode("utf-8")
    declarator = _find_typedef_declarator(ast_tree, message)
    if declarator is None:
        return None
    declaration = declarator.parent
    if declaration is None or declaration.type not in {"lexical_declaration", "variable_declaration"}:
        return None
    if _variable_declarator_count(declaration) != 1:
        return None
    name_node = declarator.child_by_field_name("name")
    if name_node is None or name_node.type != "identifier":
        return None
    if declarator.child_by_field_name("type") is not None:
        return None
    keyword = _declaration_keyword(declaration, source_bytes)
    if keyword is None:
        return None
    name = _node_text(name_node, source_bytes)
    return f"{keyword} {name}: <add_type_annotation>"


def _node_at_message_span(ast_tree: Tree, message: dict) -> Node | None:
    line = message["line"] - 1
    column = message["column"] - 1
    if line < 0 or column < 0:
        return None
    return ast_tree.root_node.named_descendant_for_point_range((line, column), (line, column))


def _find_typedef_declarator(ast_tree: Tree, message: dict) -> Node | None:
    node = _node_at_message_span(ast_tree, message)
    if node is not None:
        declarator = _find_ancestor(node, "variable_declarator")
        if declarator is not None:
            return declarator
    return _find_single_line_declarator(ast_tree.root_node, message["line"] - 1)


def _find_single_line_declarator(root: Node, line_index: int) -> Node | None:
    matches: list[Node] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "variable_declarator" and node.start_point.row == line_index:
            matches.append(node)
        stack.extend(reversed(node.children))
    if len(matches) != 1:
        return None
    return matches[0]


def _find_ancestor(node: Node, expected_type: str) -> Node | None:
    current: Node | None = node
    while current is not None:
        if current.type == expected_type:
            return current
        current = current.parent
    return None


def _variable_declarator_count(declaration: Node) -> int:
    return sum(1 for child in declaration.children if child.type == "variable_declarator")


def _declaration_keyword(declaration: Node, source_bytes: bytes) -> str | None:
    for child in declaration.children:
        if child.type in {"const", "let", "var"}:
            return _node_text(child, source_bytes)
    return None


def _node_text(node: Node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8")
