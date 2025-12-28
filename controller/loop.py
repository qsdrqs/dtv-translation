from __future__ import annotations
from dataclasses import dataclass

from core.budget import Budget
from core.interfaces import Generator, Oracle, OracleRunner, Renderer
from core.types import (
    Action,
    Artifact,
    ControllerState,
    GenerateContext,
    GenerateMessage,
    Granularity,
    OracleOutput,
    RollbackScope,
    StopReason,
    TraceEvent,
)
from feedback.strategies import AppendToLastAssistant, FeedbackStrategy
from feedback.feedback import FeedbackState
from rollback.manager import RollbackManager


@dataclass
class Policy:
    def choose_granularity(self, stop_reason: StopReason) -> Granularity:
        return Granularity.STMT

    def on_render_fail(self, stop_reason: StopReason, retries: int) -> Action:
        if retries >= 2:
            return Action.ROLLBACK
        return Action.CONTINUE

    def select_oracles(self, artifact: Artifact, budget: Budget, available: list[Oracle]) -> list[Oracle]:
        # TODO: consider required_granularity and per-oracle budgets.
        return [o for o in available if o.required_granularity == artifact.granularity]

    def act(
        self,
        outputs: list[OracleOutput],
        budget: Budget,
        rollback: RollbackManager,
    ) -> Action:
        if outputs and all(out.passed for out in outputs):
            return Action.COMMIT
        if outputs and any(not out.passed for out in outputs):
            return Action.ROLLBACK
        return Action.COMMIT # Default to commit if no oracles were run.


class DummyOracleRunner:
    def run(self, oracles: list[Oracle], state: ControllerState, artifact: Artifact) -> list[OracleOutput]:
        outputs: list[OracleOutput] = []
        for oracle in oracles:
            outputs.append(oracle.run(state, artifact))
        return outputs

def update_last_assistant(messages: list[GenerateMessage], content: str) -> None:
    for idx in range(len(messages) - 1, -1, -1):
        if messages[idx].role == "assistant":
            messages[idx] = GenerateMessage(
                role="assistant",
                content=content,
                stop=messages[idx].stop,
            )
            return
    messages.append(GenerateMessage(role="assistant", content=content))

def run_dtv_loop(
    generator: Generator,
    renderer: Renderer,
    oracles: list[Oracle],
    budget: Budget,
    feedback_state: FeedbackState,
    rollback_manager: RollbackManager,
    feedback_strategy: FeedbackStrategy | None = None,
    policy: Policy | None = None,
    max_steps: int = 100,
    max_new_length: int = 1024,
    prompt_prefix: str = "",
    oracle_runner: OracleRunner | None = None,
) -> tuple[str, list[TraceEvent]]:
    if policy is None:
        policy = Policy()
    if feedback_strategy is None:
        feedback_strategy = AppendToLastAssistant()
    if oracle_runner is None:
        oracle_runner = DummyOracleRunner()
    state = ControllerState(prefix="")
    trace: list[TraceEvent] = []
    base_messages: list[GenerateMessage] = []
    if prompt_prefix:
        base_messages.append(GenerateMessage(role="user", content=prompt_prefix, stop=True))
    base_messages.append(GenerateMessage(role="assistant", content=""))
    context = GenerateContext(messages=base_messages, steps=0, max_new_length=max_new_length)


    while state.step < max_steps and budget.can_spend_tokens(1):
        remaining = budget.gen_tokens_budget - budget.gen_tokens_used
        context.steps = state.step
        context.max_new_length = min(max_new_length, max(0, remaining))
        update_last_assistant(base_messages, state.prefix)
        feedback = feedback_state.encode()
        context.messages = feedback_strategy.apply(base_messages, feedback, state.prefix)

        result = generator.generate_step(context)
        state.prefix += result.delta_text
        budget.add_tokens(result.delta_tokens)

        update_last_assistant(base_messages, state.prefix)
        context.messages = base_messages
        stop_reason = result.stop_reason

        granularity = policy.choose_granularity(stop_reason)
        artifact = renderer.try_render(state.prefix, granularity)
        if artifact is None:
            retries = rollback_manager.record_retry(f"render_fail:{granularity.value}")
            action = policy.on_render_fail(stop_reason, retries)
            if action == Action.ROLLBACK:
                state.prefix = rollback_manager.rollback(RollbackScope.STMT)
            trace.append(
                TraceEvent(
                    step=state.step,
                    stop_reason=stop_reason,
                    action=action,
                    granularity=granularity,
                    budget_snapshot=budget.snapshot(),
                    notes="render failed",
                )
            )
            state.step += 1
            continue

        selected_oracles = policy.select_oracles(artifact, budget, oracles)
        outputs = oracle_runner.run(selected_oracles, state, artifact)
        for output in outputs:
            budget.record_oracle_call(output.oracle_name, output.realized_cost)
        feedback_state.update(outputs)

        action = policy.act(outputs, budget, rollback_manager)
        if action == Action.COMMIT:
            # Group events are interpreted as happening within the current stmt,
            # so apply them before committing the stmt checkpoint to avoid
            # off-by-one group starts.
            rollback_manager.apply_group_events(artifact.group_events)
            rollback_manager.add_stmt_checkpoint(state.prefix)
        elif action == Action.ROLLBACK:
            state.prefix = rollback_manager.rollback(RollbackScope.STMT)
        elif action == Action.TERMINATE:
            trace.append(
                TraceEvent(
                    step=state.step,
                    stop_reason=stop_reason,
                    action=action,
                    granularity=granularity,
                    budget_snapshot=budget.snapshot(),
                    oracle_outputs=tuple(outputs),
                )
            )
            break

        trace.append(
            TraceEvent(
                step=state.step,
                stop_reason=stop_reason,
                action=action,
                granularity=granularity,
                budget_snapshot=budget.snapshot(),
                oracle_outputs=tuple(outputs),
            )
        )
        state.step += 1

    return state.prefix, trace
