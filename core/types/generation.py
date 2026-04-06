from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from core.llm_output import AssistantContent

from .enums import GenerationChannel


@dataclass(frozen=True)
class StopReason:
    kind: str
    detail: str = ""


@dataclass(frozen=True)
class GenerateMessage:
    role: str
    content: str | AssistantContent
    stop: bool


@dataclass
class GenerateContext:
    messages: Sequence[GenerateMessage | dict[str, Any]]
    steps: int = 0
    max_new_length: int = 1024
    extract_write_region: bool = False
    channel: GenerationChannel = GenerationChannel.CONTINUATION


@dataclass(frozen=True)
class GenerateResult:
    delta_text: str
    delta_tokens: int
    stop_reason: StopReason
    assistant_delta: AssistantContent | None = None
