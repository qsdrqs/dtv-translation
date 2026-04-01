from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from transformers import StoppingCriteria

from core.llm_output import FenceParser, FenceState
from core.logger import get_logger
from core.types import GenerationChannel
from feedback.output_parser import FeedbackFenceStreamParser
import torch
from torch import BoolTensor


@dataclass(frozen=True)
class LanguageProfile:
    """Delimiters used to identify strings and comments for a language."""
    line_comment_starts: tuple[str, ...]
    block_comment_pairs: tuple[tuple[str, str], ...]
    string_delims: tuple[str, ...]  # Quote characters treated as string delimiters.


RUST_PROFILE = LanguageProfile(
    line_comment_starts=("//",),
    block_comment_pairs=(("/*", "*/"),),
    string_delims=('"',),
)

# TODO: Rust char literals like '}' and lifetimes are not handled here.

TS_PROFILE = LanguageProfile(
    line_comment_starts=("//",),
    block_comment_pairs=(("/*", "*/"),),
    string_delims=('"', "'", "`"),
)

logger = get_logger(__name__)


def _scan_string_comment_state(text: str, profile: LanguageProfile) -> dict[str, bool]:
    in_line_comment = False
    in_block_comment = False
    in_string = False
    string_delim = ""
    escape = False
    block_end = ""

    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        two = ch + nxt

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            if block_end and text.startswith(block_end, i):
                in_block_comment = False
                i += len(block_end)
            else:
                i += 1
            continue

        if in_string:
            if escape:
                escape = False
                i += 1
                continue
            if ch == "\\":
                escape = True
                i += 1
                continue
            if ch == string_delim:
                in_string = False
                string_delim = ""
            i += 1
            continue

        if two in profile.line_comment_starts:
            in_line_comment = True
            i += 2
            continue

        for start, end in profile.block_comment_pairs:
            if text.startswith(start, i):
                in_block_comment = True
                block_end = end
                i += len(start)
                break
        if in_block_comment:
            continue

        if ch in profile.string_delims:
            in_string = True
            string_delim = ch
            i += 1
            continue

        i += 1

    return {
        "in_string": in_string,
        "in_line_comment": in_line_comment,
        "in_block_comment": in_block_comment,
    }


class DTVStoppingCriteria(StoppingCriteria):
    def __init__(
        self,
        tokenizer,
        language_profile: LanguageProfile,
        fence_parser: FenceParser | None = None,
    ) -> None:
        self.tokenizer = tokenizer
        self.language_profile = language_profile
        self.fence_parser = fence_parser
        self._calls = 0
        self._boundary_checks = 0
        self._boundary_suppressed = 0
        self._boundary_triggered = 0
        self._last_token_count = 0
        self._prompt_token_count: int | None = None
        self._code_text = ""
        self._last_boundary_len: int | None = None
        self._parser_epoch = fence_parser.epoch if fence_parser is not None else None
        self._generation_channel = GenerationChannel.CONTINUATION
        self._feedback_fence_parser = FeedbackFenceStreamParser()
        self._stop_on_fence_open = False

    def _reset_stream_state(self) -> None:
        self._calls = 0
        self._boundary_checks = 0
        self._boundary_suppressed = 0
        self._boundary_triggered = 0
        self._last_token_count = self._prompt_token_count or 0
        self._code_text = ""
        self._last_boundary_len = None
        self._feedback_fence_parser.reset()

    def set_prompt_token_count(self, prompt_token_count: int) -> None:
        if prompt_token_count < 0:
            raise ValueError("prompt_token_count must be >= 0")
        self._prompt_token_count = prompt_token_count
        self._last_token_count = prompt_token_count
        self._calls = 0

    def set_stop_on_fence_open(self, enabled: bool) -> None:
        self._stop_on_fence_open = enabled

    def set_generation_channel(self, generation_channel: GenerationChannel | str) -> None:
        next_channel = GenerationChannel(generation_channel)
        if next_channel == self._generation_channel:
            return
        self._generation_channel = next_channel
        self._reset_stream_state()

    def __call__(self, input_ids, scores, **kwargs) -> BoolTensor:
        TORCH_FALSE = cast(BoolTensor, torch.tensor([False], dtype=torch.bool, device=input_ids.device))
        TORCH_TRUE = cast(BoolTensor, torch.tensor([True], dtype=torch.bool, device=input_ids.device))

        if self.fence_parser is not None and self._parser_epoch != self.fence_parser.epoch:
            self._parser_epoch = self.fence_parser.epoch
            self._reset_stream_state()

        token_count = input_ids.shape[-1]
        if token_count < self._last_token_count:
            self._reset_stream_state()

        new_text = ""
        if token_count > self._last_token_count:
            new_text = self.tokenizer.decode(
                input_ids[0, self._last_token_count : token_count],
                skip_special_tokens=True,
            )
        self._last_token_count = token_count
        self._calls += 1

        if self._generation_channel == GenerationChannel.PATCH:
            if new_text:
                self._feedback_fence_parser.feed(new_text)
            if self._feedback_fence_parser.complete:
                return TORCH_TRUE
            return TORCH_FALSE

        if self.fence_parser is not None:
            if new_text:
                assistant_delta = self.fence_parser.feed(new_text)
                inside_piece = assistant_delta.code
                if inside_piece:
                    self._code_text += inside_piece
            if self.fence_parser.state != FenceState.INSIDE:
                return TORCH_FALSE
            if self._stop_on_fence_open:
                return TORCH_TRUE
            stripped = self._code_text.rstrip()
        else:
            decoded = self.tokenizer.decode(input_ids[0], skip_special_tokens=True)
            stripped = decoded.rstrip()
        if not stripped:
            return TORCH_FALSE

        if self._calls == 1:
            logger.info(
                "stop criteria active: tokens=%s tail=%s",
                token_count,
                stripped[-80:],
            )

        last_char = stripped[-1]
        if last_char not in {";", "}"}:
            return TORCH_FALSE

        current_len = len(stripped)
        if self._last_boundary_len is not None and current_len == self._last_boundary_len:
            return TORCH_FALSE

        self._boundary_checks += 1
        state = _scan_string_comment_state(stripped, self.language_profile)
        if state["in_string"] or state["in_line_comment"] or state["in_block_comment"]:
            self._boundary_suppressed += 1
            logger.info(
                "stop suppressed: last_char=%s in_string=%s in_line_comment=%s in_block_comment=%s tail=%s",
                last_char,
                state["in_string"],
                state["in_line_comment"],
                state["in_block_comment"],
                stripped[-80:],
            )
            return TORCH_FALSE

        # TODO: bracket/brace depth tracking to avoid stopping mid-block context.
        # TODO: raw strings (Rust) and template literals (TS) are not handled here.
        self._boundary_triggered += 1
        self._last_boundary_len = current_len
        logger.info("stop triggered: last_char=%s tail=%s", last_char, stripped[-80:])
        return TORCH_TRUE
