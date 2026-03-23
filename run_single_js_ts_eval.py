from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from js_ts.feedback import TS_FEEDBACK_LANG
from js_ts.oracles import EslintOracle, TscOracle, TscProgramOracle
from js_ts.oracles.compiler_oracle.tsc_driver import _find_type_roots
from js_ts.render import JSToTSRenderer
from controller.adapters import GeneratorAdapter
from controller.loop import run_dtv_loop
from controller.policy import DefaultPolicy, DefaultPolicyConfig
from controller.stop_criteria import DTVStoppingCriteria, TS_PROFILE
from core.llm_output import FenceParser
from core.budget import Budget
from core.types import RenderStatus, TestCase, TranslationSample
from feedback.formatter import RepairFeedbackFormatConfig
from feedback.feedback import FeedbackState
from rollback.manager import RollbackManager


MODEL_NAME = "Qwen/Qwen3-4B-Instruct-2507"
TOKEN_BUDGET = 20480
MAX_NEW_LENGTH = 1024
PROMPT_PREFIX = "Translate the following JavaScript code into TypeScript with strict type annotations:"


def _load_tests(path: Path) -> list[TestCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("tests")
    if not isinstance(raw, list):
        raise ValueError('tests JSON must be a list or a {"tests": [...]} object')
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


def _run_node(script: Path, stdin: str, timeout_s: float = 5.0) -> subprocess.CompletedProcess[str] | None:
    """Run a JS file with node. Returns None on timeout."""
    try:
        return subprocess.run(
            ["node", str(script)],
            input=stdin, capture_output=True, text=True,
            timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired:
        return None


def evaluate_final_program(
    final_prefix: str,
    renderer: JSToTSRenderer,
    js_source: str,
    test_cases: list[TestCase],
) -> tuple[bool, int, int]:
    """Ad-hoc post-loop evaluation: run JS and compiled TS, compare stdout.

    Returns (compiles, tests_passed, tests_total).
    """
    render_result = renderer.try_render(final_prefix)
    if render_result.status != RenderStatus.OK or render_result.artifact is None:
        return False, 0, len(test_cases)

    ts_code = render_result.artifact.code

    with tempfile.TemporaryDirectory(prefix="dtv-eval-jsts-") as tmpdir:
        workdir = Path(tmpdir)
        js_file = workdir / "source.js"
        ts_file = workdir / "output.ts"
        js_file.write_text(js_source, encoding="utf-8")
        ts_file.write_text(ts_code, encoding="utf-8")

        # Compile TS -> JS (no --noEmit; emits output.js next to output.ts)
        type_roots = _find_type_roots()
        type_roots_args = ["--typeRoots", type_roots] if type_roots else []
        tsc_result = subprocess.run(
            ["tsc", "--pretty", "false", "--strict", "--target", "ES2020",
             "--lib", "ES2020,DOM", "--skipLibCheck",
             *type_roots_args, str(ts_file)],
            capture_output=True, text=True, timeout=10.0, check=False,
        )
        if tsc_result.returncode != 0:
            print(f"TS compilation failed:\n{tsc_result.stdout}")
            return False, 0, len(test_cases)

        compiled_js = workdir / "output.js"
        if not compiled_js.exists():
            print("Compiled JS not found after tsc")
            return False, 0, len(test_cases)

        passed = 0
        for i, tc in enumerate(test_cases):
            test_id = tc.test_id or f"test_{i}"
            js_run = _run_node(js_file, tc.stdin)
            ts_run = _run_node(compiled_js, tc.stdin)

            if js_run is None or ts_run is None:
                timed_out = "js" if js_run is None else "ts"
                print(f"  {test_id}: TIMEOUT ({timed_out})")
                continue

            if js_run.stdout == ts_run.stdout and js_run.returncode == ts_run.returncode:
                passed += 1
            else:
                print(f"  {test_id}: MISMATCH "
                      f"(js_exit={js_run.returncode}, ts_exit={ts_run.returncode})")
                if js_run.stdout != ts_run.stdout:
                    print(f"    js_stdout={js_run.stdout[:200]!r}")
                    print(f"    ts_stdout={ts_run.stdout[:200]!r}")

    return True, passed, len(test_cases)


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: python run_single_js_ts_eval.py <js_source> <tests.json> <out.ts>")
        raise SystemExit(2)

    js_source_path = Path(sys.argv[1])
    tests_path = Path(sys.argv[2])
    out_path = Path(sys.argv[3])

    js_program = js_source_path.read_text(encoding="utf-8").strip()
    test_cases = _load_tests(tests_path)

    prompt = f"""\
{PROMPT_PREFIX}
```javascript
{js_program}
```
"""

    sample = TranslationSample(
        source_code=js_program,
        source_lang="js",
        test_cases=test_cases,
    )

    fence_parser = FenceParser(allowed_langs=("typescript", "ts"))
    generator = GeneratorAdapter(
        model_name=MODEL_NAME,
        stop_criteria_factory=lambda tok: [
            DTVStoppingCriteria(tok, TS_PROFILE, fence_parser=fence_parser)
        ],
        fence_parser=fence_parser,
    )
    print("Model loaded:", MODEL_NAME)
    renderer = JSToTSRenderer(sample=sample)
    # TODO: Add FunctionOracle and ProgramDiffTestOracle when implemented
    oracles = [TscOracle(), TscProgramOracle(), EslintOracle()]
    budget = Budget(gen_tokens_budget=TOKEN_BUDGET)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = DefaultPolicy(DefaultPolicyConfig(enable_feedback=True))

    final_prefix, trace = run_dtv_loop(
        generator=generator,
        renderer=renderer,
        oracles=oracles,
        budget=budget,
        feedback_state=feedback_state,
        rollback_manager=rollback_manager,
        policy=policy,
        feedback_lang_config=TS_FEEDBACK_LANG,
        repair_feedback_format_config=RepairFeedbackFormatConfig(include_failed_snippet=True),
        max_steps=500,
        max_new_length=MAX_NEW_LENGTH,
        prompt_prefix=prompt,
    )

    out_path.write_text(final_prefix, encoding="utf-8")
    print(f"Generated TS saved to {out_path}")

    for event in trace:
        if not event.oracle_outputs:
            continue
        print(f"step={event.step} action={event.action}")
        for output in event.oracle_outputs:
            print(f"  {output.oracle_name}: {output.verdict}")
            for diag in output.diagnostics:
                print(f"    - {diag.message}")

    # Post-loop evaluation
    print("\n--- Post-loop evaluation ---")
    compiles, test_passed, test_total = evaluate_final_program(
        final_prefix, renderer, js_program, test_cases,
    )
    print(f"Compiles: {compiles}")
    print(f"Tests: {test_passed}/{test_total}")


if __name__ == "__main__":
    main()
