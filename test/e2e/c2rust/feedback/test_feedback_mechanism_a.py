from __future__ import annotations

import shutil
import subprocess
from typing import ClassVar

import pytest
import torch

from c_rust.oracles import ProgramOracle, RustcOracle
from c_rust.render import CRustRenderer
from controller.adapters import GeneratorAdapter
from controller.loop import run_dtv_loop
from controller.policy import DefaultPolicy, DefaultPolicyConfig
from controller.stop_criteria import DTVStoppingCriteria, RUST_PROFILE
from core.budget import Budget
from core.generator_backend import GeneratorBackend, infer_stop_reason
from core.llm_output import AssistantContent, FenceParser
from core.types import (
    Action,
    FeedbackMechanism,
    FeedbackMode,
    GenerateContext,
    GenerateResult,
    GenerationChannel,
    Granularity,
    StopReason,
    TestCase,
    TranslationSample,
    Verdict,
)
from feedback.feedback import FeedbackState
from rollback.manager import RollbackManager


class _ScriptedBackend(GeneratorBackend):
    scripts: ClassVar[tuple[str, ...]] = ()
    seen_assistant_messages: ClassVar[list[str]] = []
    seen_user_messages: ClassVar[list[str]] = []

    @classmethod
    def configure(cls, scripts: tuple[str, ...]) -> None:
        cls.scripts = scripts
        cls.seen_assistant_messages = []
        cls.seen_user_messages = []

    def __init__(self, model_name: str, stop_criteria_factory=None) -> None:
        super().__init__(model_name=model_name, stop_criteria_factory=stop_criteria_factory)
        self._index = 0
        self._token_ids: list[int] = []
        self._stop_criteria = self._build_stop_criteria()
        self._generation_channel = GenerationChannel.CONTINUATION

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
            if callable(setter):
                setter(prompt_token_count)

    def generate_step(self, context: GenerateContext) -> GenerateResult:
        self.__class__.seen_assistant_messages.append(_last_assistant_message(context))
        self.__class__.seen_user_messages.append(_last_user_message(context))
        self._generation_channel = context.channel
        if self._index >= len(self.__class__.scripts):
            return GenerateResult(
                delta_text="",
                delta_tokens=0,
                stop_reason=StopReason(kind="eos", detail=""),
            )

        delta = self.__class__.scripts[self._index]
        self._index += 1
        if self._stop_criteria and delta:
            self._set_prompt_token_count()
            self._token_ids.extend(ord(ch) for ch in delta)
            input_ids = torch.tensor([self._token_ids], dtype=torch.long)
            for criterion in self._stop_criteria:
                _ = criterion(input_ids, None)
        delta_tokens = len(delta)
        stop_reason = infer_stop_reason(
            delta_text=delta,
            delta_tokens=delta_tokens,
            max_new_length=context.max_new_length,
            eos_reached=self._index >= len(self.__class__.scripts),
        )
        return GenerateResult(
            delta_text=delta,
            delta_tokens=delta_tokens,
            stop_reason=stop_reason,
        )


class _MainBackend(_ScriptedBackend):
    pass


class _FeedbackBackend(_ScriptedBackend):
    pass


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


def _last_assistant_message(context: GenerateContext) -> str:
    for message in reversed(context.messages):
        role = getattr(message, "role", None)
        if role != "assistant":
            continue
        content = getattr(message, "content", "")
        if isinstance(content, AssistantContent):
            return content.render()
        return str(content)
    return ""


def _last_user_message(context: GenerateContext) -> str:
    for message in reversed(context.messages):
        role = getattr(message, "role", None)
        if role != "user":
            continue
        return str(getattr(message, "content", ""))
    return ""


