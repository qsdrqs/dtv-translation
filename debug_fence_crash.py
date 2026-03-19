#!/usr/bin/env python3
"""Reproduce fence-related crashes and dump model input at the crash point.

Usage:
    .venv/bin/python debug_fence_crash.py <case_id>

Crash cases from the 79-case experiment:
  FenceReopenError:     s972128356  s775589530  s661065982  s842128761
  fence state diverged: s329328806  s763753836
"""
from __future__ import annotations

import json
import sys
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any

from c_rust.feedback import RUST_FEEDBACK_LANG
from core.llm_output import AssistantContent, FenceReopenError, FenceState, OutputExtractorState
from core.types import GenerateContext, GenerateMessage, GenerationChannel
from run_ab_experiment import (
    DATASET_DIR,
    DTV_CONFIG,
    MAX_NEW_LENGTH,
    MODEL_NAME,
    OUTPUT_TOKEN_CAP,
    PROMPT_PREFIX,
    load_test_cases,
    run_single,
)


def _serialize_message(msg: GenerateMessage) -> dict[str, Any]:
    content = msg.content
    if isinstance(content, AssistantContent):
        rendered = content.render()
        return {
            "role": msg.role,
            "content_rendered": rendered,
            "fence_state": content.fence_state.value,
            "pre_fence_len": len(content.pre_fence),
            "code_len": len(content.code),
            "post_fence_len": len(content.post_fence),
            "fence_lang": content.fence_lang,
            "stop": msg.stop,
        }
    return {"role": msg.role, "content": str(content), "stop": msg.stop}


