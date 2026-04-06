from __future__ import annotations

from core.llm_output import BEGIN_WRITE_CODE, END_WRITE_CODE
from core.types import Granularity
from c_rust.feedback import RUST_FEEDBACK_LANG
from js_ts.feedback import TS_FEEDBACK_LANG
from feedback.output_parser import (
    FeedbackWriteRegionStreamParser,
    parse_diff_feedback_output,
    parse_feedback_output,
    snippet_contains_function,
    validate_patch_scope,
)


def test_parse_feedback_output_single_write_region_success() -> None:
    result = parse_feedback_output(
        f"""{BEGIN_WRITE_CODE}
fn main() {{
    println!("ok");
}}
{END_WRITE_CODE}""",
        RUST_FEEDBACK_LANG,
    )

    assert result.patch == """fn main() {
    println!("ok");
}"""
    assert result.error is None
    assert result.used_write_region is True


def test_parse_feedback_output_rejects_multiple_regions() -> None:
    result = parse_feedback_output(
        f"""{BEGIN_WRITE_CODE}
let x = 1;
{END_WRITE_CODE}
{BEGIN_WRITE_CODE}
let y = 2;
{END_WRITE_CODE}""",
        RUST_FEEDBACK_LANG,
    )

    assert result.patch is None
    assert result.error == "multiple write regions found"
    assert result.used_write_region is True


def test_parse_feedback_output_rejects_empty_output() -> None:
    result = parse_feedback_output("   \n\n", RUST_FEEDBACK_LANG)

    assert result.patch is None
    assert result.error == "empty model output"
    assert result.used_write_region is False


def test_parse_feedback_output_rejects_missing_region() -> None:
    result = parse_feedback_output(
        """fn main() {
    println!("ok");
}""",
        RUST_FEEDBACK_LANG,
    )

    assert result.patch is None
    assert result.error == "missing write region"
    assert result.used_write_region is False


def test_parse_diff_feedback_output_requires_diff_patch() -> None:
    result = parse_diff_feedback_output(
        f"""{BEGIN_WRITE_CODE}
fn main() {{
    println!("ok");
}}
{END_WRITE_CODE}"""
    )

    assert result.patch is None
    assert result.error == "patch must be a unified diff with '+' and '-' lines only"
    assert result.used_write_region is True


def test_parse_feedback_output_rejects_unterminated_write_region() -> None:
    result = parse_diff_feedback_output(
        f"""{BEGIN_WRITE_CODE}
- const x: any = value;"""
    )

    assert result.patch is None
    assert result.error == "unterminated write region"
    assert result.used_write_region is True


def test_parse_feedback_output_extracts_diff_replacement_from_write_region() -> None:
    result = parse_diff_feedback_output(
        f"""{BEGIN_WRITE_CODE}
- function parseJson(
+ function parseJson(
+   txt: string,
+   reviver?: ((this: unknown, key: string, value: unknown) => unknown) | undefined,
{END_WRITE_CODE}"""
    )

    assert result.patch == """function parseJson(
  txt: string,
  reviver?: ((this: unknown, key: string, value: unknown) => unknown) | undefined,"""
    assert result.error is None
    assert result.used_write_region is True


def test_parse_feedback_output_rejects_trailing_text_after_end_marker() -> None:
    result = parse_diff_feedback_output(
        f"""{BEGIN_WRITE_CODE}
- const x: any = value;
+ const x: unknown = value;
{END_WRITE_CODE}<|im_end|>"""
    )

    assert result.patch is None
    assert result.error == "unterminated write region"
    assert result.used_write_region is True


def test_parse_feedback_output_rejects_inner_fence() -> None:
    result = parse_feedback_output(
        f"""{BEGIN_WRITE_CODE}
```python
print("hi")
```
{END_WRITE_CODE}""",
        RUST_FEEDBACK_LANG,
    )

    assert result.patch is None
    assert result.error == "write region must contain raw code only"
    assert result.used_write_region is True


def test_validate_patch_scope_stmt_rejects_function_wrapper() -> None:
    error = validate_patch_scope(
        """fn main() {
    let x: i32 = 1;
}""",
        Granularity.STMT,
        RUST_FEEDBACK_LANG,
    )

    assert error == "scope validator: stmt-scope patch cannot include top-level items (function_item)"


