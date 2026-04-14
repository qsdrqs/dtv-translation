from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, cast

import torch
import transformers
from transformers import StoppingCriteria, StoppingCriteriaList

from core.generator_backend import GeneratorBackend, infer_stop_reason
from core.llm_output import AssistantContent
from core.logger import get_logger
from core.types import GenerateContext, GenerateResult, GenerationChannel

logger = get_logger(__name__)

# Gemma 4 chat template tokens.
_TURN_START = "<|turn>"
_TURN_END = "<turn|>"
_THINK_TOKEN = "<|think|>"

# Gemma uses "model" for assistant role in its chat template.
_ROLE_MAP: dict[str, str] = {"assistant": "model", "user": "user", "system": "system"}


class GemmaGeneratorBackend(GeneratorBackend):
    """Generator backend for Google Gemma 4 models.

    Uses ``<|turn>``/``<turn|>`` chat template format instead of the
    ChatML ``<|im_start|>``/``<|im_end|>`` tokens used by Qwen.
    """

    def __init__(
        self,
        model_name: str = "google/gemma-4-E4B",
        stop_criteria_factory: Callable[
            [transformers.PreTrainedTokenizerBase],
            Sequence[StoppingCriteria],
        ]
        | None = None,
        do_sample: bool | None = None,
        temperature: float | None = None,
        enable_thinking: bool | None = None,
    ) -> None:
        super().__init__(
            model_name=model_name,
            stop_criteria_factory=stop_criteria_factory,
            do_sample=do_sample,
            temperature=temperature,
            enable_thinking=enable_thinking,
        )
        self.model_name = model_name
        use_cuda = torch.cuda.is_available()
        model_kwargs: dict[str, object] = {}
        if use_cuda:
            model_kwargs["device_map"] = "auto"
            model_kwargs["dtype"] = (
                torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
            )
        self.tokenizer = transformers.AutoTokenizer.from_pretrained(model_name)
        self.model = transformers.AutoModelForCausalLM.from_pretrained(model_name, **model_kwargs)
        self.model.eval()
        self._use_cuda = use_cuda
        stop_criteria = stop_criteria_factory(self.tokenizer) if stop_criteria_factory is not None else []
        self.stop_criteria: StoppingCriteriaList = StoppingCriteriaList(list(stop_criteria))

    def set_generation_channel(self, channel: GenerationChannel) -> None:
        for criteria in self.stop_criteria:
            setter = getattr(criteria, "set_generation_channel", None)
            if callable(setter):
                setter(channel)

    def set_stop_on_write_region_open(self, enabled: bool) -> None:
        for criteria in self.stop_criteria:
            setter = getattr(criteria, "set_stop_on_write_region_open", None)
            if callable(setter):
                setter(enabled)

    def _build_prompt(self, context: GenerateContext) -> str:
        """Build a Gemma chat-formatted prompt string.

        Format per turn:
          <|turn>{role}\\n{content}<turn|>\\n   (closed turn)
          <|turn>{role}\\n{content}             (open turn, no closing)

        The assistant role is mapped to ``model`` per Gemma convention.
        """
        if not context.messages:
            return ""

        parts: list[str] = []
        has_system = False

        for msg in context.messages:
            if isinstance(msg, dict):
                if "stop" not in msg:
                    raise ValueError("GenerateMessage requires explicit stop")
                role = str(msg.get("role", ""))
                raw_content = msg.get("content", "")
                content = (
                    raw_content if isinstance(raw_content, AssistantContent) else str(raw_content)
                )
                stop = bool(msg["stop"])
            else:
                role = msg.role
                content = msg.content
                stop = msg.stop

            rendered = self._render_content(content)
            gemma_role = _ROLE_MAP.get(role, role)

            if role == "system":
                has_system = True

            segment = f"{_TURN_START}{gemma_role}\n"

            # Gemma controls thinking via a token in the system message.
            if self.enable_thinking is True and role == "system":
                segment += f"{_THINK_TOKEN}\n"

            segment += rendered
            if stop:
                segment += f"{_TURN_END}\n"
            parts.append(segment)

        # If thinking is enabled but no system message exists, prepend a
        # minimal system turn carrying only the think token.
        if self.enable_thinking is True and not has_system:
            parts.insert(0, f"{_TURN_START}system\n{_THINK_TOKEN}\n{_TURN_END}\n")

        return "".join(parts)

    def _get_eos_token_ids(self) -> set[int]:
        if self.model.generation_config is None:
            raise RuntimeError(f"Model {self.model_name} has no generation_config")
        eos_ids = self.model.generation_config.eos_token_id
        if eos_ids is None:
            eos_ids = self.tokenizer.eos_token_id
        if eos_ids is None:
            return set()
        if isinstance(eos_ids, (list, tuple, set)):
            return {int(token_id) for token_id in eos_ids}
        return {int(eos_ids)}

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        prompt = self._build_prompt(context)
        logger.model_input("%s", prompt)

        inputs = self.tokenizer(prompt, return_tensors="pt")
        if self._use_cuda:
            inputs = inputs.to(self.model.device)
        prompt_token_count = int(inputs.input_ids.shape[-1])
        self.set_generation_channel(context.channel)
        for criteria in self.stop_criteria:
            setter = getattr(criteria, "set_prompt_token_count", None)
            if setter is None:
                raise TypeError(
                    "StoppingCriteria must implement set_prompt_token_count(prompt_token_count)"
                )
            if not callable(setter):
                raise TypeError("set_prompt_token_count is not callable on StoppingCriteria")
            setter(prompt_token_count)
        model = cast(Any, self.model)
        outputs = model.generate(
            inputs.input_ids,
            attention_mask=inputs.attention_mask,
            max_new_tokens=context.max_new_length,
            stopping_criteria=self.stop_criteria,
            do_sample=self.do_sample,
            temperature=self.temperature,
        )

        output_ids = outputs[0]
        input_len = inputs.input_ids.shape[-1]
        new_ids = output_ids[input_len:]
        delta_text = self.tokenizer.decode(new_ids, skip_special_tokens=True)
        logger.model_output("%s", f"{prompt}{delta_text}")

        delta_tokens = int(new_ids.shape[-1]) if new_ids is not None else 0
        eos_ids = self._get_eos_token_ids()
        eos_reached = False
        if eos_ids and new_ids is not None and delta_tokens > 0:
            eos_reached = int(new_ids[-1]) in eos_ids
        stop_reason = infer_stop_reason(delta_text, delta_tokens, context.max_new_length, eos_reached)
        return GenerateResult(delta_text=delta_text, delta_tokens=delta_tokens, stop_reason=stop_reason)
