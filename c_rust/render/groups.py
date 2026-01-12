from __future__ import annotations

from tree_sitter_language_pack import get_parser

from core.types import Granularity

_PARSER = get_parser("rust")


def parse_rust(code: str):
    return _PARSER.parse(code.encode("utf-8"))


def rust_group_stack(
    tree,
    *,
    prefix_end_byte: int,
    skip_function_body_block: bool = True,
) -> tuple[Granularity, ...]:
    """Return enclosing (FUNC/BLOCK) groups at the prefix cursor position.

    The cursor is defined as being immediately after the last non-whitespace byte
    in the decoded prefix (prefix_end_byte). Returned stack order is outer -> inner.
    """
    root = tree.root_node
    anchor = root.descendant_for_byte_range(prefix_end_byte, prefix_end_byte)
    if anchor is None:
        return ()

    kinds: list[Granularity] = []
    cur = anchor
    while cur is not None:
        if cur.type == "function_item":
            kinds.append(Granularity.FUNC)
        elif cur.type == "block":
            if skip_function_body_block and _is_function_body_block(cur):
                pass
            else:
                kinds.append(Granularity.BLOCK)
        cur = cur.parent

    kinds.reverse()
    return tuple(kinds)


def _is_function_body_block(node) -> bool:
    parent = node.parent
    if parent is None or parent.type != "function_item":
        return False
    body = parent.child_by_field_name("body")
    return body is not None and body.id == node.id

