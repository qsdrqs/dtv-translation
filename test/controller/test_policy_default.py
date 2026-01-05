from __future__ import annotations

from controller.loop import PolicyContext
from controller.policy import DefaultPolicy, DefaultPolicyConfig
from core.budget import Budget
from core.types import (
    Action,
    Artifact,
    ControllerState,
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
        failed_prefix=None,
        pending_patch=None,
        repair_base_prefix=None,
    )


def _outputs(*verdicts: Verdict) -> tuple[OracleOutput, ...]:
    return tuple(
        OracleOutput(oracle_name=f"oracle_{idx}", verdict=verdict)
        for idx, verdict in enumerate(verdicts)
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
    artifact = Artifact(code="let x = 1;", granularity=Granularity.STMT)
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
    assert op.granularity == Granularity.STMT


def test_default_policy_eos_uses_program_granularity() -> None:
    policy = DefaultPolicy()
    ctx = _ctx(
        prefix="fn main() {}",
        last_action=Action.GENERATE,
        last_stop_reason=StopReason(kind="eos"),
    )
    op = policy.next_action(ctx)
    assert op.action == Action.VERIFY
    assert op.granularity == Granularity.PROGRAM


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
