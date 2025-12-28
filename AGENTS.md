# AGENTS.md (dtv)

## Project: Decoding Time Verification (DTV) for Code Translation

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
  - `controller/loop.py`: DTV loop skeleton (meta-steps, render, oracle calls, feedback, rollback).
  - `controller/adapters.py`: adapter from `GeneratorBackend` to `Generator` protocol.
- `feedback/`: deterministic feedback state + prompt augmentation strategies
  - `feedback/feedback.py`: `FeedbackState` (bounded, deduped diagnostics summary).
  - `feedback/strategies.py`: how feedback is inserted into chat/prompt (e.g., append to last assistant).
- `rollback/`: rollback/checkpoint management (pre-CDHR)
  - `rollback/manager.py`: stmt checkpoints + block/func group stack (driven by `Artifact.group_events`).
- `c_rust/`, `js_ts/`: task-specific renderers/oracles (mostly TODO; will emit `group_events`).
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
- [ ] Define an ordering/applicability check for `Granularity` (oracle applicable if artifact granularity >= required).
- [ ] Implement task renderers that are total enough for meta-steps:
  - [ ] `c_rust`: stmt/block/func harness rendering + `Artifact.group_events` extraction.
  - [ ] `js_ts`: stmt/block/func harness rendering + `Artifact.group_events` extraction (handle TS template literals, ASI risks).
- [ ] Implement verifiers (deterministic oracles):
  - [ ] `c_rust`: `rustc` compile oracle (parse JSON diagnostics), then differential test oracle.
  - [ ] `js_ts`: `tsc` oracle (diagnostics), then differential test oracle.
- [ ] Add rollback scope selection to the controller loop:
  - [ ] Replace `Action.ROLLBACK` with `(rollback_scope, reason)` (pre-CDHR heuristic).
  - [ ] Add CDHR mapping: diagnostics -> minimal plausible rollback scope.
- [ ] Add experiment runner:
  - [ ] Dataset adapters: CodeNet (C->Rust), TypeWeaver (JS->TS).
  - [ ] Curves: success rate vs verifier cost (token-budget first), plus ablations (no rollback, no CDHR, fixed scope).
  - [ ] Persist per-sample traces for failure analysis and paper qualitative examples.
- [ ] Add wall-clock cost and caching:
  - [ ] Record oracle runtime in `TraceEvent`.
  - [ ] Cache compile/test results by artifact hash where safe.
