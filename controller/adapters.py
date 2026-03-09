from __future__ import annotations

from collections.abc import Callable, Sequence

import transformers

from core.generator_backend import GeneratorBackend
from core.llm_output import (
    AssistantContent,
    FenceParser,
    FenceParserSnapshot,
    FenceState,
    OutputExtractorState,
    merge_assistant_content,
)
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
        fence_parser: FenceParser | None = None,
        backend_cls: type[GeneratorBackend] = QwenGeneratorBackend,
        do_sample: bool | None = None,
        temperature: float | None = None,
    ) -> None:
        self.backend = backend_cls(
            model_name=model_name,
            stop_criteria_factory=stop_criteria_factory,
            do_sample=do_sample,
            temperature=temperature,
        )
        self._fence_parser = fence_parser
        allowed_langs = fence_parser.allowed_langs if fence_parser is not None else ("rust", "rs")
        self._segment_parser = FenceParser(allowed_langs=allowed_langs)
        self._extract_parser = FenceParser(allowed_langs=allowed_langs)
        self._warning_emitted = False

    def reset_output_extractor(self) -> None:
        if self._fence_parser is not None:
            self._fence_parser.reset()
        self._segment_parser.reset()
        self._extract_parser.reset()
        self._warning_emitted = False

    def get_output_extractor_state(self) -> FenceState:
        if self._fence_parser is not None:
            return self._fence_parser.state
        return self._extract_parser.state

    def capture_output_extractor_state(self) -> OutputExtractorState:
        shared_snapshot = self._fence_parser.capture() if self._fence_parser is not None else None
        return OutputExtractorState(
            segment=self._segment_parser.capture(),
            extract=self._extract_parser.capture(),
            shared=shared_snapshot,
            warning_emitted=self._warning_emitted,
        )

    def restore_output_extractor_state(self, state: OutputExtractorState) -> None:
        self._segment_parser.restore(state.segment)
        self._extract_parser.restore(state.extract)
        if self._fence_parser is not None:
            shared_state = state.shared
            if shared_state is None:
                shared_state = FenceParserSnapshot(
                    state=state.extract.state,
                    saw_fence=state.extract.saw_fence,
                    buffer=state.extract.buffer,
                    inside_parts=state.extract.inside_parts,
                )
            self._fence_parser.restore(shared_state)
        self._warning_emitted = state.warning_emitted

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        logger.info(
            "generate_step: steps=%s extract_fence=%s max_new_length=%s",
            context.steps,
            context.extract_fence,
            context.max_new_length,
        )
        if context.steps == 0:
            if self._fence_parser is not None:
                self._fence_parser.reset()
            self._segment_parser.reset()
            self._extract_parser.reset()
            self._warning_emitted = False
        self.backend.set_generation_channel(context.channel)
        result = self.backend.generate_step(context)
        if not context.extract_fence:
            assistant_delta = AssistantContent.from_unfenced(result.delta_text)
            logger.info(
                "generate_step complete: delta_tokens=%s stop_reason=%s",
                result.delta_tokens,
                result.stop_reason.kind,
            )
            return GenerateResult(
                delta_text=result.delta_text,
                delta_tokens=result.delta_tokens,
                stop_reason=result.stop_reason,
                assistant_delta=assistant_delta,
            )

        assistant_accum = self._segment_parser.feed(result.delta_text)
        if self._fence_parser is not None:
            if result.stop_reason.kind == "eos":
                self._fence_parser.flush()
            extracted = self._fence_parser.consume_inside()
            stop_reason = result.stop_reason
            if stop_reason.kind == "eos" and not self._fence_parser.saw_fence:
                if not self._warning_emitted:
                    logger.warning("No rust fenced block found in model output; terminating")
                    self._warning_emitted = True
                stop_reason = StopReason(kind="no_fence_eos", detail="")
            assistant_accum = assistant_accum.with_code(extracted)
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
                assistant_delta=assistant_accum,
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
                self._extract_parser.state,
                self._extract_parser.saw_fence,
            )
            if result.delta_text:
                self._extract_parser.feed(result.delta_text)
                extracted_piece = self._extract_parser.consume_inside()
            if extracted_piece:
                logger.debug(
                    "fence extracted: chars=%s state=%s",
                    len(extracted_piece),
                    self._extract_parser.state,
                )
                extracted = extracted_piece
                break
            # Nothing new to process or nothing left to emit from the extractor.
            if not result.delta_text:
                break
            if self._extract_parser.state == FenceState.DONE:
                break
            if stop_reason.kind == "eos":
                if not self._extract_parser.saw_fence:
                    if not self._warning_emitted:
                        logger.warning("No rust fenced block found in model output; terminating")
                        self._warning_emitted = True
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
            assistant_delta = self._segment_parser.feed(result.delta_text)
            assistant_accum = merge_assistant_content(assistant_accum, assistant_delta)

        if not extracted:
            extracted = self._extract_parser.consume_inside()

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
            assistant_delta=assistant_accum.with_code(extracted),
        )
