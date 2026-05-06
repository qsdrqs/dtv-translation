#!/usr/bin/env python3
"""C->Rust translation experiment runner (naive or dtv strategy).

Both strategies share the same prompt (with write-region contract) and the same
post-generation compile-check-reprompt loop.  The only difference is the
generation phase: DTV uses incremental stmt/block/func verification, naive uses
one-shot generation.

Usage:
    .venv/bin/python run_experiments_c_rust.py --strategy {naive|dtv} [OPTIONS] [case_id ...]

Options:
    --strategy {naive,dtv}  Generation strategy (required)
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
import re
import tempfile
import time

from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable, Protocol, cast

from c_rust.feedback import RUST_FEEDBACK_LANG
from c_rust.oracles import RustcOracle
from c_rust.oracles.program_diff_test_oracle.execution_driver import compile_and_run
from c_rust.render import CRustRenderer
from controller.adapters import GeneratorAdapter
from core.gemma_generator_backend import GemmaGeneratorBackend
from core.qwen_generator_backend import QwenGeneratorBackend
from controller.loop import (
    BAILOUT_DIAGNOSTICS_HEADER,
    render_write_region_contract,
    run_dtv_loop,
)
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
GEMMA_MODEL_NAME = "google/gemma-4-E4B-it"
OUTPUT_TOKEN_CAP = 6144
TOKEN_BUDGET = OUTPUT_TOKEN_CAP
MAX_NEW_LENGTH = 1024
MAX_NEW_LENGTH_BON = 8192
# INNER counts controller actions, OUTER counts SR retry rounds; different
# units, do not conflate. Real termination for both is the token budget.
INNER_MAX_STEPS = 2000
OUTER_MAX_ROUNDS = 2000
PROMPT_PREFIX = "Translate the following C code into Rust:"
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

DTV_NO_FEEDBACK_CONFIG = replace(DTV_CONFIG, enable_feedback=False)
DTV_NO_ESCALATION_CONFIG = replace(DTV_CONFIG, max_rollback_scope=Granularity.STMT)
DTV_DETECT_AND_ABORT_CONFIG = replace(DTV_CONFIG, bailout_visit_threshold=1)

# Strategy name -> config mapping. naive and bon-nsr are handled separately
# (they don't run DTV inner loop, so config is unused there).
DTV_STRATEGY_CONFIGS: dict[str, DefaultPolicyConfig] = {
    "dtv": DTV_CONFIG,
    "dtv-no-feedback": DTV_NO_FEEDBACK_CONFIG,
    "dtv-no-escalation": DTV_NO_ESCALATION_CONFIG,
    "dtv-detect-and-abort": DTV_DETECT_AND_ABORT_CONFIG,
}


class _StopCriteriaBackend(Protocol):
    stop_criteria: StoppingCriteriaList


class _TokenizerBackend(Protocol):
    tokenizer: PreTrainedTokenizerBase


def resolve_backend_config(
    *,
    backend: str,
    model_name: str | None,
) -> tuple[type[QwenGeneratorBackend] | type[GemmaGeneratorBackend], str]:
    if backend == "gemma":
        resolved_model_name = model_name or GEMMA_MODEL_NAME
        if "gemma" not in resolved_model_name.lower():
            raise SystemExit(
                f"ERROR: --backend gemma but --model-name '{resolved_model_name}' "
                f"does not look like a Gemma model. Did you mean --backend qwen?"
            )
        return GemmaGeneratorBackend, resolved_model_name

    resolved_model_name = model_name or MODEL_NAME
    if "qwen" not in resolved_model_name.lower():
        raise SystemExit(
            f"ERROR: --backend qwen (default) but --model-name '{resolved_model_name}' "
            f"does not look like a Qwen model. Did you forget --backend gemma?"
        )
    return QwenGeneratorBackend, resolved_model_name


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
    saved_output_path: str | None = None
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


def _sanitize_case_id(case_id: str) -> str:
    return case_id.replace("/", "__")


def _save_pass_output(
    pass_output_dir: Path,
    case_id: str,
    config_name: str,
    final_code: str,
) -> str:
    target_dir = pass_output_dir / config_name
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / f"{_sanitize_case_id(case_id)}.rs"
    output_path.write_text(final_code, encoding="utf-8")
    return str(output_path)


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


def _generate_bon_round(
    generator: GeneratorAdapter,
    messages: list[GenerateMessage],
) -> tuple[str, int]:
    context = GenerateContext(
        messages=list(messages),
        steps=0,
        max_new_length=MAX_NEW_LENGTH_BON,
        extract_write_region=False,
        channel=GenerationChannel.CONTINUATION,
    )
    result = generator.backend.generate_step(context)
    return result.delta_text, result.delta_tokens


# Sentinel error count for BoN-nsr ranking when the sample produced no usable
# code (empty write-region or missing markers). Large enough to always lose
# to any real-error-count sample, small enough to avoid JSON overflow.
_EMPTY_CODE_ERROR_SENTINEL = 10**9

# rustc summary: "error: aborting due to N previous errors" (plural) or
# "error: aborting due to previous error" (singular, N=1).
_RUSTC_ABORT_SUMMARY_RE = re.compile(
    r"error: aborting due to (?:(\d+) previous errors?|previous error)"
)


def _count_rustc_errors(stderr: str) -> int:
    """Count rustc error-level diagnostics, filtering warnings.

    Prefers rustc's own "aborting due to N previous errors" summary when
    present. Falls back to counting `error[...]:` and top-level `error:`
    lines (excluding the aborting summary itself).
    """
    m = _RUSTC_ABORT_SUMMARY_RE.search(stderr)
    if m is not None:
        return int(m.group(1)) if m.group(1) else 1
    count = 0
    for line in stderr.splitlines():
        stripped = line.strip()
        if stripped.startswith("error[") and "]:" in stripped:
            count += 1
        elif stripped.startswith("error:") and "aborting due to" not in stripped:
            count += 1
    return count


def _compile_rust_code(rust_code: str) -> tuple[bool, str, int]:
    """Compile rust code with rustc only (no diff tests).

    Returns:
        (compiles, compiler_output, error_count)
        error_count is 0 iff `compiles is True`; otherwise at least 1.
    """
    if not rust_code.strip():
        return (
            False,
            "- rustc received empty Rust code (no code extracted from model output)",
            _EMPTY_CODE_ERROR_SENTINEL,
        )
    with tempfile.TemporaryDirectory(prefix="eval-rustc-") as tmpdir:
        compile_result, _ = compile_and_run(rust_code, [], "rust", Path(tmpdir))
    outputs = [part for part in (compile_result.stderr, compile_result.stdout) if part]
    compiler_output = "\n".join(outputs).strip()
    compiles = not compile_result.compilation_failed and not compile_result.timed_out
    if compiles:
        error_count = 0
    else:
        error_count = _count_rustc_errors(compile_result.stderr or "")
        # Timeout / non-zero exit with unparseable stderr still means failure.
        if error_count == 0:
            error_count = 1
    return compiles, compiler_output, error_count


def _format_compile_feedback(compiler_output: str, max_lines: int = 20) -> str:
    lines = [line.strip() for line in compiler_output.splitlines() if line.strip()]
    if not lines:
        return "- rustc did not emit diagnostics"
    shown = lines[:max_lines]
    if len(lines) > max_lines:
        shown.append(f"... {len(lines) - max_lines} more lines omitted")
    return "\n".join(f"- {line}" for line in shown)


def _experiment_oracles() -> list[Oracle]:
    return [RustcOracle()]


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
            c_stderr_snippet = (c_compile.stderr or "").strip().splitlines()[:3]
            print(
                "  !! eval WARN: C reference compilation failed; "
                "Rust compile not attempted. Returned compiles=False does NOT mean the Rust code is broken.",
                flush=True,
            )
            for ln in c_stderr_snippet:
                print(f"     c_stderr: {ln}", flush=True)
            return False, 0, len(test_cases)

        rust_compile, rust_results = compile_and_run(rust_code, test_cases, "rust", rust_dir)
        if rust_compile.compilation_failed:
            rust_stderr_snippet = (rust_compile.stderr or "").strip().splitlines()[:3]
            print(
                "  !! eval WARN: Rust compilation failed in evaluate_final_rust_code "
                "(C reference compiled OK).",
                flush=True,
            )
            for ln in rust_stderr_snippet:
                print(f"     rust_stderr: {ln}", flush=True)
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
        raw_output, trace = run_dtv_loop(
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


def _extract_bailout_postlude(raw_text: str, markers: WriteRegionMarkers) -> str | None:
    """Return in-loop bailout diagnostics that DTV appended after END marker.

    Mirrors the JS->TS runner; see `_handle_bailout_terminate` in
    controller/loop.py for the producer side.
    """
    end_idx = raw_text.find(markers.end_marker)
    if end_idx < 0:
        return None
    after_end = raw_text[end_idx + len(markers.end_marker):].strip()
    if not after_end.startswith(BAILOUT_DIAGNOSTICS_HEADER):
        return None
    return after_end


def program_eval_loop(
    initial_code: str | None,
    prompt: str,
    budget: Budget,
    markers: WriteRegionMarkers,
    regenerate_round: Callable[[list[GenerateMessage], Budget], RegenerationRoundResult],
    last_raw_output: str = "",
    max_rounds: int | None = OUTER_MAX_ROUNDS,
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
            if max_rounds is not None and rounds >= max_rounds:
                break
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

        compiles, compiler_output, _ = _compile_rust_code(code)
        bailout_postlude = _extract_bailout_postlude(last_raw, markers)
        trace.append({
            "phase": "outer",
            "round": rounds,
            "action": "VERIFY_PROGRAM",
            "tokens_used": budget.gen_tokens_used,
            "compiles": compiles,
            "used_bailout_feedback": bailout_postlude is not None and not compiles,
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

        if max_rounds is not None and rounds >= max_rounds:
            break

        feedback_count += 1
        rollback_count += 1
        repair_feedback_text = bailout_postlude if bailout_postlude else compiler_output
        repair_prompt = _build_repair_prompt(repair_feedback_text, markers)
        messages = [
            GenerateMessage(role="user", content=prompt, stop=True),
            GenerateMessage(role="assistant", content=last_raw, stop=True),
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


# -- BoN-nsr (Best-of-N, no self-repair) --------------------------------------

@dataclass
class BoNSampleRecord:
    sample_idx: int
    code: str
    compiles: bool
    error_count: int
    tokens_used: int
    selected: bool = False


def _run_bon_nsr(
    generator: GeneratorAdapter,
    prompt: str,
    budget: Budget,
    markers: WriteRegionMarkers,
    n: int,
) -> tuple[str, str, list[BoNSampleRecord], list[dict]]:
    """Run Best-of-N with no per-sample self-repair.

    Generates up to N independent one-shot samples. Token budget is used
    only as posthoc cost accounting for BoN, not as a generation-time
    sampling limit. Samples are ranked by rustc error count (warnings
    excluded). The first sample with `error_count == 0` triggers early-stop
    of the sampling loop.

    Returns:
        (selected_code, selected_raw_output, records, trace_log)
        - selected_code: the write-region code of the chosen sample (may be "")
        - selected_raw_output: raw model output of the chosen sample
        - records: one BoNSampleRecord per actually-generated sample
        - trace_log: one dict per sample (phase="bon") for RunResult.trace_log
    """
    records: list[BoNSampleRecord] = []
    trace_log: list[dict] = []
    raw_outputs: list[str] = []

    for idx in range(n):
        messages = [
            GenerateMessage(role="user", content=prompt, stop=True),
            GenerateMessage(role="assistant", content="", stop=False),
        ]
        with _temporary_no_stopping_criteria(generator):
            raw_output, delta_tokens = _generate_bon_round(generator, messages)

        # BoN treats token budget as posthoc cost accounting. Do not use the
        # budget to limit sampling; record the actual draw after generation.
        budget.add_tokens(delta_tokens)

        extracted = _extract_write_region_code(raw_output, markers)
        if extracted is None or not extracted.strip():
            compiles = False
            error_count = _EMPTY_CODE_ERROR_SENTINEL
            code_text = extracted or ""
            verifier_output = "- rustc received empty Rust code (no code extracted from model output)"
        else:
            code_text = extracted
            compiles, verifier_output, error_count = _compile_rust_code(code_text)
        verifier_verdict = "pass" if compiles else "fail"

        records.append(BoNSampleRecord(
            sample_idx=idx,
            code=code_text,
            compiles=compiles,
            error_count=error_count,
            tokens_used=delta_tokens,
        ))
        raw_outputs.append(raw_output)
        trace_log.append({
            "phase": "bon",
            "sample_idx": idx,
            "tokens": delta_tokens,
            "verifier": "rustc",
            "verdict": verifier_verdict,
            "compiles": compiles,
            "errors": error_count,
            "verifier_output": verifier_output,
            "code_hash": hash(code_text) & 0xFFFFFFFF,
            "selected": False,
        })

        if error_count == 0:
            break

    if not records:
        return "", "", [], trace_log

    # Selection: minimum error_count; ties broken by first-appearing (min()
    # returns the first index with the minimum value).
    best_idx = min(range(len(records)), key=lambda i: records[i].error_count)
    records[best_idx].selected = True
    trace_log[best_idx]["selected"] = True

    return records[best_idx].code, raw_outputs[best_idx], records, trace_log


# -- S* (parallel sampling + iterative compile-based self-debug) --------------

@dataclass
class SStarSampleRoundRecord:
    """One round (initial generation OR self-debug regeneration) of one sample.

    For round_idx=0 this is the initial generation. For round_idx>=1 this is
    a self-debug regeneration using rustc diagnostics from the previous round
    as feedback.
    """
    sample_idx: int
    round_idx: int
    code: str
    compiles: bool
    error_count: int
    tokens_used: int
    # rustc diagnostics from this round, truncated upstream of trace storage.
    # Empty string when the round produced compiling code.
    compiler_output: str


@dataclass
class SStarSampleRecord:
    """Final state of one S* sample after up to R rounds."""
    sample_idx: int
    final_round_idx: int
    rounds: list[SStarSampleRoundRecord]
    final_code: str
    final_compiles: bool
    final_error_count: int
    total_tokens: int
    selected: bool = False


def _s_star_select_best_idx(records: list[SStarSampleRecord]) -> int:
    """Lexicographic argmin selection: prefer compiling, then min errors, then first idx.

    Sort key per sample i: (not final_compiles, final_error_count, i).
    Mirrors S* `selection=first` semantics for the no-behavioral-test setup.
    """
    if not records:
        raise ValueError("cannot select from empty records")
    return min(
        range(len(records)),
        key=lambda i: (not records[i].final_compiles, records[i].final_error_count, i),
    )


def _build_s_star_self_debug_prompt(
    base_prompt: str,
    rounds: list[SStarSampleRoundRecord],
    markers: WriteRegionMarkers,
) -> str:
    """Build a self-debug prompt that accumulates prior code + rustc feedback.

    Format mirrors S*'s `prompt_with_trace` accumulation. The trailing
    instruction tells the model how to emit corrected code via write-region
    markers (we do not rely on markdown fences).
    """
    parts = [base_prompt.rstrip()]
    for prev in rounds:
        parts.append(f"\n[Round {prev.round_idx} Generated code]:\n{prev.code}")
        feedback_text = _format_compile_feedback(prev.compiler_output)
        parts.append(f"\n[Round {prev.round_idx} Test Feedback]:\n{feedback_text}")
    parts.append(
        "\nThe previous Rust code failed to compile. Fix the compile errors "
        "and return a full corrected Rust program.\n"
        f"Output the corrected code inside {markers.begin_marker} ... "
        f"{markers.end_marker} markers.\n"
        "Do not use markdown fences inside the write region."
    )
    return "\n".join(parts)


def _run_s_star(
    generator: GeneratorAdapter,
    prompt: str,
    budget: Budget,
    markers: WriteRegionMarkers,
    n: int,
    num_rounds: int,
) -> tuple[str, str, list[SStarSampleRecord], list[dict]]:
    """Run S*-style baseline: N samples x up to R rounds of compile-based self-debug.

    Stage 1 (Generation):
        For each sample idx in 0..N-1:
            round 0: generate fresh from `prompt` (same shape as BoN)
            for r in 1..num_rounds-1:
                if previous round compiled: break early (selfdebug_decision="exit")
                else: regenerate with prior code + rustc diagnostics as feedback

    Stage 2 (Selection):
        Lexicographic argmin over (not final_compiles, final_error_count, idx).
        Prefer compiling samples; among those prefer fewer rustc errors;
        ties broken by first-appearing.

    Token budget is posthoc accounting only (matches BoN). Unlike BoN, all N
    samples are run regardless of whether earlier ones compile cleanly.
    """
    records: list[SStarSampleRecord] = []
    trace_log: list[dict] = []
    raw_outputs_final: list[str] = []

    for idx in range(n):
        rounds: list[SStarSampleRoundRecord] = []
        last_raw_output = ""

        for r in range(num_rounds):
            if r == 0:
                messages = [
                    GenerateMessage(role="user", content=prompt, stop=True),
                    GenerateMessage(role="assistant", content="", stop=False),
                ]
            else:
                # Self-debug: feed prior rounds' code + rustc diagnostics.
                self_debug_prompt = _build_s_star_self_debug_prompt(
                    base_prompt=prompt,
                    rounds=rounds,
                    markers=markers,
                )
                messages = [
                    GenerateMessage(role="user", content=self_debug_prompt, stop=True),
                    GenerateMessage(role="assistant", content="", stop=False),
                ]

            with _temporary_no_stopping_criteria(generator):
                raw_output, delta_tokens = _generate_bon_round(generator, messages)
            budget.add_tokens(delta_tokens)
            last_raw_output = raw_output

            extracted = _extract_write_region_code(raw_output, markers)
            if extracted is None or not extracted.strip():
                compiles = False
                error_count = _EMPTY_CODE_ERROR_SENTINEL
                code_text = extracted or ""
                verifier_output = "- rustc received empty Rust code (no code extracted from model output)"
            else:
                code_text = extracted
                compiles, verifier_output, error_count = _compile_rust_code(code_text)

            round_record = SStarSampleRoundRecord(
                sample_idx=idx,
                round_idx=r,
                code=code_text,
                compiles=compiles,
                error_count=error_count,
                tokens_used=delta_tokens,
                compiler_output="" if compiles else verifier_output,
            )
            rounds.append(round_record)

            trace_log.append({
                "phase": "s_star",
                "sample_idx": idx,
                "round_idx": r,
                "tokens": delta_tokens,
                "verifier": "rustc",
                "verdict": "pass" if compiles else "fail",
                "compiles": compiles,
                "errors": error_count,
                "verifier_output": verifier_output,
                "code_hash": hash(code_text) & 0xFFFFFFFF,
                "selected": False,
            })

            # selfdebug_decision="exit": stop early once a sample compiles.
            if compiles:
                break

        last_round = rounds[-1]
        records.append(SStarSampleRecord(
            sample_idx=idx,
            final_round_idx=last_round.round_idx,
            rounds=rounds,
            final_code=last_round.code,
            final_compiles=last_round.compiles,
            final_error_count=last_round.error_count,
            total_tokens=sum(rr.tokens_used for rr in rounds),
        ))
        raw_outputs_final.append(last_raw_output)

    if not records:
        return "", "", [], trace_log

    best_idx = _s_star_select_best_idx(records)
    records[best_idx].selected = True

    # Mark the selected sample's FINAL round in the trace as selected. Since
    # trace entries are appended (sample_idx, round_idx) in order, the chosen
    # entry is the last one matching (best_idx, final_round_idx).
    final_round_idx = records[best_idx].final_round_idx
    for entry in trace_log:
        if entry["sample_idx"] == best_idx and entry["round_idx"] == final_round_idx:
            entry["selected"] = True

    return (
        records[best_idx].final_code,
        raw_outputs_final[best_idx],
        records,
        trace_log,
    )


# -- Runner --------------------------------------------------------------------

def run_single(
    case_id: str,
    config: DefaultPolicyConfig,
    config_name: str,
    generator: GeneratorAdapter,
    token_budget: int,
    pass_output_dir: Path,
    markers: WriteRegionMarkers = DEFAULT_WRITE_REGION_MARKERS,
    budget_k: float | None = None,
    bon_n: int | None = None,
    s_star_n: int | None = None,
    s_star_num_rounds: int | None = None,
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
    oracle_factory = _experiment_oracles

    t0 = time.time()

    if config_name == "s_star":
        if s_star_n is None or s_star_n <= 0:
            raise ValueError(
                f"s_star_n must be a positive integer for strategy 's_star', got {s_star_n!r}"
            )
        if s_star_num_rounds is None or s_star_num_rounds <= 0:
            raise ValueError(
                f"s_star_num_rounds must be a positive integer for strategy 's_star', "
                f"got {s_star_num_rounds!r}"
            )
        selected_code, _selected_raw, s_star_records, s_star_trace = _run_s_star(
            generator=generator,
            prompt=prompt,
            budget=budget,
            markers=markers,
            n=s_star_n,
            num_rounds=s_star_num_rounds,
        )
        elapsed = time.time() - t0
        compiles, test_passed, test_total = evaluate_final_rust_code(
            rust_code=selected_code,
            c_source=c_source,
            test_cases=test_cases,
        )
        final_verdict = "pass" if compiles else "fail"
        saved_output_path = None
        if final_verdict == "pass":
            saved_output_path = _save_pass_output(
                pass_output_dir=pass_output_dir,
                case_id=case_id,
                config_name=config_name,
                final_code=selected_code,
            )
        total_rounds = sum(len(rec.rounds) for rec in s_star_records)
        feedback_used = sum(1 for rec in s_star_records for _ in rec.rounds[1:])
        return RunResult(
            case_id=case_id,
            config=config_name,
            final_verdict=final_verdict,
            total_tokens=budget.gen_tokens_used,
            total_steps=total_rounds,
            elapsed_s=round(elapsed, 1),
            verify_count=total_rounds,
            feedback_count=feedback_used,
            rollback_count=0,
            commit_count=0,
            compiles=compiles,
            test_passed=test_passed,
            test_total=test_total,
            saved_output_path=saved_output_path,
            trace_log=s_star_trace,
        )

    if config_name == "bon-nsr":
        if bon_n is None or bon_n <= 0:
            raise ValueError(f"bon_n must be a positive integer for strategy 'bon-nsr', got {bon_n!r}")
        selected_code, _selected_raw, bon_records, bon_trace = _run_bon_nsr(
            generator=generator,
            prompt=prompt,
            budget=budget,
            markers=markers,
            n=bon_n,
        )
        elapsed = time.time() - t0
        compiles, test_passed, test_total = evaluate_final_rust_code(
            rust_code=selected_code,
            c_source=c_source,
            test_cases=test_cases,
        )
        final_verdict = "pass" if compiles else "fail"
        saved_output_path = None
        if final_verdict == "pass":
            saved_output_path = _save_pass_output(
                pass_output_dir=pass_output_dir,
                case_id=case_id,
                config_name=config_name,
                final_code=selected_code,
            )
        return RunResult(
            case_id=case_id,
            config=config_name,
            final_verdict=final_verdict,
            total_tokens=budget.gen_tokens_used,
            total_steps=len(bon_records),
            elapsed_s=round(elapsed, 1),
            verify_count=len(bon_records),
            feedback_count=0,
            rollback_count=0,
            commit_count=0,
            compiles=compiles,
            test_passed=test_passed,
            test_total=test_total,
            saved_output_path=saved_output_path,
            trace_log=bon_trace,
        )

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
            max_steps=INNER_MAX_STEPS,
            max_new_length=MAX_NEW_LENGTH,
        )
        renderer = renderer_factory()
        oracles = oracle_factory()
        feedback_state = FeedbackState()
        rollback_manager = RollbackManager()
        policy = DefaultPolicy(config)
        generator.reset_output_extractor()

        raw_output, trace = run_dtv_loop(
            generator=generator,
            renderer=renderer,
            oracles=oracles,
            budget=budget,
            feedback_state=feedback_state,
            rollback_manager=rollback_manager,
            policy=policy,
            feedback_lang_config=RUST_FEEDBACK_LANG,
            repair_feedback_format_config=RepairFeedbackFormatConfig(include_failed_snippet=True),
            max_steps=INNER_MAX_STEPS,
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

        initial_code = _extract_write_region_code(raw_output, markers)
        last_raw_output = raw_output

    # Outer SR cap is identical across all configs; ablation-specific feedback
    # semantics live in trace_log phase markers, not in this knob.
    outer_max_rounds = OUTER_MAX_ROUNDS
    eval_result = program_eval_loop(
        initial_code=initial_code,
        prompt=prompt,
        budget=budget,
        markers=markers,
        regenerate_round=regenerate_round,
        last_raw_output=last_raw_output,
        max_rounds=outer_max_rounds,
    )

    elapsed = time.time() - t0

    compiles, test_passed, test_total = evaluate_final_rust_code(
        rust_code=eval_result.final_code,
        c_source=c_source,
        test_cases=test_cases,
    )

    combined_trace = gen_trace + eval_result.trace

    if compiles:
        final_verdict = "pass"
    else:
        final_verdict = "fail"

    saved_output_path = None
    if final_verdict == "pass":
        saved_output_path = _save_pass_output(
            pass_output_dir=pass_output_dir,
            case_id=case_id,
            config_name=config_name,
            final_code=eval_result.final_code,
        )

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
        saved_output_path=saved_output_path,
        trace_log=combined_trace,
    )


# -- Output --------------------------------------------------------------------

def print_summary(
    results: list[RunResult],
    model_name: str,
    token_budget: int,
    budget_k: float | None,
) -> None:
    budget_desc = f"BudgetK={budget_k}" if budget_k is not None else f"TokenBudget={token_budget}"

    # Per-strategy generic summary: always prints, handles any strategy
    # (naive, dtv, bon-nsr, ...). Useful when a run contains only one
    # strategy (e.g., --strategy bon-nsr) and the A/B table below would
    # otherwise print empty rows.
    by_config: dict[str, list[RunResult]] = {}
    for r in results:
        by_config.setdefault(r.config, []).append(r)

    print(f"\n{'=' * 95}")
    print(f"PER-STRATEGY SUMMARY  Model={model_name}  {budget_desc}")
    print(f"{'=' * 95}")
    for config_name in sorted(by_config.keys()):
        subset = by_config[config_name]
        passes = sum(1 for r in subset if r.final_verdict == "pass")
        crashes = sum(1 for r in subset if r.final_verdict == "crash")
        tests_pass = sum(r.test_passed for r in subset)
        tests_total = sum(r.test_total for r in subset)
        avg_tok = sum(r.total_tokens for r in subset) / max(len(subset), 1)
        avg_time = sum(r.elapsed_s for r in subset) / max(len(subset), 1)
        print(
            f"  [{config_name:<10}] Cases: {len(subset):>4}  Pass: {passes:>4}/{len(subset):<4}  "
            f"Tests: {tests_pass:>4}/{tests_total:<4}  Crash: {crashes:>3}  "
            f"AvgTok: {avg_tok:>6.0f}  AvgTime: {avg_time:>5.1f}s"
        )

    dtv = {r.case_id: r for r in results if r.config == "dtv"}
    naive = {r.case_id: r for r in results if r.config == "naive"}
    if not (dtv and naive):
        return
    case_ids = list(dict.fromkeys(r.case_id for r in results))

    col = (
        f"{'Case':<15} | "
        f"{'Verd':<7} {'Tok':>6} {'Stp':>5} {'V':>3} {'F':>3} {'R':>3} {'C':>2} {'Tests':>7} | "
        f"{'Verd':<7} {'Tok':>6} {'Stp':>5} {'V':>3} {'F':>3} {'R':>3} {'C':>2} {'Tests':>7}"
    )
    budget_desc = f"BudgetK={budget_k}" if budget_k is not None else f"TokenBudget={token_budget}"
    print(f"\n{'=' * 95}")
    print("A/B COMPARISON: DTV vs Naive Feedback")
    print(f"Model={model_name}  {budget_desc}  MaxSteps={INNER_MAX_STEPS}")
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
    parser = argparse.ArgumentParser(description="C->Rust translation experiment (naive, dtv, bon-nsr, or s_star)")
    parser.add_argument("case_ids", nargs="*", default=DEFAULT_CASE_IDS, help="Case IDs to run")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Output JSON path")
    parser.add_argument(
        "--strategy",
        choices=("naive", "dtv", "bon-nsr", "s_star",
                 "dtv-no-feedback", "dtv-no-escalation", "dtv-detect-and-abort"),
        required=True,
        help=(
            "Generation strategy: "
            "naive (one-shot), dtv (verified, full DTV), "
            "bon-nsr (Best-of-N, no per-sample self-repair), "
            "s_star (S*-style: parallel sampling + iterative compile-based self-debug), "
            "dtv-no-feedback / dtv-no-escalation / dtv-detect-and-abort (RQ3 ablations)"
        ),
    )
    parser.add_argument(
        "--bon-n",
        type=int,
        default=None,
        help="Number of samples for --strategy bon-nsr (required when strategy=bon-nsr; no default)",
    )
    parser.add_argument(
        "--s-star-n",
        type=int,
        default=None,
        help=(
            "Number of parallel samples for --strategy s_star "
            "(default 8 when omitted). Only valid with --strategy=s_star."
        ),
    )
    parser.add_argument(
        "--s-star-num-rounds",
        type=int,
        default=None,
        help=(
            "Number of self-debug rounds per sample for --strategy s_star "
            "(default 3 when omitted = 1 initial + 2 debug; matches S* paper R=2 debug rounds). "
            "Only valid with --strategy=s_star."
        ),
    )
    parser.add_argument(
        "--backend",
        choices=("qwen", "gemma"),
        default="qwen",
        help="Generator backend (default: qwen)",
    )
    parser.add_argument(
        "--model-name",
        default=None,
        help="HuggingFace model ID (default: backend-specific default)",
    )
    parser.add_argument("--token-budget", type=int, default=OUTPUT_TOKEN_CAP, help="Fixed token budget")
    parser.add_argument("--budget-k", type=float, default=None,
                        help="Per-case budget = k * C_source_tokens (overrides --token-budget)")
    parser.add_argument("--greedy", action="store_true", help="Greedy decoding (do_sample=False)")
    args = parser.parse_args()

    if args.strategy == "bon-nsr":
        if args.bon_n is None:
            parser.error("--bon-n is required when --strategy=bon-nsr")
        if args.bon_n <= 0:
            parser.error(f"--bon-n must be a positive integer, got {args.bon_n}")
    elif args.bon_n is not None:
        parser.error(f"--bon-n is only valid with --strategy=bon-nsr (got --strategy={args.strategy})")

    if args.strategy == "s_star":
        if args.s_star_n is None:
            args.s_star_n = 8
        elif args.s_star_n <= 0:
            parser.error(f"--s-star-n must be a positive integer, got {args.s_star_n}")
        if args.s_star_num_rounds is None:
            args.s_star_num_rounds = 3
        elif args.s_star_num_rounds <= 0:
            parser.error(
                f"--s-star-num-rounds must be a positive integer, got {args.s_star_num_rounds}"
            )
    else:
        if args.s_star_n is not None:
            parser.error(
                f"--s-star-n is only valid with --strategy=s_star "
                f"(got --strategy={args.strategy})"
            )
        if args.s_star_num_rounds is not None:
            parser.error(
                f"--s-star-num-rounds is only valid with --strategy=s_star "
                f"(got --strategy={args.strategy})"
            )

    case_ids: list[str] = args.case_ids
    output_path: Path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pass_output_dir = output_path.parent / f"{output_path.stem}_pass_outputs"

    # Resume from incremental save (see write at end of for-loop). Required
    # for preempt-capable Slurm partitions where workers may be killed mid-run.
    existing_results: list[RunResult] = []
    if output_path.exists():
        try:
            existing_data = json.loads(output_path.read_text(encoding="utf-8"))
            if isinstance(existing_data, list):
                existing_results = [RunResult(**r) for r in existing_data]
                done_case_ids = {r.case_id for r in existing_results}
                original_count = len(case_ids)
                case_ids = [cid for cid in case_ids if cid not in done_case_ids]
                print(
                    f"Resume: {len(done_case_ids)} done, "
                    f"{len(case_ids)} remaining (was {original_count})",
                    flush=True,
                )
        except Exception as exc:
            print(
                f"WARNING: failed to load existing output for resume "
                f"({exc}); starting fresh",
                flush=True,
            )
            existing_results = []

    backend_cls, model_name = resolve_backend_config(
        backend=args.backend,
        model_name=args.model_name,
    )
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
        backend_cls=backend_cls,
        do_sample=do_sample,
    )

    budget_desc = f"BudgetK={budget_k}" if budget_k is not None else f"TokenBudget={token_budget}"
    sampling_desc = "greedy" if args.greedy else "default"
    strategy_desc = args.strategy
    if args.strategy == "bon-nsr":
        strategy_desc = f"bon-nsr (N={args.bon_n})"
    elif args.strategy == "s_star":
        strategy_desc = f"s_star (N={args.s_star_n}, R={args.s_star_num_rounds})"
    print(f"Model loaded: {model_name}")
    print(f"Backend: {args.backend}")
    print(f"Strategy: {strategy_desc}")
    print(f"Cases: {len(case_ids)}, {budget_desc}, MaxSteps={INNER_MAX_STEPS}, Sampling={sampling_desc}")
    print(f"Output: {output_path}")

    results: list[RunResult] = list(existing_results)
    if args.strategy in DTV_STRATEGY_CONFIGS:
        configs = [(args.strategy, DTV_STRATEGY_CONFIGS[args.strategy])]
    elif args.strategy in ("naive", "bon-nsr", "s_star"):
        # These strategies don't use DTV config; pass DTV_CONFIG as placeholder
        # that the naive/bon-nsr/s_star code paths will ignore.
        configs = [(args.strategy, DTV_CONFIG)]
    else:
        raise ValueError(f"unhandled strategy: {args.strategy}")

    for i, case_id in enumerate(case_ids, 1):
        for config_name, config in configs:
            print(f"\n[{i}/{len(case_ids)}] {case_id} / {config_name} ...", flush=True)
            try:
                result = run_single(
                    case_id, config, config_name, generator,
                    token_budget=token_budget,
                    pass_output_dir=pass_output_dir,
                    markers=markers,
                    budget_k=budget_k,
                    bon_n=args.bon_n,
                    s_star_n=args.s_star_n,
                    s_star_num_rounds=args.s_star_num_rounds,
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

        tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps([asdict(r) for r in results], indent=2), encoding="utf-8"
        )
        tmp_path.replace(output_path)

    print_summary(results, model_name=model_name, token_budget=token_budget, budget_k=budget_k)
    print(f"\nFull results: {output_path}")


if __name__ == "__main__":
    main()
