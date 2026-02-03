from __future__ import annotations

import json
import sys
from pathlib import Path

from c_rust.oracles import FunctionOracle, ProgramOracle, RustcOracle
from c_rust.render import CRustRenderer
from controller.adapters import GeneratorAdapter
from controller.loop import run_dtv_loop
from controller.policy import DefaultPolicy, DefaultPolicyConfig
from controller.stop_criteria import DTVStoppingCriteria, RUST_PROFILE
from core.llm_output import FenceParser
from core.budget import Budget
from core.types import OracleOutput, TestCase, TranslationSample
from feedback.feedback import FeedbackState
from rollback.manager import RollbackManager


MODEL_NAME = "Qwen/Qwen3-4B-Instruct-2507"
TOKEN_BUDGET = 20480
MAX_NEW_LENGTH = 1024
PROMPT_PREFIX = "Translated the following C code into Rust:"


class DisabledFeedbackState(FeedbackState):
    def update(self, outputs: list[OracleOutput]) -> None:
        return None

    def encode(self) -> str:
        return ""


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


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: python run_single_c_rust_eval.py <c_source> <tests.json> <out.rs>")
        raise SystemExit(2)

    c_source_path = Path(sys.argv[1])
    tests_path = Path(sys.argv[2])
    out_path = Path(sys.argv[3])

    c_program = c_source_path.read_text(encoding="utf-8").strip()
    test_cases = _load_tests(tests_path)
    rust_code = '''
use std::io::{self, Read};

fn trap(height: &[i32]) -> i32 {
    let n = height.len();
    if n < 3 {
        return 0;
    }

    let mut left: usize = 0;
    let mut right: usize = n - 1;
    let mut left_max: i32 = 0;
    let mut right_max: i32 = 0;
    let mut water: i32 = 0;

    while left < right {
        if height[left] < height[right] {
            if height[left] >= left_max {
                left_max = height[left];
            } else {
                water += left_max - height[left];
            }
            left += 1;
        } else {
            if height[right] >= right_max {
                right_max = height[right];
            } else {
                water += right_max - height[right];
            }
            if right == 0 {
                break;
            }
            right -= 1;
        }
    }

    water
}

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();

    let mut it = input.split_whitespace();

    let n_opt = it.next();
    if n_opt.is_none() {
        std::process::exit(1);
    }
    let n_i64: i64 = match n_opt.unwrap().parse() {
        Ok(v) => v,
        Err(_) => std::process::exit(1),
    };
    if n_i64 < 0 {
        std::process::exit(1);
    }
    let n: usize = n_i64 as usize;

    let mut arr: Vec<i32> = Vec::with_capacity(n);
    for _ in 0..n {
        let tok = it.next().unwrap_or_else(|| std::process::exit(1));
        let v: i32 = tok.parse().unwrap_or_else(|_| std::process::exit(1));
        arr.push(v);
    }

    let result = trap(&arr);
    println!("{result}");
}
'''
    prompt = f'''
{PROMPT_PREFIX}
```c
{c_program}
```
'''

    sample = TranslationSample(
        source_code=c_program,
        source_lang="c",
        test_cases=test_cases,
    )

    fence_parser = FenceParser(allowed_langs=("rust", "rs"))
    generator = GeneratorAdapter(
        model_name=MODEL_NAME,
        stop_criteria_factory=lambda tok: [
            DTVStoppingCriteria(tok, RUST_PROFILE, fence_parser=fence_parser)
        ],
        fence_parser=fence_parser,
    )
    print("Model loaded:", MODEL_NAME)
    renderer = CRustRenderer(sample=sample)
    oracles = [RustcOracle(), FunctionOracle(), ProgramOracle()]
    budget = Budget(gen_tokens_budget=TOKEN_BUDGET)
    feedback_state = DisabledFeedbackState()
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
        max_steps=500,
        max_new_length=MAX_NEW_LENGTH,
        prompt_prefix=prompt,
    )

    out_path.write_text(final_prefix, encoding="utf-8")
    print(f"Generated Rust saved to {out_path}")

    for event in trace:
        if not event.oracle_outputs:
            continue
        print(f"step={event.step} action={event.action}")
        for output in event.oracle_outputs:
            print(f"  {output.oracle_name}: {output.verdict}")
            for diag in output.diagnostics:
                print(f"    - {diag.message}")


if __name__ == "__main__":
    main()
