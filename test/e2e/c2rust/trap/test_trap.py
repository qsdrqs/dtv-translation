from __future__ import annotations

import json
from pathlib import Path

from c_rust.feedback import RUST_FEEDBACK_LANG
from c_rust.oracles import FunctionOracle, RustcOracle
from c_rust.render import CRustRenderer
from controller.adapters import GeneratorAdapter
from controller.loop import run_dtv_loop
from controller.policy import DefaultPolicy, DefaultPolicyConfig
from controller.stop_criteria import DTVStoppingCriteria, RUST_PROFILE
from core.budget import Budget
from core.llm_output import BEGIN_WRITE_CODE, END_WRITE_CODE, WriteRegionParser
from core.types import Action, TestCase, TranslationSample, Verdict
from feedback.feedback import FeedbackState
from rollback.manager import RollbackManager
from test.e2e.mock_llm_backend import MockLLMBackend


PROMPT_PREFIX = "Translate the following C code into Rust, keep the same function order:"


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


def test_trap_end_to_end(tmp_path: Path) -> None:
    base_dir = Path(__file__).resolve().parent
    c_source_path = base_dir / "trap_c_source.c"
    tests_path = base_dir / "trap_tests.json"
    expected_rust_path = base_dir / "trap_rs.rs"

    c_program = c_source_path.read_text(encoding="utf-8").strip()
    test_cases = _load_tests(tests_path)
    sample = TranslationSample(
        source_code=c_program,
        source_lang="c",
        test_cases=test_cases,
    )

    expected_rust = expected_rust_path.read_text(encoding="utf-8")
    source_text = (
        "Here is the translated Rust code for the provided C code snippet:\n\n"
        f"{BEGIN_WRITE_CODE}\n"
        f"{expected_rust.rstrip()}\n"
        f"{END_WRITE_CODE}\n"
    )
    source_path = tmp_path / "llm_output.md"
    source_path.write_text(source_text, encoding="utf-8")
    MockLLMBackend.configure(source_path=source_path, chunk_size=1)

    write_region_parser = WriteRegionParser()
    generator = GeneratorAdapter(
        model_name="mock",
        stop_criteria_factory=lambda tok: [
            DTVStoppingCriteria(tok, RUST_PROFILE, write_region_parser=write_region_parser)
        ],
        write_region_parser=write_region_parser,
        backend_cls=MockLLMBackend,
    )

    prompt = f'''
{PROMPT_PREFIX}
```c
{c_program}
```
'''

    renderer = CRustRenderer(sample=sample)
    oracles = [RustcOracle(), FunctionOracle()]
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
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=len(source_text) + 64,
        max_new_length=1024,
        prompt_prefix=prompt,
    )

    assert expected_rust.rstrip() in final_prefix
    assert trace
    verify_events = [event for event in trace if event.action == Action.VERIFY]
    assert verify_events, "Expected at least one VERIFY event"
    function_outputs = [
        (
            event.step,
            output.verdict.value,
            tuple(diag.message for diag in output.diagnostics),
        )
        for event in verify_events
        for output in event.oracle_outputs
        if output.oracle_name == "function_diff"
    ]
    assert function_outputs, "Expected function_diff to run at least once"
    assert len(function_outputs) >= 2, (
        "Expected function_diff to run at least twice for trap test; "
        f"found {len(function_outputs)} calls: {function_outputs}"
    )
    not_applicable_outputs = [
        (step, verdict, diagnostics)
        for step, verdict, diagnostics in function_outputs
        if verdict == Verdict.NOT_APPLICABLE.value
    ]
    assert len(not_applicable_outputs) >= 1, (
        "Expected at least one NOT_APPLICABLE function_diff output for main signature mismatch; "
        f"found: {not_applicable_outputs}"
    )
    assert not_applicable_outputs[0][2] == ("return_type_mismatch",), (
        "Expected function_diff NOT_APPLICABLE reason to be return_type_mismatch; "
        f"found: {not_applicable_outputs}"
    )
    pass_outputs = [
        (step, verdict, diagnostics)
        for step, verdict, diagnostics in function_outputs
        if verdict == Verdict.PASS.value
    ]
    assert len(pass_outputs) == 1, (
        "Expected exactly one PASS function_diff output for trap function; "
        f"found: {pass_outputs}"
    )
    failing_outputs = [
        (
            event.step,
            output.oracle_name,
            output.verdict.value,
            tuple(diag.message for diag in output.diagnostics),
        )
        for event in verify_events
        for output in event.oracle_outputs
        if output.verdict == Verdict.FAIL
    ]
    assert not failing_outputs, (
        "Expected no FAIL oracle outputs for trap test; "
        f"found failures: {failing_outputs}"
    )
