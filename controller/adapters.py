from __future__ import annotations

from collections.abc import Callable, Sequence

import transformers
from transformers import StoppingCriteria

from core.generator_backend import GeneratorBackend
from core.interfaces import Generator
from core.llm_output import (
    AssistantContent,
    DEFAULT_WRITE_REGION_MARKERS,
    OutputExtractorState,
    WriteRegionParser,
    WriteRegionParserSnapshot,
    WriteRegionMarkers,
    WriteRegionState,
    merge_assistant_content,
)
from core.logger import get_logger
from core.qwen_generator_backend import QwenGeneratorBackend
from core.types import GenerateContext, GenerateResult, StopReason


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
        write_region_parser: WriteRegionParser | None = None,
        write_region_markers: WriteRegionMarkers = DEFAULT_WRITE_REGION_MARKERS,
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
        self._write_region_parser = write_region_parser
        self._write_region_markers = (
            write_region_parser.markers if write_region_parser is not None else write_region_markers
        )
        self._segment_parser = WriteRegionParser(markers=self._write_region_markers)
        self._extract_parser = WriteRegionParser(markers=self._write_region_markers)
        self._warning_emitted = False

    def reset_output_extractor(self) -> None:
        if self._write_region_parser is not None:
            self._write_region_parser.reset()
        self._segment_parser.reset()
        self._extract_parser.reset()
        self._warning_emitted = False

    def get_output_extractor_state(self) -> WriteRegionState:
        if self._write_region_parser is not None:
            return self._write_region_parser.state
        return self._extract_parser.state

    def capture_output_extractor_state(self) -> OutputExtractorState:
        shared_snapshot = self._write_region_parser.capture() if self._write_region_parser is not None else None
        return OutputExtractorState(
            segment=self._segment_parser.capture(),
            extract=self._extract_parser.capture(),
            shared=shared_snapshot,
            warning_emitted=self._warning_emitted,
        )

    def restore_output_extractor_state(self, state: OutputExtractorState) -> None:
        self._segment_parser.restore(state.segment)
        self._extract_parser.restore(state.extract)
        if self._write_region_parser is not None:
            shared_state = state.shared
            if shared_state is None:
                shared_state = WriteRegionParserSnapshot(
                    state=state.extract.state,
                    saw_begin=state.extract.saw_begin,
                    saw_end=state.extract.saw_end,
                    buffer=state.extract.buffer,
                    code_parts=state.extract.code_parts,
                    invalid_payload=state.extract.invalid_payload,
                    invalid_reason=state.extract.invalid_reason,
                )
            self._write_region_parser.restore(shared_state)
        self._warning_emitted = state.warning_emitted

    def set_stop_on_write_region_open(self, enabled: bool) -> None:
        self.backend.set_stop_on_write_region_open(enabled)

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        logger.info(
            "generate_step: steps=%s extract_write_region=%s max_new_length=%s",
            context.steps,
            context.extract_write_region,
            context.max_new_length,
        )
        if context.steps == 0:
            if self._write_region_parser is not None:
                self._write_region_parser.reset()
            self._segment_parser.reset()
            self._extract_parser.reset()
            self._warning_emitted = False

        self.backend.set_generation_channel(context.channel)
        previous_shared = self._write_region_parser.capture() if self._write_region_parser is not None else None
        result = self.backend.generate_step(context)

        if not context.extract_write_region:
            assistant_delta = AssistantContent.from_text(
                result.delta_text,
                markers=self._write_region_markers,
            )
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
        if self._write_region_parser is not None:
            if result.stop_reason.kind == "eos":
                self._write_region_parser.flush()
            extracted = self._write_region_parser.consume_code()
            current_shared = self._write_region_parser.capture()
            stop_reason = _normalize_stop_reason(
                result.stop_reason,
                previous=previous_shared,
                current=current_shared,
            )
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

        total_tokens = 0
        stop_reason = result.stop_reason
        extracted = ""
        remaining = context.max_new_length
        previous_extract = self._extract_parser.capture()

        while True:
            total_tokens += result.delta_tokens
            if result.delta_text:
                self._extract_parser.feed(result.delta_text)
            if result.stop_reason.kind == "eos":
                self._extract_parser.flush()
            current_extract = self._extract_parser.capture()
            stop_reason = _normalize_stop_reason(
                result.stop_reason,
                previous=previous_extract,
                current=current_extract,
            )
            extracted_piece = self._extract_parser.consume_code()
            if extracted_piece:
                extracted += extracted_piece
                break
            if stop_reason.kind in {
                "write_region_closed",
                "no_write_region_eos",
                "unterminated_write_region",
                "invalid_write_region_payload",
            }:
                break
            if not result.delta_text:
                break
            if result.delta_tokens <= 0:
                break
            remaining = max(0, remaining - result.delta_tokens)
            context.max_new_length = remaining
            if remaining <= 0:
                logger.info("generation halted: remaining token budget exhausted")
                break
            previous_extract = current_extract
            result = self.backend.generate_step(context)
            assistant_delta = self._segment_parser.feed(result.delta_text)
            assistant_accum = merge_assistant_content(assistant_accum, assistant_delta)

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


def _normalize_stop_reason(
    stop_reason: StopReason,
    *,
    previous: WriteRegionParserSnapshot | None,
    current: WriteRegionParserSnapshot,
) -> StopReason:
    previous_saw_begin = previous.saw_begin if previous is not None else False
    previous_saw_end = previous.saw_end if previous is not None else False
    previous_invalid = previous.invalid_payload if previous is not None else False
    if current.invalid_payload and not previous_invalid:
        return StopReason(kind="invalid_write_region_payload", detail=current.invalid_reason)
    if current.saw_end and not previous_saw_end:
        return StopReason(kind="write_region_closed", detail="")
    if stop_reason.kind == "eos" and not current.saw_begin and not previous_saw_begin:
        return StopReason(kind="no_write_region_eos", detail="")
    if stop_reason.kind == "eos" and current.state == WriteRegionState.INSIDE:
        return StopReason(kind="unterminated_write_region", detail="")
    return stop_reason
