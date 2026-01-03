"""Rust source code instrumentation for trace-based differential testing."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from tree_sitter_language_pack import get_parser


TRACE_MODULE_PATH = Path(__file__).parent / "trace_runtime" / "dtv_trace.rs"
_INSERT_ORDER = {
    "enter": 0,
    "ret_close": 1,
    "ret_open": 2,
    "implicit_exit": 3,
    "end_exit": 4,
}
_COMMENT_NODES = ("line_comment", "block_comment")

_RUST_TAGS = {
    "i8",
    "i16",
    "i32",
    "i64",
    "isize",
    "u8",
    "u16",
    "u32",
    "u64",
    "usize",
    "f32",
    "f64",
    "bool",
    "char",
}


@dataclass(frozen=True)
class RustTypeInfo:
    tag: str | None
    supported: bool
    reason: str | None = None
    pointer_like: bool = False
    is_slice: bool = False
    is_array: bool = False
    is_raw_pointer: bool = False
    is_reference: bool = False
    is_void: bool = False

    @property
    def json_tag(self) -> str | None:
        if self.tag is None:
            return None
        if self.pointer_like:
            return f"ptr_{self.tag}"
        return self.tag


@dataclass(frozen=True)
class RustParamSpec:
    name: str | None
    type_info: RustTypeInfo


@dataclass(frozen=True)
class RustSignature:
    params: list[RustParamSpec]
    ret: RustTypeInfo


def instrument_rust_functions(rust_source: str, target_function: str | None = None) -> str:
    """Instrument all Rust functions with trace calls (args/ret for target function)."""
    # TODO: Handle ? operator (early returns from Result/Option)
    parser = get_parser("rust")
    source_bytes = rust_source.encode("utf8")
    tree = parser.parse(source_bytes)

    trace_module = TRACE_MODULE_PATH.read_text()
    functions = _find_functions(tree.root_node, source_bytes)
    edits: list[tuple[int, int, str, bytes]] = []

    for func in functions:
        func_name = func["name"]
        body_node = func["body_node"]
        return_nodes = func["return_nodes"]
        implicit_return = func["implicit_return"]
        ends_with_return = _block_ends_with_return(body_node)
        signature = func.get("signature")
        is_target = target_function is not None and func_name == target_function and signature is not None

        if is_target:
            enter_code = _render_rust_enter(func_name, signature)
            edits.append(
                (
                    body_node.start_byte + 1,
                    body_node.start_byte + 1,
                    "enter",
                    enter_code.encode("utf8"),
                )
            )

            for idx, ret_node in enumerate(return_nodes):
                ret_code = _render_rust_return(
                    func_name,
                    signature,
                    ret_node,
                    source_bytes,
                    idx,
                )
                edits.append(
                    (
                        ret_node.start_byte,
                        ret_node.end_byte,
                        "ret_replace",
                        ret_code.encode("utf8"),
                    )
                )

            if implicit_return is not None:
                implicit_code = _render_rust_implicit_return(
                    func_name,
                    signature,
                    implicit_return,
                    source_bytes,
                )
                edits.append(
                    (
                        implicit_return.start_byte,
                        implicit_return.end_byte,
                        "implicit_replace",
                        implicit_code.encode("utf8"),
                    )
                )
            elif not ends_with_return:
                end_code = _render_rust_fallthrough_exit(func_name, signature)
                edits.append(
                    (
                        body_node.end_byte - 1,
                        body_node.end_byte - 1,
                        "end_exit",
                        end_code.encode("utf8"),
                    )
                )
        else:
            edits.append(
                (
                    body_node.start_byte + 1,
                    body_node.start_byte + 1,
                    "enter",
                    f'\n    trace_function_enter("{func_name}");'.encode("utf8"),
                )
            )

            for ret_node in return_nodes:
                edits.append(
                    (
                        ret_node.start_byte,
                        ret_node.start_byte,
                        "ret_open",
                        f'{{ trace_function_exit("{func_name}"); '.encode("utf8"),
                    )
                )
                edits.append((ret_node.end_byte, ret_node.end_byte, "ret_close", b" }"))

            if implicit_return is not None:
                edits.append(
                    (
                        implicit_return.start_byte,
                        implicit_return.start_byte,
                        "implicit_exit",
                        f'trace_function_exit("{func_name}"); '.encode("utf8"),
                    )
                )
            elif not ends_with_return:
                edits.append(
                    (
                        body_node.end_byte - 1,
                        body_node.end_byte - 1,
                        "end_exit",
                        f'trace_function_exit("{func_name}");'.encode("utf8"),
                    )
                )

    instrumented_bytes = _apply_edits(source_bytes, edits, _INSERT_ORDER)
    instrumented = instrumented_bytes.decode("utf8")

    header = f"#[allow(dead_code)]\nmod dtv_trace {{\n{trace_module}\n}}\n\n"
    header += "use dtv_trace::*;\n\n"

    return header + instrumented


def _apply_insertions(
    source_bytes: bytes,
    insertions: list[tuple[int, str, bytes]],
    order: dict[str, int],
) -> bytes:
    edits = [(pos, pos, kind, text) for pos, kind, text in insertions]
    return _apply_edits(source_bytes, edits, order)


def _apply_edits(
    source_bytes: bytes,
    edits: list[tuple[int, int, str, bytes]],
    order: dict[str, int],
) -> bytes:
    grouped: dict[tuple[int, int], list[tuple[str, bytes]]] = defaultdict(list)
    for start, end, kind, text in edits:
        grouped[(start, end)].append((kind, text))

    combined: list[tuple[int, int, bytes]] = []
    for (start, end), items in grouped.items():
        items.sort(key=lambda item: order.get(item[0], 0))
        combined.append((start, end, b"".join(text for _, text in items)))

    for start, end, text in sorted(combined, key=lambda item: item[0], reverse=True):
        source_bytes = source_bytes[:start] + text + source_bytes[end:]
    return source_bytes


def _find_functions(node, source: bytes) -> list[dict]:
    """Find all function definitions in Rust AST."""
    functions = []

    def visit(n):
        if n.type == 'function_item':
            func_info = _extract_function_info(n, source)
            if func_info:
                functions.append(func_info)

        for child in n.children:
            visit(child)

    visit(node)
    return functions


def _extract_function_info(func_node, source: bytes) -> dict | None:
    name_node = None
    body_node = None

    for child in func_node.children:
        if child.type == 'identifier':
            name_node = child
        elif child.type == 'block':
            body_node = child

    if not name_node or not body_node:
        return None

    func_name = source[name_node.start_byte:name_node.end_byte].decode("utf8")
    return_nodes = _find_return_statements(body_node)
    implicit_return = _find_implicit_return(body_node, source)
    signature = _extract_function_signature(func_node, source)

    return {
        "name": func_name,
        "body_node": body_node,
        "return_nodes": return_nodes,
        "implicit_return": implicit_return,
        "signature": signature,
    }


def _find_return_statements(block_node) -> list:
    """Find all return_expression nodes in the block, excluding nested functions/closures."""
    returns = []

    def visit(n):
        # Skip nested scopes to avoid instrumenting returns from inner functions
        if n.type in ("function_item", "closure_expression", "async_block"):
            return
        # Collect return statements at current scope level
        if n.type == 'return_expression':
            returns.append(n)
        # Recursively visit child nodes
        for child in n.children:
            visit(child)

    visit(block_node)
    return returns


def _find_implicit_return(block_node, source: bytes):
    last_named = _last_named_non_comment(block_node)
    if last_named is None:
        return None
    if _is_return_statement(last_named):
        return None
    if last_named.type == "let_declaration":
        return None
    if last_named.type == "expression_statement":
        if _has_semicolon_after(last_named, block_node, source):
            return None
        return last_named
    if _has_semicolon_after(last_named, block_node, source):
        return None
    return last_named


def _block_ends_with_return(block_node) -> bool:
    last_named = _last_named_non_comment(block_node)
    if last_named is None:
        return False
    if _is_return_statement(last_named):
        return True
    return False


def _last_named_non_comment(block_node):
    for child in reversed(block_node.named_children):
        if child.type in _COMMENT_NODES:
            continue
        return child
    return None


def _is_return_statement(node) -> bool:
    if node.type == "return_expression":
        return True
    if node.type != "expression_statement":
        return False
    for child in node.children:
        if child.type == "return_expression":
            return True
    return False


def _has_semicolon_after(node, block_node, source: bytes) -> bool:
    i = node.end_byte
    end = block_node.end_byte
    while i < end:
        ch = source[i]
        if ch in (9, 10, 13, 32):
            i += 1
            continue
        if ch == 47 and i + 1 < end:
            nxt = source[i + 1]
            if nxt == 47:
                i += 2
                while i < end and source[i] not in (10, 13):
                    i += 1
                continue
            if nxt == 42:
                i += 2
                while i + 1 < end and not (source[i] == 42 and source[i + 1] == 47):
                    i += 1
                i += 2
                continue
        return ch == 59
    return False


def _extract_function_signature(func_node, source: bytes) -> RustSignature | None:
    params_node = func_node.child_by_field_name("parameters")
    params: list[RustParamSpec] = []
    if params_node is not None:
        for child in params_node.named_children:
            if child.type == "parameter":
                pattern_node = child.child_by_field_name("pattern") or child.child_by_field_name("name")
                type_node = child.child_by_field_name("type")
                name = _extract_rust_pattern_name(pattern_node, source)
                type_info = _parse_rust_type(type_node, source)
                if name is None:
                    type_info = _mark_unsupported(type_info, "missing_name")
                params.append(RustParamSpec(name=name, type_info=type_info))
            elif child.type == "self_parameter":
                type_info = RustTypeInfo(tag=None, supported=False, reason="self_param")
                params.append(RustParamSpec(name="self", type_info=type_info))

    return_node = _find_return_type_node(func_node, params_node)
    if return_node is None:
        ret_info = RustTypeInfo(tag=None, supported=True, is_void=True)
    else:
        ret_info = _parse_rust_type(return_node, source)
        if ret_info.is_void:
            ret_info = RustTypeInfo(tag=None, supported=True, is_void=True)

    return RustSignature(params=params, ret=ret_info)


def _extract_rust_pattern_name(pattern_node, source: bytes) -> str | None:
    if pattern_node is None:
        return None

    identifier = None

    def visit(node):
        nonlocal identifier
        if identifier is not None:
            return
        if node.type == "identifier":
            identifier = _slice_text(source, node)
            return
        for child in node.children:
            visit(child)

    visit(pattern_node)
    return identifier


def _find_return_type_node(func_node, params_node):
    return_node = func_node.child_by_field_name("return_type")
    if return_node is not None:
        return return_node
    if params_node is None:
        return None
    for child in func_node.children:
        if child.start_byte <= params_node.end_byte:
            continue
        if child.type in (
            "primitive_type",
            "reference_type",
            "pointer_type",
            "array_type",
            "slice_type",
            "tuple_type",
            "type_identifier",
            "scoped_type_identifier",
            "generic_type",
            "unit_type",
        ):
            return child
    return None


def _parse_rust_type(node, source: bytes) -> RustTypeInfo:
    if node is None:
        return RustTypeInfo(tag=None, supported=False, reason="missing_type")

    node_text = _slice_text(source, node)
    if node.type == "unit_type" or node_text.strip() == "()":
        return RustTypeInfo(tag=None, supported=True, is_void=True)

    if node.type == "primitive_type":
        tag = node_text
        if tag in _RUST_TAGS:
            return RustTypeInfo(tag=tag, supported=True)
        return RustTypeInfo(tag=None, supported=False, reason="unsupported_type")

    if node.type == "reference_type":
        inner = node.child_by_field_name("type") or _last_named_child(node)
        inner_info = _parse_rust_type(inner, source)
        if not inner_info.supported or inner_info.is_void:
            return _mark_unsupported(inner_info, inner_info.reason or "unsupported_type")
        if inner_info.pointer_like:
            if inner_info.is_slice or inner_info.is_array:
                return RustTypeInfo(
                    tag=inner_info.tag,
                    supported=True,
                    pointer_like=True,
                    is_reference=True,
                    is_slice=inner_info.is_slice,
                    is_array=inner_info.is_array,
                )
            return RustTypeInfo(tag=None, supported=False, reason="pointer_depth>1")
        return RustTypeInfo(
            tag=inner_info.tag,
            supported=True,
            pointer_like=True,
            is_reference=True,
        )

    if node.type == "pointer_type":
        inner = node.child_by_field_name("type") or _last_named_child(node)
        inner_info = _parse_rust_type(inner, source)
        if not inner_info.supported or inner_info.is_void:
            return _mark_unsupported(inner_info, inner_info.reason or "unsupported_type")
        if inner_info.pointer_like:
            return RustTypeInfo(tag=None, supported=False, reason="pointer_depth>1")
        return RustTypeInfo(
            tag=inner_info.tag,
            supported=True,
            pointer_like=True,
            is_raw_pointer=True,
        )

    if node.type == "array_type":
        inner = node.child_by_field_name("element") or _first_named_child(node)
        inner_info = _parse_rust_type(inner, source)
        if not inner_info.supported or inner_info.is_void:
            return _mark_unsupported(inner_info, inner_info.reason or "unsupported_type")
        if inner_info.pointer_like:
            return RustTypeInfo(tag=None, supported=False, reason="pointer_depth>1")
        if node.child_by_field_name("length") is None:
            return RustTypeInfo(
                tag=inner_info.tag,
                supported=True,
                pointer_like=True,
                is_slice=True,
            )
        return RustTypeInfo(
            tag=inner_info.tag,
            supported=True,
            pointer_like=True,
            is_array=True,
        )

    if node.type == "slice_type":
        inner = node.child_by_field_name("element") or _first_named_child(node)
        inner_info = _parse_rust_type(inner, source)
        if not inner_info.supported or inner_info.is_void:
            return _mark_unsupported(inner_info, inner_info.reason or "unsupported_type")
        if inner_info.pointer_like:
            return RustTypeInfo(tag=None, supported=False, reason="pointer_depth>1")
        return RustTypeInfo(
            tag=inner_info.tag,
            supported=True,
            pointer_like=True,
            is_slice=True,
        )

    return RustTypeInfo(tag=None, supported=False, reason="unsupported_type")


def _mark_unsupported(info: RustTypeInfo, reason: str) -> RustTypeInfo:
    return RustTypeInfo(
        tag=info.tag,
        supported=False,
        reason=reason,
        pointer_like=info.pointer_like,
        is_slice=info.is_slice,
        is_array=info.is_array,
        is_raw_pointer=info.is_raw_pointer,
        is_reference=info.is_reference,
        is_void=info.is_void,
    )


def _last_named_child(node):
    for child in reversed(node.named_children):
        return child
    return None


def _first_named_child(node):
    for child in node.named_children:
        return child
    return None


def _slice_text(source: bytes, node) -> str:
    return source[node.start_byte:node.end_byte].decode("utf8")


def _render_rust_enter(func_name: str, signature: RustSignature) -> str:
    lines, args_var = _render_rust_args_json(signature.params)
    lines.append(f'trace_function_enter_args("{func_name}", &{args_var});')
    return _indent_lines(lines)


def _render_rust_return(
    func_name: str,
    signature: RustSignature,
    ret_node,
    source_bytes: bytes,
    index: int,
) -> str:
    expr_node = ret_node.named_children[0] if ret_node.named_children else None
    expr_text = _slice_text(source_bytes, expr_node) if expr_node is not None else None

    if expr_text is None:
        ptr_lines, ptr_var = _render_rust_ptr_args_json(signature.params, index)
        ret_lines, ret_var = _render_rust_ret_json(signature.ret, None, index)
        ptr_arg = f"Some(&{ptr_var})" if ptr_var is not None else "None"
        ret_arg = f"Some(&{ret_var})" if ret_var is not None else "None"
        ptr_block = "\n".join(ptr_lines)
        ret_block = "\n".join(ret_lines)
        content = f"""\
{{
{ptr_block}
{ret_block}
trace_function_exit_ret("{func_name}", {ret_arg}, {ptr_arg});
return;
}}"""
        lines = [line for line in content.splitlines() if line]
        return _indent_lines(lines)

    ret_var = f"__dtv_ret_{index}"
    ptr_lines, ptr_var = _render_rust_ptr_args_json(signature.params, index)
    ret_lines, ret_json = _render_rust_ret_json(signature.ret, ret_var, index)
    ptr_arg = f"Some(&{ptr_var})" if ptr_var is not None else "None"
    ret_arg = f"Some(&{ret_json})" if ret_json is not None else "None"
    ptr_block = "\n".join(ptr_lines)
    ret_block = "\n".join(ret_lines)
    content = f"""\
