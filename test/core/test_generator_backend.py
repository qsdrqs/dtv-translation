from __future__ import annotations

from core.generator_backend import infer_stop_reason
from core.qwen_generator_backend import QwenGeneratorBackend
from core.types import GenerateContext, GenerateMessage


def _make_backend(*, enable_thinking: bool | None = None) -> QwenGeneratorBackend:
    backend = QwenGeneratorBackend.__new__(QwenGeneratorBackend)
    backend.enable_thinking = enable_thinking
    return backend


def test_infer_stop_reason_eos_precedence() -> None:
    reason = infer_stop_reason("let x = 1;", delta_tokens=1, max_new_length=1, eos_reached=True)
    assert reason.kind == "eos"


def test_infer_stop_reason_max_length() -> None:
    reason = infer_stop_reason("let x = 1", delta_tokens=5, max_new_length=5, eos_reached=False)
    assert reason.kind == "max_length"
    assert reason.detail == "5"


def test_infer_stop_reason_boundary() -> None:
    reason = infer_stop_reason("let x = 1;", delta_tokens=3, max_new_length=10, eos_reached=False)
    assert reason.kind == "boundary"


def test_infer_stop_reason_empty() -> None:
    reason = infer_stop_reason("", delta_tokens=0, max_new_length=10, eos_reached=False)
    assert reason.kind == "empty"


def test_infer_stop_reason_unknown() -> None:
    reason = infer_stop_reason("let x = 1", delta_tokens=3, max_new_length=10, eos_reached=False)
    assert reason.kind == "unknown"


def test_build_prompt_trailing_assistant_no_stop() -> None:
    backend = _make_backend()
    context = GenerateContext(
        messages=(
            GenerateMessage(role="user", content="hello", stop=True),
            GenerateMessage(role="assistant", content="prefix", stop=False),
        )
    )

    prompt = backend._build_prompt(context)

    assert prompt == "<|im_start|>user\nhello\n<|im_end|>\n<|im_start|>assistant\nprefix"


def test_build_prompt_trailing_assistant_with_stop() -> None:
    backend = _make_backend()
    context = GenerateContext(
        messages=(
            GenerateMessage(role="user", content="hello", stop=True),
            GenerateMessage(role="assistant", content="prefix", stop=True),
        )
    )

    prompt = backend._build_prompt(context)

    assert prompt == "<|im_start|>user\nhello\n<|im_end|>\n<|im_start|>assistant\nprefix\n<|im_end|>"


def test_build_prompt_trailing_empty_assistant_no_stop() -> None:
    backend = _make_backend()
    context = GenerateContext(messages=(
        GenerateMessage(role="user", content="hello", stop=True),
        GenerateMessage(role="assistant", content="", stop=False),
    ))

    prompt = backend._build_prompt(context)

    assert prompt == "<|im_start|>user\nhello\n<|im_end|>\n<|im_start|>assistant\n"


def test_build_prompt_user_only() -> None:
    backend = _make_backend()
    context = GenerateContext(messages=(GenerateMessage(role="user", content="hello", stop=True),))

    prompt = backend._build_prompt(context)

    assert prompt == "<|im_start|>user\nhello\n<|im_end|>"


def test_build_prompt_thinking_enabled_empty_assistant() -> None:
    backend = _make_backend(enable_thinking=True)
    context = GenerateContext(messages=(
        GenerateMessage(role="user", content="hello", stop=True),
        GenerateMessage(role="assistant", content="", stop=False),
    ))

    prompt = backend._build_prompt(context)

    assert prompt == (
        "<|im_start|>user\nhello\n<|im_end|>\n"
        "<|im_start|>assistant\n<think>\n"
    )


def test_build_prompt_thinking_disabled_empty_assistant() -> None:
    backend = _make_backend(enable_thinking=False)
    context = GenerateContext(messages=(
        GenerateMessage(role="user", content="hello", stop=True),
        GenerateMessage(role="assistant", content="", stop=False),
    ))

    prompt = backend._build_prompt(context)

    assert prompt == (
        "<|im_start|>user\nhello\n<|im_end|>\n"
        "<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )


def test_build_prompt_thinking_enabled_nonempty_assistant_skips_prefix() -> None:
    backend = _make_backend(enable_thinking=True)
    context = GenerateContext(messages=(
        GenerateMessage(role="user", content="hello", stop=True),
        GenerateMessage(role="assistant", content="existing code", stop=False),
    ))

    prompt = backend._build_prompt(context)

    assert prompt == (
        "<|im_start|>user\nhello\n<|im_end|>\n"
        "<|im_start|>assistant\nexisting code"
    )


def test_build_prompt_thinking_none_no_prefix() -> None:
    backend = _make_backend(enable_thinking=None)
    context = GenerateContext(messages=(
        GenerateMessage(role="user", content="hello", stop=True),
        GenerateMessage(role="assistant", content="", stop=False),
    ))

    prompt = backend._build_prompt(context)

    assert prompt == "<|im_start|>user\nhello\n<|im_end|>\n<|im_start|>assistant\n"
