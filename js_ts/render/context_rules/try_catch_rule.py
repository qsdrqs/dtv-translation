from __future__ import annotations


def apply_try_catch(code: str, prefix_len: int, tree, source_bytes: bytes) -> str:
    patches: list[tuple[int, str]] = []
    for node in _find_try_statements(tree.root_node):
        has_handler = any(
            c.type in ("catch_clause", "finally_clause")
            for c in node.children
        )
        if has_handler:
            continue
        body = node.child_by_field_name("body")
        if body is None or body.end_byte < prefix_len:
            continue
        patches.append((body.end_byte, " catch(e) {}"))

    if not patches:
        return code
    patches.sort(key=lambda p: p[0], reverse=True)
    patched = source_bytes
    for pos, text in patches:
        patched = patched[:pos] + text.encode("utf-8") + patched[pos:]
    return patched.decode("utf-8")


def _find_try_statements(root):
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "try_statement":
            yield node
        stack.extend(reversed(node.children))
