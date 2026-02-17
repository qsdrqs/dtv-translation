from __future__ import annotations

import json
from pathlib import Path

from c_rust.oracles import FunctionOracle, ProgramOracle, RustcOracle
from c_rust.render import CRustRenderer
from controller.adapters import GeneratorAdapter
from controller.loop import run_dtv_loop
from controller.policy import DefaultPolicy, DefaultPolicyConfig
from controller.stop_criteria import DTVStoppingCriteria, RUST_PROFILE
from core.budget import Budget
from core.llm_output import FenceParser
from core.types import Action, TestCase, TranslationSample, Verdict
from feedback.feedback import FeedbackState
from rollback.manager import RollbackManager
from test.e2e.mock_llm_backend import MockLLMBackend


PROMPT_PREFIX = "Translated the following C code into Rust:"


def _load_tests(path: Path) -> list[TestCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("tests")
    if not isinstance(raw, list):
        raise ValueError("tests JSON must be a list or a {\"tests\": [...]} object")
    cases: list[TestCase] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"test case {idx} must be an object")
        if "stdin" not in item:
            raise ValueError(f"test case {idx} missing 'stdin'")
        stdin = item["stdin"]
        if not isinstance(stdin, str):
            stdin = str(stdin)
        cases.append(TestCase(stdin=stdin, test_id=item.get("test_id")))
    return cases


def test_trap_end_to_end() -> None:
    base_dir = Path(__file__).resolve().parent
    c_source_path = base_dir / "trap_c_source.c"
    tests_path = base_dir / "trap_tests.json"
    source_path = base_dir / "llm_output.md"
    expected_rust_path = base_dir / "trap_rs.rs"

    c_program = c_source_path.read_text(encoding="utf-8").strip()
    test_cases = _load_tests(tests_path)
    sample = TranslationSample(
        source_code=c_program,
        source_lang="c",
        test_cases=test_cases,
    )

    source_text = source_path.read_text(encoding="utf-8")
    MockLLMBackend.configure(source_path=source_path, chunk_size=1)

    fence_parser = FenceParser(allowed_langs=("rust", "rs"))
    generator = GeneratorAdapter(
        model_name="mock",
        stop_criteria_factory=lambda tok: [
            DTVStoppingCriteria(tok, RUST_PROFILE, fence_parser=fence_parser)
        ],
        fence_parser=fence_parser,
        backend_cls=MockLLMBackend,
    )

    prompt = f'''
{PROMPT_PREFIX}
```c
{c_program}
```
'''

    renderer = CRustRenderer(sample=sample)
    oracles = [RustcOracle(), FunctionOracle(), ProgramOracle()]
    budget = Budget(gen_tokens_budget=len(source_text) + 16)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = DefaultPolicy(DefaultPolicyConfig(enable_feedback=False))

    final_prefix, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=oracles,
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        max_steps=len(source_text) + 64,
        max_new_length=1024,
        prompt_prefix=prompt,
    )

    expected_rust = expected_rust_path.read_text(encoding="utf-8")
    assert final_prefix == expected_rust
    assert trace
    verify_events = [event for event in trace if event.action == Action.VERIFY]
    assert verify_events, "Expected at least one VERIFY event"
    failing_outputs = [
        (
            event.step,
            output.oracle_name,
            output.verdict.value,
            tuple(diag.message for diag in output.diagnostics),
        )
        for event in verify_events
        for output in event.oracle_outputs
        if output.verdict != Verdict.PASS
    ]
    assert not failing_outputs, (
        "Expected all oracle outputs to PASS for trap test; "
        f"found failures: {failing_outputs}"
    )
