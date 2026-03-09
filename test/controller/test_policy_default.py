from __future__ import annotations

from controller.loop import PolicyContext, run_dtv_loop
from controller.policy import DefaultPolicy, DefaultPolicyConfig
from core.budget import Budget
from core.llm_output import AssistantContent, FenceParser, FenceState, OutputExtractorState
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
    RollbackScope,
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
    repair_scope: RollbackScope | None = None,
    fence_state: FenceState = FenceState.DONE,
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
        fence_state=fence_state,
    )


def _outputs(*verdicts: Verdict) -> tuple[OracleOutput, ...]:
    return tuple(
        OracleOutput(oracle_name=f"oracle_{idx}", verdict=verdict)
        for idx, verdict in enumerate(verdicts)
    )


def _fail_outputs(*, scope: RollbackScope = RollbackScope.STMT) -> tuple[OracleOutput, ...]:
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
    rollback_scope = RollbackScope.STMT

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


class _EscalationFenceReopenGenerator:
    def __init__(self) -> None:
        self._parser = FenceParser(allowed_langs=("rust", "rs"))
        self._did_generate = False
        self.feedback_mechanisms: list[FeedbackMechanism] = []

    def reset_output_extractor(self) -> None:
        self._parser.reset()

    def get_output_extractor_state(self) -> FenceState:
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
            self._parser.feed("```rust\n")
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
                    fence_lang="rust",
                    code="bad;",
                    fence_state=FenceState.INSIDE,
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
    policy = DefaultPolicy(DefaultPolicyConfig(enable_rollback=True, default_fail_scope=RollbackScope.STMT))
    ctx = _ctx(
        prefix="let x = 1;",
        last_action=Action.VERIFY,
        last_stop_reason=StopReason(kind="boundary"),
        last_render_status=RenderStatus.OK,
        last_outputs=_outputs(Verdict.FAIL),
    )
    op = policy.next_action(ctx)
    assert op.action == Action.ROLLBACK
    assert op.rollback_scope == RollbackScope.STMT


def test_default_policy_stmt_stall_escalates_to_block_after_retry_budget() -> None:
    policy = DefaultPolicy(
        DefaultPolicyConfig(
            enable_rollback=True,
            default_fail_scope=RollbackScope.STMT,
            stmt_stall_max_retries_before_escalation=3,
        )
    )

    for _ in range(3):
        ctx = _ctx(
            prefix="bad;",
            last_action=Action.VERIFY,
            last_render_status=RenderStatus.OK,
            last_outputs=_fail_outputs(scope=RollbackScope.STMT),
        )
        ctx.rollback.open_group(Granularity.FUNC)
        ctx.rollback.open_group(Granularity.BLOCK)
        op = policy.next_action(ctx)
        assert op.action == Action.ROLLBACK
        assert op.rollback_scope == RollbackScope.STMT

    ctx = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=RollbackScope.STMT),
    )
    ctx.rollback.open_group(Granularity.FUNC)
    ctx.rollback.open_group(Granularity.BLOCK)
    op = policy.next_action(ctx)

    assert op.action == Action.ROLLBACK
    assert op.rollback_scope == RollbackScope.BLOCK


def test_default_policy_stmt_stall_escalates_to_func_without_active_block() -> None:
    policy = DefaultPolicy(
        DefaultPolicyConfig(
            enable_rollback=True,
            default_fail_scope=RollbackScope.STMT,
            stmt_stall_max_retries_before_escalation=3,
        )
    )

    for _ in range(3):
        ctx = _ctx(
            prefix="bad;",
            last_action=Action.VERIFY,
            last_render_status=RenderStatus.OK,
            last_outputs=_fail_outputs(scope=RollbackScope.STMT),
        )
        ctx.rollback.open_group(Granularity.FUNC)
        op = policy.next_action(ctx)
        assert op.action == Action.ROLLBACK
        assert op.rollback_scope == RollbackScope.STMT

    ctx = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=RollbackScope.STMT),
    )
    ctx.rollback.open_group(Granularity.FUNC)
    op = policy.next_action(ctx)

    assert op.action == Action.ROLLBACK
    assert op.rollback_scope == RollbackScope.FUNC


