from __future__ import annotations

from c_rust.feedback import RUST_FEEDBACK_LANG
from controller.loop import PolicyContext, run_dtv_loop
from controller.policy import DefaultPolicy, DefaultPolicyConfig
from core.budget import Budget
from core.llm_output import AssistantContent, WriteRegionParser, WriteRegionState, OutputExtractorState
from core.types import (
    Action,
    Artifact,
    ControllerState,
    Diagnostic,
    FeedbackMechanism,
    GenerateContext,
    GenerateResult,
    Granularity,
    OracleOutput,
    RenderResult,
    RenderStatus,
    Granularity,
    StopReason,
    Verdict,
)
from feedback.feedback import FeedbackState
from rollback.manager import RollbackManager


def _ctx(
    *,
    prefix: str = "",
    last_action: Action | None = None,
    last_stop_reason: StopReason | None = None,
    last_render_status: RenderStatus | None = None,
    last_outputs: tuple[OracleOutput, ...] = (),
    last_artifact: Artifact | None = None,
    budget: Budget | None = None,
    failed_prefix: str | None = None,
    pending_patch: str | None = None,
    repair_base_prefix: str | None = None,
    repair_scope: Granularity | None = None,
    write_region_state: WriteRegionState = WriteRegionState.OUTSIDE,
) -> PolicyContext:
    return PolicyContext(
        state=ControllerState(prefix=prefix),
        budget=budget or Budget(gen_tokens_budget=8),
        rollback=RollbackManager(),
        last_action=last_action,
        last_stop_reason=last_stop_reason,
        last_render_status=last_render_status,
        last_artifact=last_artifact,
        last_outputs=last_outputs,
        failed_prefix=failed_prefix,
        pending_patch=pending_patch,
        repair_base_prefix=repair_base_prefix,
        repair_scope=repair_scope,
        write_region_state=write_region_state,
    )


def _outputs(*verdicts: Verdict) -> tuple[OracleOutput, ...]:
    return tuple(
        OracleOutput(oracle_name=f"oracle_{idx}", verdict=verdict)
        for idx, verdict in enumerate(verdicts)
    )


def _fail_outputs(*, scope: Granularity = Granularity.STMT) -> tuple[OracleOutput, ...]:
    return (
        OracleOutput(
            oracle_name="oracle_0",
            verdict=Verdict.FAIL,
            diagnostics=(Diagnostic(message="type mismatch", severity="error"),),
            rollback_scope=scope,
        ),
    )


class _AlwaysOkRenderer:
    def try_render(self, prefix: str) -> RenderResult:
        return RenderResult(status=RenderStatus.OK, artifact=Artifact(code=prefix))


class _AlwaysFailOracle:
    name = "oracle"
    required_granularity = Granularity.STMT
    rollback_scope = Granularity.STMT

    def run(self, state, artifact, context) -> OracleOutput:
        _ = state
        _ = artifact
        _ = context
        # Intentionally fail forever: these tests validate policy scheduling, not patch correctness.
        return OracleOutput(
            oracle_name=self.name,
            verdict=Verdict.FAIL,
            diagnostics=(Diagnostic(message="type mismatch", severity="error"),),
            rollback_scope=self.rollback_scope,
            realized_cost=1,
        )


class _EscalationWriteRegionGenerator:
    def __init__(self) -> None:
        self._parser = WriteRegionParser()
        self._did_generate = False
        self.feedback_mechanisms: list[FeedbackMechanism] = []

    def reset_output_extractor(self) -> None:
        self._parser.reset()

    def get_output_extractor_state(self) -> WriteRegionState:
        return self._parser.state

    def capture_output_extractor_state(self) -> OutputExtractorState:
        snapshot = self._parser.capture()
        return OutputExtractorState(
            segment=snapshot,
            extract=snapshot,
            shared=snapshot,
            warning_emitted=False,
        )

    def restore_output_extractor_state(self, state: OutputExtractorState) -> None:
        self._parser.restore(state.extract)

    def set_stop_on_write_region_open(self, enabled: bool) -> None:
        _ = enabled

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        mechanism = self._feedback_mechanism(context)
        if mechanism is not None:
            self.feedback_mechanisms.append(mechanism)
            if mechanism == FeedbackMechanism.A:
                self._parser.feed("bad;")
                return GenerateResult(
                    delta_text="bad;",
                    delta_tokens=1,
                    stop_reason=StopReason(kind="boundary"),
                )
            self._parser.feed("<<BEGIN_WRITE_CODE>>\n")
            return GenerateResult(
                delta_text="bad;",
                delta_tokens=1,
                stop_reason=StopReason(kind="boundary"),
            )

        if not self._did_generate:
            self._did_generate = True
            return GenerateResult(
                delta_text="bad;",
                delta_tokens=1,
                stop_reason=StopReason(kind="boundary"),
                assistant_delta=AssistantContent(
                    code="bad;",
                    has_begin_marker=True,
                    region_state=WriteRegionState.INSIDE,
                ),
            )

        return GenerateResult(
            delta_text="",
            delta_tokens=0,
            stop_reason=StopReason(kind="empty"),
        )

    def _feedback_mechanism(self, context: GenerateContext) -> FeedbackMechanism | None:
        for message in reversed(context.messages):
            if self._message_role(message) != "user":
                continue
            text = self._message_text(message)
            if "The previous generated next code snippet was:" in text:
                return FeedbackMechanism.B
        for message in reversed(context.messages):
            if self._message_role(message) != "assistant":
                continue
            text = self._message_text(message)
            if "/* repair feedback:" in text:
                return FeedbackMechanism.A
        return None

    @staticmethod
    def _message_role(message: object) -> str:
        if isinstance(message, dict):
            return str(message.get("role", ""))
        return str(getattr(message, "role", ""))

    @staticmethod
    def _message_text(message: object) -> str:
        if isinstance(message, dict):
            content = message.get("content", "")
        else:
            content = getattr(message, "content", "")
        if isinstance(content, AssistantContent):
            return content.render()
        return str(content)


