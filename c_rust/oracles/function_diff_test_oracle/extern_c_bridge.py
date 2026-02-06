"""Generate extern "C" wrappers for LD_PRELOAD interposition."""

from __future__ import annotations

from dataclasses import dataclass

from c_rust.oracles.function_diff_test_oracle.c_instrumenter import FunctionSignature, ParamSpec, ReturnSpec
from c_rust.oracles.function_diff_test_oracle.rust_instrumenter import RustSignature, RustTypeInfo


_INT_TAGS = {"i8", "i16", "i32", "i64", "isize"}
_UINT_TAGS = {"u8", "u16", "u32", "u64", "usize"}


@dataclass(frozen=True)
class ExternCWrapperResult:
    code: str | None
    reason: str | None = None


def generate_extern_c_wrapper(
    c_function_name: str,
    rust_function_name: str,
    c_signature: FunctionSignature,
    rust_signature: RustSignature,
) -> ExternCWrapperResult:
    wrapper_params: list[str] = []
    call_args: list[str] = []
    setup_lines: list[str] = []

    c_params = c_signature.params
    r_params = rust_signature.params
    c_index = 0

    for r_index, r_param in enumerate(r_params):
        r_info = r_param.type_info
        if not _rust_param_supported(r_info):
            return ExternCWrapperResult(None, "unsupported_rust_param")

        if r_info.is_slice:
            if c_index + 1 >= len(c_params):
                return ExternCWrapperResult(None, "c_params_missing_len")
            c_ptr = c_params[c_index]
            c_len = c_params[c_index + 1]
            if not _c_param_supported(c_ptr, pointer_required=True):
                return ExternCWrapperResult(None, "unsupported_c_ptr_param")
            if not _c_len_param_supported(c_len):
                return ExternCWrapperResult(None, "unsupported_c_len_param")
            if c_ptr.tag != r_info.tag:
                return ExternCWrapperResult(None, "slice_element_type_mismatch")

            ptr_name = _param_name(c_ptr, c_index)
            len_name = _param_name(c_len, c_index + 1)
            wrapper_params.append(f"{ptr_name}: *mut {r_info.tag}")
            wrapper_params.append(f"{len_name}: {c_len.tag}")

            rust_name = r_param.name or f"__dtv_arg_{r_index}"
            setup_lines.append(
                "let {name} = unsafe {{ std::slice::from_raw_parts_mut({ptr}, {len_name} as usize) }};".format(
                    name=rust_name,
                    ptr=ptr_name,
                    len_name=len_name,
                )
            )
            call_args.append(rust_name)
            c_index += 2
            continue

        if r_info.pointer_like:
            if not r_info.is_raw_pointer:
                return ExternCWrapperResult(None, "unsupported_rust_pointer")
            if c_index >= len(c_params):
                return ExternCWrapperResult(None, "c_params_missing")
            c_param = c_params[c_index]
            if not _c_param_supported(c_param, pointer_required=True):
                return ExternCWrapperResult(None, "unsupported_c_ptr_param")
            if c_param.tag != r_info.tag:
                return ExternCWrapperResult(None, "pointer_type_mismatch")

            name = _param_name(c_param, c_index)
            wrapper_params.append(f"{name}: *mut {r_info.tag}")
            call_args.append(name)
            c_index += 1
            continue

        if c_index >= len(c_params):
            return ExternCWrapperResult(None, "c_params_missing")
        c_param = c_params[c_index]
        if not _c_param_supported(c_param, pointer_required=False):
            return ExternCWrapperResult(None, "unsupported_c_param")
        if c_param.pointer_like:
            return ExternCWrapperResult(None, "value_pointer_mismatch")
        if c_param.tag != r_info.tag:
            return ExternCWrapperResult(None, "value_type_mismatch")

        name = _param_name(c_param, c_index)
        wrapper_params.append(f"{name}: {r_info.tag}")
        call_args.append(name)
        c_index += 1

    if c_index != len(c_params):
        return ExternCWrapperResult(None, "unused_c_params")

    ret_type, return_lines, reason = _build_return(
        c_signature.ret,
        rust_signature.ret,
        rust_function_name,
        call_args,
    )
    if reason is not None:
        return ExternCWrapperResult(None, reason)

    params_str = ", ".join(wrapper_params)
    ret_str = f" -> {ret_type}" if ret_type else ""
    body_lines = []
    body_lines.extend(setup_lines)
    if return_lines:
        body_lines.extend(return_lines)

    body = "\n    ".join(body_lines) if body_lines else ""
    body_block = f"    {body}\n" if body else ""
    code = f'''#[export_name = "{c_function_name}"]
pub extern "C" fn __dtv_export_{c_function_name}({params_str}){ret_str} {{
{body_block}}}
'''
    return ExternCWrapperResult(code, None)


def _rust_param_supported(info: RustTypeInfo) -> bool:
    if not info.supported or info.tag is None or info.is_void:
        return False
    if info.is_reference and not info.is_slice:
        return False
    if info.is_array:
        return False
    return True


def _c_param_supported(param: ParamSpec, pointer_required: bool) -> bool:
    if not param.supported or param.tag is None:
        return False
    if pointer_required and not param.pointer_like:
        return False
    if not pointer_required and param.pointer_like:
        return False
    return True


def _c_len_param_supported(param: ParamSpec) -> bool:
    if not param.supported or param.tag is None:
        return False
    if param.pointer_like:
        return False
    return param.tag in _INT_TAGS or param.tag in _UINT_TAGS


def _param_name(param: ParamSpec, index: int) -> str:
    return param.name or f"arg{index}"


def _build_return(
    c_ret: ReturnSpec,
    rust_ret: RustTypeInfo,
    function_name: str,
    call_args: list[str],
) -> tuple[str | None, list[str] | None, str | None]:
    call_expr = f"{function_name}({', '.join(call_args)})"

    if rust_ret.is_void:
        if not c_ret.is_void:
            return None, None, "return_type_mismatch"
        return "", [f"{call_expr};"], None

    if not rust_ret.supported or rust_ret.tag is None:
        return None, None, "unsupported_rust_return"
    if not c_ret.supported or c_ret.tag is None:
        return None, None, "unsupported_c_return"

    if rust_ret.pointer_like:
        if not rust_ret.is_raw_pointer:
            return None, None, "unsupported_rust_return_pointer"
        if not c_ret.pointer_like or c_ret.tag != rust_ret.tag:
            return None, None, "return_pointer_mismatch"
        return f"*mut {rust_ret.tag}", [f"let __dtv_ret = {call_expr};", "__dtv_ret"], None

    if c_ret.pointer_like or c_ret.tag != rust_ret.tag:
        return None, None, "return_value_mismatch"

    return rust_ret.tag, [f"let __dtv_ret = {call_expr};", "__dtv_ret"], None
