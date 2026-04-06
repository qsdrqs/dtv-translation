from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum


_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WriteRegionMarkers:
    begin_marker: str = "<<BEGIN_WRITE_CODE>>"
    end_marker: str = "<<END_WRITE_CODE>>"


DEFAULT_WRITE_REGION_MARKERS = WriteRegionMarkers()
BEGIN_WRITE_CODE = DEFAULT_WRITE_REGION_MARKERS.begin_marker
END_WRITE_CODE = DEFAULT_WRITE_REGION_MARKERS.end_marker


class WriteRegionState(str, Enum):
    OUTSIDE = "outside"
    INSIDE = "inside"


@dataclass(frozen=True)
class WriteRegionParserSnapshot:
    state: WriteRegionState
    saw_begin: bool
    saw_end: bool
    buffer: str = ""
    code_parts: tuple[str, ...] = ()
    invalid_payload: bool = False
    invalid_reason: str = ""

    def force_inside(self) -> "WriteRegionParserSnapshot":
        return WriteRegionParserSnapshot(
            state=WriteRegionState.INSIDE,
            saw_begin=True,
            saw_end=False,
            buffer="",
            code_parts=(),
            invalid_payload=False,
            invalid_reason="",
        )


@dataclass(frozen=True)
class OutputExtractorState:
    segment: WriteRegionParserSnapshot
    extract: WriteRegionParserSnapshot
    shared: WriteRegionParserSnapshot | None
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
    prelude: str = ""
    code: str = ""
    postlude: str = ""
    pending_text: str = ""
    has_begin_marker: bool = False
    has_end_marker: bool = False
    region_state: WriteRegionState = WriteRegionState.OUTSIDE
    markers: WriteRegionMarkers = DEFAULT_WRITE_REGION_MARKERS

    @classmethod
    def empty(cls, *, markers: WriteRegionMarkers = DEFAULT_WRITE_REGION_MARKERS) -> "AssistantContent":
        return cls(markers=markers)

    @classmethod
    def from_text(
        cls,
        text: str,
        *,
        markers: WriteRegionMarkers = DEFAULT_WRITE_REGION_MARKERS,
    ) -> "AssistantContent":
        return cls(prelude=text, region_state=WriteRegionState.OUTSIDE, markers=markers)

    def render(self) -> str:
        parts: list[str] = [self.prelude]
        if self.has_begin_marker:
            parts.append(f"{self.markers.begin_marker}\n")
            parts.append(self.code)
            if self.has_end_marker:
                parts.append(f"{self.markers.end_marker}\n")
                parts.append(self.postlude)
        else:
            parts.append(self.code)
            parts.append(self.postlude)
        parts.append(self.pending_text)
        return "".join(parts)

    def with_code(self, code: str) -> "AssistantContent":
        return AssistantContent(
            prelude=self.prelude,
            code=code,
            postlude=self.postlude,
            pending_text=self.pending_text,
            has_begin_marker=self.has_begin_marker,
            has_end_marker=self.has_end_marker,
            region_state=self.region_state,
            markers=self.markers,
        )


def merge_assistant_content(prefix: AssistantContent, delta: AssistantContent) -> AssistantContent:
    return AssistantContent(
        prelude=prefix.prelude + delta.prelude,
        code=prefix.code + delta.code,
        postlude=prefix.postlude + delta.postlude,
        pending_text=delta.pending_text,
        has_begin_marker=prefix.has_begin_marker or delta.has_begin_marker,
        has_end_marker=prefix.has_end_marker or delta.has_end_marker,
        region_state=delta.region_state,
        markers=prefix.markers,
    )


