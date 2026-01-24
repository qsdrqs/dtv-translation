from __future__ import annotations

from controller.adapters import GeneratorAdapter
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


def _context(*, extract_fence: bool) -> GenerateContext:
    return GenerateContext(messages=(), steps=0, max_new_length=16, extract_fence=extract_fence)


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