def test_default_policy_verify_inconclusive_returns_continue() -> None:
    policy = DefaultPolicy(DefaultPolicyConfig(enable_feedback=False))
    ctx = _ctx(
        prefix="let x = 1;",
        last_action=Action.VERIFY,
        last_stop_reason=StopReason(kind="boundary"),
        last_render_status=RenderStatus.CONTINUE,
    )
    op = policy.next_action(ctx)
    assert op.action == Action.CONTINUE


def test_default_policy_no_oracle_selected_commits_when_enabled() -> None:
    policy = DefaultPolicy(DefaultPolicyConfig(commit_when_no_oracle_selected=True))
    artifact = Artifact(code="let x = 1;")
    ctx = _ctx(
        prefix="let x = 1;",
        last_action=Action.VERIFY,
        last_stop_reason=StopReason(kind="boundary"),
        last_render_status=RenderStatus.OK,
        last_outputs=(),
        last_artifact=artifact,
    )
    op = policy.next_action(ctx)
    assert op.action == Action.COMMIT


def test_default_policy_fail_rolls_back() -> None:
    policy = DefaultPolicy(DefaultPolicyConfig(enable_rollback=True, default_fail_scope=Granularity.STMT))
    ctx = _ctx(
        prefix="let x = 1;",
        last_action=Action.VERIFY,
        last_stop_reason=StopReason(kind="boundary"),
        last_render_status=RenderStatus.OK,
        last_outputs=_outputs(Verdict.FAIL),
    )
    op = policy.next_action(ctx)
    assert op.action == Action.ROLLBACK
    assert op.rollback_scope == Granularity.STMT


def test_default_policy_stmt_stall_escalates_to_func_without_active_block() -> None:
    policy = DefaultPolicy(DefaultPolicyConfig(
        enable_feedback=True,
        enable_rollback=True,
        default_fail_scope=Granularity.STMT,
        stmt_stall_max_retries_before_escalation=3,
        feedback_default_mechanism=FeedbackMechanism.A,
    ))

    def _verify_fail_rollback_with_groups(*, groups):
        ctx = _ctx(
            prefix="bad;",
            last_action=Action.VERIFY,
            last_render_status=RenderStatus.OK,
            last_outputs=_fail_outputs(scope=Granularity.STMT),
        )
        for g in groups:
            ctx.rollback.open_group(g)
        return policy.next_action(ctx)

    for i in range(3):
        # VERIFY FAIL -> ROLLBACK STMT (stall retries 1, 2, 3)
        op = _verify_fail_rollback_with_groups(groups=[Granularity.FUNC])
        assert op.action == Action.ROLLBACK
        assert op.rollback_scope == Granularity.STMT, f"iteration {i}"

        ctx = _ctx(
            prefix="base;",
            last_action=Action.ROLLBACK,
            failed_prefix="bad;",
            repair_base_prefix="base;",
            repair_scope=Granularity.STMT,
        )
        op = policy.next_action(ctx)
        assert op.action == Action.FEEDBACK

        ctx = _ctx(
            pending_patch="still_bad;",
            repair_base_prefix="base;",
            repair_scope=Granularity.STMT,
        )
        op = policy.next_action(ctx)
        assert op.action == Action.APPLY_PATCH

        ctx = _ctx(
            prefix="base;still_bad;",
            last_action=Action.APPLY_PATCH,
            repair_base_prefix="base;",
            repair_scope=Granularity.STMT,
        )
        op = policy.next_action(ctx)
        assert op.action == Action.VERIFY

    # 4th VERIFY FAIL: no active BLOCK -> escalate to FUNC
    op = _verify_fail_rollback_with_groups(groups=[Granularity.FUNC])
    assert op.action == Action.ROLLBACK
    assert op.rollback_scope == Granularity.FUNC


def test_default_policy_stmt_stall_counter_resets_after_pass() -> None:
    policy = DefaultPolicy(
        DefaultPolicyConfig(
            enable_feedback=False,
            enable_rollback=True,
            default_fail_scope=Granularity.STMT,
            stmt_stall_max_retries_before_escalation=1,
        )
    )

    first_fail = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=Granularity.STMT),
    )
    first_fail.rollback.open_group(Granularity.FUNC)
    first_fail.rollback.open_group(Granularity.BLOCK)
    first_op = policy.next_action(first_fail)
    assert first_op.action == Action.ROLLBACK
    assert first_op.rollback_scope == Granularity.STMT

    pass_ctx = _ctx(
        prefix="good;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_outputs(Verdict.PASS),
    )
    pass_op = policy.next_action(pass_ctx)
    assert pass_op.action == Action.COMMIT

    second_fail = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=Granularity.STMT),
    )
    second_fail.rollback.open_group(Granularity.FUNC)
    second_fail.rollback.open_group(Granularity.BLOCK)
    second_op = policy.next_action(second_fail)
    assert second_op.action == Action.ROLLBACK
    assert second_op.rollback_scope == Granularity.STMT