def _ensure_rustc() -> None:
    rustc = shutil.which("rustc")
    if rustc is None:
        pytest.skip("rustc not available")
    try:
        subprocess.run(
            [rustc, "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("rustc not functional")


def _ensure_gcc() -> None:
    gcc = shutil.which("gcc")
    if gcc is None:
        pytest.skip("gcc not available")
    try:
        subprocess.run(
            [gcc, "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("gcc not functional")


def _build_generator(backend_cls: type[GeneratorBackend]) -> GeneratorAdapter:
    fence_parser = FenceParser(allowed_langs=("rust", "rs"))

    def _stop_factory(tokenizer):
        return [DTVStoppingCriteria(tokenizer, RUST_PROFILE, fence_parser=fence_parser)]

    return GeneratorAdapter(
        model_name="mock",
        stop_criteria_factory=_stop_factory,
        fence_parser=fence_parser,
        backend_cls=backend_cls,
    )


def _run_feedback_case(
    *,
    sample: TranslationSample,
    initial_output: str,
    feedback_output: str,
    oracles: list,
    policy: DefaultPolicy,
) -> tuple[str, list]:
    _MainBackend.configure((initial_output,))
    _FeedbackBackend.configure((feedback_output,))
    generator = _build_generator(_MainBackend)
    feedback_generator = _build_generator(_FeedbackBackend)
    renderer = CRustRenderer(sample=sample)
    budget = Budget(gen_tokens_budget=4096)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    prompt_prefix = f"""Translate C to Rust.
```c
{sample.source_code}
```"""
    return run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=oracles,
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_generator=feedback_generator,
        max_steps=20,
        max_new_length=4096,
        prompt_prefix=prompt_prefix,
    )


def test_feedback_e2e_compile_failure_then_repair_success() -> None:
    _ensure_rustc()
    sample = TranslationSample(
        source_code="int main(void) { return 0; }",
        source_lang="c",
        test_cases=[TestCase(stdin="", test_id="empty")],
    )
    initial_output = """```rust
fn main() {
    let x: i32 = \"1\";
}
```"""
    feedback_output = """```rust
fn main() {
    let x: i32 = 1;
}
```"""
    policy = DefaultPolicy(
        DefaultPolicyConfig(
            verify_on_boundary=False,
            verify_on_eos=True,
            eos_granularity=Granularity.PROGRAM,
            enable_feedback=True,
            feedback_mode=FeedbackMode.FENCED,
            max_repair_rounds=1,
            repair_verify_granularity=Granularity.STMT,
        )
    )

    final_prefix, trace = _run_feedback_case(
        sample=sample,
        initial_output=initial_output,
        feedback_output=feedback_output,
        oracles=[RustcOracle()],
        policy=policy,
    )

    actions = [event.action for event in trace]
    assert actions[:7] == [
        Action.GENERATE,
        Action.VERIFY,
        Action.ROLLBACK,
        Action.FEEDBACK,
        Action.APPLY_PATCH,
        Action.VERIFY,
        Action.COMMIT,
    ]
    assert final_prefix == """fn main() {
    let x: i32 = 1;
}
"""
    verify_events = [event for event in trace if event.action == Action.VERIFY]
    assert any(
        any(output.oracle_name == "rustc" and output.verdict == Verdict.FAIL for output in event.oracle_outputs)
        for event in verify_events
    )
    assert any(
        any(output.oracle_name == "rustc" and output.verdict == Verdict.PASS for output in event.oracle_outputs)
        for event in verify_events
    )
    feedback_events = [event for event in trace if event.action == Action.FEEDBACK]
    assert len(feedback_events) == 1
    assert feedback_events[0].notes == "feedback_mechanism=a"
    feedback_message = _FeedbackBackend.seen_assistant_messages[0]
    assert "/* repair feedback:" in feedback_message
    assert "oracle=rustc" in feedback_message
    assert "failed snippet:" in feedback_message


def test_feedback_e2e_behavior_mismatch_then_program_repair_success() -> None:
    _ensure_rustc()
    _ensure_gcc()
    sample = TranslationSample(
        source_code="""#include <stdio.h>

int main(void) {
    printf("42\\n");
    return 0;
}
""",
        source_lang="c",
        test_cases=[TestCase(stdin="", test_id="stdout_case")],
    )
    initial_output = """```rust
fn main() {
    println!("24");
}
```"""
    feedback_output = """```rust
fn main() {
    println!("42");
}
```"""
    policy = DefaultPolicy(
        DefaultPolicyConfig(
            verify_on_boundary=False,
            verify_on_eos=True,
            eos_granularity=Granularity.PROGRAM,
            enable_feedback=True,
            feedback_mode=FeedbackMode.FENCED,
            max_repair_rounds=1,
            repair_verify_granularity=Granularity.PROGRAM,
        )
    )

    final_prefix, trace = _run_feedback_case(
        sample=sample,
        initial_output=initial_output,
        feedback_output=feedback_output,
        oracles=[RustcOracle(), ProgramOracle()],
        policy=policy,
    )

    actions = [event.action for event in trace]
    assert actions[:7] == [
        Action.GENERATE,
        Action.VERIFY,
        Action.ROLLBACK,
        Action.FEEDBACK,
        Action.APPLY_PATCH,
        Action.VERIFY,
        Action.COMMIT,
    ]
    assert final_prefix.strip() == """fn main() {
    println!("42");
}"""
    verify_events = [event for event in trace if event.action == Action.VERIFY]
    assert any(
        any(output.oracle_name == "program_diff" and output.verdict == Verdict.FAIL for output in event.oracle_outputs)
        for event in verify_events
    )
    assert any(
        any(output.oracle_name == "program_diff" and output.verdict == Verdict.PASS for output in event.oracle_outputs)
        for event in verify_events
    )
    feedback_events = [event for event in trace if event.action == Action.FEEDBACK]
    assert len(feedback_events) == 1
    assert feedback_events[0].notes == "feedback_mechanism=a"
    feedback_message = _FeedbackBackend.seen_assistant_messages[0]
    assert "/* repair feedback:" in feedback_message
    assert "oracle=program_diff" in feedback_message
    assert "stdout mismatch" in feedback_message
    assert "oracle=rustc" not in feedback_message


def test_feedback_e2e_program_failure_then_mechanism_b_repair_success() -> None:
    _ensure_rustc()
    _ensure_gcc()
    sample = TranslationSample(
        source_code="""#include <stdio.h>

int main(void) {
    printf("42\\n");
    return 0;
}
""",
        source_lang="c",
        test_cases=[TestCase(stdin="", test_id="stdout_case")],
    )
    initial_output = """```rust
fn main() {
    println!("24");
}
```"""
    feedback_output = """```rust
fn main() {
    println!("42");
}
```"""
    policy = DefaultPolicy(
        DefaultPolicyConfig(
            verify_on_boundary=False,
            verify_on_eos=True,
            eos_granularity=Granularity.PROGRAM,
            enable_feedback=True,
            feedback_mode=FeedbackMode.FENCED,
            feedback_force_mechanism=FeedbackMechanism.B,
            max_repair_rounds=1,
            repair_verify_granularity=Granularity.PROGRAM,
        )
    )

    final_prefix, trace = _run_feedback_case(
        sample=sample,
        initial_output=initial_output,
        feedback_output=feedback_output,
        oracles=[RustcOracle(), ProgramOracle()],
        policy=policy,
    )

    actions = [event.action for event in trace]
    assert actions[:7] == [
        Action.GENERATE,
        Action.VERIFY,
        Action.ROLLBACK,
        Action.FEEDBACK,
        Action.APPLY_PATCH,
        Action.VERIFY,
        Action.COMMIT,
    ]
    assert final_prefix.strip() == """fn main() {
    println!("42");
}"""
    feedback_events = [event for event in trace if event.action == Action.FEEDBACK]
    assert len(feedback_events) == 1
    assert feedback_events[0].notes == "feedback_mechanism=b"
    feedback_prompt = _FeedbackBackend.seen_user_messages[0]
    assert "The previous generated next code snippet was:" in feedback_prompt
    assert "output contract:" in feedback_prompt
