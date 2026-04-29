from __future__ import annotations

from core.types import Granularity, GroupStackFrame

_FUNC_TYPES = frozenset({
    "function_declaration",
    "method_definition",
    "arrow_function",
    "generator_function_declaration",
})

# Only true top-level function declarations and class declarations split
# top-level code into blocks.
# Arrow functions assigned to variables (lexical_declaration > arrow_function)
# and method definitions (inside classes) do not split.
_TOPLEVEL_BLOCK_SEPARATOR_TYPES = frozenset({
    "function_declaration",
    "generator_function_declaration",
    "class_declaration",
    "abstract_class_declaration",
})

_WRAPPER_TYPES = frozenset({
    "export_statement",
    "ambient_declaration",
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
        toplevel_frame = _toplevel_block_frame(root, source_bytes, prefix_end_byte)
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


def _toplevel_block_frame(
    root,
    source_bytes: bytes,
    prefix_end_byte: int,
) -> GroupStackFrame | None:
    if root.type != "program":
        return None

    # If the cursor is inside or at the exact end of a top-level declaration,
    # no toplevel block yet: the declaration boundary must be fully passed.
    for child in root.children:
        sep = _find_separator(child)
        if sep is not None:
            if sep.start_byte < prefix_end_byte <= sep.end_byte:
                return None

    block_start = 0
    for child in root.children:
        sep = _find_separator(child)
        if sep is not None and sep.end_byte < prefix_end_byte:
            block_start = sep.end_byte

    # No frame until the cursor has actually advanced past the boundary into
    # real (non-whitespace) content. Otherwise the frame would open with
    # start_stmt at the boundary commit, and BLOCK rollback would land one
    # checkpoint earlier - inside the just-closed declaration - dropping its
    # closing brace.
    if not source_bytes[block_start:prefix_end_byte].strip():
        return None

    return GroupStackFrame(
        kind=Granularity.BLOCK,
        group_id=f"toplevel_block@{block_start}",
    )


def _find_separator(node):
    """Return the inner declaration node if `node` (or its child in a wrapper)
    is a top-level block separator; otherwise return None."""
    if node.type in _WRAPPER_TYPES:
        for child in node.children:
            if child.type in _TOPLEVEL_BLOCK_SEPARATOR_TYPES:
                return child
        return None
    if node.type in _TOPLEVEL_BLOCK_SEPARATOR_TYPES:
        return node
    return None


def _is_function_body_block(node) -> bool:
    parent = node.parent
    if parent is None or parent.type not in _FUNC_TYPES:
        return False
    body = parent.child_by_field_name("body")
    return body is not None and body.id == node.id
