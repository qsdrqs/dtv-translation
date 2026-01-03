"""C source code instrumentation for trace-based differential testing."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from tree_sitter_language_pack import get_parser


TRACE_HEADER_PATH = Path(__file__).parent / "trace_runtime" / "dtv_trace.h"
_INSERT_ORDER = {
    "enter": 0,
    "ret_close": 1,
    "ret_open": 2,
    "end_exit": 3,
}

_C_TYPE_TAGS = {
    "int": "i32",
    "long": "i64",
    "long long": "i64",
    "short": "i16",
    "char": "i8",
    "signed char": "i8",
    "unsigned int": "u32",
    "unsigned long": "u64",
    "unsigned long long": "u64",
    "unsigned short": "u16",
    "unsigned char": "u8",
    "float": "f32",
    "double": "f64",
    "bool": "bool",
    "_bool": "bool",
    "size_t": "usize",
    "ssize_t": "isize",
}

_INT_TAGS = {"i8", "i16", "i32", "i64", "isize"}
_UINT_TAGS = {"u8", "u16", "u32", "u64", "usize"}
_FLOAT_TAGS = {"f32", "f64"}
_BOOL_TAGS = {"bool"}


@dataclass(frozen=True)
class ParamSpec:
    name: str | None
    tag: str | None
    pointer_like: bool
    supported: bool
    reason: str | None = None

    @property
    def json_tag(self) -> str | None:
        if self.tag is None:
            return None
        if self.pointer_like:
            return f"ptr_{self.tag}"
        return self.tag


@dataclass(frozen=True)
class ReturnSpec:
    tag: str | None
    pointer_like: bool
    supported: bool
    reason: str | None = None
    is_void: bool = False

    @property
    def json_tag(self) -> str | None:
        if self.tag is None:
            return None
        if self.pointer_like:
            return f"ptr_{self.tag}"
        return self.tag


@dataclass(frozen=True)
class FunctionSignature:
    params: list[ParamSpec]
    ret: ReturnSpec


def instrument_c_functions(c_source: str, target_function: str | None = None) -> str:
    """Instrument all C functions with trace calls (args/ret for target function)."""
    parser = get_parser("c")
    source_bytes = c_source.encode("utf8")
    tree = parser.parse(source_bytes)

    functions = _find_functions(tree.root_node, source_bytes)
    edits: list[tuple[int, int, str, bytes]] = []

    for func in functions:
        func_name = func["name"]
        body_node = func["body_node"]
        return_nodes = func["return_nodes"]
        signature = func.get("signature")
        is_target = target_function is not None and func_name == target_function and signature is not None

        if is_target:
            enter_code = _render_c_enter(func_name, signature.params)
            edits.append(
                (
                    body_node.start_byte + 1,
                    body_node.start_byte + 1,
                    "enter",
                    enter_code.encode("utf8"),
                )
            )

            for idx, ret_node in enumerate(return_nodes):
                ret_code = _render_c_return(
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

            if not return_nodes:
                end_code = _render_c_fallthrough_exit(func_name, signature)
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
                    f'\n    dtv_trace_function_enter("{func_name}");'.encode("utf8"),
                )
            )

            for ret_node in return_nodes:
                edits.append(
                    (
                        ret_node.start_byte,
                        ret_node.start_byte,
                        "ret_open",
                        f'{{ dtv_trace_function_exit("{func_name}"); '.encode("utf8"),
                    )
                )
                edits.append((ret_node.end_byte, ret_node.end_byte, "ret_close", b" }"))

            if not return_nodes:
                edits.append(
                    (
                        body_node.end_byte - 1,
                        body_node.end_byte - 1,
                        "end_exit",
                        f' dtv_trace_function_exit("{func_name}");'.encode("utf8"),
                    )
                )

    instrumented_bytes = _apply_edits(source_bytes, edits, _INSERT_ORDER)
    instrumented = instrumented_bytes.decode("utf8")
    header_include = f'#include "{TRACE_HEADER_PATH}"\n\n'
    return header_include + instrumented


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
    """Find all function definitions in C AST."""
    functions = []

    def visit(n):
        if n.type == 'function_definition':
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
        if child.type == 'function_declarator':
            for subchild in child.children:
                if subchild.type == 'identifier':
                    name_node = subchild
                    break
        elif child.type == 'compound_statement':
            body_node = child

    if not name_node or not body_node:
        return None

    func_name = source[name_node.start_byte:name_node.end_byte].decode("utf8")
    return_nodes = _find_return_statements(body_node)
    signature = _extract_function_signature(func_node, source)

    return {
        "name": func_name,
        "body_node": body_node,
        "return_nodes": return_nodes,
        "signature": signature,
    }


def _find_return_statements(block_node) -> list:
    returns = []

    def visit(n):
        if n.type == 'return_statement':
            returns.append(n)
        for child in n.children:
            visit(child)

    visit(block_node)
    return returns


def _extract_function_signature(func_node, source: bytes) -> FunctionSignature | None:
    declarator = None
    return_type_node = None

    for child in func_node.children:
        if child.type in ('primitive_type', 'type_identifier', 'sized_type_specifier'):
            return_type_node = child
        elif child.type in ('function_declarator', 'pointer_declarator', 'parenthesized_declarator'):
            declarator = child

    if declarator is None:
        return None

    declarator, return_pointer_depth = _find_function_declarator(declarator)
    if declarator is None:
        return None

    param_list = None
    for child in declarator.children:
        if child.type == 'parameter_list':
            param_list = child
            break

    params = []
    if param_list is not None:
        for param in param_list.children:
            if param.type != 'parameter_declaration':
                continue
            params.append(_parse_c_parameter(param, source))

    if len(params) == 1 and params[0].tag is None and params[0].reason == "void_param":
        params = []

    ret_spec = _parse_c_return(return_type_node, return_pointer_depth, source)
    return FunctionSignature(params=params, ret=ret_spec)


def _parse_c_return(return_type_node, pointer_depth: int, source: bytes) -> ReturnSpec:
    if return_type_node is None:
        return ReturnSpec(tag=None, pointer_like=False, supported=False, reason="missing_return_type")
    base_type = _normalize_c_type(_slice_text(source, return_type_node))
    if base_type == "void" and pointer_depth == 0:
        return ReturnSpec(tag=None, pointer_like=False, supported=True, is_void=True)
    if pointer_depth > 1:
        return ReturnSpec(tag=None, pointer_like=False, supported=False, reason="pointer_depth>1")
    tag = _C_TYPE_TAGS.get(base_type)
    if tag is None:
        return ReturnSpec(tag=None, pointer_like=pointer_depth == 1, supported=False, reason="unsupported_type")
    return ReturnSpec(tag=tag, pointer_like=pointer_depth == 1, supported=True)


def _parse_c_parameter(param_node, source: bytes) -> ParamSpec:
    pointer_depth = _count_pointer_declarators(param_node)
    has_array = _has_array_declarator(param_node)
    pointer_like = pointer_depth > 0 or has_array

    name = _find_identifier(param_node, source)
    type_node = _find_type_node(param_node)
    if type_node is None:
        return ParamSpec(name=name, tag=None, pointer_like=pointer_like, supported=False, reason="missing_type")

    base_type = _normalize_c_type(_slice_text(source, type_node))
    if base_type == "void" and name is None and not pointer_like:
        return ParamSpec(name=None, tag=None, pointer_like=False, supported=False, reason="void_param")
    if pointer_depth > 1:
        return ParamSpec(name=name, tag=None, pointer_like=pointer_like, supported=False, reason="pointer_depth>1")

    tag = _C_TYPE_TAGS.get(base_type)
    if tag is None:
        return ParamSpec(name=name, tag=None, pointer_like=pointer_like, supported=False, reason="unsupported_type")
    if name is None:
        return ParamSpec(name=None, tag=tag, pointer_like=pointer_like, supported=False, reason="missing_name")
    return ParamSpec(name=name, tag=tag, pointer_like=pointer_like, supported=True)


def _find_type_node(param_node):
    for child in param_node.children:
        if child.type in ('primitive_type', 'type_identifier', 'sized_type_specifier'):
            return child
    return None


def _find_identifier(param_node, source: bytes) -> str | None:
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

    visit(param_node)
    return identifier


def _normalize_c_type(type_text: str) -> str:
    return " ".join(type_text.replace("\n", " ").split()).lower()


def _slice_text(source: bytes, node) -> str:
    return source[node.start_byte:node.end_byte].decode("utf8")


def _find_function_declarator(node, pointer_depth: int = 0):
    if node.type == "pointer_declarator":
        for child in node.children:
            if child.type in ("pointer_declarator", "function_declarator", "parenthesized_declarator"):
                return _find_function_declarator(child, pointer_depth + 1)
        return None, pointer_depth
    if node.type == "parenthesized_declarator":
        for child in node.children:
            if child.type in ("pointer_declarator", "function_declarator", "parenthesized_declarator"):
                return _find_function_declarator(child, pointer_depth)
        return None, pointer_depth
    if node.type == "function_declarator":
        return node, pointer_depth
    return None, pointer_depth


def _count_pointer_declarators(node) -> int:
    count = 0

    def visit(n):
        nonlocal count
        if n.type == "pointer_declarator":
            count += 1
        for child in n.children:
            visit(child)

    visit(node)
    return count


def _has_array_declarator(node) -> bool:
    found = False

    def visit(n):
        nonlocal found
        if found:
            return
        if n.type == "array_declarator":
            found = True
            return
        for child in n.children:
            visit(child)

    visit(node)
    return found


def _render_c_enter(func_name: str, params: list[ParamSpec]) -> str:
    args_lines, args_var = _render_c_json_array("__dtv_args", params, "DTV_JSON_ARGS_CAP")
    args_block = "\n".join(args_lines)
    content = f"""\
{args_block}
dtv_trace_function_enter_args("{func_name}", {args_var});"""
    lines = [line for line in content.splitlines() if line]
    return _indent_lines(lines)


def _render_c_return(
    func_name: str,
    signature: FunctionSignature,
    ret_node,
    source_bytes: bytes,
    index: int,
) -> str:
    expr_node = ret_node.named_children[0] if ret_node.named_children else None
    expr_text = _slice_text(source_bytes, expr_node) if expr_node is not None else None

    ret_var = None
    ret_decl = ""
    if expr_text is not None:
        ret_var = f"__dtv_ret_{index}"
        ret_decl = f"__auto_type {ret_var} = ({expr_text});"

    ptr_lines, ptr_var = _render_c_ptr_args_json(signature.params, index)
    ret_lines, ret_var_name = _render_c_ret_json(signature.ret, ret_var, index)
    ret_arg = ret_var_name if ret_var_name is not None else "NULL"
    ptr_arg = ptr_var if ptr_var is not None else "NULL"
    return_line = "return;" if expr_text is None else f"return {ret_var};"
    ptr_block = "\n".join(ptr_lines)
    ret_block = "\n".join(ret_lines)
    content = f"""\
{{
{ret_decl}
{ptr_block}
{ret_block}
dtv_trace_function_exit_ret("{func_name}", {ret_arg}, {ptr_arg});
{return_line}
}}"""
    lines = [line for line in content.splitlines() if line]
    return _indent_lines(lines)


def _render_c_fallthrough_exit(func_name: str, signature: FunctionSignature) -> str:
    ptr_lines, ptr_var = _render_c_ptr_args_json(signature.params, "end")
    ptr_arg = ptr_var if ptr_var is not None else "NULL"
    ptr_block = "\n".join(ptr_lines)
    content = f"""\
{ptr_block}
dtv_trace_function_exit_ret("{func_name}", NULL, {ptr_arg});"""
    lines = [line for line in content.splitlines() if line]
    return _indent_lines(lines)


def _render_c_json_array(
    prefix: str,
    params: list[ParamSpec],
    cap_macro: str,
) -> tuple[list[str], str]:
    push_lines = [
        _render_c_json_push(
            prefix,
            param,
            value_expr=param.name,
            pointer_value=param.pointer_like,
        )
        for param in params
    ]
    push_block = "\n".join(push_lines)
    json_var = f"{prefix}_json"
    content = f"""\