def _serialize_extractor_state(state: OutputExtractorState | None) -> dict[str, Any] | None:
    if state is None:
        return None
    return {
        "segment_state": state.segment.state.value,
        "segment_saw_fence": state.segment.saw_fence,
        "segment_buffer": repr(state.segment.buffer),
        "extract_state": state.extract.state.value,
        "shared_state": state.shared.state.value if state.shared else None,
    }


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    case_id = sys.argv[1]
    case_dir = DATASET_DIR / case_id
    if not case_dir.exists():
        print(f"Case directory not found: {case_dir}")
        sys.exit(1)

    import controller.loop as loop_mod

    original_handle_generate = loop_mod._handle_generate
    original_handle_feedback = loop_mod._handle_feedback

    crash_context: dict[str, Any] = {}

    def patched_handle_generate(runtime, base_messages, context, generator, *args, **kwargs):
        crash_context["trigger"] = "GENERATE"
        crash_context["step"] = runtime.state.step
        crash_context["prefix_len"] = len(runtime.state.prefix)
        crash_context["prefix_tail_500"] = runtime.state.prefix[-500:]
        crash_context["assistant_prefix_fence_state"] = runtime.assistant_prefix.fence_state.value
        crash_context["assistant_prefix_code_tail_300"] = runtime.assistant_prefix.code[-300:]
        crash_context["extractor_state"] = _serialize_extractor_state(runtime.extractor_state)

        context.extract_fence = True
        context.channel = GenerationChannel.CONTINUATION
        loop_mod.update_last_assistant(base_messages, runtime.assistant_prefix)
        crash_context["messages"] = [_serialize_message(m) for m in base_messages]

        try:
            return original_handle_generate(runtime, base_messages, context, generator, *args, **kwargs)
        except (FenceReopenError, RuntimeError) as exc:
            crash_context["error"] = str(exc)
            crash_context["error_type"] = type(exc).__name__
            crash_context["traceback"] = traceback.format_exc()
            raise

    def patched_handle_feedback(runtime, op, base_messages, context, generator, *args, **kwargs):
        crash_context["trigger"] = "FEEDBACK"
        crash_context["step"] = runtime.state.step
        crash_context["prefix_len"] = len(runtime.state.prefix)
        crash_context["prefix_tail_500"] = runtime.state.prefix[-500:]
        crash_context["assistant_prefix_fence_state"] = runtime.assistant_prefix.fence_state.value
        crash_context["assistant_prefix_code_tail_300"] = runtime.assistant_prefix.code[-300:]
        crash_context["extractor_state"] = _serialize_extractor_state(runtime.extractor_state)
        crash_context["repair_base_prefix_len"] = (
            len(runtime.repair_base_prefix) if runtime.repair_base_prefix else None
        )
        crash_context["failed_prefix_len"] = (
            len(runtime.failed_prefix) if runtime.failed_prefix else None
        )
        crash_context["messages"] = [_serialize_message(m) for m in base_messages]

        try:
            return original_handle_feedback(runtime, op, base_messages, context, generator, *args, **kwargs)
        except (FenceReopenError, RuntimeError) as exc:
            crash_context["error"] = str(exc)
            crash_context["error_type"] = type(exc).__name__
            crash_context["traceback"] = traceback.format_exc()
            raise

    loop_mod._handle_generate = patched_handle_generate
    loop_mod._handle_feedback = patched_handle_feedback

    print(f"Running case {case_id} with DTV config...")
    print(f"Model: {MODEL_NAME}")
    print(f"Dataset: {DATASET_DIR}")

    from c_rust.oracles import FunctionOracle, RustcOracle, RustcProgramOracle
    from controller.adapters import GeneratorAdapter
    from controller.stop_criteria import DTVStoppingCriteria, RUST_PROFILE
    from core.llm_output import FenceParser
    from core.budget import Budget
    from controller.loop import run_dtv_loop
    from controller.policy import DefaultPolicy
    from feedback.feedback import FeedbackState
    from feedback.formatter import RepairFeedbackFormatConfig
    from rollback.manager import RollbackManager
    from core.types import TranslationSample

    fence_parser = FenceParser(allowed_langs=("rust", "rs"))
    generator = GeneratorAdapter(
        model_name=MODEL_NAME,
        stop_criteria_factory=lambda tok: [
            DTVStoppingCriteria(tok, RUST_PROFILE, fence_parser=fence_parser)
        ],
        fence_parser=fence_parser,
    )
    print("Model loaded.")

    c_source = (case_dir / "source.c").read_text(encoding="utf-8").strip()
    test_cases = load_test_cases(case_dir)
    sample = TranslationSample(source_code=c_source, source_lang="c", test_cases=test_cases)
    prompt = f"\n{PROMPT_PREFIX}\n```c\n{c_source}\n```\n"

    from c_rust.render import CRustRenderer

    renderer = CRustRenderer(sample=sample)
    oracles = [RustcOracle(), FunctionOracle(), RustcProgramOracle()]
    budget = Budget(gen_tokens_budget=OUTPUT_TOKEN_CAP)
    feedback_state = FeedbackState()
    rollback_manager = RollbackManager()
    policy = DefaultPolicy(DTV_CONFIG)
    generator.reset_output_extractor()

    try:
        final_prefix, trace = run_dtv_loop(
            generator=generator,
            renderer=renderer,
            oracles=oracles,
            budget=budget,
            feedback_state=feedback_state,
            rollback_manager=rollback_manager,
            policy=policy,
            feedback_lang_config=RUST_FEEDBACK_LANG,
            repair_feedback_format_config=RepairFeedbackFormatConfig(include_failed_snippet=False),
            max_steps=None,
            max_new_length=MAX_NEW_LENGTH,
            prompt_prefix=prompt,
        )
        print(f"\nCompleted without crash. Final prefix length: {len(final_prefix)}")
    except (FenceReopenError, RuntimeError) as exc:
        print(f"\n{'='*80}")
        print(f"CRASH: {type(exc).__name__}: {exc}")
        print(f"{'='*80}")

        out_path = Path(f"debug_crash_{case_id}.json")
        out_path.write_text(json.dumps(crash_context, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nCrash context dumped to: {out_path}")

        print(f"\n--- Summary ---")
        print(f"Trigger:       {crash_context.get('trigger')}")
        print(f"Step:          {crash_context.get('step')}")
        print(f"Prefix len:    {crash_context.get('prefix_len')}")
        print(f"Fence state:   {crash_context.get('assistant_prefix_fence_state')}")
        print(f"Extractor:     {crash_context.get('extractor_state')}")
        print(f"Num messages:  {len(crash_context.get('messages', []))}")

        print(f"\n--- Messages (last 2) ---")
        for msg in crash_context.get("messages", [])[-2:]:
            role = msg["role"]
            if "content_rendered" in msg:
                content = msg["content_rendered"]
                print(f"\n[{role}] fence_state={msg['fence_state']} code_len={msg['code_len']}")
                if len(content) > 2000:
                    print(f"  (first 500 chars):\n{content[:500]}")
                    print(f"  ...<{len(content) - 1000} chars omitted>...")
                    print(f"  (last 500 chars):\n{content[-500:]}")
                else:
                    print(content)
            else:
                content = msg.get("content", "")
                print(f"\n[{role}]")
                if len(content) > 2000:
                    print(f"  (first 500 chars):\n{content[:500]}")
                    print(f"  ...<{len(content) - 1000} chars omitted>...")
                    print(f"  (last 500 chars):\n{content[-500:]}")
                else:
                    print(content)

        print(f"\n--- Prefix tail (last 500 chars) ---")
        print(crash_context.get("prefix_tail_500", ""))


if __name__ == "__main__":
    main()
