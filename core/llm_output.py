from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

_logger = logging.getLogger(__name__)


class FenceState(str, Enum):
    OUTSIDE = "outside"
    INSIDE = "inside"
    DONE = "done"


@dataclass(frozen=True)
class FenceParserSnapshot:
    state: FenceState
    saw_fence: bool
    buffer: str = ""
    inside_parts: tuple[str, ...] = ()

    def force_inside(self) -> "FenceParserSnapshot":
        return FenceParserSnapshot(
            state=FenceState.INSIDE,
            saw_fence=True,
            buffer="",
            inside_parts=(),
        )


@dataclass(frozen=True)
class OutputExtractorState:
    segment: FenceParserSnapshot
    extract: FenceParserSnapshot
    shared: FenceParserSnapshot | None
    warning_emitted: bool = False

    def force_inside(self) -> "OutputExtractorState":
        shared = self.shared.force_inside() if self.shared is not None else None
        return OutputExtractorState(
            segment=self.segment.force_inside(),
            extract=self.extract.force_inside(),
            shared=shared,
            warning_emitted=self.warning_emitted,
        )


@dataclass(frozen=True)
class AssistantContent:
    pre_fence: str = ""
    fence_lang: str = ""
    code: str = ""
    post_fence: str = ""
    # Streaming buffer: text that may be a fence marker prefix (e.g. "```")
    # but has not been confirmed by a newline yet.  Included in render() so
    # the LLM sees a faithful snapshot; reclassified on the next
    # FenceParser.feed() call via the internal _buffer.
    pending_text: str = ""
    fence_state: FenceState = FenceState.OUTSIDE

    @classmethod
    def empty(cls) -> "AssistantContent":
        return cls()

    @classmethod
    def from_unfenced(cls, text: str) -> "AssistantContent":
        return cls(pre_fence=text, fence_state=FenceState.OUTSIDE)

    def render(self) -> str:
        if self.fence_state == FenceState.OUTSIDE:
            return f"{self.pre_fence}{self.pending_text}"
        if self.fence_state == FenceState.INSIDE:
            return f"{self.pre_fence}```{self.fence_lang}\n{self.code}{self.pending_text}"
        return (
            f"{self.pre_fence}```{self.fence_lang}\n{self.code}"
            f"```\n{self.post_fence}{self.pending_text}"
        )

    def with_code(self, code: str) -> "AssistantContent":
        return AssistantContent(
            pre_fence=self.pre_fence,
            fence_lang=self.fence_lang,
            code=code,
            post_fence=self.post_fence,
            pending_text=self.pending_text,
            fence_state=self.fence_state,
        )


def merge_assistant_content(prefix: AssistantContent, delta: AssistantContent) -> AssistantContent:
    fence_lang = prefix.fence_lang or delta.fence_lang
    return AssistantContent(
        pre_fence=prefix.pre_fence + delta.pre_fence,
        fence_lang=fence_lang,
        code=prefix.code + delta.code,
        post_fence=prefix.post_fence + delta.post_fence,
        pending_text=delta.pending_text,
        fence_state=delta.fence_state,
    )


class FenceReopenError(RuntimeError):
    pass


@dataclass
class FenceParser:
    allowed_langs: tuple[str, ...]
    state: FenceState = FenceState.OUTSIDE
    _buffer: str = ""
    _saw_fence: bool = False
    _epoch: int = 0
    _inside_parts: list[str] = field(default_factory=list)

    def reset(self) -> None:
        self.state = FenceState.OUTSIDE
        self._buffer = ""
        self._saw_fence = False
        self._epoch += 1
        self._inside_parts.clear()

    @property
    def saw_fence(self) -> bool:
        return self._saw_fence

    @property
    def epoch(self) -> int:
        return self._epoch

    def feed(self, chunk: str) -> AssistantContent:
        if not chunk:
            return AssistantContent(fence_state=self.state)
        if self.state == FenceState.DONE and not self._buffer:
            return AssistantContent(post_fence=chunk, fence_state=self.state)

        data = f"{self._buffer}{chunk}"
        self._buffer = ""
        pre_parts: list[str] = []
        code_parts: list[str] = []
        post_parts: list[str] = []
        fence_lang = ""

        while True:
            newline_idx = data.find("\n")
            if newline_idx == -1:
                break
            line = data[: newline_idx + 1]
            data = data[newline_idx + 1 :]
            if self.state == FenceState.OUTSIDE:
                lang = _extract_fence_lang(line, self.allowed_langs)
                if lang is not None:
                    self.state = FenceState.INSIDE
                    self._saw_fence = True
                    fence_lang = lang
                else:
                    pre_parts.append(line)
                continue
            if self.state == FenceState.INSIDE:
                lang = _extract_fence_lang(line, self.allowed_langs)
                if lang is not None:
                    _logger.warning(
                        "Fence reopen detected while INSIDE; "
                        "skipping marker and continuing extraction"
                    )
                    continue
                if _is_closing_fence(line):
                    self.state = FenceState.DONE
                    continue
                code_parts.append(line)
                continue
            post_parts.append(line)

        pending = ""
        if data:
            if _looks_like_fence_start(data):
                self._buffer = data
                pending = data
            elif self.state == FenceState.OUTSIDE:
                pre_parts.append(data)
            elif self.state == FenceState.INSIDE:
                code_parts.append(data)
            else:
                post_parts.append(data)

        inside_piece = "".join(code_parts)
        if inside_piece:
            self._inside_parts.append(inside_piece)

        return AssistantContent(
            pre_fence="".join(pre_parts),
            fence_lang=fence_lang,
            code=inside_piece,
            post_fence="".join(post_parts),
            pending_text=pending,
            fence_state=self.state,
        )

    def flush(self) -> AssistantContent:
        """Finalize parsing when no more input is expected (e.g. EOS)."""
        if self._buffer:
            return self.feed("\n")
        return AssistantContent(fence_state=self.state)

    def consume_inside(self) -> str:
        if not self._inside_parts:
            return ""
        output = "".join(self._inside_parts)
        self._inside_parts.clear()
        return output

    def capture(self) -> FenceParserSnapshot:
        return FenceParserSnapshot(
            state=self.state,
            saw_fence=self._saw_fence,
            buffer=self._buffer,
            inside_parts=tuple(self._inside_parts),
        )

    def restore(self, snapshot: FenceParserSnapshot) -> None:
        self.state = snapshot.state
        self._saw_fence = snapshot.saw_fence
        self._buffer = snapshot.buffer
        self._inside_parts = list(snapshot.inside_parts)
        self._epoch += 1

def _extract_fence_lang(line: str, allowed_langs: tuple[str, ...]) -> str | None:
    """Return the language tag if *line* is an opening fence for an allowed language, else None."""
    stripped = line.strip()
    if not stripped.startswith("```"):
        return None
    lang = stripped[3:].strip()
    return lang if lang in allowed_langs else None


def _is_opening_fence(line: str, allowed_langs: tuple[str, ...]) -> bool:
    stripped = line.strip()
    if not stripped.startswith("```"):
        return False
    lang = stripped[3:].strip()
    return lang in allowed_langs


def _is_closing_fence(line: str) -> bool:
    return line.strip() == "```"


def _looks_like_fence_start(text: str) -> bool:
    stripped = text.lstrip()
    if not stripped.startswith("`"):
        return False
    tick_count = 0
    for ch in stripped:
        if ch != "`":
            break
        tick_count += 1
    return 1 <= tick_count <= 3
