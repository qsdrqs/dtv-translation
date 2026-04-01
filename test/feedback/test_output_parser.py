from __future__ import annotations

from core.types import Granularity
from c_rust.feedback import RUST_FEEDBACK_LANG
from js_ts.feedback import TS_FEEDBACK_LANG
from feedback.output_parser import (
    FeedbackFenceStreamParser,
    parse_diff_feedback_output,
    parse_feedback_output,
    snippet_contains_function,
    validate_patch_scope,
)


def test_parse_feedback_output_single_fence_success() -> None:
    result = parse_feedback_output(
        """```rust
fn main() {
    println!(\"ok\");
}
```""",
        RUST_FEEDBACK_LANG,
    )

    assert result.patch == """fn main() {
    println!(\"ok\");
}"""
    assert result.error is None
    assert result.used_fence is True


def test_parse_feedback_output_rejects_multiple_fences() -> None:
    result = parse_feedback_output(
        """```rust
let x = 1;
```
```rust
let y = 2;
```""",
        RUST_FEEDBACK_LANG,
    )

    assert result.patch is None
    assert result.error == "multiple fenced code blocks found"
    assert result.used_fence is True


def test_parse_feedback_output_rejects_empty_output() -> None:
    result = parse_feedback_output("   \n\n", RUST_FEEDBACK_LANG)

    assert result.patch is None
    assert result.error == "empty model output"
    assert result.used_fence is False


def test_parse_feedback_output_accepts_plain_text_fallback() -> None:
    result = parse_feedback_output(
        """fn main() {
    println!(\"ok\");
}""",
        RUST_FEEDBACK_LANG,
    )

    assert result.patch == """fn main() {
    println!(\"ok\");
}"""
    assert result.error is None
    assert result.used_fence is False


def test_parse_diff_feedback_output_requires_diff_patch() -> None:
    result = parse_diff_feedback_output(
        """```rust
fn main() {
    println!(\"ok\");
}
```"""
    )

    assert result.patch is None
    assert result.error == "patch must be a unified diff with '+' and '-' lines only"
    assert result.used_fence is True


def test_parse_feedback_output_extracts_diff_replacement_without_closing_fence() -> None:
    result = parse_diff_feedback_output(
        """- function parseJson(
-   txt: string,
-   reviver?: ((this: any, key: string, value: any) => any) | undefined,
+ function parseJson(
+   txt: string,
+   reviver?: ((this: unknown, key: string, value: unknown) => unknown) | undefined,"""
    )

    assert result.patch == """function parseJson(
  txt: string,
  reviver?: ((this: unknown, key: string, value: unknown) => unknown) | undefined,"""
    assert result.error is None
    assert result.used_fence is False


def test_parse_feedback_output_extracts_diff_replacement_from_open_fence() -> None:
    result = parse_diff_feedback_output(
        """```typescript
- function parseJson(
+ function parseJson(
+   txt: string,
+   reviver?: ((this: unknown, key: string, value: unknown) => unknown) | undefined,"""
    )

    assert result.patch == """function parseJson(
  txt: string,
  reviver?: ((this: unknown, key: string, value: unknown) => unknown) | undefined,"""
    assert result.error is None
    assert result.used_fence is True


def test_parse_feedback_output_extracts_diff_replacement_before_closing_fence() -> None:
    result = parse_diff_feedback_output(
        """```typescript
- const x: any = value;
+ const x: unknown = value;
```<|im_end|>""",
    )

    assert result.patch == "const x: unknown = value;"
    assert result.error is None
    assert result.used_fence is True


def test_parse_feedback_output_rejects_non_rust_fence() -> None:
    result = parse_feedback_output(
        """```python
print(\"hi\")
```""",
        RUST_FEEDBACK_LANG,
    )

    assert result.patch is None
    assert result.error == "fenced code block language must be rust"
    assert result.used_fence is True


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


def test_feedback_fence_stream_parser_detects_complete_fence() -> None:
    parser = FeedbackFenceStreamParser()

    parser.feed("```rust\nlet x = 1;\n")
    assert parser.complete is False

    parser.feed("```")
    assert parser.complete is True


def test_feedback_fence_stream_parser_reset_clears_state() -> None:
    parser = FeedbackFenceStreamParser()

    parser.feed("```rust\nlet x = 1;\n```")
    assert parser.complete is True

    parser.reset()
    assert parser.complete is False


def test_feedback_fence_stream_parser_requires_closing_fence() -> None:
    parser = FeedbackFenceStreamParser()

    parser.feed("+ const x: number = 1;")

    assert parser.complete is False
