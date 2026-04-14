from __future__ import annotations

from controller.adapters import GeneratorAdapter
from core.generator_backend import GeneratorBackend
from core.llm_output import BEGIN_WRITE_CODE, END_WRITE_CODE, WriteRegionMarkers, WriteRegionParser
from core.types import GenerateContext, GenerateResult, StopReason


_STEPS: list[GenerateResult] = []
_CALLS = 0


class _StubBackend(GeneratorBackend):
    def __init__(self, model_name: str, stop_criteria_factory=None, **kwargs) -> None:
        super().__init__(model_name=model_name, stop_criteria_factory=stop_criteria_factory, **kwargs)

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


def _context(*, extract_write_region: bool, steps: int = 0) -> GenerateContext:
    return GenerateContext(
        messages=(),
        steps=steps,
        max_new_length=16,
        extract_write_region=extract_write_region,
    )


def _set_steps(steps: list[GenerateResult]) -> None:
    global _STEPS, _CALLS
    _STEPS = steps
    _CALLS = 0


def test_adapter_continues_until_code_extracted() -> None:
    adapter = GeneratorAdapter(model_name="stub", backend_cls=_StubBackend)
    _set_steps([
        GenerateResult(
            delta_text=f"preface\n{BEGIN_WRITE_CODE}\n",
            delta_tokens=2,
            stop_reason=StopReason(kind="unknown"),
        ),
        GenerateResult(
            delta_text="line1\n",
            delta_tokens=1,
            stop_reason=StopReason(kind="boundary"),
        ),
    ])

    result = adapter.generate_step(_context(extract_write_region=True))

    assert result.delta_text == "line1\n"
    assert result.delta_tokens == 3
    assert result.stop_reason.kind == "boundary"
    assert result.assistant_delta is not None
    assert result.assistant_delta.prelude == "preface\n"
    assert result.assistant_delta.has_begin_marker
    assert result.assistant_delta.code == "line1\n"


def test_adapter_no_write_region_eos_terminates() -> None:
    adapter = GeneratorAdapter(model_name="stub", backend_cls=_StubBackend)
    _set_steps([
        GenerateResult(
            delta_text="header\n",
            delta_tokens=2,
            stop_reason=StopReason(kind="eos"),
        ),
    ])

    result = adapter.generate_step(_context(extract_write_region=True))

    assert result.delta_text == ""
    assert result.delta_tokens == 2
    assert result.stop_reason.kind == "no_write_region_eos"
    assert result.assistant_delta is not None
    assert result.assistant_delta.prelude == "header\n"


def test_adapter_emits_write_region_closed() -> None:
    adapter = GeneratorAdapter(model_name="stub", backend_cls=_StubBackend)
    _set_steps([
        GenerateResult(
            delta_text=f"{BEGIN_WRITE_CODE}\nline1\n{END_WRITE_CODE}\n",
            delta_tokens=3,
            stop_reason=StopReason(kind="unknown"),
        ),
    ])

    result = adapter.generate_step(_context(extract_write_region=True))

    assert result.delta_text == "line1\n"
    assert result.stop_reason.kind == "write_region_closed"


def test_adapter_passes_through_when_extraction_disabled() -> None:
    adapter = GeneratorAdapter(model_name="stub", backend_cls=_StubBackend)
    _set_steps([
        GenerateResult(
            delta_text="raw output",
            delta_tokens=1,
            stop_reason=StopReason(kind="boundary"),
        ),
    ])

    result = adapter.generate_step(_context(extract_write_region=False))

    assert result.delta_text == "raw output"
    assert result.delta_tokens == 1


def test_adapter_accepts_custom_markers() -> None:
    markers = WriteRegionMarkers(begin_marker="[[BEGIN]]", end_marker="[[END]]")
    adapter = GeneratorAdapter(
        model_name="stub",
        backend_cls=_StubBackend,
        write_region_markers=markers,
    )
    _set_steps([
        GenerateResult(
            delta_text="intro\n[[BEGIN]]\nline1\n[[END]]\n",
            delta_tokens=3,
            stop_reason=StopReason(kind="unknown"),
        ),
    ])

    result = adapter.generate_step(_context(extract_write_region=True))

    assert result.delta_text == "line1\n"
    assert result.assistant_delta is not None
    assert result.assistant_delta.markers == markers
