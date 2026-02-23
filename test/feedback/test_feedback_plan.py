from __future__ import annotations

from core.types import (
    Diagnostic,
    FeedbackMechanism,
    FeedbackMode,
    GenerationChannel,
    OracleOutput,
    RollbackScope,
    Verdict,
)
from feedback.feedback import FeedbackState
from feedback.plan import build_feedback_plan, render_feedback_prompt
from feedback.repair_context import RepairContext


def test_build_repair_context_collects_scope_aligned_diagnostics() -> None:
    state = FeedbackState()
    outputs = [
        OracleOutput(
            oracle_name="rustc",
            verdict=Verdict.FAIL,
            diagnostics=(
                Diagnostic(
                    message="mismatched types",
                    severity="error",
                    error_code="E0308",
                ),
            ),
            rollback_scope=RollbackScope.STMT,
        ),
        OracleOutput(
            oracle_name="program_diff",
            verdict=Verdict.FAIL,
            diagnostics=(
                Diagnostic(message="stdout mismatch on test_1", severity="error"),
            ),
            rollback_scope=RollbackScope.STMT,
        ),
    ]
    state.on_verify(outputs, selected_scope=RollbackScope.STMT)

    repair_context = RepairContext.from_feedback_state(state, bad_snippet='let x: i32 = "1";')

    assert repair_context.failed_snippet == 'let x: i32 = "1";'
    assert repair_context.repair_scope == RollbackScope.STMT
    assert repair_context.parser_error_context is None
    assert len(repair_context.outputs) == 2
    assert repair_context.outputs[0].oracle_name == "rustc"
    assert repair_context.outputs[0].diagnostics[0].error_code == "E0308"
    assert repair_context.outputs[0].diagnostics[0].message == "mismatched types"
    assert repair_context.outputs[1].oracle_name == "program_diff"
    assert repair_context.outputs[1].diagnostics[0].message == "stdout mismatch on test_1"


def test_render_feedback_prompt_includes_parser_error_context() -> None:
    state = FeedbackState()
    state.on_verify([
        OracleOutput(
            oracle_name="rustc",
            verdict=Verdict.FAIL,
            diagnostics=(
                Diagnostic(message="expected `i32`, found `&str`", severity="error"),
            ),
            rollback_scope=RollbackScope.STMT,
        )
    ],
    selected_scope=RollbackScope.STMT,)

    repair_context = RepairContext.from_feedback_state(
        state,
        bad_snippet='let x: i32 = "1";',
        parser_error_context="multiple fenced code blocks found",
    )

    prompt = render_feedback_prompt(repair_context)

    assert prompt == """The previous generated next code snippet was:

```
let x: i32 = \"1\";
```

It error with diagnostics:
- [rustc] expected `i32`, found `&str`

Your goal:
- Produce a minimal Rust patch that resolves the listed failures.

repair scope:
- stmt

constraints:
- Keep unchanged code outside the failed snippet.
- Return code only. Do not add prose.
- Prefer the smallest valid edit.

Previous parse error:
- multiple fenced code blocks found

scope rules:
- Replace only the failed snippet.
- Do not return full function wrappers (for example, `fn main() { ... }`).

output contract:
Return exactly one Rust code block:
```rust
<Your patch here>
```
"""


def test_build_feedback_plan_maps_mechanism_a_to_continuation() -> None:
    state = FeedbackState()
    state.on_verify([
        OracleOutput(
            oracle_name="rustc",
            verdict=Verdict.FAIL,
            diagnostics=(
                Diagnostic(message="expected `i32`, found `&str`", severity="error"),
            ),
            rollback_scope=RollbackScope.STMT,
        )
    ],
    selected_scope=RollbackScope.STMT,)
    repair_context = RepairContext.from_feedback_state(state, bad_snippet='let x: i32 = "1";')

    plan = build_feedback_plan(
        mechanism=FeedbackMechanism.A,
        requested_mode=FeedbackMode.INLINE,
        repair_context=repair_context,
        repair_feedback_format_config=None,
    )

    assert plan.mode == FeedbackMode.INLINE
    assert plan.channel == GenerationChannel.CONTINUATION
    assert "/* repair feedback:" in plan.prompt


def test_build_feedback_plan_maps_mechanism_b_to_patch_fenced() -> None:
    state = FeedbackState()
    state.on_verify([
        OracleOutput(
            oracle_name="rustc",
            verdict=Verdict.FAIL,
            diagnostics=(
                Diagnostic(message="expected `i32`, found `&str`", severity="error"),
            ),
            rollback_scope=RollbackScope.STMT,
        )
    ],
    selected_scope=RollbackScope.STMT,)
    repair_context = RepairContext.from_feedback_state(state, bad_snippet='let x: i32 = "1";')

    plan = build_feedback_plan(
        mechanism=FeedbackMechanism.B,
        requested_mode=FeedbackMode.INLINE,
        repair_context=repair_context,
        repair_feedback_format_config=None,
    )

    assert plan.mode == FeedbackMode.FENCED
    assert plan.channel == GenerationChannel.PATCH
    assert "Return exactly one Rust code block:" in plan.prompt


def test_build_repair_context_scope_filter_limits_outputs() -> None:
    state = FeedbackState()
    state.on_verify([
        OracleOutput(
            oracle_name="stmt_oracle",
            verdict=Verdict.FAIL,
            diagnostics=(Diagnostic(message="stmt mismatch", severity="error"),),
            rollback_scope=RollbackScope.STMT,
        )
    ],
    selected_scope=RollbackScope.STMT,)
    state.on_verify([
        OracleOutput(
            oracle_name="program_oracle",
            verdict=Verdict.FAIL,
            diagnostics=(Diagnostic(message="program mismatch", severity="error"),),
            rollback_scope=RollbackScope.PROGRAM,
        )
    ],
    selected_scope=RollbackScope.PROGRAM,)

    stmt_context = RepairContext.from_feedback_state(
        state,
        bad_snippet="bad stmt",
        repair_scope=RollbackScope.STMT,
        scope_filter=RollbackScope.STMT,
    )
    assert len(stmt_context.outputs) == 1
    assert stmt_context.outputs[0].oracle_name == "stmt_oracle"

    program_context = RepairContext.from_feedback_state(
        state,
        bad_snippet="bad program",
        repair_scope=RollbackScope.PROGRAM,
        scope_filter=RollbackScope.PROGRAM,
    )
    assert len(program_context.outputs) == 1
    assert program_context.outputs[0].oracle_name == "program_oracle"