# feedback + stall detection integration
# Production path: FEEDBACK -> APPLY_PATCH -> VERIFY FAIL -> ROLLBACK -> FEEDBACK -> ...
# Stall detection must work through this path, not just the no-feedback path.

def test_verify_fail_after_apply_patch_returns_rollback_not_feedback() -> None:
    policy = DefaultPolicy(DefaultPolicyConfig(
        enable_feedback=True,
        enable_rollback=True,
    ))

    # Initial VERIFY FAIL: no repair context -> ROLLBACK
    ctx = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=Granularity.STMT),
    )
    ctx.rollback.open_group(Granularity.FUNC)
    op = policy.next_action(ctx)
    assert op.action == Action.ROLLBACK
    assert op.rollback_scope == Granularity.STMT

    # After ROLLBACK: repair context set -> FEEDBACK
    ctx = _ctx(
        prefix="base;",
        last_action=Action.ROLLBACK,
        failed_prefix="bad;",
        repair_base_prefix="base;",
        repair_scope=Granularity.STMT,
    )
    op = policy.next_action(ctx)
    assert op.action == Action.FEEDBACK

    # FEEDBACK produced patch -> APPLY_PATCH
    ctx = _ctx(
        pending_patch="patched;",
        repair_base_prefix="base;",
        repair_scope=Granularity.STMT,
    )
    op = policy.next_action(ctx)
    assert op.action == Action.APPLY_PATCH

    # After APPLY_PATCH -> VERIFY
    ctx = _ctx(
        prefix="base;patched;",
        last_action=Action.APPLY_PATCH,
        repair_base_prefix="base;",
        repair_scope=Granularity.STMT,
    )
    op = policy.next_action(ctx)
    assert op.action == Action.VERIFY

    # VERIFY FAIL with repair context:
    # Must ROLLBACK (through _select_fail_scope), not skip to FEEDBACK.
    ctx = _ctx(
        prefix="base;patched;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=Granularity.STMT),
        failed_prefix="base;patched;",
        repair_base_prefix="base;",
        repair_scope=Granularity.STMT,
    )
    ctx.rollback.open_group(Granularity.FUNC)
    op = policy.next_action(ctx)
    assert op.action == Action.ROLLBACK
    assert op.rollback_scope == Granularity.STMT


def test_stmt_stall_escalates_through_feedback_repair_loop() -> None:
    policy = DefaultPolicy(DefaultPolicyConfig(
        enable_feedback=True,
        enable_rollback=True,
        default_fail_scope=Granularity.STMT,
        stmt_stall_max_retries_before_escalation=3,
        feedback_default_mechanism=FeedbackMechanism.A,
    ))

    for i in range(3):
        # VERIFY FAIL -> ROLLBACK STMT (stall retries 1, 2, 3)
        ctx = _ctx(
            prefix="bad;",
            last_action=Action.VERIFY,
            last_render_status=RenderStatus.OK,
            last_outputs=_fail_outputs(scope=Granularity.STMT),
            # First iteration: no repair context (initial failure).
            # Later iterations: repair context from prior ROLLBACK.
            failed_prefix="bad;" if i > 0 else None,
            repair_base_prefix="base;" if i > 0 else None,
            repair_scope=Granularity.STMT if i > 0 else None,
        )
        ctx.rollback.open_group(Granularity.FUNC)
        ctx.rollback.open_group(Granularity.BLOCK)
        op = policy.next_action(ctx)
        assert op.action == Action.ROLLBACK
        assert op.rollback_scope == Granularity.STMT, f"iteration {i}: expected STMT"

        # After ROLLBACK -> FEEDBACK
        ctx = _ctx(
            prefix="base;",
            last_action=Action.ROLLBACK,
            failed_prefix="bad;",
            repair_base_prefix="base;",
            repair_scope=Granularity.STMT,
        )
        op = policy.next_action(ctx)
        assert op.action == Action.FEEDBACK

        ctx = _ctx(
            pending_patch="still_bad;",
            repair_base_prefix="base;",
            repair_scope=Granularity.STMT,
        )
        op = policy.next_action(ctx)
        assert op.action == Action.APPLY_PATCH

        ctx = _ctx(
            prefix="base;still_bad;",
            last_action=Action.APPLY_PATCH,
            repair_base_prefix="base;",
            repair_scope=Granularity.STMT,
        )
        op = policy.next_action(ctx)
        assert op.action == Action.VERIFY

    # 4th VERIFY FAIL: stall should escalate to BLOCK
    ctx = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=Granularity.STMT),
        failed_prefix="bad;",
        repair_base_prefix="base;",
        repair_scope=Granularity.STMT,
    )
    ctx.rollback.open_group(Granularity.FUNC)
    ctx.rollback.open_group(Granularity.BLOCK)
    op = policy.next_action(ctx)
    assert op.action == Action.ROLLBACK
    assert op.rollback_scope == Granularity.BLOCK