def test_validate_patch_scope_stmt_accepts_statement_patch() -> None:
    error = validate_patch_scope("let x: i32 = 1;", Granularity.STMT, RUST_FEEDBACK_LANG)

    assert error is None


def test_validate_patch_scope_program_allows_function_wrapper() -> None:
    error = validate_patch_scope(
        """fn main() {
    let x: i32 = 1;
}""",
        Granularity.PROGRAM,
        RUST_FEEDBACK_LANG,
    )

    assert error is None


def test_validate_patch_scope_func_allows_single_function() -> None:
    """FUNC rollback drops an entire function; the repair patch must regenerate it."""
    error = validate_patch_scope(
        """fn min(a: i32, b: i32, c: i32, d: i32) -> i32 {
    let r = if a < b { a } else { b };
    if c < r { c } else { r }
    if d < r { d } else { r }
}""",
        Granularity.FUNC,
        RUST_FEEDBACK_LANG,
    )

    assert error is None


def test_validate_patch_scope_func_allows_multiple_functions() -> None:
    """FUNC patch with helper + main function should pass."""
    error = validate_patch_scope(
        """fn helper() -> i32 { 42 }

fn main() {
    let x = helper();
}""",
        Granularity.FUNC,
        RUST_FEEDBACK_LANG,
    )

    assert error is None


def test_validate_patch_scope_func_rejects_non_function_top_level() -> None:
    """FUNC patch should not contain unrelated top-level items like use/struct."""
    error = validate_patch_scope(
        """use std::io;

fn main() {
    let x: i32 = 1;
}""",
        Granularity.FUNC,
        RUST_FEEDBACK_LANG,
    )

    assert error == (
        "scope validator: func-scope patch cannot include"
        " non-function top-level items (use_declaration)"
    )


def test_validate_patch_scope_func_accepts_statements_only() -> None:
    """FUNC patch with only statements (no function wrapper) should pass."""
    error = validate_patch_scope("let x: i32 = 1;", Granularity.FUNC, RUST_FEEDBACK_LANG)

    assert error is None


def test_validate_patch_scope_block_still_rejects_function() -> None:
    """BLOCK scope should still reject function_item (unchanged behavior)."""
    error = validate_patch_scope(
        """fn main() {
    let x: i32 = 1;
}""",
        Granularity.BLOCK,
        RUST_FEEDBACK_LANG,
    )

    assert error == "scope validator: block-scope patch cannot include top-level items (function_item)"


def test_snippet_contains_function_detects_incomplete_ts_function() -> None:
    snippet = """\
function trap(height: number[]): number {
    const n = height.length;"""
    assert snippet_contains_function(snippet, TS_FEEDBACK_LANG) is True


def test_snippet_contains_function_detects_incomplete_rust_function() -> None:
    snippet = """\
fn trap(height: &[i32]) -> i32 {
    let n = height.len();"""
    assert snippet_contains_function(snippet, RUST_FEEDBACK_LANG) is True


def test_snippet_contains_function_rejects_bare_statement() -> None:
    assert snippet_contains_function("let x: i32 = 1;", RUST_FEEDBACK_LANG) is False
    assert snippet_contains_function("const x: number = 1;", TS_FEEDBACK_LANG) is False


def test_validate_patch_scope_stmt_accepts_incomplete_ts_prefix_when_rollback_has_func() -> None:
    patch = """\
function trap(height: number[]): number {
    const n: number = height.length;"""
    rollback_snippet = """\
function trap(height: number[]): number {
    const n = height.length;"""
    error = validate_patch_scope(
        patch,
        Granularity.STMT,
        TS_FEEDBACK_LANG,
        rollback_snippet=rollback_snippet,
    )
    assert error is None


def test_validate_patch_scope_stmt_rejects_early_closed_ts_prefix() -> None:
    patch = """\
function trap(height: number[]): number {
    const n: number = height.length;
}"""
    rollback_snippet = """\
function trap(height: number[]): number {
    const n = height.length;"""
    error = validate_patch_scope(
        patch,
        Granularity.STMT,
        TS_FEEDBACK_LANG,
        rollback_snippet=rollback_snippet,
    )
    assert error is not None


