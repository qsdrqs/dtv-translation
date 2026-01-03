from __future__ import annotations

from c_rust.oracles.function_diff_test_oracle.ffi_bridge import (
    _extract_c_function_signatures,
    _extract_rust_function_calls_from_tree,
    _extract_rust_function_defs_from_tree,
    find_missing_functions,
    _parse_rust_source,
    generate_ffi_bridge,
)


def test_c_return_pointer_signatures() -> None:
    c_source = "int *f(){return 0;} void *g(){return 0;}"
    sigs, unsupported = _extract_c_function_signatures(c_source)

    assert sigs["f"] == "() -> *mut i32"
    assert sigs["g"] == "() -> *mut core::ffi::c_void"
    assert unsupported == {}


def test_rust_extern_defs_included() -> None:
    rust_source = 'extern "C" { fn foo(x: i32) -> i32; }\nfn bar() {}'
    tree, source_bytes = _parse_rust_source(rust_source)
    defs = _extract_rust_function_defs_from_tree(tree, source_bytes)

    assert "foo" in defs
    assert "bar" in defs


def test_rust_calls_only_bare_identifiers() -> None:
    rust_source = "fn main(){ foo(); module::bar(); obj.baz(); }"
    tree, source_bytes = _parse_rust_source(rust_source)
    calls = _extract_rust_function_calls_from_tree(tree, source_bytes)

    assert calls == {"foo"}


def test_scoped_call_ignored_for_missing_functions() -> None:
    c_source = "int foo(){return 0;}"
    rust_source = "fn main(){ vec::len(); }"

    tree, source_bytes = _parse_rust_source(rust_source)
    calls = _extract_rust_function_calls_from_tree(tree, source_bytes)
    assert calls == set()

    missing = find_missing_functions(rust_source, c_source)
    assert missing.missing == []


def test_use_import_prevents_missing() -> None:
    c_source = "int foo(){return 0;}"
    rust_source = "use libc::printf;\nfn main(){ printf(); }"

    missing = find_missing_functions(rust_source, c_source)
    assert missing.missing == []


def test_normalized_name_matching_generates_wrapper() -> None:
    c_source = "int singleFunctionName(int a){return 0;}"
    rust_source = "fn main(){ let a = 1; single_function_name(a); }"

    missing = find_missing_functions(rust_source, c_source)
    assert missing.missing == ["single_function_name"]

    bridge = generate_ffi_bridge(rust_source, c_source)
    assert bridge.code is not None
    assert 'link_name = "singleFunctionName"' in bridge.code
    assert "fn single_function_name(a: i32) -> i32" in bridge.code
    assert "unsafe { __dtv_raw_singleFunctionName(" in bridge.code


def test_ambiguous_normalized_match_not_applicable() -> None:
    c_source = "int foo_bar(){return 0;} int foobar(){return 1;}"
    rust_source = "fn main(){ fooBar(); }"

    missing = find_missing_functions(rust_source, c_source)
    assert missing.missing is None
    assert missing.reason is not None
    bridge = generate_ffi_bridge(rust_source, c_source)
    assert bridge.code is None
    assert bridge.reason is not None


def test_unicode_identifiers_extracted() -> None:
    rust_source = "fn \u51fd\u6570() {}\nfn main(){ \u51fd\u6570(); }"
    tree, source_bytes = _parse_rust_source(rust_source)
    calls = _extract_rust_function_calls_from_tree(tree, source_bytes)
    defs = _extract_rust_function_defs_from_tree(tree, source_bytes)

    assert "\u51fd\u6570" in defs
    assert "\u51fd\u6570" in calls
