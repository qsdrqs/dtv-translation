#!/usr/bin/env python3
"""JS->TS translation experiment runner (naive or dtv strategy).

Both strategies share the same prompt (with write-region contract) and the same
post-generation compile-check-reprompt loop.  The only difference is the
generation phase: DTV uses incremental stmt/block/func verification, naive uses
one-shot generation.

Usage:
    .venv/bin/python run_experiments_js_ts.py --strategy {naive|dtv} [OPTIONS] [case_id ...]

Options:
    --strategy {naive,dtv}  Generation strategy (required)
    --all                   Run all cases found in the dataset directory
    --dataset-dir PATH      Dataset directory (default: DTV_JS_TS_DATASET_DIR or dataset_js_ts)
    --output PATH           Output JSON path (default: result/ab_experiment_js_ts_results.json)
    --model-name NAME       HuggingFace model ID (default: Qwen/Qwen3.5-4B)
    --token-budget N        Fixed token budget (default: 20480)
    --budget-k K            Per-case budget = K * JS_source_tokens (overrides --token-budget)
    --greedy                Use greedy decoding (do_sample=False)

Pass explicit case IDs or use --all to scan the dataset directory.
Use --output to write results to a custom path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time

import torch
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Protocol, cast

from controller.adapters import GeneratorAdapter
from core.gemma_generator_backend import GemmaGeneratorBackend
from core.qwen_generator_backend import QwenGeneratorBackend
from controller.loop import (
    BAILOUT_DIAGNOSTICS_HEADER,
    render_write_region_contract,
    run_dtv_loop,
)
from controller.policy import DefaultPolicy, DefaultPolicyConfig
from controller.stop_criteria import DTVStoppingCriteria, TS_PROFILE
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
    Artifact,
    GenerateContext,
    GenerationChannel,
    GenerateMessage,
    Granularity,
    OracleContext,
    OracleOutput,
    RenderStatus,
    TraceEvent,
    TranslationSample,
    Verdict,
)
from feedback.feedback import FeedbackState
from feedback.formatter import RepairFeedbackFormatConfig
from js_ts.feedback import TS_FEEDBACK_LANG
from js_ts.oracles import EslintOracle, TscOracle
from js_ts.oracles.compiler_oracle.tsc_driver import TscDriver
from js_ts.oracles.compiler_oracle.tsc_parser import parse_tsc_diagnostics
from js_ts.oracles.diagnostic_render import render_diagnostic
from js_ts.oracles.eslint_oracle.eslint_driver import EslintDriver
from js_ts.oracles.eslint_oracle.eslint_parser import parse_eslint_messages
from js_ts.render import JSToTSRenderer
from rollback.manager import RollbackManager
from transformers import PreTrainedTokenizerBase, StoppingCriteriaList

# -- Constants -----------------------------------------------------------------

MODEL_NAME = "Qwen/Qwen3-4B-Instruct-2507"
GEMMA_MODEL_NAME = "google/gemma-4-E4B-it"
OUTPUT_TOKEN_CAP = 6144
TOKEN_BUDGET = OUTPUT_TOKEN_CAP
MAX_NEW_LENGTH = 1024
MAX_NEW_LENGTH_BON = 8192
MAX_STEPS = 2000
PROMPT_PREFIX = "Add TypeScript type annotations to the following JavaScript code. Explicitly annotate every variable, function parameter, and function return type. Only add type annotations, do not change the code structure or logic. If you are unsure about the type, use 'any'.\n\n"
DATASET_DIR = Path(os.environ.get("DTV_JS_TS_DATASET_DIR", "dataset_js_ts"))
RESULT_DIR = Path("result")
OUTPUT_PATH = RESULT_DIR / "ab_experiment_js_ts_results.json"

def resolve_backend_config(
    *,
    backend: str,
    model_name: str | None,
) -> tuple[type[QwenGeneratorBackend] | type[GemmaGeneratorBackend], str]:
    if backend == "gemma":
        resolved_model_name = model_name or GEMMA_MODEL_NAME
        return GemmaGeneratorBackend, resolved_model_name
    resolved_model_name = model_name or MODEL_NAME
    return QwenGeneratorBackend, resolved_model_name


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
    saved_output_path: str | None = None
    trace_log: list[dict] | None = None


def _all_pass(outputs: Sequence[OracleOutput]) -> bool:
    """Same logic as the policy: at least one PASS and no FAIL."""
    saw_pass = False
    for output in outputs:
        if output.verdict == Verdict.FAIL:
            return False
        if output.verdict == Verdict.PASS:
            saw_pass = True
    return saw_pass


def _trace_verdict(oracle_outputs: Sequence[OracleOutput]) -> str | None:
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
    raw_prompt = f"\n{prompt_prefix}\n```javascript\n{source_code}\n```\n"
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
    output_path = target_dir / f"{_sanitize_case_id(case_id)}.ts"
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


def _compile_ts_code(ts_code: str, sample: TranslationSample) -> tuple[bool, str, int]:
    """Compile and lint the TS code.

    Returns:
        (compiles, compiler_output, error_count)
        error_count counts only severity="error" tsc diagnostics plus eslint
        errors (warnings excluded). `error_count == 0` iff `compiles is True`.
    """
    # Empty / whitespace-only TS trivially passes tsc + eslint (no code = no
    # errors), producing false-positive pass verdicts and empty saved output
    # files. Reject such inputs so the outer repair loop and final eval agree
    # that "no code was produced" is a failure.
    if not ts_code.strip():
        return (
            False,
            "- verifier received empty TS code (no code extracted from model output)",
            _EMPTY_CODE_ERROR_SENTINEL,
        )
    with tempfile.TemporaryDirectory(prefix="eval-tsts-") as tmpdir:
        workdir = Path(tmpdir)
        artifact = Artifact(code=ts_code, sample=sample)
        ctx = OracleContext(sample=sample, artifact=artifact, workdir=workdir, timeout_s=10.0)
        tsc_result = TscDriver().check(ctx)
        eslint_result = EslintDriver().check(ts_code, timeout_s=10.0)

    blocks: list[str] = []
    tsc_error_count = 0

    # Outer/final JS->TS verifier is strict: The in-generation TscOracle still
    # filters them for actionable feedback, but the outer/final verdict mirrors
    # the c_rust outer rustc layer (no filter).
    tsc_diagnostics = parse_tsc_diagnostics(tsc_result)
    for diag in tsc_diagnostics:
        blocks.append(render_diagnostic(diag))
        if diag.severity == "error":
            tsc_error_count += 1

    # Timeouts / exit!=0 without parseable diagnostics still indicate failure.
    if tsc_result.timed_out or (tsc_result.exit_code != 0 and tsc_error_count == 0):
        tsc_error_count = max(tsc_error_count, 1)

    stderr = (tsc_result.stderr or "").strip()
    if stderr:
        blocks.append(stderr)

    # Render eslint diagnostics through the parser's render_diagnostic so the
    # outer repair loop and the inner EslintOracle share one source of truth
    # for hint formatting (preserves naive/DTV A/B fairness).
    eslint_diagnostics = parse_eslint_messages(
        eslint_result.messages,
        source_code=ts_code,
        ast_tree=None,
    )
    for diag in eslint_diagnostics:
        blocks.append(render_diagnostic(diag))

    compiler_output = "\n".join(blocks).strip()
    compiles = (
        not tsc_result.timed_out
        and tsc_error_count == 0
        and eslint_result.error_count == 0
    )
    error_count = tsc_error_count + eslint_result.error_count
    return compiles, compiler_output, error_count


def _format_compile_feedback(compiler_output: str, max_lines: int = 40) -> str:
    # compiler_output is already formatted by _compile_ts_code as "- L<l>:<c> | <src>\n    <severity>: <msg>\n    hint: <hint>"
    # blocks. Here we only truncate to keep the prompt bounded.
    lines = compiler_output.splitlines()
    if not any(line.strip() for line in lines):
        return "- verifier did not emit diagnostics"
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... {len(lines) - max_lines} more lines omitted"]
    return "\n".join(lines)


def _build_repair_prompt(compiler_output: str, markers: WriteRegionMarkers) -> str:
    diagnostics_text = _format_compile_feedback(compiler_output)
    return (
        "Your previous TypeScript translation failed verification.\n"
        "Fix the verification errors and return a full corrected TypeScript program.\n"
        f"Output the corrected code inside {markers.begin_marker} ... {markers.end_marker} markers.\n"
        "Do not use markdown fences inside the write region.\n\n"
        f"Diagnostics:\n{diagnostics_text}\n"
    )


def _build_missing_markers_prompt(markers: WriteRegionMarkers) -> str:
    return (
        "Your response did not include write-region markers.\n"
        f"Output the code inside {markers.begin_marker} ... {markers.end_marker} markers.\n"
        "Do not use markdown fences inside the write region.\n"
    )


# -- Loading -------------------------------------------------------------------

def load_sample(case_dir: Path) -> TranslationSample:
    js_source = (case_dir / "source.js").read_text(encoding="utf-8").strip()
    return TranslationSample(source_code=js_source, source_lang="js", test_cases=[])


def evaluate_final_ts_code(
    ts_code: str,
    sample: TranslationSample,
) -> tuple[bool, int, int]:
    compiles, _, _ = _compile_ts_code(ts_code, sample)
    return compiles, 0, 0


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
    renderer_factory: Callable[[], JSToTSRenderer],
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
            feedback_lang_config=TS_FEEDBACK_LANG,
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

    `_handle_bailout_terminate` writes the formatted bailout diagnostics into
    AssistantContent.postlude (text after the END marker) prefixed with
    `BAILOUT_DIAGNOSTICS_HEADER`. Non-bailout terminations leave the postlude
    empty, and any free-form model text after END will not start with that
    header. Used to prefer in-loop bailout diagnostics over noisy outer-loop
    compile output as repair feedback.
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
    sample: TranslationSample,
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

        compiles, compiler_output, _ = _compile_ts_code(code, sample)
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
    sample: TranslationSample,
    n: int,
) -> tuple[str, str, list[BoNSampleRecord], list[dict]]:
    """Run Best-of-N with no per-sample self-repair.

    Generates up to N independent one-shot samples. Token budget is used
    only as posthoc cost accounting for BoN, not as a generation-time
    sampling limit. Samples are ranked by error-severity diagnostic count
    (tsc + eslint, warnings excluded). The first sample with
    `error_count == 0` triggers early-stop of the sampling loop.

    Returns:
        (selected_code, selected_raw_output, records, trace_log)
        - selected_code: the write-region code of the chosen sample (may be "")
        - selected_raw_output: the raw model output of the chosen sample (used
          as last_raw for any downstream tool; not relevant for BoN-nsr
          itself since there is no repair loop)
        - records: one BoNSampleRecord per actually-generated sample
        - trace_log: one dict per sample (phase="bon") for RunResult.trace_log
    """
    records: list[BoNSampleRecord] = []
    trace_log: list[dict] = []
    raw_outputs: list[str] = []

    # Derive a deterministic seed base from the prompt so BoN samples for the
    # same case are reproducible across runs. Python's hash() is seeded per
    # process (PYTHONHASHSEED), so use hashlib for stability. Per-sample seed
    # is seed_base + idx; without this, HF's internal RNG advancement between
    # consecutive generate() calls yields limited variance (adjacent samples
    # often collapse to identical outputs under narrow temp/top_p).
    seed_base = int.from_bytes(
        hashlib.sha256(prompt.encode("utf-8")).digest()[:4],
        "big",
    ) & 0x7FFFFFFF

    for idx in range(n):
        sample_seed = (seed_base + idx) & 0x7FFFFFFF
        torch.manual_seed(sample_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(sample_seed)

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
            verifier_output = "- verifier received empty TS code (no code extracted from model output)"
        else:
            code_text = extracted
            compiles, verifier_output, error_count = _compile_ts_code(code_text, sample)
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
            "verifier": "tsc+eslint",
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


# -- Runner --------------------------------------------------------------------

def run_single(
    case_id: str,
    case_dir: Path,
    config: DefaultPolicyConfig,
    config_name: str,
    generator: GeneratorAdapter,
    token_budget: int,
    pass_output_dir: Path,
    markers: WriteRegionMarkers = DEFAULT_WRITE_REGION_MARKERS,
    budget_k: float | None = None,
    bon_n: int | None = None,
) -> RunResult:
    sample = load_sample(case_dir)
    js_source = sample.source_code

    if budget_k is not None:
        backend = cast(_TokenizerBackend, generator.backend)
        js_token_count = len(backend.tokenizer.encode(js_source))
        effective_budget = int(budget_k * js_token_count)
    else:
        effective_budget = token_budget

    prompt = _build_prompt(js_source, PROMPT_PREFIX, "TypeScript", markers)
    budget = Budget(gen_tokens_budget=effective_budget)
    renderer_factory = lambda: JSToTSRenderer(sample=sample)
    oracle_factory = lambda: cast(list[Oracle], [TscOracle(), EslintOracle()])

    t0 = time.time()

    if config_name == "bon-nsr":
        if bon_n is None or bon_n <= 0:
            raise ValueError(f"bon_n must be a positive integer for strategy 'bon-nsr', got {bon_n!r}")
        selected_code, _selected_raw, bon_records, bon_trace = _run_bon_nsr(
            generator=generator,
            prompt=prompt,
            budget=budget,
            markers=markers,
            sample=sample,
            n=bon_n,
        )
        elapsed = time.time() - t0
        compiles, test_passed, test_total = evaluate_final_ts_code(
            ts_code=selected_code,
            sample=sample,
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
            max_steps=MAX_STEPS,
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
            feedback_lang_config=TS_FEEDBACK_LANG,
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

        initial_code = _extract_write_region_code(raw_output, markers)
        last_raw_output = raw_output

    eval_result = program_eval_loop(
        initial_code=initial_code,
        prompt=prompt,
        budget=budget,
        markers=markers,
        sample=sample,
        regenerate_round=regenerate_round,
        last_raw_output=last_raw_output,
    )

    elapsed = time.time() - t0

    compiles, test_passed, test_total = evaluate_final_ts_code(
        ts_code=eval_result.final_code,
        sample=sample,
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

def _discover_case_ids(dataset_dir: Path) -> list[str]:
    if not dataset_dir.is_dir():
        raise FileNotFoundError(f"dataset directory not found: {dataset_dir}")
    case_ids = sorted(
        path.name
        for path in dataset_dir.iterdir()
        if path.is_dir() and (path / "source.js").is_file()
    )
    if not case_ids:
        raise ValueError(f"no JS->TS cases found in dataset directory: {dataset_dir}")
    return case_ids


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
        avg_tok = sum(r.total_tokens for r in subset) / max(len(subset), 1)
        avg_time = sum(r.elapsed_s for r in subset) / max(len(subset), 1)
        print(
            f"  [{config_name:<10}] Cases: {len(subset):>4}  Pass: {passes:>4}/{len(subset):<4}  "
            f"Crash: {crashes:>3}  AvgTok: {avg_tok:>6.0f}  AvgTime: {avg_time:>5.1f}s"
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
    print("A/B COMPARISON: JS->TS DTV vs Naive Feedback")
    print(f"Model={model_name}  {budget_desc}  MaxSteps={MAX_STEPS}")
    print(f"{'=' * 95}")
    print(f"{'':15}   {'--- DTV (JS->TS) ---':^40}   {'--- Naive (JS->TS) ---':^40}")
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
        "V=verify, F=feedback, R=rollback, C=final TS compiles, Tests=passed/total"
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
    parser = argparse.ArgumentParser(description="JS->TS translation experiment (naive, dtv, or bon-nsr)")
    parser.add_argument("case_ids", nargs="*", help="Case IDs to run")
    parser.add_argument("--all", action="store_true", help="Run all cases in the dataset directory")
    parser.add_argument("--dataset-dir", type=Path, default=DATASET_DIR, help="Dataset directory")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Output JSON path")
    parser.add_argument(
        "--strategy",
        choices=("naive", "dtv", "bon-nsr"),
        required=True,
        help="Generation strategy: naive (one-shot), dtv (verified), or bon-nsr (Best-of-N, no per-sample self-repair)",
    )
    parser.add_argument(
        "--bon-n",
        type=int,
        default=None,
        help="Number of samples for --strategy bon-nsr (required when strategy=bon-nsr; no default)",
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
    parser.add_argument(
        "--budget-k",
        type=float,
        default=None,
        help="Per-case budget = k * JS_source_tokens (overrides --token-budget)",
    )
    parser.add_argument("--greedy", action="store_true", help="Greedy decoding (do_sample=False)")
    args = parser.parse_args()

    if args.strategy == "bon-nsr":
        if args.bon_n is None:
            parser.error("--bon-n is required when --strategy=bon-nsr")
        if args.bon_n <= 0:
            parser.error(f"--bon-n must be a positive integer, got {args.bon_n}")
    elif args.bon_n is not None:
        parser.error(f"--bon-n is only valid with --strategy=bon-nsr (got --strategy={args.strategy})")

    dataset_dir: Path = args.dataset_dir
    if args.all:
        if args.case_ids:
            parser.error("pass case IDs or --all, not both")
        case_ids = _discover_case_ids(dataset_dir)
    else:
        if not args.case_ids:
            parser.error("provide case IDs or use --all")
        case_ids = args.case_ids

    output_path: Path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pass_output_dir = output_path.parent / f"{output_path.stem}_pass_outputs"

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
            DTVStoppingCriteria(tok, TS_PROFILE, write_region_parser=write_region_parser)
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
    print(f"Model loaded: {model_name}")
    print(f"Backend: {args.backend}")
    print(f"Strategy: {strategy_desc}")
    print(f"Cases: {len(case_ids)}, {budget_desc}, MaxSteps={MAX_STEPS}, Sampling={sampling_desc}")
    print(f"Dataset: {dataset_dir}")
    print(f"Output: {output_path}")

    results: list[RunResult] = []
    configs = [(args.strategy, DTV_CONFIG)]

    for i, case_id in enumerate(case_ids, 1):
        case_dir = dataset_dir / case_id
        for config_name, config in configs:
            print(f"\n[{i}/{len(case_ids)}] {case_id} / {config_name} ...", flush=True)
            try:
                result = run_single(
                    case_id,
                    case_dir,
                    config,
                    config_name,
                    generator,
                    token_budget=token_budget,
                    pass_output_dir=pass_output_dir,
                    markers=markers,
                    budget_k=budget_k,
                    bon_n=args.bon_n,
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
