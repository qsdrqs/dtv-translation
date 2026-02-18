from __future__ import annotations

from pathlib import Path

from core.generator_backend import GeneratorBackend, infer_stop_reason
from core.types import GenerateContext, GenerateResult, GenerationChannel, StopReason


class _CharTokenizer:
    def decode(self, ids, skip_special_tokens: bool = True) -> str:
        _ = skip_special_tokens
        if hasattr(ids, "tolist"):
            ids = ids.tolist()
        if isinstance(ids, list) and ids and isinstance(ids[0], list):
            flat: list[int] = []
            for item in ids:
                flat.extend(item)
            ids = flat
        return "".join(chr(int(value)) for value in ids)


class MockLLMBackend(GeneratorBackend):
    source_path: Path | None = None
    chunk_size: int = 1

    def __init__(self, model_name: str, stop_criteria_factory=None) -> None:
        super().__init__(model_name=model_name, stop_criteria_factory=stop_criteria_factory)
        if self.source_path is None:
            raise ValueError("MockLLMBackend.source_path is not set")
        self._content = self.source_path.read_text(encoding="utf-8")
        self._cursor = 0
        self._token_ids: list[int] = []
        self._stop_criteria = self._build_stop_criteria()
        self._generation_channel = GenerationChannel.CONTINUATION

    @classmethod
    def configure(cls, *, source_path: Path, chunk_size: int = 1) -> None:
        cls.source_path = source_path
        cls.chunk_size = chunk_size

    def _build_stop_criteria(self) -> list:
        if self.stop_criteria_factory is None:
            return []
        criteria = self.stop_criteria_factory(_CharTokenizer())
        return list(criteria) if criteria is not None else []

    def _set_prompt_token_count(self) -> None:
        prompt_token_count = len(self._token_ids)
        for criterion in self._stop_criteria:
            channel_setter = getattr(criterion, "set_generation_channel", None)
            if callable(channel_setter):
                channel_setter(self._generation_channel)
            setter = getattr(criterion, "set_prompt_token_count", None)
            if setter is None:
                raise TypeError(
                    "StoppingCriteria must implement set_prompt_token_count(prompt_token_count)"
                )
            if not callable(setter):
                raise TypeError("set_prompt_token_count is not callable on StoppingCriteria")
            setter(prompt_token_count)

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        self._generation_channel = context.channel
        if self._cursor >= len(self._content):
            return GenerateResult(
                delta_text="",
                delta_tokens=0,
                stop_reason=StopReason(kind="eos", detail=""),
            )

        if context.max_new_length <= 0:
            return GenerateResult(
                delta_text="",
                delta_tokens=0,
                stop_reason=StopReason(kind="max_length", detail=str(context.max_new_length)),
            )

        if self._stop_criteria:
            self._set_prompt_token_count()

        pieces: list[str] = []
        total_tokens = 0
        stop_triggered = False
        remaining_budget = context.max_new_length

        while self._cursor < len(self._content) and remaining_budget > 0:
            remaining = len(self._content) - self._cursor
            step_len = min(self.chunk_size, remaining, remaining_budget)
            piece = self._content[self._cursor : self._cursor + step_len]
            self._cursor += step_len
            remaining_budget -= step_len
            if piece:
                self._token_ids.extend(ord(ch) for ch in piece)
                pieces.append(piece)
                total_tokens += len(piece)

            if self._stop_criteria and piece:
                import torch

                input_ids = torch.tensor([self._token_ids], dtype=torch.long)
                for criterion in self._stop_criteria:
                    result = criterion(input_ids, None)
                    stop_triggered = bool(result.item()) if hasattr(result, "item") else bool(result)
                    if stop_triggered:
                        break
            if stop_triggered:
                break

        chunk = "".join(pieces)
        eos_reached = self._cursor >= len(self._content)
        stop_reason = infer_stop_reason(
            delta_text=chunk,
            delta_tokens=total_tokens,
            max_new_length=context.max_new_length,
            eos_reached=eos_reached,
        )
        if stop_triggered:
            stop_reason = StopReason(kind="boundary", detail="stop_criteria")
        elif self._stop_criteria and stop_reason.kind == "boundary":
            stop_reason = StopReason(kind="unknown", detail="")
        return GenerateResult(
            delta_text=chunk,
            delta_tokens=total_tokens,
            stop_reason=stop_reason,
        )
