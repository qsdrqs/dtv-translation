from __future__ import annotations

from core.generator_backend import infer_stop_reason


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
