from __future__ import annotations

from controller.adapters import GeneratorAdapter
from controller.loop import run_dtv_loop
from controller.stop_criteria import DTVStoppingCriteria, RUST_PROFILE
from core.budget import Budget
from core.types import Artifact, Granularity, RenderResult, RenderStatus
from feedback.feedback import FeedbackState
from rollback.manager import RollbackManager


class DummyRenderer:
    def try_render(self, prefix, granularity):
        return RenderResult(
            status=RenderStatus.OK,
            artifact=Artifact(code=prefix, granularity=granularity or Granularity.STMT),
        )


def main() -> None:
    def stop_factory(tokenizer):
        return [DTVStoppingCriteria(tokenizer, RUST_PROFILE)]

    generator = GeneratorAdapter(
        model_name="Qwen/Qwen3-4B-Instruct-2507",
        stop_criteria_factory=stop_factory,
    )
    budget = Budget(gen_tokens_budget=512)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()

    run_dtv_loop(
        generator=generator,
        renderer=DummyRenderer(),
        oracles=[],
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        max_steps=5,
        prompt_prefix="",
    )


if __name__ == "__main__":
    main()