DTV_JSON_ARRAY_DECLARE({prefix}, {cap_macro});
{push_block}
const char *{json_var} = dtv_json_array_finish(&{prefix});"""
    lines = [line for line in content.splitlines() if line]
    return lines, json_var


def _render_c_ptr_args_json(
    params: list[ParamSpec],
    index: int | str,
) -> tuple[list[str], str | None]:
    ptr_params = [param for param in params if param.pointer_like]
    if not ptr_params:
        return [], None
    prefix = f"__dtv_ptr_args_{index}"
    push_lines = [
        _render_c_json_push(
            prefix,
            param,
            value_expr=param.name,
            pointer_value=True,
        )
        for param in ptr_params
    ]
    push_block = "\n".join(push_lines)
    json_var = f"{prefix}_json"
    content = f"""\
DTV_JSON_ARRAY_DECLARE({prefix}, DTV_JSON_PTR_ARGS_CAP);
{push_block}
const char *{json_var} = dtv_json_array_finish(&{prefix});"""
    lines = [line for line in content.splitlines() if line]
    return lines, json_var


def _render_c_ret_json(
    ret_spec: ReturnSpec,
    ret_var: str | None,
    index: int,
) -> tuple[list[str], str | None]:
    if ret_spec.is_void:
        return [], None
    buf_var = f"__dtv_ret_buf_{index}"
    json_var = f"__dtv_ret_json_{index}"
    if not ret_spec.supported or ret_spec.tag is None:
        reason = ret_spec.reason or "unsupported_type"
        content = f"""\
