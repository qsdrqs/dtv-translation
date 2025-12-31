from __future__ import annotations

from pathlib import Path

from c_rust.oracles.compiler_oracle.rustc_driver import RustcResult
from c_rust.oracles.compiler_oracle.rustc_parser import has_errors, parse_rustc_diagnostics
from test.c_rust.utils import compile_rust


def test_rustc_parser_extracts_code_span() -> None:
    code = """\
fn foo() -> i32 {
    "hi"
}
"""
    byte_start = code.index('"hi"')
    byte_end = byte_start + len('"hi"')
    compile = compile_rust(code, error_format="json")
    result = RustcResult(
        stdout=compile.stdout,
        stderr=compile.stderr,
        exit_code=compile.returncode,
        elapsed_ms=0,
        command=("rustc",),
        source_path=Path("lib.rs"),
        output_path=Path("lib.rlib"),
        timed_out=False,
    )

    diagnostics = parse_rustc_diagnostics(result)
    assert has_errors(diagnostics)
    diag = next(d for d in diagnostics if d.error_code == "E0308")
    assert diag.span is not None
    assert diag.span[0] <= byte_start
    assert diag.span[1] >= byte_end
