# AGENTS.md (dtv)

## Project: Decoding Time Verification (DTV) for Code Translation

1. no trailing spaces, no lines with only spaces
2. keep this file up to date (last updated: 2026-04-13)
3. Except for explicit reasons, do not use non-ASCII characters in the codebase or documentation.
4. Although redundant comments are generally discouraged, necessary comments should be written at complex logic to explain the logic.
5. Except for explicit reasons, always add imports at the beginning of the file. For explicit reasons, like slow imports, add a comment explaining why the import is not at the top.
6. In tests, the only allowed mock is LLM output. All other behaviors must be exercised with real tools (for example, real `rustc`, `gcc`, `tsc`, filesystem, and subprocess execution).
7. In tests, prefer multi-line strings and assert the whole string directly whenever practical.
8. Do not add future-proofing, speculative generalization, or branches for unrequested future scenarios. Implement only the current validated scope unless the user explicitly asks for broader behavior.

### Goal
Implement Decoding Time Verification (DTV): integrate deterministic program verifiers into the decoding loop
(no training; a fixed pretrained code model used as a black-box generator).

Primary translation tasks:
- C -> Rust (compilation + differential tests)
- JS -> TS (tsc + ESLint; no differential tests)

Key assumptions (current):
- Generator: local Transformers model via `transformers`.
- Verification:
  - C -> Rust: compilation (rustc) + differential testing (C vs Rust execution).
  - JS -> TS: compilation (tsc, strict: false) + linting (ESLint @typescript-eslint/typedef).
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
- `js_ts/`: JS->TS task implementation
  - `js_ts/feedback.py`: TS_FEEDBACK_LANG config (tree-sitter language, closing suffix detection).
  - `js_ts/render/`: stmt-level TS renderer (legal prefix validation, context rules, group stack).
    - `renderer.py`: JSToTSRenderer (try_render, prefix validation, context rule application).
    - `scan.py`: delimiter scanning (unclosed parens/brackets/braces, string/comment/template-literal aware).
    - `groups.py`: ts_group_stack (FUNC/BLOCK boundary detection at cursor).
    - `context_rules/`: semantic patches for legal prefix: try_catch_rule (add catch to uncaught try), function_return_rule (add return to non-void functions).
  - `js_ts/oracles/compiler_oracle/`: tsc compile oracle (weakened; see Design Decisions).
    - `tsc_oracle.py`: TscOracle (stmt-level) + TscProgramOracle (program-level).
    - `tsc_parser.py`: JSON diagnostic parsing + filter_type_correctness (TS2322/TS2339/TS2345 blocklist) + filter_partial_noise.
    - `tsc_driver.py`: subprocess wrapper for tsc_check.js, timeout handling, type roots discovery.
    - `tsc_check.js`: Node.js TypeScript compiler invocation (strict: false).
  - `js_ts/oracles/eslint_oracle/`: ESLint oracle for type annotation feedback.
    - `eslint_oracle.py`: EslintOracle (stmt-level, runs eslint, filters post-prefix diagnostics).
    - `eslint_parser.py`: message parsing + hint generation for @typescript-eslint/typedef.
    - `eslint_driver.py`: subprocess wrapper (direct or npx), config/project root discovery.
  - `js_ts/dataset/`: TypeWeaver dataset tooling.
    - `filter_typeweaver.py`: CLI to filter TypeWeaver packages (rollup bundling, LOC filter 30-1000, reject already-passing).
- `test/`: unit tests (use the venv Python)
  - `test/controller/`: `test_stop_criteria`, `test_loop_integration`, `test_loop_repair_flow`, `test_loop_default_policy`, `test_policy`, `test_policy_default`.
  - `test/core/`: `test_generator_backend`.
  - `test/rollback/`: `test_manager`, `test_group_sync`.
  - `test/c_rust/`: `test_rust_renderer`, `test_rust_group_stack`, `test_c_instrumenter`, `test_rust_instrumenter`, `test_ffi_bridge`, `test_trace_comparator`, `test_program_oracle`, `test_rustc_parser`.
  - `test/js_ts/`: `test_tsc_oracle`, `test_tsc_parser`, `test_ts_renderer`, `test_ts_group_stack`, `test_eslint_oracle`.

### Contracts / Invariants (do not silently break)
- Token budget uses `GenerateResult.delta_tokens` (not character length).
- `StopReason` is a best-effort label inferred from generation outcome; do not treat it as ground truth.
- Granularity ordering: STMT < BLOCK < FUNC < PROGRAM (enum comparisons).
- Rollback semantics (current, tested):
  - `rollback(STMT)` means retry: return the last committed stmt checkpoint without deleting it.
  - `rollback(BLOCK/FUNC)` means retry: truncate to the group start and drop the corresponding group frame(s).
  - `rollback(PROGRAM)` clears all checkpoints and group state.
- Group boundaries:
  - Renderers should emit `Artifact.group_stack`: enclosing `{FUNC,BLOCK,...}` kinds at the prefix end (outer -> inner).
  - The controller syncs `rollback_manager` via `sync_groups(artifact.group_stack)` before committing the stmt checkpoint.
  - `Artifact.group_events` remains as a legacy fallback (do not rely on boundary-to-boundary deltas for correctness).
- Prefix invariant:
  - Every committed checkpoint, rollback target, and applied repair patch must remain a legal prefix of some correct full program.
  - Standalone syntax validity is not sufficient. A patch that closes a function or block early is invalid if that closed form can no longer be continued into the intended correct program.

