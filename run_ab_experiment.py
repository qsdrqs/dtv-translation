#!/usr/bin/env python3
"""A/B experiment: DTV vs naive under equal token budget.

Both strategies share the same prompt (with write-region contract) and the same
post-generation compile-check-reprompt loop.  The only difference is the
generation phase: DTV uses incremental stmt/block/func verification, naive uses
one-shot generation.

Usage:
    .venv/bin/python run_ab_experiment.py [OPTIONS] [case_id ...]

Options:
    --output PATH           Output JSON path (default: result/ab_experiment_results.json)
    --model-name NAME       HuggingFace model ID (default: Qwen/Qwen3-4B-Instruct-2507)
    --token-budget N        Fixed token budget (default: 6144)
    --budget-k K            Per-case budget = K * C_source_tokens (overrides --token-budget)
    --greedy                Use greedy decoding (do_sample=False)

If no case IDs given, uses the default 10-case smoke set.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Protocol, cast

from c_rust.feedback import RUST_FEEDBACK_LANG
from c_rust.oracles import FunctionOracle, RustcOracle
from c_rust.oracles.program_diff_test_oracle.execution_driver import compile_and_run
from c_rust.render import CRustRenderer
from controller.adapters import GeneratorAdapter
from controller.loop import render_write_region_contract, run_dtv_loop
from controller.policy import DefaultPolicy, DefaultPolicyConfig
from controller.stop_criteria import DTVStoppingCriteria, RUST_PROFILE
from core.budget import Budget
from core.interfaces import Oracle
from core.llm_output import (
    AssistantContent,
    DEFAULT_WRITE_REGION_MARKERS,
    WriteRegionMarkers,
    WriteRegionParser,
)
from core.types import (
    Action,
    GenerateContext,
    GenerationChannel,
    GenerateMessage,
    Granularity,
    RenderStatus,
    TestCase,
    TraceEvent,
    TranslationSample,
    Verdict,
)
from feedback.feedback import FeedbackState
from feedback.formatter import RepairFeedbackFormatConfig
from rollback.manager import RollbackManager
from transformers import PreTrainedTokenizerBase, StoppingCriteriaList

# -- Constants -----------------------------------------------------------------

MODEL_NAME = "Qwen/Qwen3-4B-Instruct-2507"
OUTPUT_TOKEN_CAP = 6144
TOKEN_BUDGET = OUTPUT_TOKEN_CAP
MAX_NEW_LENGTH = 2048
MAX_STEPS = 2000
PROMPT_PREFIX = "Translate the following C code into Rust, keep the same function order:"
DATASET_DIR = Path(os.environ.get("DTV_DATASET_DIR", "/home/qsdrqs/projects/agent_fuzz/selected_data_output"))
RESULT_DIR = Path("result")
OUTPUT_PATH = RESULT_DIR / "ab_experiment_results.json"

DEFAULT_CASE_IDS = [
    "s236602409", "s628961975", "s126370263", "s672064666", "s476074975",
    "s780263580", "s660236723", "s168939986", "s488265727", "s763753836",
]

# DTV: verify at every statement boundary, stmt-level rollback + repair
DTV_CONFIG = DefaultPolicyConfig(
    verify_on_boundary=True,
    verify_on_close=False,
    boundary_granularity=Granularity.STMT,
    close_granularity=Granularity.FUNC,
    enable_rollback=True,
    default_fail_scope=Granularity.STMT,
    enable_feedback=True,
    repair_verify_granularity=Granularity.STMT,
)


class _StopCriteriaBackend(Protocol):
    stop_criteria: StoppingCriteriaList


class _TokenizerBackend(Protocol):
    tokenizer: PreTrainedTokenizerBase


# -- Metrics -------------------------------------------------------------------

@dataclass
class RunResult:
    case_id: str
    config: str
    final_verdict: str
    total_tokens: int
    total_steps: int
    elapsed_s: float
    verify_count: int
    feedback_count: int
    rollback_count: int
    commit_count: int
    compiles: bool
    test_passed: int
    test_total: int
    trace_log: list[dict] | None = None


def _all_pass(outputs: tuple) -> bool:
    """Same logic as the policy: at least one PASS and no FAIL."""
    saw_pass = False
    for output in outputs:
        if output.verdict == Verdict.FAIL:
            return False
        if output.verdict == Verdict.PASS:
            saw_pass = True
    return saw_pass


def _trace_verdict(oracle_outputs: tuple) -> str | None:
    if not oracle_outputs:
        return None
    return "pass" if _all_pass(oracle_outputs) else "fail"


def _extract_dtv_metrics(trace: list[TraceEvent]) -> dict:
    verify_count = 0
    feedback_count = 0
    rollback_count = 0
    commit_count = 0
    trace_log: list[dict] = []

    for event in trace:
        if event.action == Action.VERIFY:
            verify_count += 1
        elif event.action == Action.FEEDBACK:
            feedback_count += 1
        elif event.action == Action.ROLLBACK:
            rollback_count += 1
        elif event.action == Action.COMMIT:
            commit_count += 1

        entry: dict = {
            "step": event.step,
            "action": event.action.name,
            "tokens_used": event.budget_snapshot.get("gen_tokens_used", 0),
        }
        if event.action == Action.VERIFY:
            entry["granularity"] = event.verification_granularity.name if event.verification_granularity else None
            entry["verdict"] = _trace_verdict(event.oracle_outputs)
        trace_log.append(entry)

    return {
        "total_steps": len(trace),
        "verify_count": verify_count,
        "feedback_count": feedback_count,
        "rollback_count": rollback_count,
        "commit_count": commit_count,
        "trace_log": trace_log,
    }


# -- Shared prompt / extraction / compilation ----------------------------------

def _build_prompt(
    source_code: str,
    prompt_prefix: str,
    language_name: str,
    markers: WriteRegionMarkers,
) -> str:
    raw_prompt = f"\n{prompt_prefix}\n```c\n{source_code}\n```\n"
    contract = render_write_region_contract(language_name, markers)
    return f"{raw_prompt.rstrip()}\n\n{contract}"


def _wrap_in_write_region(code: str, markers: WriteRegionMarkers) -> str:
    return f"{markers.begin_marker}\n{code}\n{markers.end_marker}"


def _dtv_terminated_without_write_region(trace: list[TraceEvent], final_prefix: str) -> bool:
    if final_prefix:
        return False
    for event in reversed(trace):
        if event.action == Action.GENERATE:
            return event.stop_reason is not None and event.stop_reason.kind == "no_write_region_eos"
    return False


def _normalize_open_assistant_message(
    messages: list[GenerateMessage],
    markers: WriteRegionMarkers,
) -> list[GenerateMessage]:
    normalized = list(messages)
    for idx in range(len(normalized) - 1, -1, -1):
        message = normalized[idx]
        if message.role != "assistant" or message.stop:
            continue
        normalized[idx] = GenerateMessage(
            role="assistant",
            content=AssistantContent.empty(markers=markers),
            stop=False,
        )
        break
    return normalized


def _extract_write_region_code(raw_text: str, markers: WriteRegionMarkers) -> str | None:
    begin_idx = raw_text.find(markers.begin_marker)
    if begin_idx < 0:
        return None
    code_start = begin_idx + len(markers.begin_marker)
    if code_start < len(raw_text) and raw_text[code_start] == "\n":
        code_start += 1
    end_idx = raw_text.find(markers.end_marker, code_start)
    if end_idx < 0:
        return raw_text[code_start:].strip()
    return raw_text[code_start:end_idx].strip()


def _remaining_tokens(budget: Budget) -> int:
    return max(0, budget.gen_tokens_budget - budget.gen_tokens_used)


@contextmanager
def _temporary_no_stopping_criteria(generator: GeneratorAdapter):
    backend = cast(_StopCriteriaBackend, generator.backend)
    original = backend.stop_criteria
    backend.stop_criteria = StoppingCriteriaList([])
    try:
        yield
    finally:
        backend.stop_criteria = original


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


def _compile_rust_code(rust_code: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="eval-rustc-") as tmpdir:
        compile_result, _ = compile_and_run(rust_code, [], "rust", Path(tmpdir))
    outputs = [part for part in (compile_result.stderr, compile_result.stdout) if part]
    compiler_output = "\n".join(outputs).strip()
    compiles = not compile_result.compilation_failed and not compile_result.timed_out
    return compiles, compiler_output


def _format_compile_feedback(compiler_output: str, max_lines: int = 20) -> str:
    lines = [line.strip() for line in compiler_output.splitlines() if line.strip()]
    if not lines:
        return "- rustc did not emit diagnostics"
    shown = lines[:max_lines]
    if len(lines) > max_lines:
        shown.append(f"... {len(lines) - max_lines} more lines omitted")
    return "\n".join(f"- {line}" for line in shown)


def _build_repair_prompt(compiler_output: str, markers: WriteRegionMarkers) -> str:
    diagnostics_text = _format_compile_feedback(compiler_output)
    return (
        "Your previous Rust translation failed to compile.\n"
        "Fix the compile errors and return a full corrected Rust program.\n"
        f"Output the corrected code inside {markers.begin_marker} ... {markers.end_marker} markers.\n"
        "Do not use markdown fences inside the write region.\n\n"
        f"Compiler diagnostics:\n{diagnostics_text}\n"
    )


def _build_missing_markers_prompt(markers: WriteRegionMarkers) -> str:
    return (
        "Your response did not include write-region markers.\n"
        f"Output the code inside {markers.begin_marker} ... {markers.end_marker} markers.\n"
        "Do not use markdown fences inside the write region.\n"
    )


# -- Loading -------------------------------------------------------------------

def load_test_cases(case_dir: Path) -> list[TestCase]:
    testcases_dir = case_dir / "testcases"
    cases: list[TestCase] = []
    skipped = 0
    for f in sorted(testcases_dir.iterdir()):
        if f.name.startswith("input_"):
            raw = f.read_bytes()
            try:
                stdin = raw.decode("utf-8")
            except UnicodeDecodeError:
                skipped += 1
                continue
            cases.append(TestCase(stdin=stdin, test_id=f.stem))
    if skipped:
        print(f"    (skipped {skipped} binary test inputs in {case_dir.name})")
    return cases


def evaluate_final_rust_code(
    rust_code: str,
    c_source: str,
    test_cases: list[TestCase],
) -> tuple[bool, int, int]:
    with tempfile.TemporaryDirectory(prefix="dtv-eval-") as tmpdir:
        c_dir = Path(tmpdir) / "c"
        c_dir.mkdir()
        rust_dir = Path(tmpdir) / "rust"
        rust_dir.mkdir()

        c_compile, c_results = compile_and_run(c_source, test_cases, "c", c_dir)
        if c_compile.compilation_failed:
            return False, 0, len(test_cases)

        rust_compile, rust_results = compile_and_run(rust_code, test_cases, "rust", rust_dir)
        if rust_compile.compilation_failed:
            return False, 0, len(test_cases)

        passed = 0
        for c_res, rust_res in zip(c_results, rust_results):
            if c_res.stdout == rust_res.stdout and c_res.exit_code == rust_res.exit_code:
                passed += 1

    return True, passed, len(test_cases)


# -- Shared program-level eval + reprompt loop ---------------------------------

@dataclass
class ProgramEvalLoopResult:
    final_code: str
    compiles: bool
    rounds: int
    total_steps: int
    verify_count: int
    feedback_count: int
    rollback_count: int
    commit_count: int
    trace: list[dict]


@dataclass
class RegenerationRoundResult:
    strategy: str
    raw_output: str
    delta_tokens: int
    total_steps: int
    verify_count: int
    feedback_count: int
    rollback_count: int
    commit_count: int
    trace_log: list[dict]


def _make_naive_regenerator(generator: GeneratorAdapter) -> Callable[[list[GenerateMessage], Budget], RegenerationRoundResult]:
    def regenerate_round(
        messages: list[GenerateMessage],
        budget: Budget,
    ) -> RegenerationRoundResult:
        with _temporary_no_stopping_criteria(generator):
            raw_output, delta_tokens = _generate_full_round(generator, messages, budget)
        return RegenerationRoundResult(
            strategy="naive",
            raw_output=raw_output,
            delta_tokens=delta_tokens,
            total_steps=1,
            verify_count=0,
            feedback_count=0,
            rollback_count=0,
            commit_count=0,
            trace_log=[{
                "action": "GENERATE",
                "tokens_used": budget.gen_tokens_used,
                "delta_tokens": delta_tokens,
            }],
        )

    return regenerate_round


def _make_dtv_regenerator(
    generator: GeneratorAdapter,
    renderer_factory: Callable[[], CRustRenderer],
    oracle_factory: Callable[[], list[Oracle]],
    config: DefaultPolicyConfig,
    markers: WriteRegionMarkers,
    max_steps: int,
    max_new_length: int,
) -> Callable[[list[GenerateMessage], Budget], RegenerationRoundResult]:
    def regenerate_round(
        messages: list[GenerateMessage],
        budget: Budget,
    ) -> RegenerationRoundResult:
        feedback_state = FeedbackState()
        rollback_manager = RollbackManager()
        policy = DefaultPolicy(config)
        generator.reset_output_extractor()
        normalized_messages = _normalize_open_assistant_message(messages, markers)
        tokens_before = budget.gen_tokens_used
        final_prefix, trace = run_dtv_loop(
            generator=generator,
            renderer=renderer_factory(),
            oracles=oracle_factory(),
            budget=budget,
            feedback_state=feedback_state,
            rollback_manager=rollback_manager,
            policy=policy,
            feedback_lang_config=RUST_FEEDBACK_LANG,
            repair_feedback_format_config=RepairFeedbackFormatConfig(include_failed_snippet=True),
            max_steps=max_steps,
            max_new_length=max_new_length,
            prompt_prefix="",
            inject_write_region_contract=False,
            initial_messages=normalized_messages,
        )
        delta_tokens = budget.gen_tokens_used - tokens_before
        dtv_metrics = _extract_dtv_metrics(trace)
        raw_output = "" if _dtv_terminated_without_write_region(trace, final_prefix) else _wrap_in_write_region(final_prefix, markers)
        return RegenerationRoundResult(
            strategy="dtv",
            raw_output=raw_output,
            delta_tokens=delta_tokens,
            total_steps=dtv_metrics["total_steps"],
            verify_count=dtv_metrics["verify_count"],
            feedback_count=dtv_metrics["feedback_count"],
            rollback_count=dtv_metrics["rollback_count"],
            commit_count=dtv_metrics["commit_count"],
            trace_log=dtv_metrics["trace_log"],
        )

    return regenerate_round


def program_eval_loop(
    initial_code: str | None,
    prompt: str,
    budget: Budget,
    markers: WriteRegionMarkers,
    regenerate_round: Callable[[list[GenerateMessage], Budget], RegenerationRoundResult],
    last_raw_output: str = "",
    max_rounds: int | None = MAX_STEPS,
) -> ProgramEvalLoopResult:
    code = initial_code
    last_raw = last_raw_output
    trace: list[dict] = []
    rounds = 0
    total_steps = 0
    verify_count = 0
    feedback_count = 0
    rollback_count = 0
    commit_count = 0

    while max_rounds is None or rounds < max_rounds:
        if _remaining_tokens(budget) <= 0:
            break

        rounds += 1

        if code is None:
            trace.append({
                "phase": "outer",
                "round": rounds,
                "action": "MISSING_MARKERS",
                "tokens_used": budget.gen_tokens_used,
                "compiles": False,
                "missing_markers": True,
            })
            total_steps += 1
            feedback_count += 1
            rollback_count += 1
            if _remaining_tokens(budget) <= 0:
                break
            feedback = _build_missing_markers_prompt(markers)
            messages = [
                GenerateMessage(role="user", content=prompt, stop=True),
                GenerateMessage(role="assistant", content=last_raw, stop=True),
                GenerateMessage(role="user", content=feedback, stop=True),
                GenerateMessage(role="assistant", content="", stop=False),
            ]
            round_result = regenerate_round(messages, budget)
            total_steps += round_result.total_steps
            verify_count += round_result.verify_count
            feedback_count += round_result.feedback_count
            rollback_count += round_result.rollback_count
            commit_count += round_result.commit_count
            trace.extend({
                **entry,
                "phase": "outer_generate",
                "outer_round": rounds,
                "strategy": round_result.strategy,
            } for entry in round_result.trace_log)
            if round_result.delta_tokens <= 0:
                break
            last_raw = round_result.raw_output
            code = _extract_write_region_code(round_result.raw_output, markers)
            continue

        compiles, compiler_output = _compile_rust_code(code)
        trace.append({
            "phase": "outer",
            "round": rounds,
            "action": "VERIFY_PROGRAM",
            "tokens_used": budget.gen_tokens_used,
            "compiles": compiles,
        })
        total_steps += 1
        verify_count += 1

        if compiles:
            return ProgramEvalLoopResult(
                final_code=code,
                compiles=True,
                rounds=rounds,
                total_steps=total_steps,
                verify_count=verify_count,
                feedback_count=feedback_count,
                rollback_count=rollback_count,
                commit_count=commit_count,
                trace=trace,
            )

        if _remaining_tokens(budget) <= 0:
            break

        feedback_count += 1
        rollback_count += 1
        repair_prompt = _build_repair_prompt(compiler_output, markers)
        messages = [
            GenerateMessage(role="user", content=prompt, stop=True),
            GenerateMessage(
                role="assistant",
                content=f"{markers.begin_marker}\n{code}\n{markers.end_marker}",
                stop=True,
            ),
            GenerateMessage(role="user", content=repair_prompt, stop=True),
            GenerateMessage(role="assistant", content="", stop=False),
        ]

        round_result = regenerate_round(messages, budget)
        total_steps += round_result.total_steps
        verify_count += round_result.verify_count
        feedback_count += round_result.feedback_count
        rollback_count += round_result.rollback_count
        commit_count += round_result.commit_count
        trace.extend({
            **entry,
            "phase": "outer_generate",
            "outer_round": rounds,
            "strategy": round_result.strategy,
        } for entry in round_result.trace_log)
        if round_result.delta_tokens <= 0:
            break
        last_raw = round_result.raw_output
        code = _extract_write_region_code(round_result.raw_output, markers)

    final_code = code if code is not None else ""
    return ProgramEvalLoopResult(
        final_code=final_code,
        compiles=False,
        rounds=rounds,
        total_steps=total_steps,
        verify_count=verify_count,
        feedback_count=feedback_count,
        rollback_count=rollback_count,
        commit_count=commit_count,
        trace=trace,
    )


# -- Runner --------------------------------------------------------------------

def run_single(
    case_id: str,
    config: DefaultPolicyConfig,
    config_name: str,
    generator: GeneratorAdapter,
    token_budget: int,
    markers: WriteRegionMarkers = DEFAULT_WRITE_REGION_MARKERS,
    budget_k: float | None = None,
) -> RunResult:
    case_dir = DATASET_DIR / case_id
    c_source = (case_dir / "source.c").read_text(encoding="utf-8").strip()
    test_cases = load_test_cases(case_dir)
    sample = TranslationSample(source_code=c_source, source_lang="c", test_cases=test_cases)

    if budget_k is not None:
        backend = cast(_TokenizerBackend, generator.backend)
        c_token_count = len(backend.tokenizer.encode(c_source))
        effective_budget = int(budget_k * c_token_count)
    else:
        effective_budget = token_budget

    prompt = _build_prompt(c_source, PROMPT_PREFIX, "Rust", markers)
    budget = Budget(gen_tokens_budget=effective_budget)
    renderer_factory = lambda: CRustRenderer(sample=sample)
    oracle_factory = lambda: cast(list[Oracle], [RustcOracle(), FunctionOracle()])

    t0 = time.time()

    if config_name == "naive":
        regenerate_round = _make_naive_regenerator(generator)
        messages = [
            GenerateMessage(role="user", content=prompt, stop=True),
            GenerateMessage(role="assistant", content="", stop=False),
        ]
        with _temporary_no_stopping_criteria(generator):
            raw_output, _ = _generate_full_round(generator, messages, budget)
        initial_code = _extract_write_region_code(raw_output, markers)
        last_raw_output = raw_output
        gen_steps = 1
        gen_verify = 0
        gen_feedback = 0
        gen_rollback = 0
        gen_commit = 0
        gen_trace: list[dict] = []
    else:
        regenerate_round = _make_dtv_regenerator(
            generator=generator,
            renderer_factory=renderer_factory,
            oracle_factory=oracle_factory,
            config=config,
            markers=markers,
            max_steps=MAX_STEPS,
            max_new_length=MAX_NEW_LENGTH,
        )
        renderer = renderer_factory()
        oracles = oracle_factory()
        feedback_state = FeedbackState()
        rollback_manager = RollbackManager()
        policy = DefaultPolicy(config)
        generator.reset_output_extractor()

        final_prefix, trace = run_dtv_loop(
            generator=generator,
            renderer=renderer,
            oracles=oracles,
            budget=budget,
            feedback_state=feedback_state,
            rollback_manager=rollback_manager,
            policy=policy,
            feedback_lang_config=RUST_FEEDBACK_LANG,
            repair_feedback_format_config=RepairFeedbackFormatConfig(include_failed_snippet=True),
            max_steps=MAX_STEPS,
            max_new_length=MAX_NEW_LENGTH,
            prompt_prefix=prompt,
            inject_write_region_contract=False,
        )
        dtv_metrics = _extract_dtv_metrics(trace)
        gen_steps = dtv_metrics["total_steps"]
        gen_verify = dtv_metrics["verify_count"]
        gen_feedback = dtv_metrics["feedback_count"]
        gen_rollback = dtv_metrics["rollback_count"]
        gen_commit = dtv_metrics["commit_count"]
        gen_trace = dtv_metrics["trace_log"]

        if _dtv_terminated_without_write_region(trace, final_prefix):
            initial_code = None
        else:
            render_result = renderer.try_render(final_prefix)
            if render_result.status == RenderStatus.OK and render_result.artifact is not None:
                initial_code = render_result.artifact.code
            else:
                initial_code = final_prefix
        last_raw_output = ""

    eval_result = program_eval_loop(
        initial_code=initial_code,
        prompt=prompt,
        budget=budget,
        markers=markers,
        regenerate_round=regenerate_round,
        last_raw_output=last_raw_output,
    )

    elapsed = time.time() - t0

    compiles, test_passed, test_total = evaluate_final_rust_code(
        rust_code=eval_result.final_code,
        c_source=c_source,
        test_cases=test_cases,
    )

    combined_trace = gen_trace + eval_result.trace

    if compiles and (test_total == 0 or test_passed == test_total):
        final_verdict = "pass"
    else:
        final_verdict = "fail"

    return RunResult(
        case_id=case_id,
        config=config_name,
        final_verdict=final_verdict,
        total_tokens=budget.gen_tokens_used,
        total_steps=gen_steps + eval_result.total_steps,
        elapsed_s=round(elapsed, 1),
        verify_count=gen_verify + eval_result.verify_count,
        feedback_count=gen_feedback + eval_result.feedback_count,
        rollback_count=gen_rollback + eval_result.rollback_count,
        commit_count=gen_commit + eval_result.commit_count,
        compiles=compiles,
        test_passed=test_passed,
        test_total=test_total,
        trace_log=combined_trace,
    )


# -- Output --------------------------------------------------------------------

def print_summary(
    results: list[RunResult],
    model_name: str,
    token_budget: int,
    budget_k: float | None,
) -> None:
    dtv = {r.case_id: r for r in results if r.config == "dtv"}
    naive = {r.case_id: r for r in results if r.config == "naive"}
    case_ids = list(dict.fromkeys(r.case_id for r in results))

    col = (
        f"{'Case':<15} | "
        f"{'Verd':<7} {'Tok':>6} {'Stp':>5} {'V':>3} {'F':>3} {'R':>3} {'C':>2} {'Tests':>7} | "
        f"{'Verd':<7} {'Tok':>6} {'Stp':>5} {'V':>3} {'F':>3} {'R':>3} {'C':>2} {'Tests':>7}"
    )
    budget_desc = f"BudgetK={budget_k}" if budget_k is not None else f"TokenBudget={token_budget}"
    print(f"\n{'=' * 95}")
    print("A/B COMPARISON: DTV vs Naive Feedback")
    print(f"Model={model_name}  {budget_desc}  MaxSteps={MAX_STEPS}")
    print(f"{'=' * 95}")
    print(f"{'':15}   {'--- DTV ---':^40}   {'--- Naive ---':^40}")
    print(col)
    print("-" * 95)

    for cid in case_ids:
        d = dtv.get(cid)
        n = naive.get(cid)
        if d and n:
            print(
                f"{cid:<15} | "
                f"{d.final_verdict:<7} {d.total_tokens:>6} {d.total_steps:>5} "
                f"{d.verify_count:>3} {d.feedback_count:>3} {d.rollback_count:>3} "
                f"{'Y' if d.compiles else 'N':>2} {f'{d.test_passed}/{d.test_total}':>7} | "
                f"{n.final_verdict:<7} {n.total_tokens:>6} {n.total_steps:>5} "
                f"{n.verify_count:>3} {n.feedback_count:>3} {n.rollback_count:>3} "
                f"{'Y' if n.compiles else 'N':>2} {f'{n.test_passed}/{n.test_total}':>7}"
            )

    print("-" * 95)
    dtv_list = [dtv[cid] for cid in case_ids if cid in dtv]
    naive_list = [naive[cid] for cid in case_ids if cid in naive]
    dtv_pass = sum(1 for r in dtv_list if r.final_verdict == "pass")
    naive_pass = sum(1 for r in naive_list if r.final_verdict == "pass")
    dtv_test_pass = sum(r.test_passed for r in dtv_list)
    naive_test_pass = sum(r.test_passed for r in naive_list)
    dtv_test_total = sum(r.test_total for r in dtv_list)
    naive_test_total = sum(r.test_total for r in naive_list)
    dtv_avg_tok = sum(r.total_tokens for r in dtv_list) / max(len(dtv_list), 1)
    naive_avg_tok = sum(r.total_tokens for r in naive_list) / max(len(naive_list), 1)
    dtv_avg_time = sum(r.elapsed_s for r in dtv_list) / max(len(dtv_list), 1)
    naive_avg_time = sum(r.elapsed_s for r in naive_list) / max(len(naive_list), 1)

    legend = (
        "Legend: Verd=final verdict, Tok=tokens used, Stp=loop steps, "
        "V=verify, F=feedback, R=rollback, C=final Rust compiles, Tests=passed/total"
    )
    print(legend)
    print(f"\nPass rate:    DTV {dtv_pass}/{len(dtv_list)}    Naive {naive_pass}/{len(naive_list)}")
    print(
        f"Test pass:    DTV {dtv_test_pass}/{dtv_test_total}    "
        f"Naive {naive_test_pass}/{naive_test_total}"
    )
    print(f"Avg tokens:   DTV {dtv_avg_tok:.0f}      Naive {naive_avg_tok:.0f}")
    print(f"Avg time(s):  DTV {dtv_avg_time:.1f}      Naive {naive_avg_time:.1f}")
    print(f"{'=' * 95}")


# -- Main ----------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="A/B experiment: DTV vs naive feedback")
    parser.add_argument("case_ids", nargs="*", default=DEFAULT_CASE_IDS, help="Case IDs to run")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Output JSON path")
    parser.add_argument("--model-name", default=MODEL_NAME, help="HuggingFace model ID")
    parser.add_argument("--token-budget", type=int, default=OUTPUT_TOKEN_CAP, help="Fixed token budget")
    parser.add_argument("--budget-k", type=float, default=None,
                        help="Per-case budget = k * C_source_tokens (overrides --token-budget)")
    parser.add_argument("--greedy", action="store_true", help="Greedy decoding (do_sample=False)")
    args = parser.parse_args()

    case_ids: list[str] = args.case_ids
    output_path: Path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    model_name: str = args.model_name
    token_budget: int = args.token_budget
    budget_k: float | None = args.budget_k
    do_sample: bool | None = False if args.greedy else None

    write_region_parser = WriteRegionParser()
    markers = write_region_parser.markers
    generator = GeneratorAdapter(
        model_name=model_name,
        stop_criteria_factory=lambda tok: [
            DTVStoppingCriteria(tok, RUST_PROFILE, write_region_parser=write_region_parser)
        ],
        write_region_parser=write_region_parser,
        do_sample=do_sample,
    )

    budget_desc = f"BudgetK={budget_k}" if budget_k is not None else f"TokenBudget={token_budget}"
    sampling_desc = "greedy" if args.greedy else "default"
    print(f"Model loaded: {model_name}")
    print(f"Cases: {len(case_ids)}, {budget_desc}, MaxSteps={MAX_STEPS}, Sampling={sampling_desc}")
    print(f"Output: {output_path}")

    results: list[RunResult] = []
    configs = [("dtv", DTV_CONFIG), ("naive", DTV_CONFIG)]

    for i, case_id in enumerate(case_ids, 1):
        for config_name, config in configs:
            print(f"\n[{i}/{len(case_ids)}] {case_id} / {config_name} ...", flush=True)
            try:
                result = run_single(
                    case_id, config, config_name, generator,
                    token_budget=token_budget, markers=markers, budget_k=budget_k,
                )
            except Exception as exc:
                import traceback
                traceback.print_exc()
                print(f"  !! CRASH: {case_id}/{config_name}: {exc}", flush=True)
                result = RunResult(
                    case_id=case_id,
                    config=config_name,
                    final_verdict="crash",
                    total_tokens=0,
                    total_steps=0,
                    elapsed_s=0.0,
                    verify_count=0,
                    feedback_count=0,
                    rollback_count=0,
                    commit_count=0,
                    compiles=False,
                    test_passed=0,
                    test_total=0,
                )
            results.append(result)
            print(
                f"  -> {result.final_verdict}  tokens={result.total_tokens}  "
                f"steps={result.total_steps}  verify={result.verify_count}  "
                f"feedback={result.feedback_count}  rollback={result.rollback_count}  "
                f"compiles={'Y' if result.compiles else 'N'}  "
                f"tests={result.test_passed}/{result.test_total}  "
                f"time={result.elapsed_s}s"
            )

        output_path.write_text(
            json.dumps([asdict(r) for r in results], indent=2), encoding="utf-8"
        )

    print_summary(results, model_name=model_name, token_budget=token_budget, budget_k=budget_k)
    print(f"\nFull results: {output_path}")


if __name__ == "__main__":
    main()