@dataclass
class WriteRegionParser:
    state: WriteRegionState = WriteRegionState.OUTSIDE
    markers: WriteRegionMarkers = DEFAULT_WRITE_REGION_MARKERS
    _buffer: str = ""
    _saw_begin: bool = False
    _saw_end: bool = False
    _invalid_payload: bool = False
    _invalid_reason: str = ""
    _epoch: int = 0
    _code_parts: list[str] = field(default_factory=list)

    def reset(self) -> None:
        self.state = WriteRegionState.OUTSIDE
        self._buffer = ""
        self._saw_begin = False
        self._saw_end = False
        self._invalid_payload = False
        self._invalid_reason = ""
        self._epoch += 1
        self._code_parts.clear()

    @property
    def saw_begin(self) -> bool:
        return self._saw_begin

    @property
    def saw_end(self) -> bool:
        return self._saw_end

    @property
    def invalid_payload(self) -> bool:
        return self._invalid_payload

    @property
    def invalid_reason(self) -> str:
        return self._invalid_reason

    @property
    def epoch(self) -> int:
        return self._epoch

    def feed(self, chunk: str) -> AssistantContent:
        if not chunk:
            return AssistantContent(region_state=self.state, markers=self.markers)

        data = f"{self._buffer}{chunk}"
        self._buffer = ""
        prelude_parts: list[str] = []
        code_parts: list[str] = []
        postlude_parts: list[str] = []
        begin_seen = False
        end_seen = False

        while True:
            newline_idx = data.find("\n")
            if newline_idx == -1:
                break
            line = data[: newline_idx + 1]
            data = data[newline_idx + 1 :]
            if self.state == WriteRegionState.OUTSIDE:
                if _is_begin_marker(line, self.markers):
                    self.state = WriteRegionState.INSIDE
                    self._saw_begin = True
                    begin_seen = True
                elif self._saw_end:
                    postlude_parts.append(line)
                else:
                    prelude_parts.append(line)
                continue

            if _is_end_marker(line, self.markers):
                self.state = WriteRegionState.OUTSIDE
                self._saw_end = True
                end_seen = True
                continue
            if _is_forbidden_inner_fence(line):
                self._invalid_payload = True
                if not self._invalid_reason:
                    self._invalid_reason = "write region must contain raw code only"
                continue
            code_parts.append(line)

        pending = ""
        if data:
            if self.state == WriteRegionState.OUTSIDE:
                if _looks_like_marker_prefix(data, self.markers.begin_marker):
                    self._buffer = data
                    pending = data
                elif self._saw_end:
                    postlude_parts.append(data)
                else:
                    prelude_parts.append(data)
            else:
                if _looks_like_marker_prefix(data, self.markers.end_marker) or _looks_like_forbidden_inner_fence_prefix(data):
                    self._buffer = data
                    pending = data
                else:
                    code_parts.append(data)

        code_piece = "".join(code_parts)
        if code_piece:
            self._code_parts.append(code_piece)

        return AssistantContent(
            prelude="".join(prelude_parts),
            code=code_piece,
            postlude="".join(postlude_parts),
            pending_text=pending,
            has_begin_marker=begin_seen,
            has_end_marker=end_seen,
            region_state=self.state,
            markers=self.markers,
        )

    def flush(self) -> AssistantContent:
        if self._buffer:
            return self.feed("\n")
        return AssistantContent(region_state=self.state, markers=self.markers)

    def consume_code(self) -> str:
        if not self._code_parts:
            return ""
        output = "".join(self._code_parts)
        self._code_parts.clear()
        return output

    def capture(self) -> WriteRegionParserSnapshot:
        return WriteRegionParserSnapshot(
            state=self.state,
            saw_begin=self._saw_begin,
            saw_end=self._saw_end,
            buffer=self._buffer,
            code_parts=tuple(self._code_parts),
            invalid_payload=self._invalid_payload,
            invalid_reason=self._invalid_reason,
        )

    def restore(self, snapshot: WriteRegionParserSnapshot) -> None:
        self.state = snapshot.state
        self._saw_begin = snapshot.saw_begin
        self._saw_end = snapshot.saw_end
        self._buffer = snapshot.buffer
        self._code_parts = list(snapshot.code_parts)
        self._invalid_payload = snapshot.invalid_payload
        self._invalid_reason = snapshot.invalid_reason
        self._epoch += 1


def _is_begin_marker(line: str, markers: WriteRegionMarkers) -> bool:
    return line.strip() == markers.begin_marker


def _is_end_marker(line: str, markers: WriteRegionMarkers) -> bool:
    return line.strip() == markers.end_marker


def _is_forbidden_inner_fence(line: str) -> bool:
    return line.strip().startswith("```")


def _looks_like_marker_prefix(text: str, marker: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return marker.startswith(stripped)


def _looks_like_forbidden_inner_fence_prefix(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return "```".startswith(stripped) or stripped.startswith("```")
