from __future__ import annotations

from pathlib import Path

from c_rust.feedback import RUST_FEEDBACK_LANG
from c_rust.oracles import RustcOracle
from c_rust.render import CRustRenderer
from controller.adapters import GeneratorAdapter
from controller.loop import run_dtv_loop
from controller.policy import DefaultPolicy, DefaultPolicyConfig
from controller.stop_criteria import DTVStoppingCriteria, RUST_PROFILE
from core.budget import Budget
from core.llm_output import WriteRegionParser
from core.types import Action, TranslationSample, Verdict
from feedback.feedback import FeedbackState
from rollback.manager import RollbackManager
from test.e2e.mock_llm_backend import MockLLMBackend


PROMPT_PREFIX = "Translate the following C code into Rust:"


def test_bailout_end_to_end(tmp_path: Path) -> None:
    """Verify bailout triggers when DTV is stuck at the same rollback target.

    The mock LLM output contains multiple fn main() blocks, each with a type
    error (assigning a string literal to i32). After each verify-fail the
    policy rolls back to the empty prefix. With bailout_visit_threshold=3 the
    third consecutive failure at the same target triggers TERMINATE(bailout).

    The bailout handler replaces the raw prefix with rendered code from the
    last artifact (includes closing braces added by the renderer).
    """
    base_dir = Path(__file__).resolve().parent
    c_source_path = base_dir / "bailout_c_source.c"
    llm_output_path = base_dir / "llm_output.md"

    c_program = c_source_path.read_text(encoding="utf-8").strip()
    sample = TranslationSample(
        source_code=c_program,
        source_lang="c",
        test_cases=[],
    )

    source_text = llm_output_path.read_text(encoding="utf-8")
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

    prompt = f"""\
{PROMPT_PREFIX}
```c
{c_program}
```
"""

    renderer = CRustRenderer(sample=sample)
    oracles = [RustcOracle()]
    budget = Budget(gen_tokens_budget=len(source_text) * 2)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = DefaultPolicy(DefaultPolicyConfig(
        enable_feedback=False,
        bailout_visit_threshold=3,
    ))

    final_prefix, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=oracles,
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=RUST_FEEDBACK_LANG,
        max_steps=200,
        max_new_length=2048,
        prompt_prefix=prompt,
    )

    # (a) Trace ends with TERMINATE after stuck detection.
    assert trace, "Expected a non-empty trace"
    assert trace[-1].action == Action.TERMINATE, (
        f"Expected last trace event to be TERMINATE, got {trace[-1].action}"
    )

    # (b) Returned prefix is rendered code (not raw prefix).
    assert final_prefix.rstrip().endswith("}"), (
        "Expected rendered prefix to end with closing brace; "
        f"got: ...{final_prefix[-40:]!r}"
    )
    assert "fn main()" in final_prefix, (
        "Expected prefix to contain fn main()"
    )

    # (c) Trace contains rollback events showing the stuck pattern.
    rollback_events = [e for e in trace if e.action == Action.ROLLBACK]
    assert len(rollback_events) >= 2, (
        f"Expected at least 2 ROLLBACK events for stuck pattern; "
        f"found {len(rollback_events)}"
    )

    verify_events = [e for e in trace if e.action == Action.VERIFY]
    assert verify_events, "Expected at least one VERIFY event"
    fail_outputs = [
        (e.step, o.oracle_name, o.verdict.value)
        for e in verify_events
        for o in e.oracle_outputs
        if o.verdict == Verdict.FAIL
    ]
    assert len(fail_outputs) >= 3, (
        f"Expected at least 3 FAIL oracle outputs to trigger bailout; "
        f"found {len(fail_outputs)}: {fail_outputs}"
    )
