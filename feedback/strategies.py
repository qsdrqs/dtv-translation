from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Sequence

from core.llm_output import AssistantContent
from core.types import GenerateMessage


class FeedbackStrategy(ABC):
    @abstractmethod
    def apply(
        self,
        messages: Sequence[GenerateMessage | dict[str, Any]],
        feedback: str,
        prefix: str | AssistantContent,
        response_prefix: str | AssistantContent | None = None,
    ) -> list[GenerateMessage | dict[str, Any]]:
        raise NotImplementedError

    @staticmethod
    def _normalize_messages(
        messages: Sequence[GenerateMessage | dict[str, Any]],
    ) -> list[GenerateMessage]:
        normalized: list[GenerateMessage] = []
        for msg in messages:
            if isinstance(msg, dict):
                if "stop" not in msg:
                    raise ValueError("GenerateMessage requires explicit stop")
                raw_content = msg.get("content", "")
                content = raw_content if isinstance(raw_content, AssistantContent) else str(raw_content)
                normalized.append(
                    GenerateMessage(
                        role=str(msg.get("role", "")),
                        content=content,
                        stop=bool(msg["stop"]),
                    )
                )
            else:
                normalized.append(msg)
        return normalized

    @staticmethod
    def _render_prefix(prefix: str | AssistantContent) -> str:
        return prefix.render() if isinstance(prefix, AssistantContent) else prefix

    @staticmethod
    def _last_assistant_index(messages: list[GenerateMessage]) -> int | None:
        return next(
            (idx for idx in range(len(messages) - 1, -1, -1) if messages[idx].role == "assistant"),
            None,
        )


# For feedback strategy A
@dataclass(frozen=True)
class AssistantInlineRepair(FeedbackStrategy):
    def apply(
        self,
        messages: Sequence[GenerateMessage | dict[str, Any]],
        feedback: str,
        prefix: str | AssistantContent,
        response_prefix: str | AssistantContent | None = None,
    ) -> list[GenerateMessage | dict[str, Any]]:
        normalized = self._normalize_messages(messages)
        assistant_index = self._last_assistant_index(normalized)

        content = self._render_prefix(prefix)
        if feedback:
            content = f"{content}\n\n{feedback}"

        if assistant_index is None:
            normalized.append(GenerateMessage(role="assistant", content=content, stop=False))
        else:
            stop = normalized[assistant_index].stop
            normalized[assistant_index] = GenerateMessage(role="assistant", content=content, stop=stop)

        return list(normalized)


# For feedback strategy B
@dataclass(frozen=True)
class UserRoundRepair(FeedbackStrategy):
    def apply(
        self,
        messages: Sequence[GenerateMessage | dict[str, Any]],
        feedback: str,
        prefix: str | AssistantContent,
        response_prefix: str | AssistantContent | None = None,
    ) -> list[GenerateMessage | dict[str, Any]]:
        normalized = self._normalize_messages(messages)

        assistant_index = self._last_assistant_index(normalized)

        content = self._render_prefix(prefix)
        if assistant_index is None:
            normalized.append(GenerateMessage(role="assistant", content=content, stop=True))
        else:
            normalized = normalized[: assistant_index + 1]
            normalized[assistant_index] = GenerateMessage(role="assistant", content=content, stop=True)

        normalized.append(GenerateMessage(role="user", content=feedback, stop=True))
        next_prefix = AssistantContent.empty()
        if response_prefix is not None:
            next_prefix = (
                response_prefix
                if isinstance(response_prefix, AssistantContent)
            else AssistantContent.from_text(response_prefix)
            )
        normalized.append(GenerateMessage(role="assistant", content=next_prefix, stop=False))

        return list(normalized)
