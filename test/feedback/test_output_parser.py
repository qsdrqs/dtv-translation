from __future__ import annotations

from core.types import RollbackScope
from c_rust.feedback import RUST_FEEDBACK_LANG
from feedback.output_parser import (
    FeedbackFenceStreamParser,
    parse_feedback_output,
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
        RollbackScope.STMT,
        RUST_FEEDBACK_LANG,
    )

    assert error == "scope validator: stmt-scope patch cannot include top-level items (function_item)"


def test_validate_patch_scope_stmt_accepts_statement_patch() -> None:
    error = validate_patch_scope("let x: i32 = 1;", RollbackScope.STMT, RUST_FEEDBACK_LANG)

    assert error is None


def test_validate_patch_scope_program_allows_function_wrapper() -> None:
    error = validate_patch_scope(
        """fn main() {
    let x: i32 = 1;
}""",
        RollbackScope.PROGRAM,
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
        RollbackScope.FUNC,
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
        RollbackScope.FUNC,
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
        RollbackScope.FUNC,
        RUST_FEEDBACK_LANG,
    )

    assert error == (
        "scope validator: func-scope patch cannot include"
        " non-function top-level items (use_declaration)"
    )


def test_validate_patch_scope_func_accepts_statements_only() -> None:
    """FUNC patch with only statements (no function wrapper) should pass."""
    error = validate_patch_scope("let x: i32 = 1;", RollbackScope.FUNC, RUST_FEEDBACK_LANG)

    assert error is None


def test_validate_patch_scope_block_still_rejects_function() -> None:
    """BLOCK scope should still reject function_item (unchanged behavior)."""
    error = validate_patch_scope(
        """fn main() {
    let x: i32 = 1;
}""",
        RollbackScope.BLOCK,
        RUST_FEEDBACK_LANG,
    )

    assert error == "scope validator: block-scope patch cannot include top-level items (function_item)"


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
