from __future__ import annotations

from controller.loop import PolicyContext
from controller.policy import DefaultPolicy, DefaultPolicyConfig
from core.budget import Budget
from core.types import (
    Action,
    Artifact,
    ControllerState,
    Diagnostic,
    FeedbackMechanism,
    Granularity,
    OracleOutput,
    RenderStatus,
    RollbackScope,
    StopReason,
    Verdict,
)
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
    )

    op = policy.next_action(ctx)

    assert op.action == Action.FEEDBACK
    assert op.feedback_mechanism == FeedbackMechanism.A


def test_default_policy_feedback_escalates_to_mechanism_b_after_no_progress() -> None:
    policy = DefaultPolicy(DefaultPolicyConfig(max_repair_rounds=4))

    initial_verify_fail_ctx = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=RollbackScope.STMT),
    )
    initial_rollback_op = policy.next_action(initial_verify_fail_ctx)
    assert initial_rollback_op.action == Action.ROLLBACK

    first_feedback_ctx = _ctx(
        prefix="bad;",
        last_action=Action.ROLLBACK,
        failed_prefix="bad;",
        repair_base_prefix="",
    )
    first_op = policy.next_action(first_feedback_ctx)
    assert first_op.action == Action.FEEDBACK
    assert first_op.feedback_mechanism == FeedbackMechanism.A

    retry_verify_fail_ctx = _ctx(
        prefix="bad;",
        last_action=Action.VERIFY,
        last_render_status=RenderStatus.OK,
        last_outputs=_fail_outputs(scope=RollbackScope.STMT),
    )
    rollback_op = policy.next_action(retry_verify_fail_ctx)
    assert rollback_op.action == Action.ROLLBACK

    second_feedback_ctx = _ctx(
        prefix="",
        last_action=Action.ROLLBACK,
        failed_prefix="bad;",
        repair_base_prefix="",
    )
    second_op = policy.next_action(second_feedback_ctx)

    assert second_op.action == Action.FEEDBACK
    assert second_op.feedback_mechanism == FeedbackMechanism.B


def test_default_policy_feedback_force_mechanism_b() -> None:
    policy = DefaultPolicy(DefaultPolicyConfig(feedback_force_mechanism=FeedbackMechanism.B))
    ctx = _ctx(
        prefix="bad;",
        last_action=Action.ROLLBACK,
        failed_prefix="bad;",
        repair_base_prefix="",
    )

    op = policy.next_action(ctx)

    assert op.action == Action.FEEDBACK
    assert op.feedback_mechanism == FeedbackMechanism.B
