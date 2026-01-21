from __future__ import annotations

from collections.abc import Callable, Sequence

import transformers

from core.generator_backend import GeneratorBackend
from core.qwen_generator_backend import QwenGeneratorBackend
from core.interfaces import Generator
from core.types import GenerateContext, GenerateResult
from transformers import StoppingCriteria


class GeneratorAdapter(Generator):
    def __init__(
        self,
        model_name: str,
        stop_criteria_factory: Callable[
            [transformers.PreTrainedTokenizerBase],
            Sequence[StoppingCriteria],
        ]
        | None = None,
        backend_cls: type[GeneratorBackend] = QwenGeneratorBackend,
    ) -> None:
        self.backend = backend_cls(
            model_name=model_name,
            stop_criteria_factory=stop_criteria_factory,
        )

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        return self.backend.generate_step(context)
