# C2Rust Adaptiveness Evaluation

## TL;DR

> **Quick Summary**: Build dataset-scale C2Rust evaluation infrastructure and run broad adaptiveness evaluation on the existing dataset with machine-verifiable outputs.
>
> **Deliverables**:
> - Dataset adapter that converts per-case files into `TranslationSample` objects
> - Batch eval runner that iterates cases and runs DTV with C2Rust oracles
> - Machine-readable JSONL outputs with adaptiveness metrics
>
> **Estimated Effort**: Medium-Large
---

## Context

### Original Request
- Adaptiveness not broadly validated on dataset at `./selected_data_output` (placed in repo root).
- Need machine-verifiable outputs for research plots and analysis.

### Research Findings
- Existing eval script `run_single_c_rust_eval.py` is single-sample.
- Dataset contains 200 per-case directories; 166 have `status: success` in `metadata.json`, 34 are `failed` and lack a `testcases/` directory.
- Each case directory structure: `source.c`, `testcases/input_000`, `input_001`, ..., `metadata.json`.
- `testcases/input_*` are raw binary/text files (not JSON); loader reads them directly as stdin bytes decoded with latin-1.

### Key Decisions
- **BlockOracle**: skipped; use existing oracles only (RustcOracle + FunctionOracle + ProgramOracle).
- **FeedbackPlan**: existing `FeedbackState` implementation is sufficient; use as-is.
- **Oracles**: same combination as `run_single_c_rust_eval.py`.
- **Dataset path**: `./selected_data_output` (repo root).
- **Output directory**: `./eval_output/`.
- **Failed cases** (metadata `status != success`): skip silently, count in summary only.
- **Testcase format**: loader reads `testcases/input_*` files directly; `stdin = file_bytes.decode("latin-1")`.
- **Exception handling**: let exceptions propagate and crash immediately (debug phase).
- **Concurrency**: sequential, no per-case timeout.
- **Testing strategy**: run dataset first to collect failure patterns, then write targeted tests, then fix. No upfront TDD.
- **`--limit N`**: CLI flag retained for running a subset (e.g. 10 cases) before full run.
- **cases.jsonl minimum fields per case**: `case_id`, `verdict`, `gen_tokens`, `actions` (dict of action -> count).

---

## Work Objectives

### Core Objective
Deliver dataset-scale adaptiveness measurement infrastructure that runs C2Rust translation with full DTV loop (RustcOracle + FunctionOracle + ProgramOracle + existing feedback) across many cases and produces machine-readable cost/behavior metrics.

### Concrete Deliverables
- `c_rust/eval/dataset_loader.py` - adapter for dataset filesystem layout
- `c_rust/eval/run_dataset_eval.py` - batch runner with JSONL output and `--limit` support
- Output layout under `./eval_output/`:
  - `cases.jsonl` - one JSON line per case: `case_id`, `verdict`, `gen_tokens`, `actions`
  - `summary.json` - aggregate metrics: `cases_total`, `cases_ran`, `cases_skipped`, `pass_rate`, `avg_gen_tokens`

### Definition of Done
- [ ] Dataset loader reads per-case directories and builds `TranslationSample` + `TestCase` objects.
- [ ] Batch runner executes multi-case evaluation and writes machine-readable JSONL outputs.
- [ ] Smoke run (10 cases via `--limit 10`) completes and writes outputs.
- [ ] Output files contain required minimum fields.

### Must Have
- Loader skips non-success cases (counts in summary, does not crash).
- Runner crashes immediately on unexpected exceptions (no silent swallowing).
- `--limit N` CLI flag for smoke runs.

### Must NOT Have (Guardrails)
- Do not mutate source dataset files.
- Do not bypass budget checks.
- Do not change model training/fine-tuning setup.
- Do not add BlockOracle (out of scope).

---

## Workflow

Debug-first iteration cycle (not upfront TDD):

1. **Implement** loader + runner (minimal, functional).
2. **Run** on first ~10 cases via `--limit 10`.
3. **Observe** failures and collect error patterns.
4. **Write targeted tests** for each failure pattern.
5. **Fix** the bugs.
6. **Repeat** until 10-case run is clean, then expand.

