from __future__ import annotations

from core.types import Granularity, GroupStackFrame

_FUNC_TYPES = frozenset({
    "function_declaration",
    "method_definition",
    "arrow_function",
    "generator_function_declaration",
})

# Only true top-level function declarations split top-level code into blocks.
# Arrow functions assigned to variables (lexical_declaration > arrow_function)
# and method definitions (inside classes) do not split.
_TOPLEVEL_FUNC_SEPARATOR_TYPES = frozenset({
    "function_declaration",
    "generator_function_declaration",
})


def ts_group_stack(
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
        if cur.type in _FUNC_TYPES:
            frames.append(
                GroupStackFrame(
                    kind=Granularity.FUNC,
                    name_id=_function_name(cur, source_bytes),
                    group_id=f"func@{cur.start_byte}",
                )
            )
        elif cur.type == "statement_block":
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

    has_func = any(f.kind == Granularity.FUNC for f in frames)
    if not has_func:
        toplevel_frame = _toplevel_block_frame(root, prefix_end_byte)
        if toplevel_frame is not None:
            frames.insert(0, toplevel_frame)

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


def _toplevel_block_frame(root, prefix_end_byte: int) -> GroupStackFrame | None:
    if root.type != "program":
        return None
    block_start = 0
    for child in root.children:
        if child.type in _TOPLEVEL_FUNC_SEPARATOR_TYPES and child.end_byte <= prefix_end_byte:
            block_start = child.end_byte
    return GroupStackFrame(
        kind=Granularity.BLOCK,
        group_id=f"toplevel_block@{block_start}",
    )


def _is_function_body_block(node) -> bool:
    parent = node.parent
    if parent is None or parent.type not in _FUNC_TYPES:
        return False
    body = parent.child_by_field_name("body")
    return body is not None and body.id == node.id