def test_repair_schedule_survives_rollback_within_feedback_loop() -> None:
    policy = DefaultPolicy(DefaultPolicyConfig(
        enable_feedback=True,
        enable_rollback=True,
        feedback_default_mechanism=FeedbackMechanism.A,
        feedback_max_a_rounds_per_key=2,
    ))

    # Initial VERIFY FAIL -> ROLLBACK (no repair context)
    ctx = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=Granularity.STMT),
    )
    ctx.rollback.open_group(Granularity.FUNC)
    op = policy.next_action(ctx)
    assert op.action == Action.ROLLBACK

    # Two rounds of FEEDBACK A (exhausting A budget for this repair_key)
    for _ in range(2):
        # ROLLBACK / VERIFY FAIL -> FEEDBACK A
        ctx = _ctx(
            prefix="base;",
            last_action=Action.ROLLBACK,
            failed_prefix="bad;",
            repair_base_prefix="base;",
            repair_scope=Granularity.STMT,
        )
        op = policy.next_action(ctx)
        assert op.action == Action.FEEDBACK

        ctx = _ctx(
            pending_patch="still_bad;",
            repair_base_prefix="base;",
            repair_scope=Granularity.STMT,
        )
        op = policy.next_action(ctx)
        assert op.action == Action.APPLY_PATCH

        ctx = _ctx(
            prefix="base;still_bad;",
            last_action=Action.APPLY_PATCH,
            repair_base_prefix="base;",
            repair_scope=Granularity.STMT,
        )
        op = policy.next_action(ctx)
        assert op.action == Action.VERIFY

        # VERIFY FAIL -> ROLLBACK (with stall tracking)
        ctx = _ctx(
            prefix="bad;",
            last_action=Action.VERIFY,
            last_render_status=RenderStatus.OK,
            last_outputs=_fail_outputs(scope=Granularity.STMT),
            failed_prefix="bad;",
            repair_base_prefix="base;",
            repair_scope=Granularity.STMT,
        )
        ctx.rollback.open_group(Granularity.FUNC)
        op = policy.next_action(ctx)
        assert op.action == Action.ROLLBACK

    # After 2 A rounds exhausted + ROLLBACK, next FEEDBACK should be B
    # (proves repair_key survived the ROLLBACK pop+push: schedule state
    # remembers a_rounds=2, so A is exhausted and B is selected).
    ctx = _ctx(
        prefix="base;",
        last_action=Action.ROLLBACK,
        failed_prefix="bad;",
        repair_base_prefix="base;",
        repair_scope=Granularity.STMT,
    )
    op = policy.next_action(ctx)
    assert op.action == Action.FEEDBACK
    assert op.feedback_mechanism == FeedbackMechanism.B


def test_default_policy_generate_boundary_triggers_verify() -> None:
    policy = DefaultPolicy()
    ctx = _ctx(
        prefix="let x = 1;",
        last_action=Action.GENERATE,
        last_stop_reason=StopReason(kind="boundary"),
        last_render_status=None,
    )
    op = policy.next_action(ctx)
    assert op.action == Action.VERIFY
    assert op.verification_granularity == Granularity.STMT


def test_default_policy_write_region_closed_uses_close_granularity() -> None:
    policy = DefaultPolicy()
    ctx = _ctx(
        prefix="fn main() {}",
        last_action=Action.GENERATE,
        last_stop_reason=StopReason(kind="write_region_closed"),
    )
    op = policy.next_action(ctx)
    assert op.action == Action.VERIFY
    assert op.verification_granularity == Granularity.FUNC


def test_default_policy_continue_then_generate() -> None:
    policy = DefaultPolicy()
    ctx = _ctx(
        prefix="let x = 1;",
        last_action=Action.CONTINUE,
        last_stop_reason=StopReason(kind="boundary"),
    )
    op = policy.next_action(ctx)
    assert op.action == Action.GENERATE


def test_eos_without_write_region_close_does_not_terminate() -> None:
    policy = DefaultPolicy()
    ctx = _ctx(
        last_action=Action.COMMIT,
        last_stop_reason=StopReason(kind="eos"),
        last_outputs=_outputs(Verdict.PASS),
    )
    op = policy.next_action(ctx)
    assert op.action == Action.GENERATE


def test_eos_without_write_region_close_uses_boundary_granularity() -> None:
    policy = DefaultPolicy()
    ctx = _ctx(
        prefix="let x = 1;",
        last_action=Action.GENERATE,
        last_stop_reason=StopReason(kind="eos"),
    )
    op = policy.next_action(ctx)
    assert op.action == Action.VERIFY
    assert op.verification_granularity == Granularity.STMT


def test_default_policy_write_region_closed_pass_commits_then_terminates() -> None:
    policy = DefaultPolicy()
    outputs = _outputs(Verdict.PASS)
    ctx_verify = _ctx(
        prefix="fn main() {}",
        last_action=Action.VERIFY,
        last_stop_reason=StopReason(kind="write_region_closed"),
        last_render_status=RenderStatus.OK,
        last_outputs=outputs,
    )
    op = policy.next_action(ctx_verify)
    assert op.action == Action.COMMIT

    ctx_commit = _ctx(
        prefix="fn main() {}",
        last_action=Action.COMMIT,
        last_stop_reason=StopReason(kind="write_region_closed"),
        last_render_status=RenderStatus.OK,
        last_outputs=outputs,
    )
    op = policy.next_action(ctx_commit)
    assert op.action == Action.TERMINATE


