from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import Any

from core.llm_output import AssistantContent
from core.types import GenerateContext, GenerateResult, GenerationChannel, StopReason


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
        do_sample: bool | None = None,
        temperature: float | None = None,
        enable_thinking: bool | None = None,
    ) -> None:
        self.model_name = model_name
        self.stop_criteria_factory = stop_criteria_factory
        self.do_sample = do_sample
        self.temperature = temperature
        self.enable_thinking = enable_thinking

    def _render_content(self, content: str | AssistantContent) -> str:
        if isinstance(content, AssistantContent):
            return content.render()
        return content

    def _sampling_kwargs(self) -> dict[str, Any]:
        # Omit None-valued keys so the model's loaded generation_config takes
        # effect. In transformers 5.5.x, passing do_sample=None as a kwarg
        # unconditionally overwrites the model's do_sample=True, and the
        # `None is not True` check then silently routes to greedy decoding.
        kwargs: dict[str, Any] = {}
        if self.do_sample is not None:
            kwargs["do_sample"] = self.do_sample
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        return kwargs

    def set_generation_channel(self, channel: GenerationChannel) -> None:
        _ = channel

    def set_stop_on_write_region_open(self, enabled: bool) -> None:
        _ = enabled

    @abstractmethod
    def generate_step(self, context: GenerateContext) -> GenerateResult:
        raise NotImplementedError
