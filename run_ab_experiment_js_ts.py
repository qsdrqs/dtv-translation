#!/usr/bin/env python3
"""A/B experiment: DTV vs naive feedback under equal token budget.

Runs each case twice (DTV config, naive config) and compares:
- Final verdict (program-level pass/fail)
- Tokens consumed
- Number of verify/feedback/rollback cycles

Usage:
    .venv/bin/python run_ab_experiment_js_ts.py [OPTIONS] [case_id ...]

Options:
    --all                   Run all cases found in the dataset directory
    --dataset-dir PATH      Dataset directory (default: DTV_JS_TS_DATASET_DIR or dataset_js_ts)
    --output PATH           Output JSON path (default: result/ab_experiment_js_ts_results.json)
    --model-name NAME       HuggingFace model ID (default: Qwen/Qwen3-4B-Instruct-2507)
    --token-budget N        Fixed token budget (default: 20480)
    --budget-k K            Per-case budget = K * JS_source_tokens (overrides --token-budget)
    --greedy                Use greedy decoding (do_sample=False)

Pass explicit case IDs or use --all to scan the dataset directory.
Use --output to write results to a custom path.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol, cast

from controller.adapters import GeneratorAdapter
from controller.loop import run_dtv_loop
from controller.policy import DefaultPolicy, DefaultPolicyConfig
from controller.stop_criteria import DTVStoppingCriteria, TS_PROFILE
from core.budget import Budget
from core.llm_output import WriteRegionParser
from core.types import (
    Action,
    GenerateContext,
    GenerationChannel,
    GenerateMessage,
    Granularity,
    RenderStatus,
    TraceEvent,
    TranslationSample,
    Verdict,
)
from feedback.feedback import FeedbackState
from feedback.formatter import RepairFeedbackFormatConfig
from js_ts.feedback import TS_FEEDBACK_LANG
from js_ts.oracles import EslintOracle, TscOracle, TscProgramOracle
from js_ts.oracles.compiler_oracle.tsc_driver import _find_type_roots
from js_ts.render import JSToTSRenderer
from rollback.manager import RollbackManager
from transformers import PreTrainedTokenizerBase, StoppingCriteriaList

MODEL_NAME = "Qwen/Qwen3.5-4B"
OUTPUT_TOKEN_CAP = 20480
TOKEN_BUDGET = OUTPUT_TOKEN_CAP
MAX_NEW_LENGTH = 16384
MAX_STEPS = 2000
PROMPT_PREFIX = "Translate the following JavaScript code into TypeScript with strict type annotations:"
DATASET_DIR = Path(os.environ.get("DTV_JS_TS_DATASET_DIR", "dataset_js_ts"))
RESULT_DIR = Path("result")
OUTPUT_PATH = RESULT_DIR / "ab_experiment_js_ts_results.json"

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

NAIVE_CONFIG = DefaultPolicyConfig(
    verify_on_boundary=False,
    verify_on_close=False,
    boundary_granularity=Granularity.STMT,
    close_granularity=Granularity.FUNC,
    enable_rollback=True,
    default_fail_scope=Granularity.PROGRAM,
    enable_feedback=True,
    repair_verify_granularity=Granularity.PROGRAM,
)


class _StopCriteriaBackend(Protocol):
    stop_criteria: StoppingCriteriaList


class _TokenizerBackend(Protocol):
    tokenizer: PreTrainedTokenizerBase


_TS_FENCE_RE = re.compile(r"```(?:typescript|ts)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_ANY_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


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


@dataclass
class NaiveLoopResult:
    final_prefix: str
    final_verdict: str
    total_tokens: int
    total_steps: int
    verify_count: int
    feedback_count: int
    rollback_count: int
    commit_count: int
    trace_log: list[dict] | None = None


def _all_pass(outputs: tuple) -> bool:
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


def extract_metrics(trace: list[TraceEvent]) -> dict:
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

    final_verdict = "unknown"
    for event in reversed(trace):
        if (
            event.action == Action.VERIFY
            and event.verification_granularity == Granularity.PROGRAM
            and event.oracle_outputs
        ):
            final_verdict = "pass" if _all_pass(event.oracle_outputs) else "fail"
            break

    total_tokens = trace[-1].budget_snapshot.get("gen_tokens_used", 0) if trace else 0

    return {
        "final_verdict": final_verdict,
        "total_tokens": total_tokens,
        "total_steps": len(trace),
        "verify_count": verify_count,
        "feedback_count": feedback_count,
        "rollback_count": rollback_count,
        "commit_count": commit_count,
        "trace_log": trace_log,
    }


def load_sample(case_dir: Path) -> TranslationSample:
    js_source = (case_dir / "source.js").read_text(encoding="utf-8").strip()
    return TranslationSample(source_code=js_source, source_lang="js", test_cases=[])


def evaluate_final_program(
    final_prefix: str,
    renderer: JSToTSRenderer,
) -> tuple[bool, int, int]:
    render_result = renderer.try_render(final_prefix)
    if render_result.status != RenderStatus.OK or render_result.artifact is None:
        return False, 0, 0

    ts_code = render_result.artifact.code
    compiles, _ = _compile_ts_code(ts_code)
    return compiles, 0, 0


def evaluate_final_ts_code(ts_code: str) -> tuple[bool, int, int]:
    compiles, _ = _compile_ts_code(ts_code)
    return compiles, 0, 0


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


def _extract_ts_code(raw_text: str) -> str:
    ts_match = _TS_FENCE_RE.search(raw_text)
    if ts_match is not None:
        return ts_match.group(1).strip()

    any_match = _ANY_FENCE_RE.search(raw_text)
    if any_match is not None:
        return any_match.group(1).strip()

    return raw_text.strip()


def _compile_ts_code(ts_code: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="naive-tsc-") as tmpdir:
        ts_file = Path(tmpdir) / "output.ts"
        ts_file.write_text(ts_code, encoding="utf-8")
        type_roots = _find_type_roots()
        type_roots_args = ["--typeRoots", type_roots] if type_roots else []
        tsc_result = subprocess.run(
            [
                "tsc",
                "--pretty",
                "false",
                "--strict",
                "--noEmit",
                "--target",
                "ES2020",
                "--lib",
                "ES2020,DOM",
                "--skipLibCheck",
                *type_roots_args,
                str(ts_file),
            ],
            capture_output=True,
            text=True,
            timeout=10.0,
            check=False,
        )

    outputs = [part for part in (tsc_result.stderr, tsc_result.stdout) if part]
    compiler_output = "\n".join(outputs).strip()
    compiles = tsc_result.returncode == 0
    return compiles, compiler_output


def _format_compile_feedback(compiler_output: str, max_lines: int = 20) -> str:
    lines = [line.strip() for line in compiler_output.splitlines() if line.strip()]
    if not lines:
        return "- tsc did not emit diagnostics"

    shown = lines[:max_lines]
    if len(lines) > max_lines:
        shown.append(f"... {len(lines) - max_lines} more lines omitted")
    return "\n".join(f"- {line}" for line in shown)


def _build_repair_prompt(compiler_output: str) -> str:
    diagnostics_text = _format_compile_feedback(compiler_output)
    return (
        "Your previous TypeScript translation failed to compile.\n"
        "Fix the compile errors and return a full corrected TypeScript program.\n"
        "Do not explain. Return exactly one fenced TypeScript code block.\n\n"
        f"Compiler diagnostics:\n{diagnostics_text}\n"
    )


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


def run_naive_minimal(
    prompt: str,
    generator: GeneratorAdapter,
    token_budget: int,
    accumulate_history: bool = False,
) -> NaiveLoopResult:
    budget = Budget(gen_tokens_budget=token_budget)
    messages: list[GenerateMessage] = [
        GenerateMessage(role="user", content=prompt, stop=True),
        GenerateMessage(role="assistant", content="", stop=False),
    ]

    final_prefix = ""
    final_verdict = "fail"
    total_steps = 0
    verify_count = 0
    feedback_count = 0
    rollback_count = 0
    commit_count = 0
    trace_log: list[dict] = []

    while (MAX_STEPS is None or total_steps < MAX_STEPS) and _remaining_tokens(budget) > 0:
        raw_output, delta_tokens = _generate_full_round(generator, messages, budget)
        total_steps += 1
        if delta_tokens <= 0:
            break

        _set_last_assistant(messages, raw_output, stop=True)
        final_prefix = _extract_ts_code(raw_output)

        verify_count += 1
        compiles, compiler_output = _compile_ts_code(final_prefix)
        trace_log.append({
            "round": total_steps,
            "tokens_used": budget.gen_tokens_used,
            "compiles": compiles,
        })
        if compiles:
            final_verdict = "pass"
            commit_count = 1
            break

        feedback_count += 1
        rollback_count += 1
        if _remaining_tokens(budget) <= 0 or (MAX_STEPS is not None and total_steps >= MAX_STEPS):
            break

        repair_prompt = _build_repair_prompt(compiler_output)
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

    return NaiveLoopResult(
        final_prefix=final_prefix,
        final_verdict=final_verdict,
        total_tokens=budget.gen_tokens_used,
        total_steps=total_steps,
        verify_count=verify_count,
        feedback_count=feedback_count,
        rollback_count=rollback_count,
        commit_count=commit_count,
        trace_log=trace_log,
    )


def run_single(
    case_id: str,
    case_dir: Path,
    config: DefaultPolicyConfig,
    config_name: str,
    generator: GeneratorAdapter,
    token_budget: int,
    budget_k: float | None = None,
) -> RunResult:
    sample = load_sample(case_dir)
    js_source = sample.source_code

    if budget_k is not None:
        backend = cast(_TokenizerBackend, generator.backend)
        js_token_count = len(backend.tokenizer.encode(js_source))
        effective_budget = int(budget_k * js_token_count)
    else:
        effective_budget = token_budget

    prompt = f"\n{PROMPT_PREFIX}\n```javascript\n{js_source}\n```\n"

    renderer = JSToTSRenderer(sample=sample)
    if config_name == "naive":
        t0 = time.time()
        with _temporary_no_stopping_criteria(generator):
            naive_result = run_naive_minimal(
                prompt=prompt,
                generator=generator,
                token_budget=effective_budget,
            )
        elapsed = time.time() - t0
        final_prefix = naive_result.final_prefix
        metrics = {
            "final_verdict": naive_result.final_verdict,
            "total_tokens": naive_result.total_tokens,
            "total_steps": naive_result.total_steps,
            "verify_count": naive_result.verify_count,
            "feedback_count": naive_result.feedback_count,
            "rollback_count": naive_result.rollback_count,
            "commit_count": naive_result.commit_count,
            "trace_log": naive_result.trace_log,
        }
    else:
        oracles = [TscOracle(), TscProgramOracle(), EslintOracle()]
        budget = Budget(gen_tokens_budget=effective_budget)
        feedback_state = FeedbackState()
        rollback_manager = RollbackManager()
        policy = DefaultPolicy(config)

        generator.reset_output_extractor()

        t0 = time.time()
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
            max_steps=MAX_STEPS,
            max_new_length=MAX_NEW_LENGTH,
            prompt_prefix=prompt,
        )
        elapsed = time.time() - t0
        metrics = extract_metrics(trace)

    if config_name == "naive":
        compiles, test_passed, test_total = evaluate_final_ts_code(ts_code=final_prefix)
    else:
        compiles, test_passed, test_total = evaluate_final_program(
            final_prefix=final_prefix,
            renderer=renderer,
        )
    return RunResult(
        case_id=case_id,
        config=config_name,
        elapsed_s=round(elapsed, 1),
        compiles=compiles,
        test_passed=test_passed,
        test_total=test_total,
        **metrics,
    )


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


def main() -> None:
    parser = argparse.ArgumentParser(description="A/B experiment: JS->TS DTV vs naive feedback")
    parser.add_argument("case_ids", nargs="*", help="Case IDs to run")
    parser.add_argument("--all", action="store_true", help="Run all cases in the dataset directory")
    parser.add_argument("--dataset-dir", type=Path, default=DATASET_DIR, help="Dataset directory")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Output JSON path")
    parser.add_argument("--model-name", default=MODEL_NAME, help="HuggingFace model ID")
    parser.add_argument("--token-budget", type=int, default=OUTPUT_TOKEN_CAP, help="Fixed token budget")
    parser.add_argument(
        "--budget-k",
        type=float,
        default=None,
        help="Per-case budget = k * JS_source_tokens (overrides --token-budget)",
    )
    parser.add_argument("--greedy", action="store_true", help="Greedy decoding (do_sample=False)")
    args = parser.parse_args()

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

    model_name: str = args.model_name
    token_budget: int = args.token_budget
    budget_k: float | None = args.budget_k
    do_sample: bool | None = False if args.greedy else None

    write_region_parser = WriteRegionParser()
    generator = GeneratorAdapter(
        model_name=model_name,
        stop_criteria_factory=lambda tok: [
            DTVStoppingCriteria(tok, TS_PROFILE, write_region_parser=write_region_parser)
        ],
        write_region_parser=write_region_parser,
        do_sample=do_sample,
    )

    budget_desc = f"BudgetK={budget_k}" if budget_k is not None else f"TokenBudget={token_budget}"
    sampling_desc = "greedy" if args.greedy else "default"
    print(f"Model loaded: {model_name}")
    print(f"Cases: {len(case_ids)}, {budget_desc}, MaxSteps={MAX_STEPS}, Sampling={sampling_desc}")
    print(f"Dataset: {dataset_dir}")
    print(f"Output: {output_path}")

    results: list[RunResult] = []
    configs = [("dtv", DTV_CONFIG), ("naive", NAIVE_CONFIG)]

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
                    budget_k=budget_k,
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