return {{
let {ret_var} = {expr_text};
{ptr_block}
{ret_block}
trace_function_exit_ret("{func_name}", {ret_arg}, {ptr_arg});
{ret_var}
}};"""
    lines = [line for line in content.splitlines() if line]
    return _indent_lines(lines)


def _render_rust_implicit_return(
    func_name: str,
    signature: RustSignature,
    expr_node,
    source_bytes: bytes,
) -> str:
    expr_text = _slice_text(source_bytes, expr_node)
    ret_var = "__dtv_ret_implicit"
    ptr_lines, ptr_var = _render_rust_ptr_args_json(signature.params, "implicit")
    ret_lines, ret_json = _render_rust_ret_json(signature.ret, ret_var, "implicit")
    ptr_arg = f"Some(&{ptr_var})" if ptr_var is not None else "None"
    ret_arg = f"Some(&{ret_json})" if ret_json is not None else "None"
    ptr_block = "\n".join(ptr_lines)
    ret_block = "\n".join(ret_lines)
    content = f"""\
{{
let {ret_var} = {expr_text};
{ptr_block}
{ret_block}
trace_function_exit_ret("{func_name}", {ret_arg}, {ptr_arg});
{ret_var}
}}"""
    lines = [line for line in content.splitlines() if line]
    return _indent_lines(lines)


def _render_rust_fallthrough_exit(func_name: str, signature: RustSignature) -> str:
    ptr_lines, ptr_var = _render_rust_ptr_args_json(signature.params, "end")
    ptr_arg = f"Some(&{ptr_var})" if ptr_var is not None else "None"
    ptr_block = "\n".join(ptr_lines)
    content = f"""\
{ptr_block}
trace_function_exit_ret("{func_name}", None, {ptr_arg});"""
    lines = [line for line in content.splitlines() if line]
    return _indent_lines(lines)


def _render_rust_args_json(params: list[RustParamSpec]) -> tuple[list[str], str]:
    lines = ["let mut __dtv_args = DtvJsonArray::new();"]
    for param in params:
        lines.extend(_render_rust_json_push(param.type_info, param.name, "__dtv_args"))
    json_var = "__dtv_args_json"
    lines.append(f"let {json_var} = __dtv_args.finish();")
    return lines, json_var


def _render_rust_ptr_args_json(
    params: list[RustParamSpec],
    index: int | str,
) -> tuple[list[str], str | None]:
    ptr_params = [param for param in params if param.type_info.pointer_like]
    if not ptr_params:
        return [], None
    prefix = f"__dtv_ptr_args_{index}"
    lines = [f"let mut {prefix} = DtvJsonArray::new();"]
    for param in ptr_params:
        lines.extend(_render_rust_json_push(param.type_info, param.name, prefix))
    json_var = f"{prefix}_json"
    lines.append(f"let {json_var} = {prefix}.finish();")
    return lines, json_var


def _render_rust_ret_json(
    ret_info: RustTypeInfo,
    ret_var: str | None,
    index: int | str,
) -> tuple[list[str], str | None]:
    if ret_info.is_void:
        return [], None
    if not ret_info.supported or ret_info.tag is None:
        reason = ret_info.reason or "unsupported_type"
        var_name = f"__dtv_ret_json_{index}"
        line = f'let {var_name} = json_value_unsupported("{reason}");'
        return [line], var_name
    if ret_var is None:
        return [], None
    var_name = f"__dtv_ret_json_{index}"
    lines = _render_rust_json_value(ret_info, ret_var, var_name)
    return lines, var_name


def _render_rust_json_push(
    type_info: RustTypeInfo,
    value_name: str | None,
    array_var: str,
) -> list[str]:
    if value_name is None or not type_info.supported or type_info.tag is None:
        reason = type_info.reason or "unsupported_type"
        return [f'{array_var}.push_json(json_value_unsupported("{reason}"));']
    func = _rust_json_value_func(type_info)
    value_expr = _rust_json_value_expr(type_info, value_name)
    return [f"{array_var}.push_json({func}({value_expr}));"]


def _render_rust_json_value(
    type_info: RustTypeInfo,
    value_name: str,
    var_name: str,
) -> list[str]:
    if not type_info.supported or type_info.tag is None:
        reason = type_info.reason or "unsupported_type"
        return [f'let {var_name} = json_value_unsupported("{reason}");']
    func = _rust_json_value_func(type_info)
    value_expr = _rust_json_value_expr(type_info, value_name)
    return [f"let {var_name} = {func}({value_expr});"]


def _rust_json_value_expr(type_info: RustTypeInfo, value_name: str) -> str:
    if type_info.is_array and not type_info.is_reference:
        return f"&{value_name}"
    return value_name


def _rust_json_value_func(type_info: RustTypeInfo) -> str:
    tag = type_info.tag or "unsupported"
    if not type_info.pointer_like:
        return f"json_value_{tag}"
    if type_info.is_slice:
        return f"json_value_slice_{tag}"
    if type_info.is_raw_pointer:
        return f"json_value_raw_ptr_{tag}"
    if type_info.is_array:
        return f"json_value_array_{tag}"
    if type_info.is_reference:
        return f"json_value_ref_{tag}"
    return f"json_value_ref_{tag}"


def _indent_lines(lines: list[str]) -> str:
    return "\n    " + "\n    ".join(lines)
