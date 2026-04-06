from __future__ import annotations

from typing import cast

import torch
from torch import FloatTensor, LongTensor

from controller.stop_criteria import DTVStoppingCriteria, RUST_PROFILE, TS_PROFILE, _scan_string_comment_state
from core.llm_output import BEGIN_WRITE_CODE, END_WRITE_CODE, WriteRegionMarkers, WriteRegionParser, WriteRegionState
from core.types import GenerationChannel


class _FakeTokenizer:
    def __init__(self, mapping: dict[int, str]) -> None:
        self._mapping = mapping

    def decode(self, ids, skip_special_tokens: bool = True) -> str:
        _ = skip_special_tokens
        return "".join(self._mapping[int(token_id)] for token_id in ids)


def _call(criteria: DTVStoppingCriteria, tokens: list[int]) -> bool:
    input_ids = cast(LongTensor, torch.tensor([tokens], dtype=torch.long))
    scores = cast(FloatTensor, torch.empty((1, 0), dtype=torch.float))
    return bool(criteria(input_ids, scores))


def test_empty() -> None:
    state = _scan_string_comment_state("", TS_PROFILE)
    assert not state["in_string"]
    assert not state["in_line_comment"]
    assert not state["in_block_comment"]


def test_stop_criteria_gates_on_write_region() -> None:
    mapping = {
        1: "Here's ",
        2: f"{BEGIN_WRITE_CODE}\n",
        3: "let x = 1",
        4: ";\n",
        5: f"{END_WRITE_CODE}\n",
    }
    parser = WriteRegionParser()
    criteria = DTVStoppingCriteria(_FakeTokenizer(mapping), RUST_PROFILE, write_region_parser=parser)

    tokens = [1]
    assert not _call(criteria, tokens)
    assert parser.state == WriteRegionState.OUTSIDE

    tokens.append(2)
    assert not _call(criteria, tokens)
    assert parser.state == WriteRegionState.INSIDE

    tokens.append(3)
    assert not _call(criteria, tokens)

    tokens.append(4)
    assert _call(criteria, tokens)

    tokens.append(5)
    assert _call(criteria, tokens)
    assert parser.state == WriteRegionState.OUTSIDE


def test_stop_on_write_region_open() -> None:
    mapping = {
        1: f"{BEGIN_WRITE_CODE}\n",
    }
    parser = WriteRegionParser()
    criteria = DTVStoppingCriteria(_FakeTokenizer(mapping), RUST_PROFILE, write_region_parser=parser)
    criteria.set_stop_on_write_region_open(True)

    assert _call(criteria, [1])


def test_patch_channel_waits_for_end_marker() -> None:
    mapping = {
        1: f"{BEGIN_WRITE_CODE}\n",
        2: "+ fixed;\n",
        3: f"{END_WRITE_CODE}\n",
    }
    criteria = DTVStoppingCriteria(_FakeTokenizer(mapping), RUST_PROFILE, write_region_parser=None)
    criteria.set_generation_channel(GenerationChannel.PATCH)

    tokens = [1]
    assert not _call(criteria, tokens)
    tokens.append(2)
    assert not _call(criteria, tokens)
    tokens.append(3)
    assert _call(criteria, tokens)


def test_custom_markers_work_in_patch_channel() -> None:
    markers = WriteRegionMarkers(begin_marker="[[BEGIN]]", end_marker="[[END]]")
    mapping = {
        1: "[[BEGIN]]\n",
        2: "+ fixed;\n",
        3: "[[END]]\n",
    }
    criteria = DTVStoppingCriteria(
        _FakeTokenizer(mapping),
        RUST_PROFILE,
        write_region_parser=None,
        write_region_markers=markers,
    )
    criteria.set_generation_channel(GenerationChannel.PATCH)

    assert not _call(criteria, [1, 2])
    assert _call(criteria, [1, 2, 3])