def test_default_policy_stmt_stall_counter_resets_after_pass() -> None:
    policy = DefaultPolicy(
        DefaultPolicyConfig(
            enable_rollback=True,
            default_fail_scope=RollbackScope.STMT,
            stmt_stall_max_retries_before_escalation=1,
        )
    )

    first_fail = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=RollbackScope.STMT),
    )
    first_fail.rollback.open_group(Granularity.FUNC)
    first_fail.rollback.open_group(Granularity.BLOCK)
    first_op = policy.next_action(first_fail)
    assert first_op.action == Action.ROLLBACK
    assert first_op.rollback_scope == RollbackScope.STMT

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
        last_outputs=_fail_outputs(scope=RollbackScope.STMT),
    )
    second_fail.rollback.open_group(Granularity.FUNC)
    second_fail.rollback.open_group(Granularity.BLOCK)
    second_op = policy.next_action(second_fail)
    assert second_op.action == Action.ROLLBACK
    assert second_op.rollback_scope == RollbackScope.STMT


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


def test_default_policy_eos_uses_program_granularity() -> None:
    policy = DefaultPolicy()
    ctx = _ctx(
        prefix="fn main() {}",
        last_action=Action.GENERATE,
        last_stop_reason=StopReason(kind="eos"),
    )
    op = policy.next_action(ctx)
    assert op.action == Action.VERIFY
    assert op.verification_granularity == Granularity.PROGRAM


def test_default_policy_continue_then_generate() -> None:
    policy = DefaultPolicy()
    ctx = _ctx(
        prefix="let x = 1;",
        last_action=Action.CONTINUE,
        last_stop_reason=StopReason(kind="boundary"),
    )
    op = policy.next_action(ctx)
    assert op.action == Action.GENERATE


def test_eos_with_fence_inside_does_not_terminate() -> None:
    """When stop_reason=eos but fence is still INSIDE, _is_eos() returns False.
    After COMMIT the policy should GENERATE (not TERMINATE), because the fence
    was never closed - the model's EOS is premature."""
    policy = DefaultPolicy(DefaultPolicyConfig(terminate_on_eos_and_pass=True))
    ctx = _ctx(
        last_action=Action.COMMIT,
        last_stop_reason=StopReason(kind="eos"),
        last_outputs=_outputs(Verdict.PASS),
        fence_state=FenceState.INSIDE,
    )
    op = policy.next_action(ctx)
    assert op.action == Action.GENERATE


def test_eos_with_fence_inside_does_not_verify_program() -> None:
    """When stop_reason=eos but fence is still INSIDE, verification should use
    boundary granularity (STMT), not EOS granularity (PROGRAM).
    The prefix ends with ';' so is_boundary=True, but _is_eos()=False."""
    policy = DefaultPolicy()
    ctx = _ctx(
        prefix="let x = 1;",
        last_action=Action.GENERATE,
        last_stop_reason=StopReason(kind="eos"),
        fence_state=FenceState.INSIDE,
    )
    op = policy.next_action(ctx)
    assert op.action == Action.VERIFY
    assert op.verification_granularity == Granularity.STMT


def test_default_policy_eos_pass_commits_then_terminates() -> None:
    policy = DefaultPolicy(DefaultPolicyConfig(terminate_on_eos_and_pass=True))
    outputs = _outputs(Verdict.PASS)
    ctx_verify = _ctx(
        prefix="fn main() {}",
        last_action=Action.VERIFY,
        last_stop_reason=StopReason(kind="eos"),
        last_render_status=RenderStatus.OK,
        last_outputs=outputs,
    )
    op = policy.next_action(ctx_verify)
    assert op.action == Action.COMMIT

    ctx_commit = _ctx(
        prefix="fn main() {}",
        last_action=Action.COMMIT,
        last_stop_reason=StopReason(kind="eos"),
        last_render_status=RenderStatus.OK,
        last_outputs=outputs,
    )
    op = policy.next_action(ctx_commit)
    assert op.action == Action.TERMINATE