char {buf_var}[DTV_JSON_RET_CAP];
const char *{json_var} = dtv_json_value_unsupported({buf_var}, sizeof({buf_var}), "{reason}");"""
        lines = [line for line in content.splitlines() if line]
        return lines, json_var
    if ret_var is None:
        return [], None
    func = _c_json_value_func(ret_spec, pointer_value=ret_spec.pointer_like)
    content = f"""\
char {buf_var}[DTV_JSON_RET_CAP];
const char *{json_var} = {func}({buf_var}, sizeof({buf_var}), {ret_var});"""
    lines = [line for line in content.splitlines() if line]
    return lines, json_var


def _render_c_json_push(
    prefix: str,
    param: ParamSpec,
    value_expr: str | None,
    pointer_value: bool,
) -> str:
    if not param.supported or param.tag is None or value_expr is None:
        reason = param.reason or "unsupported_type"
        return f'dtv_json_array_push_unsupported(&{prefix}, "{reason}");'
    func = _c_json_array_push_func(param, pointer_value=pointer_value)
    return f"{func}(&{prefix}, {value_expr});"


def _c_json_array_push_func(param: ParamSpec, pointer_value: bool) -> str:
    if param.tag is None:
        return "dtv_json_array_push_unsupported"
    if pointer_value:
        return f"dtv_json_array_push_ptr_{param.tag}"
    return f"dtv_json_array_push_{param.tag}"


def _c_json_value_func(ret_spec: ReturnSpec, pointer_value: bool) -> str:
    if ret_spec.tag is None:
        return "dtv_json_value_unsupported"
    if pointer_value:
        return f"dtv_json_value_ptr_{ret_spec.tag}"
    return f"dtv_json_value_{ret_spec.tag}"


def _indent_lines(lines: list[str]) -> str:
    return "\n    " + "\n    ".join(lines)
