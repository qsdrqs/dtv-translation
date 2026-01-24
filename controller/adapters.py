from __future__ import annotations

from collections.abc import Callable, Sequence

import transformers

from core.generator_backend import GeneratorBackend
from core.llm_output import FenceState, FenceTracker, RustFenceExtractor
from core.logger import get_logger
from core.qwen_generator_backend import QwenGeneratorBackend
from core.interfaces import Generator
from core.types import GenerateContext, GenerateResult, StopReason
from transformers import StoppingCriteria


logger = get_logger(__name__)


class GeneratorAdapter(Generator):
    def __init__(
        self,
        model_name: str,
        stop_criteria_factory: Callable[
            [transformers.PreTrainedTokenizerBase],
            Sequence[StoppingCriteria],
        ]
        | None = None,
        fence_tracker: FenceTracker | None = None,
        backend_cls: type[GeneratorBackend] = QwenGeneratorBackend,
    ) -> None:
        self.backend = backend_cls(
            model_name=model_name,
            stop_criteria_factory=stop_criteria_factory,
        )
        self._fence_tracker = fence_tracker
        self._fence_extractor = RustFenceExtractor() if fence_tracker is None else RustFenceExtractor()

    def reset_output_extractor(self) -> None:
        if self._fence_tracker is not None:
            self._fence_tracker.reset()
        self._fence_extractor.reset()

    def get_output_extractor_state(self) -> FenceState:
        return self._fence_extractor.state

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        logger.info(
            "generate_step: steps=%s extract_fence=%s max_new_length=%s",
            context.steps,
            context.extract_fence,
            context.max_new_length,
        )
        result = self.backend.generate_step(context)
        if not context.extract_fence:
            logger.info(
                "generate_step complete: delta_tokens=%s stop_reason=%s",
                result.delta_tokens,
                result.stop_reason.kind,
            )
            return result
        if context.steps == 0:
            if self._fence_tracker is not None:
                self._fence_tracker.reset()
            self._fence_extractor.reset()

        if self._fence_tracker is not None:
            extracted = self._fence_tracker.consume_inside()
            stop_reason = result.stop_reason
            if stop_reason.kind == "eos" and not self._fence_tracker.saw_fence:
                if not self._fence_extractor.warning_emitted:
                    logger.warning("No rust fenced block found in model output; terminating")
                    self._fence_extractor.mark_warning_emitted()
                stop_reason = StopReason(kind="no_fence_eos", detail="")
            logger.info(
                "generate_step complete: delta_tokens=%s stop_reason=%s extracted_chars=%s",
                result.delta_tokens,
                stop_reason.kind,
                len(extracted),
            )
            return GenerateResult(
                delta_text=extracted,
                delta_tokens=result.delta_tokens,
                stop_reason=stop_reason,
            )

        # Keep calling the backend until we extract fenced code or hit a terminal condition.
        total_tokens = 0
        stop_reason = result.stop_reason
        extracted = ""
        remaining = context.max_new_length

        while True:
            total_tokens += result.delta_tokens
            stop_reason = result.stop_reason
            extracted_piece = ""
            logger.debug(
                "backend step: delta_tokens=%s stop_reason=%s fence_state=%s saw_fence=%s",
                result.delta_tokens,
                stop_reason.kind,
                self._fence_extractor.state,
                self._fence_extractor.saw_fence,
            )
            if result.delta_text:
                extracted_piece = self._fence_extractor.feed(result.delta_text)
            if extracted_piece:
                logger.debug(
                    "fence extracted: chars=%s state=%s",
                    len(extracted_piece),
                    self._fence_extractor.state,
                )
                extracted = extracted_piece
                break
            # Nothing new to process or nothing left to emit from the extractor.
            if not result.delta_text:
                break
            if self._fence_extractor.state == FenceState.DONE:
                break
            if stop_reason.kind == "eos":
                if not self._fence_extractor.saw_fence:
                    if not self._fence_extractor.warning_emitted:
                        logger.warning("No rust fenced block found in model output; terminating")
                        self._fence_extractor.mark_warning_emitted()
                    stop_reason = StopReason(kind="no_fence_eos", detail="")
                break
            if result.delta_tokens <= 0:
                break
            # Consume remaining budget locally to avoid exceeding the caller's max_new_length.
            remaining = max(0, remaining - result.delta_tokens)
            context.max_new_length = remaining
            if remaining <= 0:
                logger.info("generation halted: remaining token budget exhausted")
                break
            result = self.backend.generate_step(context)

        logger.info(
            "generate_step complete: delta_tokens=%s stop_reason=%s extracted_chars=%s",
            total_tokens,
            stop_reason.kind,
            len(extracted),
        )
        return GenerateResult(
            delta_text=extracted,
            delta_tokens=total_tokens,
            stop_reason=stop_reason,
        )
