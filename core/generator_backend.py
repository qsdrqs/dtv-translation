from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import Any

from core.llm_output import AssistantContent
from core.types import GenerateContext, GenerateResult, StopReason


def infer_stop_reason(
    delta_text: str,
    delta_tokens: int,
    max_new_length: int,
    eos_reached: bool,
) -> StopReason:
    if eos_reached:
        return StopReason(kind="eos", detail="")
    if max_new_length > 0 and delta_tokens >= max_new_length:
        return StopReason(kind="max_length", detail=str(max_new_length))
    stripped = delta_text.rstrip()
    if stripped.endswith(";") or stripped.endswith("}"):
        return StopReason(kind="boundary", detail="; or }")
    if not delta_text:
        return StopReason(kind="empty", detail="")
    return StopReason(kind="unknown", detail="")


class GeneratorBackend(ABC):
    def __init__(
        self,
        model_name: str,
        stop_criteria_factory: Callable[[Any], Sequence[Any]] | None = None,
    ) -> None:
        self.model_name = model_name
        self.stop_criteria_factory = stop_criteria_factory

    def _render_content(self, content: str | AssistantContent) -> str:
        if isinstance(content, AssistantContent):
            return content.render()
        return content

    @abstractmethod
    def generate_step(self, context: GenerateContext) -> GenerateResult:
        raise NotImplementedError
