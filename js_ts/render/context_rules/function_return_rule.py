from __future__ import annotations

_FUNCTION_TYPES = frozenset({
    "function_declaration",
    "method_definition",
    "arrow_function",
    "generator_function_declaration",
})

_EXEMPT_RETURN_TYPES = frozenset({"void", "undefined", "any"})


def apply_function_return(
    code: str, prefix_len: int, tree, source_bytes: bytes,
) -> str:
    patches: list[tuple[int, str]] = []
    for node in _find_functions(tree.root_node):
        return_type = node.child_by_field_name("return_type")
        if return_type is None:
            continue
        type_node = _type_from_annotation(return_type)
        if type_node is None:
            continue
        type_name = source_bytes[type_node.start_byte:type_node.end_byte].decode("utf-8")
        if type_name in _EXEMPT_RETURN_TYPES:
            continue
        body = node.child_by_field_name("body")
        if body is None or body.type != "statement_block":
            continue
        if _has_return_in_body(body):
            continue
        insert_pos = body.end_byte - 1  # before the closing }
        if insert_pos < prefix_len:
            continue
        patches.append((insert_pos, "return undefined as any;\n"))

    if not patches:
        return code
    patches.sort(key=lambda p: p[0], reverse=True)
    patched = source_bytes
    for pos, text in patches:
        patched = patched[:pos] + text.encode("utf-8") + patched[pos:]
    return patched.decode("utf-8")


def _type_from_annotation(annotation_node):
    for child in annotation_node.children:
        if child.type != ":":
            return child
    return None


def _find_functions(root):
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in _FUNCTION_TYPES:
            yield node
        stack.extend(reversed(node.children))


def _has_return_in_body(body_node) -> bool:
    # Skip nested function bodies - their returns don't count for the outer function.
    stack = list(body_node.children)
    while stack:
        node = stack.pop()
        if node.type == "return_statement":
            return True
        if node.type in _FUNCTION_TYPES:
            continue
        stack.extend(node.children)
    return False
