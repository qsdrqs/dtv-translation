#!/usr/bin/env python3
"""A/B experiment: DTV vs naive feedback under equal token budget.

Runs each case twice (DTV config, naive config) and compares:
- Final verdict (program-level pass/fail)
- Tokens consumed
- Number of verify/feedback/rollback cycles

Usage:
    .venv/bin/python run_ab_experiment.py [OPTIONS] [case_id ...]

Options:
    --output PATH           Output JSON path (default: result/ab_experiment_results.json)
    --model-name NAME       HuggingFace model ID (default: Qwen/Qwen3-4B-Instruct-2507)
    --token-budget N        Fixed token budget (default: 6144)
    --budget-k K            Per-case budget = K * C_source_tokens (overrides --token-budget)
    --greedy                Use greedy decoding (do_sample=False)

If no case IDs given, uses the default 10-case smoke set.
Use --output to write results to a custom path (default: result/ab_experiment_results.json).
"""

from __future__ import annotations
import argparse

import json
import os
import re
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol, cast

from c_rust.oracles import FunctionOracle, RustcOracle, RustcProgramOracle
from c_rust.oracles.program_diff_test_oracle.execution_driver import compile_and_run
from c_rust.render import CRustRenderer
from controller.adapters import GeneratorAdapter
from controller.loop import run_dtv_loop
from controller.policy import DefaultPolicy, DefaultPolicyConfig
from controller.stop_criteria import DTVStoppingCriteria, RUST_PROFILE
from core.budget import Budget
from core.llm_output import FenceParser
from core.types import (
    Action,
    GenerateContext,
    GenerationChannel,
    GenerateMessage,
    Granularity,
    RenderStatus,
    RollbackScope,
    TestCase,
    TraceEvent,
    TranslationSample,
    Verdict,
)
from feedback.feedback import FeedbackState
from feedback.formatter import RepairFeedbackFormatConfig
from rollback.manager import RollbackManager
from transformers import PreTrainedTokenizerBase, StoppingCriteriaList

# ── Constants ──────────────────────────────────────────────────────────────────

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
    verify_on_eos=True,
    boundary_granularity=Granularity.STMT,
    eos_granularity=Granularity.PROGRAM,
    enable_rollback=True,
    default_fail_scope=RollbackScope.STMT,
    enable_feedback=True,
    repair_verify_granularity=Granularity.STMT,
)

# Naive: verify only after full generation (EOS), program-level rollback + repair
NAIVE_CONFIG = DefaultPolicyConfig(
    verify_on_boundary=False,
    verify_on_eos=True,
    boundary_granularity=Granularity.STMT,
    eos_granularity=Granularity.PROGRAM,
    enable_rollback=True,
    default_fail_scope=RollbackScope.PROGRAM,
    enable_feedback=True,
    repair_verify_granularity=Granularity.PROGRAM,
)


class _StopCriteriaBackend(Protocol):
    stop_criteria: StoppingCriteriaList


class _TokenizerBackend(Protocol):
    tokenizer: PreTrainedTokenizerBase


