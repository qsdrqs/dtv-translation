from __future__ import annotations

from core.types import Diagnostic, DiagnosticSpan
from feedback.annotation import annotate_snippet


def test_annotate_related_span_on_matching_line() -> None:
    snippet = 'const input: string = "";\ninput = "hello";'
    diagnostics = (
        Diagnostic(
            message="Cannot assign to 'input' because it is a constant.",
            severity="error",
            error_code="TS2588",
            spans=(
                DiagnosticSpan(line=2, col=1, is_primary=True),
                DiagnosticSpan(line=1, col=7, message="'input' was declared here"),
            ),
        ),
    )
    result = annotate_snippet(snippet, 1, diagnostics, "//")
    assert result == """\
const input: string = "";  // <-- error: TS2588: 'input' was declared here
input = "hello";  // <-- error: TS2588: Cannot assign to 'input' because it is a constant."""


def test_annotate_primary_span_uses_diag_message_as_fallback() -> None:
    snippet = 'const x: number = "hello";'
    diagnostics = (
        Diagnostic(
            message="Type 'string' is not assignable to type 'number'.",
            severity="error",
            error_code="TS2322",
            spans=(DiagnosticSpan(line=3, col=7, is_primary=True),),
        ),
    )
    result = annotate_snippet(snippet, 3, diagnostics, "//")
    assert result == 'const x: number = "hello";  // <-- error: TS2322: Type \'string\' is not assignable to type \'number\'.'


def test_annotate_with_related_info_from_tsc() -> None:
    snippet = """\
interface Foo { x: number; }
const obj: Foo = { x: "hello" };"""
    diagnostics = (
        Diagnostic(
            message="Type 'string' is not assignable to type 'number'.",
            severity="error",
            error_code="TS2322",
            spans=(
                DiagnosticSpan(line=5, col=20, is_primary=True),
                DiagnosticSpan(
                    line=4, col=17,
                    message="The expected type comes from property 'x' which is declared here on type 'Foo'",
                ),
            ),
        ),
    )
    result = annotate_snippet(snippet, 4, diagnostics, "//")
    assert result == """\
interface Foo { x: number; }  // <-- error: TS2322: The expected type comes from property 'x' which is declared here on type 'Foo'
const obj: Foo = { x: "hello" };  // <-- error: TS2322: Type 'string' is not assignable to type 'number'."""


def test_annotate_span_outside_snippet_ignored() -> None:
    snippet = "let x = 1;"
    diagnostics = (
        Diagnostic(
            message="error elsewhere",
            error_code="TS9999",
            spans=(DiagnosticSpan(line=100, col=1, is_primary=True),),
        ),
    )
    result = annotate_snippet(snippet, 5, diagnostics, "//")
    assert result == "let x = 1;"


def test_annotate_no_diagnostics_returns_unchanged() -> None:
    snippet = "let x = 1;\nlet y = 2;"
    result = annotate_snippet(snippet, 1, (), "//")
    assert result == snippet


def test_annotate_empty_snippet() -> None:
    result = annotate_snippet("", 1, (Diagnostic(message="err"),), "//")
    assert result == ""


def test_annotate_rust_uses_diag_message() -> None:
    snippet = 'let x: i32 = "hi";'
    diagnostics = (
        Diagnostic(
            message="mismatched types",
            error_code="E0308",
            spans=(DiagnosticSpan(line=2, col=14, is_primary=True),),
        ),
    )
    result = annotate_snippet(snippet, 2, diagnostics, "//")
    assert result == 'let x: i32 = "hi";  // <-- error: E0308: mismatched types'


def test_annotate_multiple_diagnostics_same_line() -> None:
    snippet = "let x = foo(bar);"
    diagnostics = (
        Diagnostic(
            message="err1", error_code="E001",
            spans=(DiagnosticSpan(line=1, col=1, is_primary=True),),
        ),
        Diagnostic(
            message="err2", error_code="E002",
            spans=(DiagnosticSpan(line=1, col=5, is_primary=True),),
        ),
    )
    result = annotate_snippet(snippet, 1, diagnostics, "//")
    assert result == "let x = foo(bar);  // <-- error: E001: err1; error: E002: err2"


def test_annotate_eslint_primary_span() -> None:
    snippet = "  const n = height.length;"
    diagnostics = (
        Diagnostic(
            message="Expected n to have a type annotation.",
            severity="error",
            error_code="@typescript-eslint/typedef",
            spans=(DiagnosticSpan(line=7, col=9, is_primary=True),),
        ),
    )
    result = annotate_snippet(snippet, 7, diagnostics, "//")
    assert result == "  const n = height.length;  // <-- error: @typescript-eslint/typedef: Expected n to have a type annotation."


def test_annotate_multiline_snippet_offset() -> None:
    snippet = "line A\nline B\nline C"
    diagnostics = (
        Diagnostic(
            message="err", error_code="X1",
            spans=(DiagnosticSpan(line=12, col=1, is_primary=True),),
        ),
    )
    result = annotate_snippet(snippet, 11, diagnostics, "#")
    assert result == "line A\nline B  # <-- error: X1: err\nline C"