def test_default_policy_eos_no_oracles_commits_then_terminates() -> None:
    policy = DefaultPolicy(DefaultPolicyConfig(terminate_on_eos_and_pass=True))
    ctx_verify = _ctx(
        prefix="fn main() {}",
        last_action=Action.VERIFY,
        last_stop_reason=StopReason(kind="eos"),
        last_render_status=RenderStatus.OK,
        last_outputs=(),
    )
    op = policy.next_action(ctx_verify)
    assert op.action == Action.COMMIT

    ctx_commit = _ctx(
        prefix="fn main() {}",
        last_action=Action.COMMIT,
        last_stop_reason=StopReason(kind="eos"),
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
        repair_scope=RollbackScope.STMT,
    )

    op = policy.next_action(ctx)

    assert op.action == Action.FEEDBACK
    assert op.feedback_mechanism == FeedbackMechanism.A


def test_default_policy_feedback_escalates_to_mechanism_b_after_no_progress() -> None:
    policy = DefaultPolicy(DefaultPolicyConfig(max_repair_rounds=4))
    generator = _EscalationFenceReopenGenerator()

    # Given repeated failures in one repair key.
    # When repair attempts make no progress.
    # Then policy escalates from A to B.
    run_dtv_loop(
        generator=generator,
        renderer=_AlwaysOkRenderer(),
        oracles=[_AlwaysFailOracle()],
        budget=Budget(gen_tokens_budget=32),
        feedback_state=FeedbackState(),
        rollback_manager=RollbackManager(),
        policy=policy,
        max_steps=16,
    )

    assert generator.feedback_mechanisms[:2] == [FeedbackMechanism.A, FeedbackMechanism.B]


def test_default_policy_feedback_stays_on_b_per_key_by_default() -> None:
    policy = DefaultPolicy(DefaultPolicyConfig(max_repair_rounds=4))

    first_verify_fail_ctx = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=RollbackScope.STMT),
    )
    first_rollback_op = policy.next_action(first_verify_fail_ctx)
    assert first_rollback_op.action == Action.ROLLBACK

    first_feedback_ctx = _ctx(
        prefix="",
        last_action=Action.ROLLBACK,
        failed_prefix="bad;",
        repair_base_prefix="",
        repair_scope=RollbackScope.STMT,
    )
    first_feedback_op = policy.next_action(first_feedback_ctx)
    assert first_feedback_op.action == Action.FEEDBACK
    assert first_feedback_op.feedback_mechanism == FeedbackMechanism.A

    second_verify_fail_ctx = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=RollbackScope.STMT),
    )
    second_rollback_op = policy.next_action(second_verify_fail_ctx)
    assert second_rollback_op.action == Action.ROLLBACK

    second_feedback_ctx = _ctx(
        prefix="",
        last_action=Action.ROLLBACK,
        failed_prefix="bad;",
        repair_base_prefix="",
        repair_scope=RollbackScope.STMT,
    )
    second_feedback_op = policy.next_action(second_feedback_ctx)
    assert second_feedback_op.action == Action.FEEDBACK
    assert second_feedback_op.feedback_mechanism == FeedbackMechanism.B

    third_verify_fail_ctx = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=RollbackScope.STMT),
    )
    third_rollback_op = policy.next_action(third_verify_fail_ctx)
    assert third_rollback_op.action == Action.ROLLBACK

    third_feedback_ctx = _ctx(
        prefix="",
        last_action=Action.ROLLBACK,
        failed_prefix="bad;",
        repair_base_prefix="",
        repair_scope=RollbackScope.STMT,
    )
    third_feedback_op = policy.next_action(third_feedback_ctx)
    assert third_feedback_op.action == Action.FEEDBACK
    assert third_feedback_op.feedback_mechanism == FeedbackMechanism.B


    new_key_verify_fail_ctx = _ctx(
        prefix="bad2;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=RollbackScope.STMT),
    )
    new_key_rollback_op = policy.next_action(new_key_verify_fail_ctx)
    assert new_key_rollback_op.action == Action.ROLLBACK

    new_key_feedback_ctx = _ctx(
        prefix="",
        last_action=Action.ROLLBACK,
        failed_prefix="bad2;",
        repair_base_prefix="anchor2",
        repair_scope=RollbackScope.STMT,
    )
    new_key_feedback_op = policy.next_action(new_key_feedback_ctx)
    assert new_key_feedback_op.action == Action.FEEDBACK
    assert new_key_feedback_op.feedback_mechanism == FeedbackMechanism.A


