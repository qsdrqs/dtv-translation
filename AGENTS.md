# AGENTS.md (dtv)

## Project: Decoding Time Verification (DTV) for Code Translation

1. no trailing spaces, no lines with only spaces
2. keep this file up to date (last updated: 2026-01-23)
3. Except for explicit reasons, do not use non-ASCII characters in the codebase or documentation.
4. Although redundant comments are generally discouraged, necessary comments should be written at complex logic to explain the logic.
5. Except for explicit reasons, always add imports at the beginning of the file. For explicit reasons, like slow imports, add a comment explaining why the import is not at the top.

### Goal
Implement Decoding Time Verification (DTV): integrate deterministic program verifiers into the decoding loop
(no training; a fixed pretrained code model used as a black-box generator).

Primary translation tasks:
- C -> Rust (flagship; compilation + differential tests)
- JS -> TS (secondary; tsc + differential tests)

Key assumptions (current):
- Generator: local Transformers model via `transformers`.
- Verification: end-to-end differential testing for both tasks.
- Cost: start with generated token count; add wall-clock oracle/runtime cost later.

### Current Repository Layout
This repo intentionally uses a flat top-level layout (no `src/`):

- `core/`: shared data structures and model backend glue
  - `core/types/`: type definitions (split into modules):
    - `artifact.py`: `Artifact`, `GroupEvent`, `GroupStackFrame`, `RenderResult`.
    - `enums.py`: `Action`, `Granularity`, `RenderStatus`, `Verdict`, `RollbackScope`, `GroupEventAction`.
    - `generation.py`: `GenerateContext`, `GenerateMessage`, `GenerateResult`, `StopReason`.
    - `oracle.py`: `Diagnostic`, `OracleOutput`, `OracleContext`.
    - `controller.py`: `ControllerState`, `TraceEvent`.
    - `diff_testing.py`: `TranslationSample`, `TestCase`, `ExecutionResult`, `ExecutionTraceEvent`, etc.
  - `core/generator_backend.py`: Transformers generation; returns `GenerateResult(delta_tokens, stop_reason, ...)`.
  - `core/qwen_generator_backend.py`: Qwen-specific generator backend.
  - `core/budget.py`: token-budget accounting (gen tokens + per-oracle cost tracking).
  - `core/interfaces.py`: Protocols for `Generator`, `Renderer`, `Oracle`, `OracleRunner`.
  - `core/logger.py`: logging helpers.
- `controller/`: decoding-time controller logic
  - `controller/loop.py`: DTV state machine (`run_dtv_loop`); actions: GENERATE, VERIFY, COMMIT, ROLLBACK, FEEDBACK, APPLY_PATCH, CONTINUE, TERMINATE.
  - `controller/policy.py`: `DefaultPolicy` with ablation config knobs (`DefaultPolicyConfig`).
  - `controller/stop_criteria.py`: boundary-based `StoppingCriteria` (string/comment aware; TODO: brace/paren depth).
  - `controller/adapters.py`: adapter from `GeneratorBackend` to `Generator` protocol.
- `feedback/`: deterministic feedback state + prompt augmentation strategies
  - `feedback/feedback.py`: `FeedbackState` (bounded, deduped diagnostics summary).
  - `feedback/strategies.py`: how feedback is inserted into chat/prompt (e.g., append to last assistant).
- `rollback/`: rollback/checkpoint management
  - `rollback/manager.py`: stmt checkpoints + block/func group stack (synced at COMMIT using `Artifact.group_stack`).
- `c_rust/`: C->Rust task implementation
  - `c_rust/render/`: stmt-level Rust renderer (syntax+semantic patching; emits `Artifact.group_stack` + AST for rollback grouping).
  - `c_rust/oracles/compiler_oracle/`: `rustc` compile oracle (JSON diagnostics).
  - `c_rust/oracles/program_diff_test_oracle/`: program-level differential testing oracle (C vs Rust).
  - `c_rust/oracles/function_diff_test_oracle/`: function-level diff testing (`FunctionOracle` + instrumentation + FFI bridge + trace compare).
  - `c_rust/oracles/block_diff_test_oracle/`: placeholder (TODO).
