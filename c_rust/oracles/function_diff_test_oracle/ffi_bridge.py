"""FFI bridge generation for calling C functions from Rust."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from tree_sitter_language_pack import get_parser

from core.logger import get_logger


# NOTE: architecture-specific types, can be wrong on some platforms
C_TO_RUST_TYPES = {
    "int": "i32",
    "long": "i64",
    "short": "i16",
    "char": "i8",
    "unsigned int": "u32",
    "unsigned long": "u64",
    "unsigned short": "u16",
    "unsigned char": "u8",
    "float": "f32",
    "double": "f64",
    "void": "()",
    "size_t": "usize",
    "ssize_t": "isize",
}


_LOG = get_logger(__name__)


@dataclass(frozen=True)
class MissingFunctionsResult:
    missing: list[str] | None
    reason: str | None = None


@dataclass(frozen=True)
class FfiBridgeResult:
    code: str | None
    reason: str | None = None


def find_missing_functions(rust_source: str, c_source: str) -> MissingFunctionsResult:
    """Find functions called in Rust but not defined in Rust (may exist in C)."""
    rust_tree, rust_bytes = _parse_rust_source(rust_source)
    rust_calls = _extract_rust_function_calls_from_tree(rust_tree, rust_bytes)
    rust_defs = _extract_rust_function_defs_from_tree(rust_tree, rust_bytes)
    rust_imports = _extract_rust_function_imports_from_tree(rust_tree, rust_bytes)
    rust_defs.update(rust_imports)
    c_defs = _extract_c_function_defs(c_source)
    normalized_c = build_normalized_lookup(c_defs)

    missing: set[str] = set()
    for func_name in rust_calls:
        if func_name in rust_defs:
            continue
        if func_name in c_defs:
            missing.add(func_name)
            continue
        normalized = resolve_normalized(func_name, normalized_c)
        if normalized is None:
            # Not applicable: ambiguous or no normalized C match. Should return NOT_APPLICABLE in oracle.
            reason = f"unresolved rust call: {func_name}"
            _LOG.debug("FFI not applicable: %s", reason)
            return MissingFunctionsResult(None, reason)
        missing.add(func_name)

    return MissingFunctionsResult(sorted(missing))


def generate_ffi_bridge(rust_source: str, c_source: str) -> FfiBridgeResult:
    """Generate Rust FFI bridge with extern C block and safe wrappers."""
    missing_result = find_missing_functions(rust_source, c_source)
    if missing_result.missing is None:
        # Propagate not-applicable upstream.
        return FfiBridgeResult(None, missing_result.reason)
    missing_funcs = missing_result.missing

    c_functions, unsupported = _extract_c_function_signatures(c_source)
    all_names = set(c_functions) | set(unsupported)
    normalized_c = build_normalized_lookup(all_names)

    extern_decls = []
    wrappers = []

    for func_name in missing_funcs:
        c_name = func_name
        if c_name not in all_names:
            normalized = resolve_normalized(c_name, normalized_c)
            if normalized is None:
                reason = f"unresolved C match for rust call: {func_name}"
                _LOG.debug("FFI not applicable: %s", reason)
                return FfiBridgeResult(None, reason)
            c_name = normalized

        if c_name in unsupported:
            reason = f"unsupported C signature for {c_name}: {unsupported[c_name]}"
            _LOG.debug("FFI not applicable: %s", reason)
            return FfiBridgeResult(None, reason)
        func_sig = c_functions.get(c_name)
        if func_sig is None:
            reason = f"unsupported C signature for {c_name}"
            _LOG.debug("FFI not applicable: %s", reason)
            return FfiBridgeResult(None, reason)

        # Keep the Rust symbol distinct while linking to the C name.
        raw_name = f"__dtv_raw_{c_name}"
        extern_decls.append(f'    #[link_name = "{c_name}"]\n    fn {raw_name}{func_sig};')

        wrapper = _generate_wrapper(func_name, func_sig, raw_name)
        wrappers.append(wrapper)

    if not extern_decls:
        return FfiBridgeResult("", None)

    ffi_code = 'extern "C" {\n'
    ffi_code += '\n'.join(extern_decls)
    ffi_code += '\n}\n\n'
    ffi_code += '\n\n'.join(wrappers)

    return FfiBridgeResult(ffi_code, None)


def _extract_c_function_signatures(c_source: str) -> tuple[dict[str, str], dict[str, str]]:
    """Extract function signatures from C source using tree-sitter."""
    parser = get_parser("c")
    source_bytes = c_source.encode("utf8")
    tree = parser.parse(source_bytes)

    signatures: dict[str, str] = {}
    unsupported: dict[str, str] = {}

    def visit(node):
        if node.type == 'function_definition':
            name, sig, reason = _parse_c_function_signature(node, source_bytes)
            if name is None:
                return
            if sig:
                signatures[name] = sig
            else:
                unsupported[name] = reason or "unsupported signature"
                _LOG.debug("Unsupported C signature: %s (%s)", name, unsupported[name])

        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return signatures, unsupported


def _parse_c_function_signature(
    func_node, source: bytes
) -> tuple[str | None, str | None, str | None]:
    # Find declarator and return type
    declarator = None
    return_type_node = None

    for child in func_node.children:
        if child.type in ('primitive_type', 'type_identifier', 'sized_type_specifier'):
            return_type_node = child
        elif child.type in ('function_declarator', 'pointer_declarator', 'parenthesized_declarator'):
            declarator = child

    if not declarator:
        return None, None, "missing declarator"
    # Return pointer depth is encoded in the declarator chain (e.g., int *f()).
    declarator, return_pointer_depth = _find_function_declarator(declarator)
    if declarator is None:
        return None, None, "missing function declarator"

    # Extract function name
    func_name = None
    param_list = None

    for child in declarator.children:
        if child.type == 'identifier':
            func_name = _slice_text(source, child)
        elif child.type == 'parameter_list':
            param_list = child

    if not func_name:
        return None, None, "missing function name"

    # Parse return type
    return_type = _parse_c_type(return_type_node, source) if return_type_node else "void"
    rust_return = C_TO_RUST_TYPES.get(return_type)
    if rust_return is None:
        return func_name, None, f"unsupported return type: {return_type}"
    # void* should map to c_void, then apply pointer depth.
    if return_type == "void" and return_pointer_depth > 0:
        rust_return = "core::ffi::c_void"
    for _ in range(return_pointer_depth):
        rust_return = f"*mut {rust_return}"

    # Parse parameters
    params = []
    if param_list:
        for param in param_list.children:
            if param.type == 'parameter_declaration':
                param_info, param_reason = _parse_c_parameter(param, source, len(params))
                if param_info is None:
                    return func_name, None, param_reason or "unsupported parameter"
                params.append(param_info)

    params_str = ", ".join(params)
    if rust_return == "()":
        rust_sig = f"({params_str})"
    else:
        rust_sig = f"({params_str}) -> {rust_return}"

    return func_name, rust_sig, None


def _parse_c_type(type_node, source: bytes) -> str:
    if type_node.type == 'primitive_type':
        return _slice_text(source, type_node)
    elif type_node.type == 'sized_type_specifier':
        return _slice_text(source, type_node)
    elif type_node.type == 'type_identifier':
        return _slice_text(source, type_node)
    return 'int'


def _parse_c_parameter(param_node, source: bytes, index: int) -> tuple[str | None, str | None]:
    param_type_node = None
    param_name = f"arg{index}"
    pointer_depth = _count_pointer_declarators(param_node)

    if _has_type_qualifier(param_node):
        return None, "type qualifiers not supported"
    if pointer_depth > 1:
        return None, "pointer depth > 1 not supported"
    is_pointer = pointer_depth == 1

    for child in param_node.children:
        if child.type in ('primitive_type', 'type_identifier', 'sized_type_specifier'):
            param_type_node = child
        elif child.type == 'pointer_declarator':
            for subchild in child.children:
                if subchild.type == 'identifier':
                    param_name = _slice_text(source, subchild)
        elif child.type == 'identifier':
            param_name = _slice_text(source, child)

    if not param_type_node:
        return None, "missing parameter type"

    c_type = _parse_c_type(param_type_node, source)
    rust_type = C_TO_RUST_TYPES.get(c_type)

    if rust_type is None:
        return None, f"unsupported parameter type: {c_type}"

    # Pointer parameters are modeled as *mut for now.
    if is_pointer:
        rust_type = f"*mut {rust_type}"

    return f"{param_name}: {rust_type}", None


def _generate_wrapper(func_name: str, rust_sig: str, raw_name: str) -> str:
    # Extract param names and generate safe wrapper calling unsafe extern.
    params_start = rust_sig.find('(')
    params_end = rust_sig.find(')')
    params_str = rust_sig[params_start + 1:params_end]

    arg_names = []
    if params_str:
        for param in params_str.split(','):
            arg_name = param.split(':')[0].strip()
            arg_names.append(arg_name)

    args_call = ', '.join(arg_names)

    wrapper = f"#[inline]\n"
    # Wrapper is safe; unsafe is contained inside the call.
    wrapper += f"fn {func_name}{rust_sig} {{\n"
    wrapper += f"    unsafe {{ {raw_name}({args_call}) }}\n"
    wrapper += "}"

    return wrapper


def _extract_c_function_defs(c_source: str) -> set[str]:
    parser = get_parser("c")
    source_bytes = c_source.encode("utf8")
    tree = parser.parse(source_bytes)

    defs = set()

    def visit(node):
        if node.type == 'function_definition':
            for child in node.children:
                if child.type == 'function_declarator':
                    for subchild in child.children:
                        if subchild.type == 'identifier':
                            func_name = _slice_text(source_bytes, subchild)
                            defs.add(func_name)
                            break

        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return defs


def _parse_rust_source(rust_source: str):
    parser = get_parser("rust")
    source_bytes = rust_source.encode("utf8")
    tree = parser.parse(source_bytes)
    return tree, source_bytes


def _extract_rust_function_calls_from_tree(tree, source_bytes: bytes) -> set[str]:
    calls = set()

    def visit(node):
        if node.type == 'call_expression':
            func_node = node.child_by_field_name('function')
            # Only bare identifiers; ignore module/path/method calls per project scope.
            if func_node and func_node.type == 'identifier':
                func_name = _slice_text(source_bytes, func_node)
                calls.add(func_name)

        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return calls


def _extract_rust_function_defs_from_tree(tree, source_bytes: bytes) -> set[str]:
    defs = set()

    def visit(node):
        # function_signature_item covers extern "C" { fn ...; } declarations.
        if node.type in ('function_item', 'function_signature_item'):
            for child in node.children:
                if child.type == 'identifier':
                    func_name = _slice_text(source_bytes, child)
                    defs.add(func_name)
                    break

        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return defs


def _extract_rust_function_imports_from_tree(tree, source_bytes: bytes) -> set[str]:
    imports: set[str] = set()

    def visit(node):
        if node.type == "use_declaration":
            imports.update(_collect_use_declaration_names(node, source_bytes))
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return imports


def _collect_use_declaration_names(node, source: bytes) -> set[str]:
    names: set[str] = set()

    def last_identifier(n):
        last = None
        for child in n.children:
            if child.type == "identifier":
                last = child
        if last is not None:
            names.add(_slice_text(source, last))

    def visit(n):
        if n.type == "use_as_clause":
            for child in reversed(n.children):
                if child.type == "identifier":
                    names.add(_slice_text(source, child))
                    return
        elif n.type == "scoped_use_list":
            for child in n.children:
                if child.type == "use_list":
                    visit(child)
                    return
            return
        elif n.type == "use_wildcard":
            return
        elif n.type == "scoped_identifier":
            last_identifier(n)
            return
        elif n.type == "identifier":
            names.add(_slice_text(source, n))
            return

        for child in n.children:
            visit(child)

    visit(node)
    return names


def _find_function_declarator(node, pointer_depth: int = 0):
    # Walk declarator wrappers to reach the function_declarator while tracking '*'.
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


def _has_type_qualifier(node) -> bool:
    found = False

    def visit(n):
        nonlocal found
        if found:
            return
        if n.type == "type_qualifier":
            found = True
            return
        for child in n.children:
            visit(child)

    visit(node)
    return found


def _slice_text(source: bytes, node) -> str:
    # tree-sitter byte offsets must slice bytes, then decode.
    return source[node.start_byte:node.end_byte].decode("utf8")


def normalize_identifier(name: str) -> str:
    return name.replace("_", "").lower()


def build_normalized_lookup(names) -> dict[str, list[str]]:
    lookup: dict[str, list[str]] = defaultdict(list)
    for name in names:
        lookup[normalize_identifier(name)].append(name)
    return lookup


def resolve_normalized(name: str, lookup: dict[str, list[str]]) -> str | None:
    matches = lookup.get(normalize_identifier(name))
    if not matches or len(matches) != 1:
        return None
    return matches[0]