def test_default_policy_write_region_closed_no_oracles_commits_then_terminates() -> None:
    policy = DefaultPolicy()
    ctx_verify = _ctx(
        prefix="fn main() {}",
        last_action=Action.VERIFY,
        last_stop_reason=StopReason(kind="write_region_closed"),
        last_render_status=RenderStatus.OK,
        last_outputs=(),
    )
    op = policy.next_action(ctx_verify)
    assert op.action == Action.COMMIT

    ctx_commit = _ctx(
        prefix="fn main() {}",
        last_action=Action.COMMIT,
        last_stop_reason=StopReason(kind="write_region_closed"),
        last_render_status=RenderStatus.OK,
        last_outputs=(),
    )
    op = policy.next_action(ctx_commit)
    assert op.action == Action.TERMINATE


def test_default_policy_feedback_starts_with_mechanism_a() -> None:
    policy = DefaultPolicy()
    ctx = _ctx(
        prefix="bad;",
        last_action=Action.ROLLBACK,
        failed_prefix="bad;",
        repair_base_prefix="",
        repair_scope=Granularity.STMT,
    )

    op = policy.next_action(ctx)

    assert op.action == Action.FEEDBACK
    assert op.feedback_mechanism == FeedbackMechanism.A



def _do_verify_fail_rollback_feedback(policy, *, prefix="bad;", repair_base="",
                                       expected_mechanism=None):
    ctx = _ctx(
        prefix=prefix,
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=Granularity.STMT),
    )
    op = policy.next_action(ctx)
    assert op.action == Action.ROLLBACK

    ctx = _ctx(
        prefix=repair_base,
        last_action=Action.ROLLBACK,
        failed_prefix=prefix,
        repair_base_prefix=repair_base,
        repair_scope=Granularity.STMT,
    )
    op = policy.next_action(ctx)
    assert op.action == Action.FEEDBACK
    if expected_mechanism is not None:
        assert op.feedback_mechanism == expected_mechanism
    return op


def test_default_policy_feedback_stays_on_b_per_key_by_default() -> None:
    policy = DefaultPolicy(DefaultPolicyConfig(max_repair_rounds=6))

    # A exhausts its budget (max_a_rounds_per_key=2), then B takes over.
    _do_verify_fail_rollback_feedback(policy, expected_mechanism=FeedbackMechanism.A)
    _do_verify_fail_rollback_feedback(policy, expected_mechanism=FeedbackMechanism.A)
    _do_verify_fail_rollback_feedback(policy, expected_mechanism=FeedbackMechanism.B)
    _do_verify_fail_rollback_feedback(policy, expected_mechanism=FeedbackMechanism.B)

    # New repair key resets to A.
    _do_verify_fail_rollback_feedback(
        policy, prefix="bad2;", repair_base="anchor2",
        expected_mechanism=FeedbackMechanism.A,
    )


def test_default_policy_feedback_terminates_when_b_cap_is_reached() -> None:
    policy = DefaultPolicy(
        DefaultPolicyConfig(
            max_repair_rounds=6,
            feedback_max_b_rounds_per_key=1,
        )
    )

    # 2 A rounds (budget exhausted), then 1 B round (capped), then TERMINATE.
    _do_verify_fail_rollback_feedback(policy, expected_mechanism=FeedbackMechanism.A)
    _do_verify_fail_rollback_feedback(policy, expected_mechanism=FeedbackMechanism.A)
    _do_verify_fail_rollback_feedback(policy, expected_mechanism=FeedbackMechanism.B)

    ctx = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=Granularity.STMT),
    )
    op = policy.next_action(ctx)
    assert op.action == Action.ROLLBACK

    ctx = _ctx(
        prefix="",
        last_action=Action.ROLLBACK,
        failed_prefix="bad;",
        repair_base_prefix="",
        repair_scope=Granularity.STMT,
    )
    op = policy.next_action(ctx)
    assert op.action == Action.TERMINATE


def test_default_policy_program_scope_escalates_to_b_even_when_failed_prefix_changes() -> None:
    policy = DefaultPolicy(DefaultPolicyConfig(max_repair_rounds=4))

    first_verify_fail_ctx = _ctx(
        prefix="program_fail_v1",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=Granularity.PROGRAM),
    )
    first_rollback_op = policy.next_action(first_verify_fail_ctx)
    assert first_rollback_op.action == Action.ROLLBACK

    first_feedback_ctx = _ctx(
        prefix="",
        last_action=Action.ROLLBACK,
        failed_prefix="program_fail_v1",
        repair_base_prefix="",
        repair_scope=Granularity.PROGRAM,
    )
    first_feedback_op = policy.next_action(first_feedback_ctx)
    assert first_feedback_op.action == Action.FEEDBACK
    assert first_feedback_op.feedback_mechanism == FeedbackMechanism.A

    second_verify_fail_ctx = _ctx(
        prefix="program_fail_v2",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=Granularity.PROGRAM),
    )
    second_rollback_op = policy.next_action(second_verify_fail_ctx)
    assert second_rollback_op.action == Action.ROLLBACK

    second_feedback_ctx = _ctx(
        prefix="",
        last_action=Action.ROLLBACK,
        failed_prefix="program_fail_v2",
        repair_base_prefix="",
        repair_scope=Granularity.PROGRAM,
    )
    second_feedback_op = policy.next_action(second_feedback_ctx)
    assert second_feedback_op.action == Action.FEEDBACK
    assert second_feedback_op.feedback_mechanism == FeedbackMechanism.B