def test_default_policy_feedback_terminates_when_b_cap_is_reached() -> None:
    policy = DefaultPolicy(
        DefaultPolicyConfig(
            max_repair_rounds=4,
            feedback_max_b_rounds_per_key=1,
        )
    )

    first_verify_fail_ctx = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=RollbackScope.STMT),
    )
    first_rollback_op = policy.next_action(first_verify_fail_ctx)
    assert first_rollback_op.action == Action.ROLLBACK

    first_feedback_ctx = _ctx(
        prefix="",
        last_action=Action.ROLLBACK,
        failed_prefix="bad;",
        repair_base_prefix="",
        repair_scope=RollbackScope.STMT,
    )
    first_feedback_op = policy.next_action(first_feedback_ctx)
    assert first_feedback_op.action == Action.FEEDBACK
    assert first_feedback_op.feedback_mechanism == FeedbackMechanism.A

    second_verify_fail_ctx = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=RollbackScope.STMT),
    )
    second_rollback_op = policy.next_action(second_verify_fail_ctx)
    assert second_rollback_op.action == Action.ROLLBACK

    second_feedback_ctx = _ctx(
        prefix="",
        last_action=Action.ROLLBACK,
        failed_prefix="bad;",
        repair_base_prefix="",
        repair_scope=RollbackScope.STMT,
    )
    second_feedback_op = policy.next_action(second_feedback_ctx)
    assert second_feedback_op.action == Action.FEEDBACK
    assert second_feedback_op.feedback_mechanism == FeedbackMechanism.B

    third_verify_fail_ctx = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=RollbackScope.STMT),
    )
    third_rollback_op = policy.next_action(third_verify_fail_ctx)
    assert third_rollback_op.action == Action.ROLLBACK

    third_feedback_ctx = _ctx(
        prefix="",
        last_action=Action.ROLLBACK,
        failed_prefix="bad;",
        repair_base_prefix="",
        repair_scope=RollbackScope.STMT,
    )
    third_feedback_op = policy.next_action(third_feedback_ctx)
    assert third_feedback_op.action == Action.TERMINATE


def test_default_policy_program_scope_escalates_to_b_even_when_failed_prefix_changes() -> None:
    policy = DefaultPolicy(DefaultPolicyConfig(max_repair_rounds=4))

    first_verify_fail_ctx = _ctx(
        prefix="program_fail_v1",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=RollbackScope.PROGRAM),
    )
    first_rollback_op = policy.next_action(first_verify_fail_ctx)
    assert first_rollback_op.action == Action.ROLLBACK

    first_feedback_ctx = _ctx(
        prefix="",
        last_action=Action.ROLLBACK,
        failed_prefix="program_fail_v1",
        repair_base_prefix="",
        repair_scope=RollbackScope.PROGRAM,
    )
    first_feedback_op = policy.next_action(first_feedback_ctx)
    assert first_feedback_op.action == Action.FEEDBACK
    assert first_feedback_op.feedback_mechanism == FeedbackMechanism.A

    second_verify_fail_ctx = _ctx(
        prefix="program_fail_v2",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=RollbackScope.PROGRAM),
    )
    second_rollback_op = policy.next_action(second_verify_fail_ctx)
    assert second_rollback_op.action == Action.ROLLBACK

    second_feedback_ctx = _ctx(
        prefix="",
        last_action=Action.ROLLBACK,
        failed_prefix="program_fail_v2",
        repair_base_prefix="",
        repair_scope=RollbackScope.PROGRAM,
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
        repair_scope=RollbackScope.STMT,
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
        last_outputs=_fail_outputs(scope=RollbackScope.STMT),
    )
    rollback_op = policy.next_action(verify_fail_ctx)
    assert rollback_op.action == Action.ROLLBACK
    assert rollback_op.rollback_scope == RollbackScope.STMT

    # After ROLLBACK -> first FEEDBACK(B) (b_no_patch not incremented; last_action=ROLLBACK)
    after_rollback_ctx = _ctx(
        prefix="",
        last_action=Action.ROLLBACK,
        failed_prefix="bad;",
        repair_base_prefix="",
        repair_scope=RollbackScope.STMT,
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
            repair_scope=RollbackScope.STMT,
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
        repair_scope=RollbackScope.STMT,
    )
    escalation_op = policy.next_action(final_no_patch_ctx)
    assert escalation_op.action == Action.ROLLBACK
    assert escalation_op.rollback_scope == RollbackScope.STMT
