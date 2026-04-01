from __future__ import annotations

from c_rust.feedback import RUST_FEEDBACK_LANG
from controller.adapters import GeneratorAdapter
from controller.loop import ControllerOp, run_dtv_loop, select_oracles_by_granularity
from controller.policy import DefaultPolicy
from controller.stop_criteria import DTVStoppingCriteria, RUST_PROFILE
from core.llm_output import FenceParser
from core.budget import Budget
from core.types import Action, Artifact, Granularity, RenderResult, RenderStatus, Verdict
from feedback.feedback import FeedbackState
from rollback.manager import RollbackManager


class DummyRenderer:
    def try_render(self, prefix):
        return RenderResult(
            status=RenderStatus.OK,
            artifact=Artifact(code=prefix),
        )


class DemoPolicy:
    def next_action(self, ctx) -> ControllerOp:
        if ctx.last_action is None:
            return ControllerOp(Action.GENERATE)
        if ctx.last_action == Action.GENERATE:
            return ControllerOp(Action.VERIFY, verification_granularity=Granularity.STMT)
        if ctx.last_action == Action.VERIFY:
            if any(out.verdict == Verdict.FAIL for out in ctx.last_outputs):
                return ControllerOp(Action.ROLLBACK, rollback_scope=Granularity.STMT)
            if ctx.last_outputs and all(out.verdict == Verdict.PASS for out in ctx.last_outputs):
                return ControllerOp(Action.COMMIT)
            return ControllerOp(Action.CONTINUE)
        if ctx.last_action == Action.CONTINUE:
            return ControllerOp(Action.GENERATE)
        return ControllerOp(Action.TERMINATE)

    def select_oracles(self, artifact, budget, available, *, selection_granularity=None):
        if selection_granularity is None:
            raise ValueError("selection_granularity is required")
        return select_oracles_by_granularity(
            artifact,
            budget,
            available,
            selection_granularity=selection_granularity,
        )


def main() -> None:
    fence_parser = FenceParser(allowed_langs=("rust", "rs"))

    def stop_factory(tokenizer):
        return [DTVStoppingCriteria(tokenizer, RUST_PROFILE, fence_parser=fence_parser)]

    generator = GeneratorAdapter(
        model_name="Qwen/Qwen3-4B-Instruct-2507",
        stop_criteria_factory=stop_factory,
        fence_parser=fence_parser,
    )
    budget = Budget(gen_tokens_budget=512)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = DefaultPolicy()

    run_dtv_loop(
        generator=generator,
        renderer=DummyRenderer(),
        oracles=[],
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=5,
        prompt_prefix="",
    )


if __name__ == "__main__":
    main()
