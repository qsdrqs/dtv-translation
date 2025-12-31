from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from core.types import GenerateMessage


class FeedbackStrategy(Protocol):
    def apply(
        self,
        messages: Sequence[GenerateMessage | dict[str, Any]],
        feedback: str,
        prefix: str,
    ) -> list[GenerateMessage | dict[str, Any]]:
        ...


@dataclass(frozen=True)
class AppendToLastAssistant:
    """Appends feedback to the last assistant message."""
    header: str = "# Feedback"  # Optional heading before feedback lines.

    def apply(
        self,
        messages: Sequence[GenerateMessage | dict[str, Any]],
        feedback: str,
        prefix: str,
    ) -> list[GenerateMessage | dict[str, Any]]:
        normalized: list[GenerateMessage | dict[str, Any]] = []
        for msg in messages:
            if isinstance(msg, dict):
                normalized.append(
                    GenerateMessage(
                        role=str(msg.get("role", "")),
                        content=str(msg.get("content", "")),
                        stop=bool(msg.get("stop", False)),
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

        content = prefix
        if feedback:
            if self.header:
                content = f"{content}\n\n{self.header}\n{feedback}"
            else:
                content = f"{content}\n\n{feedback}"

        stop = False
        if assistant_index is None:
            normalized.append(GenerateMessage(role="assistant", content=content, stop=stop))
        else:
            existing = normalized[assistant_index]
            stop = existing.stop if isinstance(existing, GenerateMessage) else False
            normalized[assistant_index] = GenerateMessage(role="assistant", content=content, stop=stop)
        return normalized