def test_default_policy_feedback_force_mechanism_b() -> None:
    policy = DefaultPolicy(DefaultPolicyConfig(feedback_force_mechanism=FeedbackMechanism.B))
    ctx = _ctx(
        prefix="bad;",
        last_action=Action.ROLLBACK,
        failed_prefix="bad;",
        repair_base_prefix="",
        repair_scope=Granularity.STMT,
    )

    op = policy.next_action(ctx)

    assert op.action == Action.FEEDBACK
    assert op.feedback_mechanism == FeedbackMechanism.B


def test_default_policy_b_no_patch_escalates_to_rollback() -> None:
    """When B repeatedly produces no usable patch (parser/scope validation fail),
    treat as a verify fail and rollback with stall escalation."""
    policy = DefaultPolicy(
        DefaultPolicyConfig(
            enable_rollback=True,
            enable_feedback=True,
            feedback_force_mechanism=FeedbackMechanism.B,
            feedback_max_b_no_patch_rounds=3,
        )
    )

    # VERIFY FAIL -> ROLLBACK
    verify_fail_ctx = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=Granularity.STMT),
    )
    rollback_op = policy.next_action(verify_fail_ctx)
    assert rollback_op.action == Action.ROLLBACK
    assert rollback_op.rollback_scope == Granularity.STMT

    # After ROLLBACK -> first FEEDBACK(B) (b_no_patch not incremented; last_action=ROLLBACK)
    after_rollback_ctx = _ctx(
        prefix="",
        last_action=Action.ROLLBACK,
        failed_prefix="bad;",
        repair_base_prefix="",
        repair_scope=Granularity.STMT,
    )
    feedback_op = policy.next_action(after_rollback_ctx)
    assert feedback_op.action == Action.FEEDBACK
    assert feedback_op.feedback_mechanism == FeedbackMechanism.B

    # B produced no patch x2 -> still FEEDBACK(B)
    for i in range(2):
        no_patch_ctx = _ctx(
            prefix="",
            last_action=Action.FEEDBACK,
            failed_prefix="bad;",
            repair_base_prefix="",
            repair_scope=Granularity.STMT,
        )
        op = policy.next_action(no_patch_ctx)
        assert op.action == Action.FEEDBACK, f"expected FEEDBACK at no-patch round {i + 1}"
        assert op.feedback_mechanism == FeedbackMechanism.B

    # B produced no patch (3rd) -> ROLLBACK (treated as verify fail)
    final_no_patch_ctx = _ctx(
        prefix="",
        last_action=Action.FEEDBACK,
        failed_prefix="bad;",
        repair_base_prefix="",
        repair_scope=Granularity.STMT,
    )
    escalation_op = policy.next_action(final_no_patch_ctx)
    assert escalation_op.action == Action.ROLLBACK
    assert escalation_op.rollback_scope == Granularity.STMT


# bailout mechanism tests


def _add_checkpoint(rm: RollbackManager, prefix: str) -> None:
    """Add a stmt checkpoint with the given code prefix."""
    rm.add_stmt_checkpoint(prefix, AssistantContent.empty(), None)


def test_bailout_on_repeated_target() -> None:
    """Policy returns TERMINATE when the same rollback target is visited
    bailout_visit_threshold times."""
    config = DefaultPolicyConfig(
        bailout_visit_threshold=3,
        enable_feedback=False,
    )
    policy = DefaultPolicy(config)

    for i in range(3):
        ctx = _ctx(
            prefix="fn main() { let x = bad;",
            last_action=Action.VERIFY,
            last_render_status=RenderStatus.OK,
            last_outputs=_fail_outputs(scope=Granularity.STMT),
        )
        _add_checkpoint(ctx.rollback, "fn main() { ")
        op = policy.next_action(ctx)
        if i < 2:
            assert op.action == Action.ROLLBACK, f"iteration {i}: expected ROLLBACK"
        else:
            assert op.action == Action.TERMINATE, f"iteration {i}: expected TERMINATE (bailout)"
            assert op.bailout is True