_RUST_FENCE_RE = re.compile(r"```(?:rust|rs)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_ANY_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


# ── Metrics ────────────────────────────────────────────────────────────────────

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


# ── Runner ─────────────────────────────────────────────────────────────────────

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


def evaluate_final_program(
    final_prefix: str,
    renderer: CRustRenderer,
    c_source: str,
    test_cases: list[TestCase],
) -> tuple[bool, int, int]:
    """Returns (compiles, test_passed, test_total)."""
    render_result = renderer.try_render(final_prefix)
    if render_result.status != RenderStatus.OK or render_result.artifact is None:
        return False, 0, len(test_cases)

    rust_code = render_result.artifact.code

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


def evaluate_final_rust_code(
    rust_code: str,
    c_source: str,
    test_cases: list[TestCase],
) -> tuple[bool, int, int]:
    with tempfile.TemporaryDirectory(prefix="dtv-eval-naive-") as tmpdir:
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


def _extract_rust_code(raw_text: str) -> str:
    rust_match = _RUST_FENCE_RE.search(raw_text)
    if rust_match is not None:
        return rust_match.group(1).strip()

    any_match = _ANY_FENCE_RE.search(raw_text)
    if any_match is not None:
        return any_match.group(1).strip()

    return raw_text.strip()


def _compile_rust_code(rust_code: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="naive-rustc-") as tmpdir:
        compile_result, _ = compile_and_run(
            rust_code,
            [],
            "rust",
            Path(tmpdir),
        )

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


def _build_repair_prompt(compiler_output: str) -> str:
    diagnostics_text = _format_compile_feedback(compiler_output)
    return (
        "Your previous Rust translation failed to compile.\n"
        "Fix the compile errors and return a full corrected Rust program.\n"
        "Do not explain. Return exactly one fenced Rust code block.\n\n"
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
        extract_fence=False,
        channel=GenerationChannel.CONTINUATION,
    )
    result = generator.backend.generate_step(context)
    budget.add_tokens(result.delta_tokens)
    return result.delta_text, result.delta_tokens


def run_naive_minimal(
    prompt: str,
    generator: GeneratorAdapter,
    token_budget: int,
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
        final_prefix = _extract_rust_code(raw_output)

        verify_count += 1
        compiles, compiler_output = _compile_rust_code(final_prefix)
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
        messages.append(GenerateMessage(role="user", content=repair_prompt, stop=True))
        messages.append(GenerateMessage(role="assistant", content="", stop=False))

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
    config: DefaultPolicyConfig,
    config_name: str,
    generator: GeneratorAdapter,
    token_budget: int,
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

    prompt = f"\n{PROMPT_PREFIX}\n```c\n{c_source}\n```\n"

    renderer = CRustRenderer(sample=sample)
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
        oracles = [RustcOracle(), FunctionOracle(), RustcProgramOracle()]
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
            repair_feedback_format_config=RepairFeedbackFormatConfig(include_failed_snippet=False),
            max_steps=MAX_STEPS,
            max_new_length=MAX_NEW_LENGTH,
            prompt_prefix=prompt,
        )
        elapsed = time.time() - t0
        metrics = extract_metrics(trace)

    if config_name == "naive":
        compiles, test_passed, test_total = evaluate_final_rust_code(
            rust_code=final_prefix,
            c_source=c_source,
            test_cases=test_cases,
        )
    else:
        compiles, test_passed, test_total = evaluate_final_program(
            final_prefix=final_prefix,
            renderer=renderer,
            c_source=c_source,
            test_cases=test_cases,
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


# ── Output ─────────────────────────────────────────────────────────────────────

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


# ── Main ───────────────────────────────────────────────────────────────────────

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

    fence_parser = FenceParser(allowed_langs=("rust", "rs"))
    generator = GeneratorAdapter(
        model_name=model_name,
        stop_criteria_factory=lambda tok: [
            DTVStoppingCriteria(tok, RUST_PROFILE, fence_parser=fence_parser)
        ],
        fence_parser=fence_parser,
        do_sample=do_sample,
    )

    budget_desc = f"BudgetK={budget_k}" if budget_k is not None else f"TokenBudget={token_budget}"
    sampling_desc = "greedy" if args.greedy else "default"
    print(f"Model loaded: {model_name}")
    print(f"Cases: {len(case_ids)}, {budget_desc}, MaxSteps={MAX_STEPS}, Sampling={sampling_desc}")
    print(f"Output: {output_path}")

    results: list[RunResult] = []
    configs = [("dtv", DTV_CONFIG), ("naive", NAIVE_CONFIG)]

    for i, case_id in enumerate(case_ids, 1):
        for config_name, config in configs:
            print(f"\n[{i}/{len(case_ids)}] {case_id} / {config_name} ...", flush=True)
            try:
                result = run_single(
                    case_id, config, config_name, generator,
                    token_budget=token_budget, budget_k=budget_k,
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
