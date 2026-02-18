# Test Hardening TODO

Last updated: 2026-02-17

## Scope and constraints

- Goal: strengthen tests conservatively (more real-path coverage, less fake confidence).
- Current known bug (`FenceReopenError` on feedback A -> B) is intentionally parked for now.
- Keep each change small: one test gap at a time, with targeted verification.

## Priority 0: baseline and tracking

- [x] Keep a running map of "coverage claim vs actual covered path" for each changed test.
- [x] For every new/updated test, record the exact production path it exercises.

### Coverage map (changed tests)

- `test/controller/test_stop_criteria.py::test_stop_criteria_resets_stream_on_parser_epoch_change`
  - Claim: parser epoch changes reset stop-criteria stream counters.
  - Path: `controller/stop_criteria.py:152` -> `controller/stop_criteria.py:154`.
- `test/controller/test_loop_default_policy.py::test_default_policy_force_b_feedback_flows_through_loop`
  - Claim: loop consumes `DefaultPolicy` mechanism selection with mechanism B.
  - Path: `controller/policy.py:205` + `controller/loop.py:664`.
- `test/controller/test_loop_default_policy.py::test_default_policy_inline_feedback_restores_extractor_before_generation`
  - Claim: inline FEEDBACK restores extractor state before generation and restores base state after generation.
  - Path: `controller/loop.py:613` -> `controller/loop.py:634` -> `controller/loop.py:636`.
- `test/controller/test_generator_adapter_flow.py::test_adapter_restore_round_trip_replays_extraction_with_shared_parser`
  - Claim: adapter restore round-trip replays extraction when shared parser state is restored to base snapshot.
  - Path: `controller/adapters.py:67` -> `controller/adapters.py:80`.
- `test/controller/test_generator_adapter_flow.py::test_adapter_restore_triggers_stop_criteria_epoch_sync_with_shared_parser`
  - Claim: restore increments parser epoch and stop criteria resets stream state on next call.
  - Path: `controller/adapters.py:79` + `controller/stop_criteria.py:152` -> `controller/stop_criteria.py:154`.
- `test/e2e/c2rust/feedback/test_feedback_mechanism_a.py::test_feedback_e2e_program_failure_then_mechanism_b_repair_success`
  - Claim: non-A-only e2e feedback path works with mechanism B and trace note wiring.
  - Path: `controller/policy.py:205` + `controller/loop.py:664` + `controller/loop.py:638`.

## Priority 1: high-risk controller gaps

- [x] Add stop-criteria test for parser epoch reset behavior after parser state restore.
  - Target path: `controller/stop_criteria.py:152` -> `controller/stop_criteria.py:154`.
  - Added test: `test/controller/test_stop_criteria.py::test_stop_criteria_resets_stream_on_parser_epoch_change`.
- [x] Add loop-level test that validates `DefaultPolicy` mechanism decision is consumed by loop actions (without hardcoded policy shim).
  - Target path: `controller/policy.py:205` + `controller/loop.py` FEEDBACK action wiring.
  - Added test: `test/controller/test_loop_default_policy.py::test_default_policy_force_b_feedback_flows_through_loop`.
- [x] Add test that verifies repair-base extractor state is restored before FEEDBACK generation in inline mode.
  - Target path: `controller/loop.py:613` then `controller/loop.py:634`.
  - Added test: `test/controller/test_loop_default_policy.py::test_default_policy_inline_feedback_restores_extractor_before_generation`.

## Priority 2: adapter and parser integration

- [x] Add adapter test that validates restore round-trip (`capture` -> `restore` -> continued extraction) with shared fence parser state.
  - Target path: `controller/adapters.py:67` -> `controller/adapters.py:80`.
- [x] Add integration-style test where stop criteria and adapter share one parser and restoration happens between calls.
  - Target path: `controller/adapters.py` + `controller/stop_criteria.py` epoch sync.
  - Added tests:
    - `test/controller/test_generator_adapter_flow.py::test_adapter_restore_round_trip_replays_extraction_with_shared_parser`
    - `test/controller/test_generator_adapter_flow.py::test_adapter_restore_triggers_stop_criteria_epoch_sync_with_shared_parser`

## Priority 3: e2e feedback coverage

- [x] Add at least one e2e feedback scenario that is not mechanism-A-only.
  - Existing reference: `test/e2e/c2rust/feedback/test_feedback_mechanism_a.py`.
- [x] Add explicit assertions around mechanism labels in trace notes for e2e feedback path.
  - Added tests/assertions:
    - `test/e2e/c2rust/feedback/test_feedback_mechanism_a.py::test_feedback_e2e_compile_failure_then_repair_success`
    - `test/e2e/c2rust/feedback/test_feedback_mechanism_a.py::test_feedback_e2e_behavior_mismatch_then_program_repair_success`
    - `test/e2e/c2rust/feedback/test_feedback_mechanism_a.py::test_feedback_e2e_program_failure_then_mechanism_b_repair_success`

## Process checklist per item

- [ ] Add/modify test with deterministic fixture setup.
- [ ] Run targeted pytest for changed test(s).
- [ ] Run lsp diagnostics on changed files.
- [ ] Update this todo file status and move to next item.

## Iteration notes

- Iteration 1 completed:
  - Test change: `test/controller/test_stop_criteria.py`.
  - Verified with: `./.venv/bin/python -m pytest -q test/controller/test_stop_criteria.py::test_stop_criteria_resets_stream_on_parser_epoch_change`.
  - Module check: `./.venv/bin/python -m pytest -q test/controller/test_stop_criteria.py`.
- Iteration 2 completed:
  - Test change: `test/controller/test_loop_default_policy.py`.
  - Verified with: `./.venv/bin/python -m pytest -q test/controller/test_loop_default_policy.py::test_default_policy_force_b_feedback_flows_through_loop`.
  - Module check: `./.venv/bin/python -m pytest -q test/controller/test_loop_default_policy.py`.
- Iteration 3 completed:
  - Test change: `test/controller/test_loop_default_policy.py`.
  - Verified with: `./.venv/bin/python -m pytest -q test/controller/test_loop_default_policy.py::test_default_policy_inline_feedback_restores_extractor_before_generation`.
  - Module check: `./.venv/bin/python -m pytest -q test/controller/test_loop_default_policy.py`.
- Iteration 4 completed:
  - Test change: `test/controller/test_generator_adapter_flow.py`.
  - Verified with: `./.venv/bin/python -m pytest -q test/controller/test_generator_adapter_flow.py::test_adapter_restore_round_trip_replays_extraction_with_shared_parser test/controller/test_generator_adapter_flow.py::test_adapter_restore_triggers_stop_criteria_epoch_sync_with_shared_parser`.
  - Module check: `./.venv/bin/python -m pytest -q test/controller/test_generator_adapter_flow.py`.
- Iteration 5 completed:
  - Test change: `test/e2e/c2rust/feedback/test_feedback_mechanism_a.py`.
  - Verified with: `./.venv/bin/python -m pytest -q test/e2e/c2rust/feedback/test_feedback_mechanism_a.py::test_feedback_e2e_compile_failure_then_repair_success test/e2e/c2rust/feedback/test_feedback_mechanism_a.py::test_feedback_e2e_program_failure_then_mechanism_b_repair_success`.
  - Module check: `./.venv/bin/python -m pytest -q test/e2e/c2rust/feedback/test_feedback_mechanism_a.py`.