def test_bailout_counter_tracks_per_target() -> None:
    """Visit counter is per diagnostic signature. Different error codes have
    independent counts even at the same checkpoint location."""
    config = DefaultPolicyConfig(
        bailout_visit_threshold=3,
        enable_feedback=False,
    )
    policy = DefaultPolicy(config)

    # 2 visits for error E0308
    for _ in range(2):
        ctx = _ctx(
            prefix="bad;",
            last_action=Action.VERIFY,
            last_render_status=RenderStatus.OK,
            last_outputs=_fail_outputs_with_code(
                error_code="E0308", message="mismatched types",
            ),
        )
        _add_checkpoint(ctx.rollback, "target_A")
        op = policy.next_action(ctx)
        assert op.action == Action.ROLLBACK

    # 1 visit for a different error E0384 - should NOT push E0308 over threshold
    ctx = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs_with_code(
            error_code="E0384", message="cannot assign to immutable",
        ),
    )
    _add_checkpoint(ctx.rollback, "target_A")
    op = policy.next_action(ctx)
    assert op.action == Action.ROLLBACK

    # 3rd visit for E0308 -> reaches threshold=3 -> bailout
    ctx = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs_with_code(
            error_code="E0308", message="mismatched types",
        ),
    )
    _add_checkpoint(ctx.rollback, "target_A")
    op = policy.next_action(ctx)
    assert op.action == Action.TERMINATE
    assert op.bailout is True


def test_bailout_counter_persists_across_commit() -> None:
    """COMMIT does NOT reset visit counters. Visits accumulate across commits
    so that global oscillation patterns (fail-pass-fail at same target) are
    detected."""
    config = DefaultPolicyConfig(
        bailout_visit_threshold=3,
        enable_feedback=False,
    )
    policy = DefaultPolicy(config)

    for _ in range(2):
        ctx = _ctx(
            prefix="bad;",
            last_action=Action.VERIFY,
            last_render_status=RenderStatus.OK,
            last_outputs=_fail_outputs(scope=Granularity.STMT),
        )
        _add_checkpoint(ctx.rollback, "target_A")
        policy.next_action(ctx)

    ctx = _ctx(
        prefix="good;",
        last_action=Action.COMMIT,
    )
    policy.next_action(ctx)

    ctx = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=Granularity.STMT),
    )
    _add_checkpoint(ctx.rollback, "target_A")
    op = policy.next_action(ctx)
    assert op.action == Action.TERMINATE
    assert op.bailout is True


def test_bailout_on_ping_pong() -> None:
    """Alternating STMT and BLOCK failures with the same diagnostic share a
    single bailout counter. The BLOCK failure counts toward the same error
    signature, so bailout triggers after 6 total failures (not 6 per-scope)."""
    config = DefaultPolicyConfig(
        bailout_visit_threshold=6,
        enable_feedback=False,
        stmt_stall_max_retries_before_escalation=100,
    )
    policy = DefaultPolicy(config)

    def _make_stmt_fail_ctx():
        c = _ctx(
            prefix="bad;",
            last_action=Action.VERIFY,
            last_render_status=RenderStatus.OK,
            last_outputs=_fail_outputs(scope=Granularity.STMT),
        )
        _add_checkpoint(c.rollback, "prefix_B")
        c.rollback.open_group(Granularity.FUNC)
        c.rollback.open_group(Granularity.BLOCK)
        _add_checkpoint(c.rollback, "prefix_A")
        return c

    def _make_block_fail_ctx():
        c = _ctx(
            prefix="bad;",
            last_action=Action.VERIFY,
            last_render_status=RenderStatus.OK,
            last_outputs=_fail_outputs(scope=Granularity.BLOCK),
        )
        _add_checkpoint(c.rollback, "prefix_B")
        c.rollback.open_group(Granularity.FUNC)
        c.rollback.open_group(Granularity.BLOCK)
        _add_checkpoint(c.rollback, "prefix_A")
        return c

    actions = []

    # 3 STMT + 1 BLOCK = 4 visits to same diagnostic key
    for _ in range(3):
        op = policy.next_action(_make_stmt_fail_ctx())
        actions.append(op.action)
        assert op.action == Action.ROLLBACK

    op = policy.next_action(_make_block_fail_ctx())
    actions.append(op.action)
    assert op.action == Action.ROLLBACK

    # 2 more STMT -> total 6 -> bailout on 6th
    for i in range(2):
        op = policy.next_action(_make_stmt_fail_ctx())
        actions.append(op.action)
        if i < 1:
            assert op.action == Action.ROLLBACK, f"cycle 2 iter {i}"
        else:
            assert op.action == Action.TERMINATE, "cycle 2 iter 1: expected bailout"
            assert op.bailout is True

    assert actions.count(Action.TERMINATE) == 1


def test_bailout_counter_survives_continue_between_rollbacks() -> None:
    """VERIFY with render_status=CONTINUE between rollbacks must NOT reset
    the bailout visit counter. This reproduces the real-world stuck pattern:
    rollback -> generate -> VERIFY(CONTINUE) -> generate -> VERIFY(FAIL) -> rollback.
    """
    config = DefaultPolicyConfig(
        bailout_visit_threshold=3,
        enable_feedback=False,
    )
    policy = DefaultPolicy(config)

    for i in range(3):
        # Simulate VERIFY -> CONTINUE (renderer says prefix incomplete).
        # This must NOT reset the bailout counter.
        ctx = _ctx(
            prefix="fn main() { let x = partial",
            last_action=Action.VERIFY,
            last_render_status=RenderStatus.CONTINUE,
        )
        op = policy.next_action(ctx)
        assert op.action == Action.CONTINUE or op.action == Action.TERMINATE

        # Simulate VERIFY -> FAIL (oracle rejects complete stmt).
        ctx = _ctx(
            prefix="fn main() { let x = bad;",
            last_action=Action.VERIFY,
            last_render_status=RenderStatus.OK,
            last_outputs=_fail_outputs(scope=Granularity.STMT),
        )
        _add_checkpoint(ctx.rollback, "fn main() { ")
        op = policy.next_action(ctx)
        if i < 2:
            assert op.action == Action.ROLLBACK, f"iteration {i}: expected ROLLBACK"
        else:
            assert op.action == Action.TERMINATE, f"iteration {i}: expected bailout"
            assert op.bailout is True