### Renderer
- Legal prefix: a prefix is legal only if some completion can make the full program valid. If a construct is closed and non-exhaustive (for example, a closed `match` block without a wildcard arm), that prefix is illegal for the renderer.
- This legal-prefix rule is a repo-wide invariant, not just a renderer detail. Feedback validation, checkpoint commits, and repair application must preserve the same property.

### Design Decisions
- Weakened Program Oracle (project-wide):
  The program-level oracle used during DTV generation is intentionally weaker
  than a full-correctness check. DTV is a superset of the naive baseline: both
  share the same post-hoc verification step, so in-generation oracles do not
  need to enforce full correctness - that is already handled post-hoc. The
  in-generation oracle only needs to provide actionable feedback that the model
  can use to improve the code during decoding.
  - C -> Rust: program diff test oracle runs with relaxed matching; full
    correctness verified post-hoc.
  - JS -> TS: two layers of weakening:
    1. `strict: false` in `tsc_check.js`.
    2. Type-correctness errors (TS2322/TS2339/TS2345) filtered from diagnostics
       before verdict (`filter_type_correctness` in `tsc_parser.py`).
  Full type correctness is evaluated post-hoc (strict=true recheck on pass
  outputs) rather than enforced during generation.
- ESLint as supplementary oracle (JS -> TS):
  - `@typescript-eslint/typedef` rule checks for missing type annotations.
  - ESLint hints (e.g. "Add an explicit type annotation") are included in
    feedback diagnostics.
  - Both DTV and naive receive ESLint hints equally (fairness constraint in
    `run_ab_experiment_js_ts.py`).
- Context rules for legal prefix (JS -> TS):
  - `try_catch_rule`: adds `catch(e) {}` to uncaught try statements so tsc can
    compile the prefix.
  - `function_return_rule`: adds `return undefined as any;` to non-void
    functions before closing brace.

### How to Run
- Unit tests: `./.venv/bin/python -m pytest -q`
- Smoke demo: `./.venv/bin/python main.py`

### Experiment Infrastructure
Top-level scripts for A/B experiments (DTV vs naive under equal token budget):

- `run_ab_experiment_js_ts.py`: JS->TS A/B runner. Saves pass outputs to `*_pass_outputs/{dtv,naive}/*.ts`.
- `run_ab_experiment.py`: C->Rust A/B runner.
- `run_single_js_ts_eval.py` / `run_single_js_ts_eval_naive.py`: single-case JS->TS eval (DTV / naive).
- `select_cases_js_ts.py` / `select_cases.py`: random case selection (LOC filter, seed).
- `merge_results_js_ts.py` / `merge_results.py`: merge parallel batch JSONs from workers.
- `plot_ab_results_js_ts.py` / `plot_ab_results.py`: result plotting (pass rate, token usage, scatter, etc.).
- `analyze_dtv_rollbacks.py`: rollback pattern + feedback effectiveness analysis.
- `ablation.py`: ablation study runner (policy config knobs).

Sample lists (generated by `select_cases_*.py --seed 42`):
- `100_samples_js_ts.txt`, `10_samples_js_ts_smoke.txt`: JS->TS.
- `100_samples.txt`, `151_samples.txt`: C->Rust.

Delta supercomputer deployment (`develop/`):
- `run_delta_js_ts.sh` / `run_delta.sh`: Slurm job launcher (Apptainer, `JOB_TIME_MIN` override).
- `sync_delta_js_ts.sh` / `sync_delta.sh`: rsync repo to DeltaAI.
- `sync_delta_back_js_ts.sh` / `sync_delta_back.sh`: rsync results back.
- `delta_js_ts.md` / `delta.md`: runbooks.

Dataset:
- `dataset_js_ts/`: 196 TypeWeaver JS->TS translation cases (each has `source.js`).

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
  - [x] Support feedback retries within a single DTV step (bounded by `max_repair_rounds`). Multi-round generation across DTV invocations is an application-layer concern, not a DTV responsibility.
- [ ] CDHR core component: `ScopeSelector` (diagnostics -> minimal plausible rollback scope) using oracle diagnostics + structure + rollback state.
- [ ] Budget + trace infrastructure for research plots:
  - [x] Track token cost vs oracle cost separately (wall-clock later).
  - [ ] Export JSONL traces for analysis (action sequence + costs + diagnostics summary).
- [x] Ablations/baselines as config knobs (same loop, different policy):
  - [x] outcome-only (verify only at end), naive-process (fixed verify cadence), no-rollback, no-CDHR, fixed-scope-only.

### Task-specific
- [x] `c_rust`:
  - [x] Emit `Artifact.group_stack` from the renderer (block/func boundaries).
  - [x] Wrap existing components into `FunctionOracle` (function-level diff testing).
- [x] `js_ts`:
  - [x] Implement renderer (JSToTSRenderer + context rules + group stack).
  - [x] Implement tsc oracle (weakened: strict:false, type-correctness filter).
  - [x] Implement ESLint oracle (@typescript-eslint/typedef hints).

### Experiments
- [x] Dataset adapters: CodeNet (C->Rust), TypeWeaver (JS->TS).
- [x] A/B experiment framework (`run_ab_experiment_js_ts.py`, merge, plot).
- [ ] Curves: success rate vs verifier cost (generated tokens first), plus ablations.
- [ ] Add wall-clock cost and caching:
  - [ ] Record oracle runtime in `TraceEvent`.
  - [ ] Cache compile/test results by artifact hash where safe.
