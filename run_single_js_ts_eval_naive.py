#!/usr/bin/env python3
"""Naive JS->TS translation: generate full output, verify with oracles, retry on failure.

Mirrors the naive baseline from run_ab_experiment.py but for the JS->TS task.
Generates the complete translation in one shot, runs the same oracles as the
DTV version (TscOracle, TscProgramOracle, EslintOracle), and retries with a
repair prompt if any oracle fails.

Usage:
    .venv/bin/python run_single_js_ts_eval_naive.py <js_source> <tests.json> <out.ts>
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol, cast

from controller.adapters import GeneratorAdapter
from controller.stop_criteria import DTVStoppingCriteria, TS_PROFILE
from core.gemma_generator_backend import GemmaGeneratorBackend
from core.budget import Budget
from core.interfaces import Oracle
from core.llm_output import WriteRegionParser
from core.types import (
    Artifact,
    ControllerState,
    GenerateContext,
    GenerationChannel,
    GenerateMessage,
    OracleContext,
    OracleOutput,
    TestCase,
    TranslationSample,
    Verdict,
)
from js_ts.oracles import EslintOracle, TscOracle, TscProgramOracle
from js_ts.oracles.compiler_oracle.tsc_driver import _find_type_roots
from transformers import StoppingCriteriaList

MODEL_NAME = "google/gemma-4-E4B-it"
TOKEN_BUDGET = 2048
MAX_NEW_LENGTH = 1024
MAX_STEPS = 100
PROMPT_PREFIX = "Translate the following JavaScript code into TypeScript with strict type annotations:"

_TS_FENCE_RE = re.compile(r"```(?:typescript|ts)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_ANY_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


class _StopCriteriaBackend(Protocol):
    stop_criteria: StoppingCriteriaList


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
    try:
        return subprocess.run(
            ["node", str(script)],
            input=stdin, capture_output=True, text=True,
            timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired:
        return None


def _extract_ts_code(raw_text: str) -> str:
    ts_match = _TS_FENCE_RE.search(raw_text)
    if ts_match is not None:
        return ts_match.group(1).strip()
    any_match = _ANY_FENCE_RE.search(raw_text)
    if any_match is not None:
        return any_match.group(1).strip()
    return raw_text.strip()


def _run_oracles(
    oracles: list[Oracle],
    ts_code: str,
    sample: TranslationSample,
) -> list[OracleOutput]:
    state = ControllerState(prefix=ts_code)
    artifact = Artifact(code=ts_code, sample=sample)
    context = OracleContext(sample=sample, artifact=artifact)
    outputs: list[OracleOutput] = []
    for oracle in oracles:
        output = oracle.run(state, artifact, context)
        outputs.append(output)
    return outputs


def _all_pass(outputs: list[OracleOutput]) -> bool:
    saw_pass = False
    for output in outputs:
        if output.verdict == Verdict.FAIL:
            return False
        if output.verdict == Verdict.PASS:
            saw_pass = True
    return saw_pass


def _build_repair_prompt(outputs: list[OracleOutput]) -> str:
    parts: list[str] = []
    for output in outputs:
        if output.verdict != Verdict.FAIL or not output.diagnostics:
            continue
        parts.append(f"[{output.oracle_name}]")
        for diag in output.diagnostics:
            primary = next((s for s in diag.spans if s.is_primary), None)
            loc = f"line {primary.line}:" if primary else ""
            parts.append(f"  {loc} {diag.message}")
    diagnostics_text = "\n".join(parts) if parts else "verification failed"
    return (
        "Your previous TypeScript translation failed verification.\n"
        "Fix the errors and return a full corrected TypeScript program.\n"
        "Do not explain. Return exactly one fenced TypeScript code block.\n\n"
        f"Diagnostics:\n{diagnostics_text}\n"
    )


def _remaining_tokens(budget: Budget) -> int:
    return max(0, budget.gen_tokens_budget - budget.gen_tokens_used)


@contextmanager
def _temporary_no_stopping_criteria(generator: GeneratorAdapter):
    backend = cast(_StopCriteriaBackend, generator.backend)
    original_stop_criteria = backend.stop_criteria
    backend.stop_criteria = StoppingCriteriaList([])
    try:
        yield
    finally:
        backend.stop_criteria = original_stop_criteria


def _set_last_assistant(
    messages: list[GenerateMessage],
    content: str,
    stop: bool,
) -> None:
    for idx in range(len(messages) - 1, -1, -1):
        if messages[idx].role == "assistant":
            messages[idx] = GenerateMessage(role="assistant", content=content, stop=stop)
            return
    messages.append(GenerateMessage(role="assistant", content=content, stop=stop))


def _generate_full_round(
    generator: GeneratorAdapter,
    messages: list[GenerateMessage],
    budget: Budget,
) -> tuple[str, int]:
    context = GenerateContext(
        messages=list(messages),
        steps=0,
        max_new_length=_remaining_tokens(budget),
        extract_write_region=False,
        channel=GenerationChannel.CONTINUATION,
    )
    result = generator.backend.generate_step(context)
    budget.add_tokens(result.delta_tokens)
    return result.delta_text, result.delta_tokens


def run_naive_loop(
    prompt: str,
    generator: GeneratorAdapter,
    oracles: list[Oracle],
    sample: TranslationSample,
    token_budget: int,
    accumulate_history: bool = False,
) -> tuple[str, dict]:
    budget = Budget(gen_tokens_budget=token_budget)
    messages: list[GenerateMessage] = [
        GenerateMessage(role="user", content=prompt, stop=True),
        GenerateMessage(role="assistant", content="", stop=False),
    ]

    final_ts = ""
    final_verdict = "fail"
    total_steps = 0
    verify_count = 0
    feedback_count = 0
    rollback_count = 0
    commit_count = 0
    trace_log: list[dict] = []

    while (total_steps < MAX_STEPS) and _remaining_tokens(budget) > 0:
        raw_output, delta_tokens = _generate_full_round(generator, messages, budget)
        total_steps += 1
        if delta_tokens <= 0:
            break

        _set_last_assistant(messages, raw_output, stop=True)
        final_ts = _extract_ts_code(raw_output)

        verify_count += 1
        outputs = _run_oracles(oracles, final_ts, sample)
        passed = _all_pass(outputs)
        oracle_summary = {o.oracle_name: o.verdict.name for o in outputs}
        trace_log.append({
            "round": total_steps,
            "tokens_used": budget.gen_tokens_used,
            "passed": passed,
            "oracles": oracle_summary,
        })
        print(f"  round={total_steps}  tokens={budget.gen_tokens_used}  "
              f"passed={passed}  oracles={oracle_summary}")

        if passed:
            final_verdict = "pass"
            commit_count = 1
            break

        feedback_count += 1
        rollback_count += 1
        if _remaining_tokens(budget) <= 0 or total_steps >= MAX_STEPS:
            break

        repair_prompt = _build_repair_prompt(outputs)
        if accumulate_history:
            messages.append(GenerateMessage(role="user", content=repair_prompt, stop=True))
            messages.append(GenerateMessage(role="assistant", content="", stop=False))
        else:
            messages = [
                GenerateMessage(role="user", content=prompt, stop=True),
                GenerateMessage(role="assistant", content=raw_output, stop=True),
                GenerateMessage(role="user", content=repair_prompt, stop=True),
                GenerateMessage(role="assistant", content="", stop=False),
            ]

    metrics = {
        "final_verdict": final_verdict,
        "total_tokens": budget.gen_tokens_used,
        "total_steps": total_steps,
        "verify_count": verify_count,
        "feedback_count": feedback_count,
        "rollback_count": rollback_count,
        "commit_count": commit_count,
        "trace_log": trace_log,
    }
    return final_ts, metrics


def evaluate_final_program(
    ts_code: str,
    js_source: str,
    test_cases: list[TestCase],
) -> tuple[bool, int, int]:
    """Compile TS, run JS and compiled TS, compare stdout.

    Returns (compiles, tests_passed, tests_total).
    """
    type_roots = _find_type_roots()
    type_roots_args = ["--typeRoots", type_roots] if type_roots else []

    with tempfile.TemporaryDirectory(prefix="dtv-eval-naive-jsts-") as tmpdir:
        workdir = Path(tmpdir)
        js_file = workdir / "source.js"
        ts_file = workdir / "output.ts"
        js_file.write_text(js_source, encoding="utf-8")
        ts_file.write_text(ts_code, encoding="utf-8")

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
        print("Usage: python run_single_js_ts_eval_naive.py <js_source> <tests.json> <out.ts>")
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

    write_region_parser = WriteRegionParser()
    generator = GeneratorAdapter(
        model_name=MODEL_NAME,
        stop_criteria_factory=lambda tok: [
            DTVStoppingCriteria(tok, TS_PROFILE, write_region_parser=write_region_parser)
        ],
        write_region_parser=write_region_parser,
        backend_cls=GemmaGeneratorBackend,
    )
    print("Model loaded:", MODEL_NAME)

    oracles: list[Oracle] = [TscProgramOracle(), EslintOracle()]

    t0 = time.time()
    with _temporary_no_stopping_criteria(generator):
        final_ts, metrics = run_naive_loop(
            prompt=prompt,
            generator=generator,
            oracles=oracles,
            sample=sample,
            token_budget=TOKEN_BUDGET,
        )
    elapsed = time.time() - t0

    out_path.write_text(final_ts, encoding="utf-8")
    print(f"\nGenerated TS saved to {out_path}")
    print(f"Verdict: {metrics['final_verdict']}")
    print(f"Tokens: {metrics['total_tokens']}  Steps: {metrics['total_steps']}  "
          f"Verify: {metrics['verify_count']}  Feedback: {metrics['feedback_count']}  "
          f"Rollback: {metrics['rollback_count']}  Time: {elapsed:.1f}s")

    for entry in metrics.get("trace_log", []):
        print(f"  round={entry['round']}  tokens={entry['tokens_used']}  "
              f"passed={entry['passed']}  oracles={entry['oracles']}")

    # Post-loop evaluation (differential testing)
    print("\n--- Post-loop evaluation ---")
    compiles, test_passed, test_total = evaluate_final_program(
        final_ts, js_program, test_cases,
    )
    print(f"Compiles: {compiles}")
    print(f"Tests: {test_passed}/{test_total}")


if __name__ == "__main__":
    main()
