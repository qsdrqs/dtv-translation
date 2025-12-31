from __future__ import annotations

from collections.abc import Callable, Sequence

import transformers
from transformers import StoppingCriteria, StoppingCriteriaList

from core.logger import get_logger
from core.types import GenerateContext, GenerateResult, StopReason

logger = get_logger(__name__)


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


class GeneratorBackend:
    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-4B-Instruct-2507",
        stop_criteria_factory: Callable[
            [transformers.PreTrainedTokenizerBase],
            Sequence[StoppingCriteria],
        ]
        | None = None,
    ) -> None:
        self.model_name = model_name
        self.tokenizer = transformers.AutoTokenizer.from_pretrained(model_name)
        self.model = transformers.AutoModelForCausalLM.from_pretrained(model_name)
        stop_criteria = stop_criteria_factory(self.tokenizer) if stop_criteria_factory is not None else []
        self.stop_criteria: StoppingCriteriaList = StoppingCriteriaList(list(stop_criteria))

    def _build_prompt(self, context: GenerateContext) -> str:
        if not context.messages:
            return ""

        normalized: list[tuple[str, str, bool]] = []
        for msg in context.messages:
            if isinstance(msg, dict):
                role = str(msg.get("role", ""))
                content = str(msg.get("content", ""))
                stop = bool(msg.get("stop", False))
            else:
                role = msg.role
                content = msg.content
                stop = msg.stop
            normalized.append((role, content, stop))

        chat_messages = [{"role": role, "content": content} for role, content, _ in normalized]
        last_role = normalized[-1][0] if normalized else ""
        add_generation_prompt = last_role != "assistant"
        if hasattr(self.tokenizer, "apply_chat_template"):
            try:
                return self.tokenizer.apply_chat_template(
                    chat_messages,
                    tokenize=False,
                    add_generation_prompt=add_generation_prompt,
                )
            except Exception:
                pass

        parts: list[str] = []
        for role, content, stop in normalized:
            role_prefix = f"{role}: " if role else ""
            parts.append(f"{role_prefix}{content}")
            if stop:
                parts.append("")
        return "\n".join(parts)

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
        outputs = self.model.generate(
            inputs.input_ids,
            max_new_tokens=context.max_new_length,
            stopping_criteria=self.stop_criteria,
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
