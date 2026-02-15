from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from core.llm_output import AssistantContent
from core.types import GenerateMessage


class FeedbackStrategy(Protocol):
    def apply(
        self,
        messages: Sequence[GenerateMessage | dict[str, Any]],
        feedback: str,
        prefix: str | AssistantContent,
    ) -> list[GenerateMessage | dict[str, Any]]:
        ...


@dataclass(frozen=True)
class AppendToLastAssistant:
    """Appends feedback to the last assistant message."""

    def apply(
        self,
        messages: Sequence[GenerateMessage | dict[str, Any]],
        feedback: str,
        prefix: str | AssistantContent,
    ) -> list[GenerateMessage | dict[str, Any]]:
        normalized: list[GenerateMessage | dict[str, Any]] = []
        for msg in messages:
            if isinstance(msg, dict):
                if "stop" not in msg:
                    raise ValueError("GenerateMessage requires explicit stop")
                normalized.append(
                    GenerateMessage(
                        role=str(msg.get("role", "")),
                        content=str(msg.get("content", "")),
                        stop=bool(msg["stop"]),
                    )
                )
            else:
                normalized.append(msg)
        assistant_index = next(
            (
                idx
                for idx in range(len(normalized) - 1, -1, -1)
                if isinstance(normalized[idx], GenerateMessage) and normalized[idx].role == "assistant"  # type: ignore[union-attr]
            ),
            None,
        )

        content = prefix.render() if isinstance(prefix, AssistantContent) else prefix
        if feedback:
            content = f"{content}\n\n{feedback}"

        stop = False
        if assistant_index is None:
            normalized.append(GenerateMessage(role="assistant", content=content, stop=stop))
        else:
            existing = normalized[assistant_index]
            stop = existing.stop if isinstance(existing, GenerateMessage) else False
            normalized[assistant_index] = GenerateMessage(role="assistant", content=content, stop=stop)
        return normalized
