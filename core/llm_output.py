from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FenceState(str, Enum):
    OUTSIDE = "outside"
    INSIDE = "inside"
    DONE = "done"


@dataclass
class FenceExtractor:
    """Incremental fenced-code extractor with line-based fence detection."""

    allowed_langs: tuple[str, ...]
    state: FenceState = FenceState.OUTSIDE
    _buffer: str = ""
    _saw_fence: bool = False
    _warning_emitted: bool = False

    def reset(self) -> None:
        self.state = FenceState.OUTSIDE
        self._buffer = ""
        self._saw_fence = False
        self._warning_emitted = False

    @property
    def saw_fence(self) -> bool:
        return self._saw_fence

    @property
    def warning_emitted(self) -> bool:
        return self._warning_emitted

    def mark_warning_emitted(self) -> None:
        self._warning_emitted = True

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        if self.state == FenceState.DONE and not self._buffer:
            return ""

        # Carry over incomplete line fragments so fence markers split across chunks are detected.
        data = f"{self._buffer}{chunk}"
        self._buffer = ""
        output_parts: list[str] = []

        # Fence detection is line-based; only process complete lines here.
        while True:
            newline_idx = data.find("\n")
            if newline_idx == -1:
                break
            line = data[: newline_idx + 1]
            data = data[newline_idx + 1 :]
            self._process_line(line, output_parts)
            if self.state == FenceState.DONE:
                data = ""
                break

        if data:
            if self.state == FenceState.INSIDE:
                # Inside a fence, emit trailing fragments unless they might start a fence line.
                if _looks_like_fence_start(data):
                    self._buffer = data
                else:
                    output_parts.append(data)
            else:
                self._buffer = data

        return "".join(output_parts)

    def _process_line(self, line: str, output_parts: list[str]) -> None:
        if self.state == FenceState.OUTSIDE:
            if _is_opening_fence(line, self.allowed_langs):
                self.state = FenceState.INSIDE
                self._saw_fence = True
            return
        if self.state == FenceState.INSIDE:
            if _is_closing_fence(line):
                self.state = FenceState.DONE
                return
            output_parts.append(line)
            return


@dataclass
class RustFenceExtractor(FenceExtractor):
    allowed_langs: tuple[str, ...] = ("rust", "rs")


def _is_opening_fence(line: str, allowed_langs: tuple[str, ...]) -> bool:
    stripped = line.strip()
    if not stripped.startswith("```"):
        return False
    lang = stripped[3:].strip()
    return lang in allowed_langs


def _is_closing_fence(line: str) -> bool:
    return line.strip() == "```"


def _looks_like_fence_start(text: str) -> bool:
    return text.lstrip().startswith("```")
