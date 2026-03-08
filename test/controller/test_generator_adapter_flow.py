from __future__ import annotations

from typing import cast

import pytest
import torch
from torch import FloatTensor, LongTensor

from controller.adapters import GeneratorAdapter
from controller.stop_criteria import DTVStoppingCriteria, RUST_PROFILE
from core.llm_output import FenceParser, FenceReopenError
from core.generator_backend import GeneratorBackend
from core.types import GenerateContext, GenerateResult, StopReason


_STEPS: list[GenerateResult] = []
_CALLS = 0


class _StubBackend(GeneratorBackend):
    def __init__(self, model_name: str, stop_criteria_factory=None) -> None:
        super().__init__(model_name=model_name, stop_criteria_factory=stop_criteria_factory)

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        _ = context
        global _CALLS
        _CALLS += 1
        if _CALLS > len(_STEPS):
            return GenerateResult(
                delta_text="",
                delta_tokens=0,
                stop_reason=StopReason(kind="empty"),
            )
        return _STEPS[_CALLS - 1]


class _FakeTokenizer:
    def __init__(self, mapping: dict[int, str]) -> None:
        self._mapping = mapping

    def decode(self, ids, skip_special_tokens: bool = True) -> str:
        _ = skip_special_tokens
        return "".join(self._mapping[int(token_id)] for token_id in ids)


class _StopCriteriaBackend(GeneratorBackend):
    def __init__(self, model_name: str, stop_criteria_factory=None) -> None:
        super().__init__(model_name=model_name, stop_criteria_factory=stop_criteria_factory)
        mapping = {
            1: "```rust\n",
            2: "let x = 1;\n",
            3: "```\n",
        }
        self._tokenizer = _FakeTokenizer(mapping)
        self._criteria = stop_criteria_factory(self._tokenizer) if stop_criteria_factory else []

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        _ = context
        input_ids = cast(LongTensor, torch.tensor([[1, 2, 3]], dtype=torch.long))
        scores = cast(FloatTensor, torch.empty((1, 0), dtype=torch.float))
        for criteria in self._criteria:
            _ = criteria(input_ids, scores)
        return GenerateResult(
            delta_text="",
            delta_tokens=3,
            stop_reason=StopReason(kind="eos"),
        )


class _TrackingStoppingCriteria(DTVStoppingCriteria):
    def __init__(self, tokenizer, language_profile, fence_parser=None) -> None:
        super().__init__(tokenizer, language_profile, fence_parser=fence_parser)
        self.stream_resets = 0

    def _reset_stream_state(self) -> None:
        self.stream_resets += 1
        super()._reset_stream_state()


def _context(*, extract_fence: bool, steps: int = 0) -> GenerateContext:
    return GenerateContext(
        messages=(),
        steps=steps,
        max_new_length=16,
        extract_fence=extract_fence,
    )


def _set_steps(steps: list[GenerateResult]) -> None:
    global _STEPS, _CALLS
    _STEPS = steps
    _CALLS = 0


def test_adapter_continues_until_code_extracted() -> None:
    adapter = GeneratorAdapter(model_name="stub", backend_cls=_StubBackend)
    _set_steps([
        GenerateResult(
            delta_text="preface\n```rust\n",
            delta_tokens=2,
            stop_reason=StopReason(kind="boundary"),
        ),
        GenerateResult(
            delta_text="line1\n",
            delta_tokens=1,
            stop_reason=StopReason(kind="boundary"),
        ),
    ])

    result = adapter.generate_step(_context(extract_fence=True))

    assert result.delta_text == "line1\n"
    assert result.delta_tokens == 3
    assert result.stop_reason.kind == "boundary"
    assert result.assistant_delta is not None
    assert result.assistant_delta.pre_fence == "preface\n"
    assert result.assistant_delta.fence_lang == "rust"
    assert result.assistant_delta.code == "line1\n"
    assert _CALLS == 2