def test_validate_patch_scope_stmt_still_rejects_function_without_rollback_snippet() -> None:
    patch = """\
function trap(height: number[]): number {
    const n: number = height.length;"""
    error = validate_patch_scope(patch, Granularity.STMT, TS_FEEDBACK_LANG)
    assert error is not None


def test_validate_patch_scope_stmt_still_rejects_function_when_rollback_has_no_func() -> None:
    patch = """\
function trap(height: number[]): number {
    const n: number = height.length;"""
    error = validate_patch_scope(
        patch,
        Granularity.STMT,
        TS_FEEDBACK_LANG,
        rollback_snippet="const n = height.length;",
    )
    assert error is not None


def test_validate_patch_scope_stmt_accepts_incomplete_rust_prefix_when_rollback_has_func() -> None:
    patch = """\
fn main() {
    let x: i32 = 1;"""
    rollback_snippet = """\
fn main() {
    let x = 1;"""
    error = validate_patch_scope(
        patch,
        Granularity.STMT,
        RUST_FEEDBACK_LANG,
        rollback_snippet=rollback_snippet,
    )
    assert error is None


def test_validate_patch_scope_stmt_rejects_early_closed_rust_prefix() -> None:
    patch = """\
fn main() {
    let x: i32 = 1;
}"""
    rollback_snippet = """\
fn main() {
    let x = 1;"""
    error = validate_patch_scope(
        patch,
        Granularity.STMT,
        RUST_FEEDBACK_LANG,
        rollback_snippet=rollback_snippet,
    )
    assert error is not None


def test_validate_patch_scope_block_not_affected_by_rollback_snippet() -> None:
    patch = """\
fn main() {
    let x: i32 = 1;"""
    rollback_snippet = """\
fn main() {
    let x = 1;"""
    error = validate_patch_scope(
        patch,
        Granularity.BLOCK,
        RUST_FEEDBACK_LANG,
        rollback_snippet=rollback_snippet,
    )
    assert error is not None


def test_validate_patch_scope_stmt_accepts_ts_lexical_declaration() -> None:
    patch = 'const syntaxErr: RegExpMatchArray | null = (e as Error).message.match(/pattern/i);'
    error = validate_patch_scope(patch, Granularity.STMT, TS_FEEDBACK_LANG)
    assert error is None


def test_validate_patch_scope_stmt_accepts_catch_continuation_when_rollback_also_catch() -> None:
    patch = """\
 catch (e: unknown) {
    if (typeof txt !== 'string') {
      const isEmptyArray: boolean = Array.isArray(txt) && txt.length === 0;"""
    rollback_snippet = """\
 catch (e: unknown) {
    if (typeof txt !== 'string') {
      const isEmptyArray = Array.isArray(txt) && txt.length === 0;"""
    error = validate_patch_scope(
        patch,
        Granularity.STMT,
        TS_FEEDBACK_LANG,
        rollback_snippet=rollback_snippet,
    )
    assert error is None


def test_validate_patch_scope_stmt_rejects_invalid_syntax_when_rollback_parses_ok() -> None:
    patch = "catch (e: unknown) { %%% invalid"
    rollback_snippet = "const x: number = 1;"
    error = validate_patch_scope(
        patch,
        Granularity.STMT,
        TS_FEEDBACK_LANG,
        rollback_snippet=rollback_snippet,
    )
    assert error is not None
    assert "not valid TypeScript syntax" in error


def test_feedback_write_region_stream_parser_detects_complete_region() -> None:
    parser = FeedbackWriteRegionStreamParser()

    parser.feed(f"{BEGIN_WRITE_CODE}\nlet x = 1;\n")
    assert parser.complete is False

    parser.feed(END_WRITE_CODE)
    assert parser.complete is True


def test_feedback_write_region_stream_parser_reset_clears_state() -> None:
    parser = FeedbackWriteRegionStreamParser()

    parser.feed(f"{BEGIN_WRITE_CODE}\nlet x = 1;\n{END_WRITE_CODE}")
    assert parser.complete is True

    parser.reset()
    assert parser.complete is False


def test_feedback_write_region_stream_parser_requires_end_marker() -> None:
    parser = FeedbackWriteRegionStreamParser()

    parser.feed("+ const x: number = 1;")

    assert parser.complete is False
