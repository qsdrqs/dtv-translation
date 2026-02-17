from __future__ import annotations

import re
from dataclasses import dataclass

from tree_sitter_language_pack import get_parser

from core.types import RollbackScope


_FENCED_BLOCK_RE = re.compile(r"```(?P<lang>[^\n`]*)\n(?P<body>.*?)```", re.DOTALL)
_RUST_LANGS = {"rust", "rs"}
_RUST_PARSER = get_parser("rust")
_TOP_LEVEL_ITEM_TYPES = {
    "function_item",
    "const_item",
    "static_item",
    "struct_item",
    "enum_item",
    "union_item",
    "trait_item",
    "impl_item",
    "mod_item",
    "type_item",
    "extern_crate_declaration",
    "use_declaration",
    "macro_definition",
}


@dataclass(frozen=True)
class ParseResult:
    patch: str | None
    error: str | None
    used_fence: bool


def parse_feedback_output(text: str) -> ParseResult:
    stripped = text.strip()
    if not stripped:
        return ParseResult(patch=None, error="empty model output", used_fence=False)

    matches = list(_FENCED_BLOCK_RE.finditer(stripped))
    if matches:
        if len(matches) > 1:
            return ParseResult(
                patch=None,
                error="multiple fenced code blocks found",
                used_fence=True,
            )
        match = matches[0]
        lang = match.group("lang").strip().lower()
        if lang not in _RUST_LANGS:
            return ParseResult(
                patch=None,
                error="fenced code block language must be rust",
                used_fence=True,
            )
        prefix = stripped[: match.start()].strip()
        suffix = stripped[match.end() :].strip()
        if prefix or suffix:
            return ParseResult(
                patch=None,
                error="fenced output must contain only one code block",
                used_fence=True,
            )
        patch = match.group("body").strip()
        if not patch:
            return ParseResult(
                patch=None,
                error="empty fenced patch",
                used_fence=True,
            )
        return ParseResult(patch=patch, error=None, used_fence=True)

    if "```" in stripped:
        return ParseResult(
            patch=None,
            error="malformed fenced code block",
            used_fence=True,
        )
    return ParseResult(patch=stripped, error=None, used_fence=False)


def validate_patch_scope(patch: str, scope: RollbackScope) -> str | None:
    if scope == RollbackScope.PROGRAM:
        return None

    tree = _RUST_PARSER.parse(patch.encode("utf-8"))
    root = tree.root_node
    if root.has_error:
        return "scope validator: patch is not valid Rust syntax"

    named_children = [child for child in root.children if child.is_named]
    if not named_children:
        return "scope validator: patch has no Rust syntax nodes"

    disallowed = sorted(
        {
            child.type
            for child in named_children
            if child.type in _TOP_LEVEL_ITEM_TYPES or child.type.endswith("_item")
        }
    )
    if disallowed:
        node_types = ", ".join(disallowed)
        return f"scope validator: {scope.value}-scope patch cannot include top-level items ({node_types})"
    return None