def test_adapter_no_fence_eos_terminates() -> None:
    adapter = GeneratorAdapter(model_name="stub", backend_cls=_StubBackend)
    _set_steps([
        GenerateResult(
            delta_text="header\n",
            delta_tokens=2,
            stop_reason=StopReason(kind="eos"),
        ),
    ])

    result = adapter.generate_step(_context(extract_fence=True))

    assert result.delta_text == ""
    assert result.delta_tokens == 2
    assert result.stop_reason.kind == "no_fence_eos"
    assert result.assistant_delta is not None
    assert result.assistant_delta.pre_fence == "header\n"


def test_adapter_passes_through_when_extraction_disabled() -> None:
    adapter = GeneratorAdapter(model_name="stub", backend_cls=_StubBackend)
    _set_steps([
        GenerateResult(
            delta_text="raw output",
            delta_tokens=1,
            stop_reason=StopReason(kind="boundary"),
        ),
    ])

    result = adapter.generate_step(_context(extract_fence=False))

    assert result.delta_text == "raw output"
    assert result.delta_tokens == 1


def test_adapter_fence_reopen_skips_marker() -> None:
    adapter = GeneratorAdapter(model_name="stub", backend_cls=_StubBackend)
    _set_steps([
        GenerateResult(
            delta_text="```rust\nline1\n```rust\nline2\n",
            delta_tokens=3,
            stop_reason=StopReason(kind="boundary"),
        ),
    ])

    result = adapter.generate_step(_context(extract_fence=True))
    assert "line1" in result.delta_text
    assert "line2" in result.delta_text


def test_adapter_keeps_fence_parser_state_from_stop_criteria() -> None:
    parser = FenceParser(allowed_langs=("rust", "rs"))

    def _criteria_factory(tokenizer):
        return [DTVStoppingCriteria(tokenizer, RUST_PROFILE, fence_parser=parser)]

    adapter = GeneratorAdapter(
        model_name="stub",
        backend_cls=_StopCriteriaBackend,
        stop_criteria_factory=_criteria_factory,
        fence_parser=parser,
    )

    result = adapter.generate_step(_context(extract_fence=True))

    assert result.stop_reason.kind == "eos"


def test_adapter_restore_round_trip_replays_extraction_with_shared_parser() -> None:
    parser = FenceParser(allowed_langs=("rust", "rs"))

    def _criteria_factory(tokenizer):
        return [DTVStoppingCriteria(tokenizer, RUST_PROFILE, fence_parser=parser)]

    adapter = GeneratorAdapter(
        model_name="stub",
        backend_cls=_StopCriteriaBackend,
        stop_criteria_factory=_criteria_factory,
        fence_parser=parser,
    )
    initial_state = adapter.capture_output_extractor_state()

    first = adapter.generate_step(_context(extract_fence=True))

    adapter.restore_output_extractor_state(initial_state)
    second = adapter.generate_step(_context(extract_fence=True, steps=1))

    assert first.delta_text == "let x = 1;\n"
    assert second.delta_text == "let x = 1;\n"
    assert first.stop_reason.kind == "eos"
    assert second.stop_reason.kind == "eos"


def test_adapter_restore_triggers_stop_criteria_epoch_sync_with_shared_parser() -> None:
    parser = FenceParser(allowed_langs=("rust", "rs"))
    criteria_refs: list[_TrackingStoppingCriteria] = []

    def _criteria_factory(tokenizer):
        criteria = _TrackingStoppingCriteria(tokenizer, RUST_PROFILE, fence_parser=parser)
        criteria_refs.append(criteria)
        return [criteria]

    adapter = GeneratorAdapter(
        model_name="stub",
        backend_cls=_StopCriteriaBackend,
        stop_criteria_factory=_criteria_factory,
        fence_parser=parser,
    )
    initial_state = adapter.capture_output_extractor_state()

    first = adapter.generate_step(_context(extract_fence=True))
    criteria = criteria_refs[0]
    resets_after_first = criteria.stream_resets

    adapter.restore_output_extractor_state(initial_state)
    second = adapter.generate_step(_context(extract_fence=True, steps=1))

    assert first.delta_text == "let x = 1;\n"
    assert second.delta_text == "let x = 1;\n"
    assert criteria.stream_resets == resets_after_first + 1
    assert criteria._calls == 1
