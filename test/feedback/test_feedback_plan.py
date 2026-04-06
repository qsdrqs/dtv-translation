from __future__ import annotations

from core.types import (
    Diagnostic,
    FeedbackMechanism,
    GenerationChannel,
    OracleOutput,
    Granularity,
    Verdict,
)
from core.llm_output import BEGIN_WRITE_CODE, END_WRITE_CODE, AssistantContent
from c_rust.feedback import RUST_FEEDBACK_LANG
from feedback.feedback import FeedbackState
from feedback.plan import build_feedback_plan, render_feedback_prompt
from feedback.repair_context import RepairContext
from js_ts.feedback import TS_FEEDBACK_LANG


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
            rollback_scope=Granularity.STMT,
        ),
        OracleOutput(
            oracle_name="program_diff",
            verdict=Verdict.FAIL,
            diagnostics=(
                Diagnostic(message="stdout mismatch on test_1", severity="error"),
            ),
            rollback_scope=Granularity.STMT,
        ),
    ]
    state.on_verify(outputs, selected_scope=Granularity.STMT)

    repair_context = RepairContext.from_feedback_state(state, bad_snippet='let x: i32 = "1";')

    assert repair_context.failed_snippet == 'let x: i32 = "1";'
    assert repair_context.repair_scope == Granularity.STMT
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
            rollback_scope=Granularity.STMT,
        )
    ],
    selected_scope=Granularity.STMT,)

    repair_context = RepairContext.from_feedback_state(
        state,
        bad_snippet='let x: i32 = "1";',
        parser_error_context="multiple write regions found",
    )

    prompt = render_feedback_prompt(repair_context, RUST_FEEDBACK_LANG)

    assert f"{BEGIN_WRITE_CODE}\nlet x: i32 = \"1\";\n{END_WRITE_CODE}" in prompt
    assert "Previous parse error:" in prompt
    assert "multiple write regions found" in prompt
    assert "Return exactly one write-code region containing raw Rust text:" in prompt
    assert f"{BEGIN_WRITE_CODE}\n<Your patch here>\n{END_WRITE_CODE}" in prompt


def test_render_feedback_prompt_stmt_scope_forbids_function_wrapper_for_normal_stmt() -> None:
    state = FeedbackState()
    state.on_verify([
        OracleOutput(
            oracle_name="rustc",
            verdict=Verdict.FAIL,
            diagnostics=(
                Diagnostic(message="expected `i32`, found `&str`", severity="error"),
            ),
            rollback_scope=Granularity.STMT,
        )
    ],
    selected_scope=Granularity.STMT,)

    repair_context = RepairContext.from_feedback_state(state, bad_snippet='let x: i32 = "1";')

    prompt = render_feedback_prompt(repair_context, RUST_FEEDBACK_LANG)

    assert "Do not return full function wrappers" in prompt
    assert "The repair target includes a function header" not in prompt


def test_build_feedback_plan_maps_mechanism_a_to_continuation() -> None:
    state = FeedbackState()
    state.on_verify([
        OracleOutput(
            oracle_name="rustc",
            verdict=Verdict.FAIL,
            diagnostics=(
                Diagnostic(message="expected `i32`, found `&str`", severity="error"),
            ),
            rollback_scope=Granularity.STMT,
        )
    ],
    selected_scope=Granularity.STMT,)
    repair_context = RepairContext.from_feedback_state(state, bad_snippet='let x: i32 = "1";')

    plan = build_feedback_plan(
        mechanism=FeedbackMechanism.A,
        repair_context=repair_context,
        repair_feedback_format_config=None,
        lang_config=RUST_FEEDBACK_LANG,
    )

    assert plan.channel == GenerationChannel.CONTINUATION
    assert "/* repair feedback:" in plan.prompt


def test_build_feedback_plan_maps_mechanism_b_to_patch_write_region() -> None:
    state = FeedbackState()
    state.on_verify([
        OracleOutput(
            oracle_name="rustc",
            verdict=Verdict.FAIL,
            diagnostics=(
                Diagnostic(message="expected `i32`, found `&str`", severity="error"),
            ),
            rollback_scope=Granularity.STMT,
        )
    ],
    selected_scope=Granularity.STMT,)
    repair_context = RepairContext.from_feedback_state(state, bad_snippet='let x: i32 = "1";')

    plan = build_feedback_plan(
        mechanism=FeedbackMechanism.B,
        repair_context=repair_context,
        repair_feedback_format_config=None,
        lang_config=RUST_FEEDBACK_LANG,
    )

    assert plan.channel == GenerationChannel.PATCH
    assert "Return exactly one write-code region containing the unified diff patch:" in plan.prompt
    assert plan.response_prefix is None
    assert plan.post_region_injection is not None


def test_build_feedback_plan_puts_diff_in_post_region_injection() -> None:
    state = FeedbackState()
    state.on_verify([
        OracleOutput(
            oracle_name="tsc",
            verdict=Verdict.FAIL,
            diagnostics=(
                Diagnostic(message="Unexpected any", severity="error"),
            ),
            rollback_scope=Granularity.STMT,
        )
    ],
    selected_scope=Granularity.STMT,)
    repair_context = RepairContext.from_feedback_state(
        state,
        bad_snippet="""function parseJson(\n  txt: string\n): any {\n  return JSON.parse(txt);""",
        repair_scope=Granularity.STMT,
    )

    plan = build_feedback_plan(
        mechanism=FeedbackMechanism.B,
        repair_context=repair_context,
        repair_feedback_format_config=None,
        lang_config=TS_FEEDBACK_LANG,
    )

    assert 'Return a unified diff patch for the failed snippet.' in plan.prompt
    assert plan.response_prefix is None
    assert plan.post_region_injection == """\
- function parseJson(
-   txt: string
- ): any {
-   return JSON.parse(txt);
+ """


def test_build_repair_context_scope_filter_limits_outputs() -> None:
    state = FeedbackState()
    state.on_verify([
        OracleOutput(
            oracle_name="stmt_oracle",
            verdict=Verdict.FAIL,
            diagnostics=(Diagnostic(message="stmt mismatch", severity="error"),),
            rollback_scope=Granularity.STMT,
        )
    ],
    selected_scope=Granularity.STMT,)
    state.on_verify([
        OracleOutput(
            oracle_name="program_oracle",
            verdict=Verdict.FAIL,
            diagnostics=(Diagnostic(message="program mismatch", severity="error"),),
            rollback_scope=Granularity.PROGRAM,
        )
    ],
    selected_scope=Granularity.PROGRAM,)

    stmt_context = RepairContext.from_feedback_state(
        state,
        bad_snippet="bad stmt",
        repair_scope=Granularity.STMT,
        scope_filter=Granularity.STMT,
    )
    assert len(stmt_context.outputs) == 1
    assert stmt_context.outputs[0].oracle_name == "stmt_oracle"

    program_context = RepairContext.from_feedback_state(
        state,
        bad_snippet="bad program",
        repair_scope=Granularity.PROGRAM,
        scope_filter=Granularity.PROGRAM,
    )
    assert len(program_context.outputs) == 1
    assert program_context.outputs[0].oracle_name == "program_oracle"