---

## TODOs

- [ ] 1. Build dataset loader

  **What to do**:
  - Add `c_rust/eval/dataset_loader.py` for `./selected_data_output` layout:
    - Skip case if `metadata.json` has `status != "success"` (return `None`, log skip reason).
    - Load `source.c` as UTF-8.
    - Load each `testcases/input_*` file as `TestCase(stdin=content.decode("latin-1"), test_id=filename)`.
  - Return `TranslationSample` and list of `TestCase` objects for valid cases.

  **Must NOT do**:
  - Do not mutate source dataset files.
  - Do not raise on non-success metadata; return `None` with a logged reason.

  **References**:
  - `core/types/diff_testing.py` - `TranslationSample` and `TestCase` shape.
  - `run_single_c_rust_eval.py` - baseline sample construction patterns.

  **Commit**: YES
  - Message: `feat(c_rust): add dataset loader for adaptiveness evaluation`
  - Files: `c_rust/eval/dataset_loader.py`

- [ ] 2. Build batch eval runner with JSONL output

  **What to do**:
  - Add `c_rust/eval/run_dataset_eval.py` as a runnable module (`python -m c_rust.eval.run_dataset_eval`).
  - CLI args: `--dataset PATH` (default `./selected_data_output`), `--out DIR` (default `./eval_output`), `--limit N` (optional).
  - For each loaded case: run `run_dtv_loop` with `RustcOracle + FunctionOracle + ProgramOracle` and existing `FeedbackState`.
  - Write `{out}/cases.jsonl` (one line per ran case) and `{out}/summary.json`.
  - Per-case fields: `case_id`, `verdict`, `gen_tokens`, `actions` (dict action->count from trace).
  - Summary fields: `cases_total`, `cases_ran`, `cases_skipped`, `pass_rate`, `avg_gen_tokens`.
  - Do NOT catch unexpected exceptions; let them propagate and crash.

  **Must NOT do**:
  - Do not bypass budget checks.
  - Do not change model/training setup.
  - Do not add BlockOracle.

  **References**:
  - `run_single_c_rust_eval.py` - model/oracle assembly and `run_dtv_loop` call pattern.
  - `core/types/controller.py` - `TraceEvent` fields for action counting.
  - `core/budget.py` - token accounting.

  **Commit**: YES
  - Message: `feat(c_rust): add batch eval runner with JSONL output`
  - Files: `c_rust/eval/run_dataset_eval.py`

- [ ] 3. Smoke run and iterative debug

  **What to do**:
  - Run: `uv run python -m c_rust.eval.run_dataset_eval --limit 10 --out ./eval_output`
  - Observe failures; collect error patterns.
  - Write targeted tests for each failure pattern found.
  - Fix bugs; repeat until 10-case run is clean.
  - Expand to full dataset when stable.

  **Acceptance Criteria**:
  - [ ] Smoke run completes without crash for 10 cases.
  - [ ] `./eval_output/cases.jsonl` exists with entries containing `case_id`, `verdict`, `gen_tokens`, `actions`.
  - [ ] `./eval_output/summary.json` exists with `cases_total`, `cases_ran`, `cases_skipped`, `pass_rate`, `avg_gen_tokens`.

---

## Success Criteria

### Verification Commands

```bash
uv run python -m c_rust.eval.run_dataset_eval --limit 10 --out ./eval_output
uv run python -m c_rust.eval.run_dataset_eval --out ./eval_output
```

### Final Checklist
- [ ] Loader correctly skips failed cases and counts them in summary.
- [ ] Runner writes valid JSONL with minimum required fields.
- [ ] Smoke run (10 cases) completes cleanly.
- [ ] Full run completes without unexpected crashes.

---

## Dependencies

- **BlockOracle**: OUT OF SCOPE for this evaluation. Skipped.
- **FeedbackPlan + Output Parser**: existing `FeedbackState` is sufficient. No new abstraction needed.
