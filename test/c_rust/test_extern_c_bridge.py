from __future__ import annotations

from c_rust.oracles.function_diff_test_oracle.c_instrumenter import (
    FunctionSignature,
    ParamSpec,
    ReturnSpec,
    extract_function_signature as extract_c_signature,
)
from c_rust.oracles.function_diff_test_oracle.extern_c_bridge import generate_extern_c_wrapper
from c_rust.oracles.function_diff_test_oracle.rust_instrumenter import (
    extract_function_signature as extract_rust_signature,
)


def _generate(
    *,
    c_source: str,
    c_name: str,
    rust_source: str,
    rust_name: str,
):
    c_sig = extract_c_signature(c_source, c_name)
    r_sig = extract_rust_signature(rust_source, rust_name)
    assert c_sig is not None
    assert r_sig is not None
    return generate_extern_c_wrapper(c_name, rust_name, c_sig, r_sig)


def test_extern_c_wrapper_uses_c_name_for_export_and_rust_name_for_call() -> None:
    c_source = "int singleFunction(int x){return x + 1;}"
    rust_source = "fn single_function(x: i32) -> i32 { x + 1 }"

    result = _generate(
        c_source=c_source,
        c_name="singleFunction",
        rust_source=rust_source,
        rust_name="single_function",
    )

    assert result.code is not None
    assert result.reason is None
    assert result.code == (
        """#[export_name = "singleFunction"]
pub extern "C" fn __dtv_export_singleFunction(x: i32) -> i32 {
    let __dtv_ret = single_function(x);
    __dtv_ret
}
"""
    )


def test_extern_c_wrapper_generates_slice_bridge_for_ptr_len() -> None:
    c_source = "int trap(int *height, int heightSize){return 0;}"
    rust_source = "fn trap(height: &[i32]) -> i32 { let _ = height; 0 }"

    result = _generate(c_source=c_source, c_name="trap", rust_source=rust_source, rust_name="trap")

    assert result.code is not None
    assert result.code == (
        """#[export_name = "trap"]
pub extern "C" fn __dtv_export_trap(height: *mut i32, heightSize: i32) -> i32 {
    let height = unsafe { std::slice::from_raw_parts_mut(height, heightSize as usize) };
    let __dtv_ret = trap(height);
    __dtv_ret
}
"""
    )


def test_extern_c_wrapper_slice_missing_len_not_applicable() -> None:
    c_source = "int trap(int *height){return 0;}"
    rust_source = "fn trap(height: &[i32]) -> i32 { let _ = height; 0 }"

    result = _generate(c_source=c_source, c_name="trap", rust_source=rust_source, rust_name="trap")

    assert result.code is None
    assert result.reason == "c_params_missing_len"


def test_extern_c_wrapper_slice_len_not_integer_not_applicable() -> None:
    c_source = "int trap(int *height, float heightSize){return 0;}"
    rust_source = "fn trap(height: &[i32]) -> i32 { let _ = height; 0 }"

    result = _generate(c_source=c_source, c_name="trap", rust_source=rust_source, rust_name="trap")

    assert result.code is None
    assert result.reason == "unsupported_c_len_param"


def test_extern_c_wrapper_slice_element_type_mismatch_not_applicable() -> None:
    c_source = "int trap(long *height, int heightSize){return 0;}"
    rust_source = "fn trap(height: &[i32]) -> i32 { let _ = height; 0 }"

    result = _generate(c_source=c_source, c_name="trap", rust_source=rust_source, rust_name="trap")

    assert result.code is None
    assert result.reason == "slice_element_type_mismatch"


def test_extern_c_wrapper_unused_c_params_not_applicable() -> None:
    c_source = "int trap(int *height, int heightSize, int extra){return 0;}"
    rust_source = "fn trap(height: &[i32]) -> i32 { let _ = height; 0 }"

    result = _generate(c_source=c_source, c_name="trap", rust_source=rust_source, rust_name="trap")

    assert result.code is None
    assert result.reason == "unused_c_params"


def test_extern_c_wrapper_pointer_param_and_pointer_return() -> None:
    rust_source = "fn f(p: *mut i32) -> *mut i32 { p }"

    # c_instrumenter does not currently extract signatures for pointer-return functions,
    # so build the C signature directly for this unit test.
    c_sig = FunctionSignature(
        params=[ParamSpec(name="p", tag="i32", pointer_like=True, supported=True)],
        ret=ReturnSpec(tag="i32", pointer_like=True, supported=True),
    )
    r_sig = extract_rust_signature(rust_source, "f")
    assert r_sig is not None
    result = generate_extern_c_wrapper("f", "f", c_sig, r_sig)

    assert result.code is not None
    assert result.code == (
        """#[export_name = "f"]
pub extern "C" fn __dtv_export_f(p: *mut i32) -> *mut i32 {
    let __dtv_ret = f(p);
    __dtv_ret
}
"""
    )


def test_extern_c_wrapper_void_return() -> None:
    c_source = "void logit(int x){(void)x;}"
    rust_source = "fn log_it(x: i32) { let _ = x; }"

    result = _generate(c_source=c_source, c_name="logit", rust_source=rust_source, rust_name="log_it")

    assert result.code is not None
    assert result.code == (
        """#[export_name = "logit"]
pub extern "C" fn __dtv_export_logit(x: i32) {
    log_it(x);
}
"""
    )


def test_extern_c_wrapper_rejects_non_slice_reference_param() -> None:
    c_source = "int f(int x){return x;}"
    rust_source = "fn f(x: &i32) -> i32 { *x }"

    result = _generate(c_source=c_source, c_name="f", rust_source=rust_source, rust_name="f")

    assert result.code is None
    assert result.reason == "unsupported_rust_param"


def test_extern_c_wrapper_pointer_type_mismatch_not_applicable() -> None:
    c_source = "int f(int *p){return 0;}"
    rust_source = "fn f(p: *mut i64) -> i32 { let _ = p; 0 }"

    result = _generate(c_source=c_source, c_name="f", rust_source=rust_source, rust_name="f")

    assert result.code is None
    assert result.reason == "pointer_type_mismatch"


def test_extern_c_wrapper_return_pointer_mismatch_not_applicable() -> None:
    c_source = "int f(int x){return x;}"
    rust_source = "fn f(x: i32) -> *mut i32 { let _ = x; core::ptr::null_mut() }"

    result = _generate(c_source=c_source, c_name="f", rust_source=rust_source, rust_name="f")

    assert result.code is None
    assert result.reason == "return_pointer_mismatch"


def test_extern_c_wrapper_value_param_type_mismatch_not_applicable() -> None:
    c_source = "int f(int x){return x;}"
    rust_source = "fn f(x: i64) -> i32 { let _ = x; 0 }"

    result = _generate(c_source=c_source, c_name="f", rust_source=rust_source, rust_name="f")

    assert result.code is None
    assert result.reason == "value_type_mismatch"
