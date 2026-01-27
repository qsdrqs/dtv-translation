from __future__ import annotations

from typing import cast

import pytest
import torch
from torch import FloatTensor, LongTensor

from controller.stop_criteria import (
    DTVStoppingCriteria,
    RUST_PROFILE,
    TS_PROFILE,
    _scan_string_comment_state,
)
from core.llm_output import FenceParser, FenceReopenError, FenceState


class _FakeTokenizer:
    def __init__(self, mapping: dict[int, str]) -> None:
        self._mapping = mapping

    def decode(self, ids, skip_special_tokens: bool = True) -> str:
        _ = skip_special_tokens
        return "".join(self._mapping[int(token_id)] for token_id in ids)


def test_empty() -> None:
    state = _scan_string_comment_state("", TS_PROFILE)
    assert not state["in_string"]
    assert not state["in_line_comment"]
    assert not state["in_block_comment"]


def test_line_comment_unterminated() -> None:
    state = _scan_string_comment_state("let x = 1; // comment", TS_PROFILE)
    assert state["in_line_comment"]
    assert not state["in_string"]
    assert not state["in_block_comment"]


def test_line_comment_terminated_by_newline() -> None:
    state = _scan_string_comment_state("let x = 1; // comment\nlet y = 2;", TS_PROFILE)
    assert not state["in_line_comment"]
    assert not state["in_string"]
    assert not state["in_block_comment"]


def test_block_comment_unterminated() -> None:
    state = _scan_string_comment_state("let x = 1; /* comment", TS_PROFILE)
    assert state["in_block_comment"]
    assert not state["in_string"]
    assert not state["in_line_comment"]


def test_block_comment_terminated() -> None:
    state = _scan_string_comment_state("let x = 1; /* comment */ let y = 2;", TS_PROFILE)
    assert not state["in_block_comment"]
    assert not state["in_string"]
    assert not state["in_line_comment"]


def test_comment_markers_inside_string_not_counted() -> None:
    state = _scan_string_comment_state('let s = "// not a comment";', TS_PROFILE)
    assert not state["in_string"]
    assert not state["in_line_comment"]
    assert not state["in_block_comment"]


def test_escaped_quote_inside_string() -> None:
    state = _scan_string_comment_state('let s = "a \\" b";', TS_PROFILE)
    assert not state["in_string"]
    assert not state["in_line_comment"]
    assert not state["in_block_comment"]


def test_ts_backtick_string() -> None:
    state = _scan_string_comment_state("const s = `hello", TS_PROFILE)
    assert state["in_string"]
    assert not state["in_line_comment"]
    assert not state["in_block_comment"]


def test_rust_does_not_treat_backticks_as_string() -> None:
    state = _scan_string_comment_state("let s = `hello", RUST_PROFILE)
    assert not state["in_string"]
    assert not state["in_line_comment"]
    assert not state["in_block_comment"]


def _call(criteria: DTVStoppingCriteria, tokens: list[int]) -> bool:
    input_ids = cast(LongTensor, torch.tensor([tokens], dtype=torch.long))
    scores = cast(FloatTensor, torch.empty((1, 0), dtype=torch.float))
    return bool(criteria(input_ids, scores))


def test_stop_criteria_gates_on_fence() -> None:
    mapping = {
        1: "Here's ",
        2: "preamble;\n",
        3: "```rust\n",
        4: "let x = 1",
        5: ";\n",
        6: "```\n",
    }
    parser = FenceParser(allowed_langs=("rust", "rs"))
    criteria = DTVStoppingCriteria(_FakeTokenizer(mapping), RUST_PROFILE, fence_parser=parser)

    tokens: list[int] = [1]
    assert not _call(criteria, tokens)

    tokens.append(2)
    assert not _call(criteria, tokens)
    assert parser.state == FenceState.OUTSIDE

    tokens.append(3)
    assert not _call(criteria, tokens)
    assert parser.state == FenceState.INSIDE

    tokens.append(4)
    assert not _call(criteria, tokens)

    tokens.append(5)
    assert _call(criteria, tokens)

    tokens.append(6)
    assert not _call(criteria, tokens)
    assert parser.state == FenceState.DONE


def test_stop_criteria_raises_on_fence_reopen() -> None:
    mapping = {
        1: "```rust\n",
        2: "let x = 1\n",
        3: "```rust\n",
    }
    parser = FenceParser(allowed_langs=("rust", "rs"))
    criteria = DTVStoppingCriteria(_FakeTokenizer(mapping), RUST_PROFILE, fence_parser=parser)

    tokens: list[int] = [1]
    assert not _call(criteria, tokens)

    tokens.append(2)
    assert not _call(criteria, tokens)

    tokens.append(3)
    with pytest.raises(FenceReopenError):
        _call(criteria, tokens)


def test_stop_criteria_dedupes_same_boundary_across_calls() -> None:
    mapping = {
        1: "let x = 1;",
        2: "\n",
        3: "let y = 2;",
    }
    criteria = DTVStoppingCriteria(_FakeTokenizer(mapping), RUST_PROFILE, fence_parser=None)

    tokens: list[int] = [1]
    assert _call(criteria, tokens)

    tokens.append(2)
    assert not _call(criteria, tokens)

    tokens.append(3)
    assert _call(criteria, tokens)