- `js_ts/`: JS->TS task implementation (currently placeholders; TODO: renderer + `tsc` oracle + diff testing).
- `test/`: unit tests (use the venv Python)
  - `test/controller/`: `test_stop_criteria`, `test_loop_integration`, `test_loop_repair_flow`, `test_loop_default_policy`, `test_policy`, `test_policy_default`.
  - `test/core/`: `test_generator_backend`.
  - `test/rollback/`: `test_manager`, `test_group_sync`.
  - `test/c_rust/`: `test_rust_renderer`, `test_rust_group_stack`, `test_c_instrumenter`, `test_rust_instrumenter`, `test_ffi_bridge`, `test_trace_comparator`, `test_program_oracle`, `test_rustc_parser`.

### Contracts / Invariants (do not silently break)
- Token budget uses `GenerateResult.delta_tokens` (not character length).
- `StopReason` is a best-effort label inferred from generation outcome; do not treat it as ground truth.
- Rollback semantics (current, tested):
  - `rollback(STMT)` means retry: return the last committed stmt checkpoint without deleting it.
  - `rollback(BLOCK/FUNC)` means retry: truncate to the group start and drop the corresponding group frame(s).
  - `rollback(PROGRAM)` clears all checkpoints and group state.
- Group boundaries:
  - Renderers should emit `Artifact.group_stack`: enclosing `{FUNC,BLOCK,...}` kinds at the prefix end (outer -> inner).
  - The controller syncs `rollback_manager` via `sync_groups(artifact.group_stack)` before committing the stmt checkpoint.
  - `Artifact.group_events` remains as a legacy fallback (do not rely on boundary-to-boundary deltas for correctness).

### How to Run
- Unit tests: `./.venv/bin/python -m pytest -q`
- Smoke demo: `./.venv/bin/python main.py`

## Roadmap (TODO)
### Core (paper-critical)
- [x] Refactor controller into explicit actions/state machine: `GENERATE`, `VERIFY(scope)`, `ROLLBACK(scope)`, `COMMIT`, `TERMINATE`.
- [x] Structural boundary protocol for variable-sized verification:
  - [x] Standardize `Artifact` fields for boundaries/anchors (stmt boundary + block/func grouping at minimum).
  - [x] Make rollback semantics depend on these boundaries (not just stmt retries).
- [ ] Process rewards without training:
  - [ ] Define a deterministic `ProcessSignal`/reward summary from `OracleOutput` (pass/fail/diag deltas) + scope + cost.
  - [ ] Define aggregation rules across multiple oracles and multiple scopes.
- [ ] Feedback as interaction protocol (not just a string append):
  - [ ] Add a `FeedbackPlan` abstraction (what to ask the model to do next) + an output parser (how to consume structured model outputs).
  - [x] Support multi-round repair attempts per step under a fixed token budget (inference-time scaling via extra repair turns).
- [ ] CDHR core component: `ScopeSelector` (diagnostics -> minimal plausible rollback scope) using oracle diagnostics + structure + rollback state.
- [ ] Budget + trace infrastructure for research plots:
  - [x] Track token cost vs oracle cost separately (wall-clock later).
  - [ ] Export JSONL traces for analysis (action sequence + costs + diagnostics summary).
- [x] Ablations/baselines as config knobs (same loop, different policy):
  - [x] outcome-only (verify only at end), naive-process (fixed verify cadence), no-rollback, no-CDHR, fixed-scope-only.

### Task-specific
- [ ] `c_rust`:
  - [x] Emit `Artifact.group_stack` from the renderer (block/func boundaries).
  - [x] Wrap existing components into `FunctionOracle` (function-level diff testing).
  - [ ] Implement `BlockOracle` (block-level diff testing).
- [ ] `js_ts`:
  - [ ] Implement a minimal renderer + `tsc` oracle + diff testing baseline.

### Experiments
- [ ] Dataset adapters: CodeNet (C->Rust), TypeWeaver (JS->TS).
- [ ] Curves: success rate vs verifier cost (generated tokens first), plus ablations.
- [ ] Add wall-clock cost and caching:
  - [ ] Record oracle runtime in `TraceEvent`.
  - [ ] Cache compile/test results by artifact hash where safe.

