# AGENTS.md (dtv)

## Project: Decoding Time Verification (DTV) for Code Translation

1. no trailing spaces, no lines with only spaces
2. keep this file up to date (last updated: 2026-01-05)

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
  - `core/types.py`: `Artifact`, `Granularity`, `StopReason`, `GenerateContext/Result`, `GroupEvent`, `TraceEvent`, etc.
  - `core/generator_backend.py`: Transformers generation; returns `GenerateResult(delta_tokens, stop_reason, ...)`.
  - `core/budget.py`: token-budget accounting (oracle costs counted but not wall-clock yet).
  - `core/interfaces.py`: Protocols for `Generator`, `Renderer`, `Oracle`, `OracleRunner`.
  - `core/logger.py`: logging helpers.
- `controller/`: decoding-time controller logic
  - `controller/stop_criteria.py`: boundary-based `StoppingCriteria` (string/comment aware; TODO: brace/paren depth).
  - `controller/loop.py`: DTV loop (currently step-wise generate->render->oracle->act; TODO: explicit action/state machine).
  - `controller/adapters.py`: adapter from `GeneratorBackend` to `Generator` protocol.
- `feedback/`: deterministic feedback state + prompt augmentation strategies
  - `feedback/feedback.py`: `FeedbackState` (bounded, deduped diagnostics summary).
  - `feedback/strategies.py`: how feedback is inserted into chat/prompt (e.g., append to last assistant).
- `rollback/`: rollback/checkpoint management (pre-CDHR)
  - `rollback/manager.py`: stmt checkpoints + block/func group stack (driven by `Artifact.group_events`).
- `c_rust/`: C->Rust task implementation
  - `c_rust/render/`: stmt-level Rust renderer (syntax+semantic patching; TODO: emit `group_events` for block/func).
  - `c_rust/oracles/compiler_oracle/`: `rustc` compile oracle (JSON diagnostics).
  - `c_rust/oracles/program_diff_test_oracle/`: program-level differential testing oracle (C vs Rust).
  - `c_rust/oracles/function_diff_test_oracle/`: components for function-level diff testing (instrumentation + FFI bridge + trace compare; TODO: `FunctionOracle` wrapper).
  - `c_rust/oracles/block_diff_test_oracle/`: placeholder (TODO).
- `js_ts/`: JS->TS task implementation (currently placeholders; TODO: renderer + `tsc` oracle + diff testing).
- `test/`: unit tests (use the venv Python)
  - `test/controller/test_stop_criteria.py`
  - `test/core/test_generator_backend.py`
  - `test/rollback/test_manager.py`

### Contracts / Invariants (do not silently break)
- Token budget uses `GenerateResult.delta_tokens` (not character length).
- `StopReason` is a best-effort label inferred from generation outcome; do not treat it as ground truth.
- Rollback semantics (current, tested):
  - `rollback(STMT)` means retry: return the last committed stmt checkpoint without deleting it.
  - `rollback(BLOCK/FUNC)` means retry: truncate to the group start and drop the corresponding group frame(s).
  - `rollback(PROGRAM)` clears all checkpoints and group state.
- Group events:
  - Renderers should emit `Artifact.group_events` as a sequence of `{OPEN,CLOSE} x {BLOCK,FUNC}` events.
  - The controller applies `group_events` before committing the stmt checkpoint to avoid off-by-one group starts.

### How to Run
- Unit tests: `./.venv/bin/python -m pytest -q`
- Smoke demo: `./.venv/bin/python main.py`

## Roadmap (TODO)
### Core (paper-critical)
- [ ] Refactor controller into explicit actions/state machine: `GENERATE`, `VERIFY(scope)`, `ROLLBACK(scope)`, `COMMIT`, `TERMINATE`.
- [ ] Structural boundary protocol for variable-sized verification:
  - [ ] Standardize `Artifact` fields for boundaries/anchors (stmt boundary + block/func OPEN/CLOSE events at minimum).
  - [ ] Make rollback semantics depend on these boundaries (not just stmt retries).
- [ ] Process rewards without training:
  - [ ] Define a deterministic `ProcessSignal`/reward summary from `OracleOutput` (pass/fail/diag deltas) + scope + cost.
  - [ ] Define aggregation rules across multiple oracles and multiple scopes.
- [ ] Feedback as interaction protocol (not just a string append):
  - [ ] Add a `FeedbackPlan` abstraction (what to ask the model to do next) + an output parser (how to consume structured model outputs).
  - [ ] Support multi-round repair attempts per step under a fixed token budget (inference-time scaling via extra repair turns).
- [ ] CDHR core component: `ScopeSelector` (diagnostics -> minimal plausible rollback scope) using oracle diagnostics + structure + rollback state.
- [ ] Budget + trace infrastructure for research plots:
  - [ ] Track token cost vs oracle cost separately (wall-clock later).
  - [ ] Export JSONL traces for analysis (action sequence + costs + diagnostics summary).
- [ ] Ablations/baselines as config knobs (same loop, different policy):
  - [ ] outcome-only (verify only at end), naive-process (fixed verify cadence), no-rollback, no-CDHR, fixed-scope-only.

### Task-specific
- [ ] `c_rust`:
  - [ ] Emit `Artifact.group_events` from the renderer (block/func boundaries).
  - [ ] Wrap existing components into `FunctionOracle` and `BlockOracle` (function/block-level diff testing).
- [ ] `js_ts`:
  - [ ] Implement a minimal renderer + `tsc` oracle + diff testing baseline.

### Experiments
- [ ] Dataset adapters: CodeNet (C->Rust), TypeWeaver (JS->TS).
- [ ] Curves: success rate vs verifier cost (generated tokens first), plus ablations.
- [ ] Add wall-clock cost and caching:
  - [ ] Record oracle runtime in `TraceEvent`.
  - [ ] Cache compile/test results by artifact hash where safe.