def test_bailout_counter_survives_commit() -> None:
    """COMMIT must NOT reset bailout visit counter. The model can oscillate:
    fail at target A several times, pass a small stmt (COMMIT), then fail
    at A again. The cumulative count should still trigger bailout.
    """
    config = DefaultPolicyConfig(
        bailout_visit_threshold=4,
        enable_feedback=False,
    )
    policy = DefaultPolicy(config)

    # 2 failures at target A
    for _ in range(2):
        ctx = _ctx(
            prefix="bad;",
            last_action=Action.VERIFY,
            last_render_status=RenderStatus.OK,
            last_outputs=_fail_outputs(scope=Granularity.STMT),
        )
        _add_checkpoint(ctx.rollback, "target_A")
        op = policy.next_action(ctx)
        assert op.action == Action.ROLLBACK

    # Model passes one stmt -> COMMIT
    ctx = _ctx(
        prefix="good;",
        last_action=Action.COMMIT,
    )
    policy.next_action(ctx)

    # 2 more failures at target A -> should reach threshold=4
    for i in range(2):
        ctx = _ctx(
            prefix="bad;",
            last_action=Action.VERIFY,
            last_render_status=RenderStatus.OK,
            last_outputs=_fail_outputs(scope=Granularity.STMT),
        )
        _add_checkpoint(ctx.rollback, "target_A")
        op = policy.next_action(ctx)
        if i < 1:
            assert op.action == Action.ROLLBACK, f"post-commit iter {i}"
        else:
            assert op.action == Action.TERMINATE, f"post-commit iter {i}: expected bailout"
            assert op.bailout is True


def _fail_outputs_with_code(
    *,
    error_code: str = "E0308",
    message: str = "mismatched types",
    scope: Granularity = Granularity.STMT,
) -> tuple[OracleOutput, ...]:
    return (
        OracleOutput(
            oracle_name="oracle_0",
            verdict=Verdict.FAIL,
            diagnostics=(
                Diagnostic(
                    message=message,
                    severity="error",
                    error_code=error_code,
                ),
            ),
            rollback_scope=scope,
        ),
    )


def test_bailout_accumulates_across_drifting_prefixes() -> None:
    """Same diagnostic (error_code + message) at different checkpoint prefixes
    should share a single stall counter, triggering bailout even though the
    exact checkpoint text changes each time.

    This reproduces the s988421966 pattern: the model keeps hitting E0308 in
    the same code region, but small committed changes shift the checkpoint,
    creating 'new' targets under prefix-based keying.
    """
    config = DefaultPolicyConfig(
        bailout_visit_threshold=3,
        enable_feedback=False,
    )
    policy = DefaultPolicy(config)

    drifting_prefixes = [
        "fn main() { let x = 1;",
        "fn main() { let x = 1; let y = 2;",
        "fn main() { let x = 1; let y = 2; let z = 3;",
    ]

    for i, checkpoint in enumerate(drifting_prefixes):
        ctx = _ctx(
            prefix=checkpoint + " bad_code;",
            last_action=Action.VERIFY,
            last_render_status=RenderStatus.OK,
            last_outputs=_fail_outputs_with_code(
                error_code="E0308",
                message="mismatched types",
            ),
        )
        _add_checkpoint(ctx.rollback, checkpoint)
        op = policy.next_action(ctx)
        if i < 2:
            assert op.action == Action.ROLLBACK, f"iter {i}: expected ROLLBACK"
        else:
            assert op.action == Action.TERMINATE, f"iter {i}: expected bailout"
            assert op.bailout is True


def test_different_errors_have_separate_stall_counts() -> None:
    """Different error codes at the same checkpoint should NOT share a stall
    counter. Two E0308 + two E0384 at threshold=3 should not trigger bailout
    because neither error alone reaches the threshold.
    """
    config = DefaultPolicyConfig(
        bailout_visit_threshold=3,
        enable_feedback=False,
    )
    policy = DefaultPolicy(config)

    errors = [
        ("E0308", "mismatched types"),
        ("E0384", "cannot assign to immutable"),
        ("E0308", "mismatched types"),
        ("E0384", "cannot assign to immutable"),
    ]

    for i, (code, msg) in enumerate(errors):
        ctx = _ctx(
            prefix="fn main() { let x = bad;",
            last_action=Action.VERIFY,
            last_render_status=RenderStatus.OK,
            last_outputs=_fail_outputs_with_code(error_code=code, message=msg),
        )
        _add_checkpoint(ctx.rollback, "fn main() { ")
        op = policy.next_action(ctx)
        assert op.action == Action.ROLLBACK, (
            f"iter {i} ({code}): expected ROLLBACK, got {op.action}"
        )
