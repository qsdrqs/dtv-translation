from __future__ import annotations

from tree_sitter_language_pack import get_parser

from core.types import Granularity, GroupStackFrame

_PARSER = get_parser("rust")


def parse_rust(code: str):
    return _PARSER.parse(code.encode("utf-8"))


def rust_group_stack(
    tree,
    *,
    prefix_end_byte: int,
    source_bytes: bytes,
    skip_function_body_block: bool = True,
) -> tuple[GroupStackFrame, ...]:
    """Return enclosing (FUNC/BLOCK) groups at the prefix cursor position.

    The cursor is defined as being immediately after the last non-whitespace byte
    in the decoded prefix (prefix_end_byte). Returned stack order is outer -> inner.
    """
    root = tree.root_node
    anchor = root.descendant_for_byte_range(prefix_end_byte, prefix_end_byte)
    if anchor is None:
        return ()

    frames: list[GroupStackFrame] = []
    cur = anchor
    while cur is not None:
        if cur.type == "function_item":
            frames.append(
                GroupStackFrame(
                    kind=Granularity.FUNC,
                    name_id=_function_name(cur, source_bytes),
                    group_id=f"func@{cur.start_byte}",
                )
            )
        elif cur.type == "block":
            if skip_function_body_block and _is_function_body_block(cur):
                pass
            else:
                frames.append(
                    GroupStackFrame(
                        kind=Granularity.BLOCK,
                        group_id=f"block@{cur.start_byte}",
                    )
                )
        cur = cur.parent

    frames.reverse()
    return tuple(frames)


def _function_name(node, source_bytes: bytes) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        for child in node.children:
            if child.type == "identifier":
                name_node = child
                break
    if name_node is None:
        return None
    return source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8")


def _is_function_body_block(node) -> bool:
    parent = node.parent
    if parent is None or parent.type != "function_item":
        return False
    body = parent.child_by_field_name("body")
    return body is not None and body.id == node.id
