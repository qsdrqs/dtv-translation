from __future__ import annotations

from core.types import RollbackScope
from feedback.output_parser import parse_feedback_output, validate_patch_scope


def test_parse_feedback_output_single_fence_success() -> None:
    result = parse_feedback_output(
        """```rust
fn main() {
    println!(\"ok\");
}
```"""
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
```"""
    )

    assert result.patch is None
    assert result.error == "multiple fenced code blocks found"
    assert result.used_fence is True


def test_parse_feedback_output_rejects_empty_output() -> None:
    result = parse_feedback_output("   \n\n")

    assert result.patch is None
    assert result.error == "empty model output"
    assert result.used_fence is False


def test_parse_feedback_output_accepts_plain_text_fallback() -> None:
    result = parse_feedback_output(
        """fn main() {
    println!(\"ok\");
}"""
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
```"""
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
    )

    assert error == "scope validator: stmt-scope patch cannot include top-level items (function_item)"


def test_validate_patch_scope_stmt_accepts_statement_patch() -> None:
    error = validate_patch_scope("let x: i32 = 1;", RollbackScope.STMT)

    assert error is None


def test_validate_patch_scope_program_allows_function_wrapper() -> None:
    error = validate_patch_scope(
        """fn main() {
    let x: i32 = 1;
}""",
        RollbackScope.PROGRAM,
    )

    assert error is None
