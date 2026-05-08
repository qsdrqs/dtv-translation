# AGENTS.md (dtv)

## Project: Decoding Time Verification (DTV) for Code Translation

1. no trailing spaces, no lines with only spaces
2. keep this file up to date (last updated: 2026-05-06)
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
- `test/`: unit tests (use the venv Python). Run with `./.venv/bin/python -m pytest -q`.
  - `test/controller/`, `test/core/`, `test/feedback/`, `test/rollback/`, `test/c_rust/`, `test/js_ts/`, `test/e2e/`: see directory listings for the current set; only LLM output may be mocked, all other tools (rustc, gcc, tsc, ESLint, filesystem, subprocess) run for real.

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
- FP/FN priority: the renderer must minimize False Positives first, then False Negatives.
  - FP = a correct prefix is rejected because scaffold/patch introduces an error the user did not write. Unacceptable: the oracle then blames a bug on the model that is actually our scaffold's fault.
  - FN = an incorrect prefix is accepted because scaffold/patch masks a real error. Acceptable in moderation: DTV stmt-level generation rechecks the same region on subsequent steps, so a masked error surfaces later.
  - Concretely, when a patch has two equally local options, prefer the one that is unconditionally compile-safe (for example, downgrading a value-context expression into a statement plus an independent `todo!()` tail) over the one that requires the user's branches to have compatible types.

### Design Decisions
- Weakened Program Oracle (project-wide):
  The program-level oracle used during DTV generation is intentionally weaker
  than a full-correctness check. DTV is a superset of the naive baseline: both
  share the same post-hoc verification step, so in-generation oracles do not
  need to enforce full correctness - that is already handled post-hoc. The
  in-generation oracle only needs to provide actionable feedback that the model
  can use to improve the code during decoding.
  - C -> Rust:
    - Program diff test oracle runs with relaxed matching; full correctness
      verified post-hoc.
    - `rustc` compile oracle filters resolvable E0277 at sub-PROGRAM
      granularity (`_filter_resolvable_trait_bounds` in `compiler_oracle.py`):
      E0277 whose fix may land in a later stmt is kept as PASS.
      Triggers: rustc attached any machine suggestion (e.g.
      `#[derive(PartialOrd)]` for super-trait, or `&`/`*` for usage-site
      fixes), or the primary span sits on an `impl X for Y {` header (a later
      `impl SuperTrait for Y` can satisfy it). Strict post-hoc recheck
      catches any never-fixed cases. PROGRAM-level compilation does not
      apply this filter.
  - JS -> TS layered verification:
    - `strict: false` in `tsc_check.js` across all verifier paths (inner,
      outer, final eval).
    - Inner DTV (STMT-level, `TscOracle` + `EslintOracle` via the oracle
      interface): additional weakening via `filter_partial_noise` and
      `filter_type_correctness` (drops TS2322/TS2339/TS2345 from verdict).
      Provides actionable feedback during decoding.
    - Outer repair loop and final evaluation bypass the oracle interface:
      `_compile_ts_code` in `run_experiments_js_ts.py` directly invokes
      `TscDriver` + `EslintDriver` and treats any `tsc.exit_code != 0` or
      `eslint.error_count != 0` as failure, mirroring c_rust's
      `_compile_rust_code`. No type-correctness filter at this layer, so the
      outer loop is stricter than the inner DTV oracle (matches the c_rust
      layering where outer rustc has no E0277 filter).
    - Full type correctness via strict=true post-hoc recheck is NOT
      implemented. If a paper claim requires it, add a `--strict` flag to
      `tsc_check.js` and route final eval through a separate strict path.
- ESLint as supplementary oracle (JS -> TS):
  - `@typescript-eslint/typedef` rule checks for missing type annotations.
  - ESLint hints (e.g. "Add an explicit type annotation") are included in
    feedback diagnostics.
  - Both DTV and naive receive ESLint hints equally (fairness constraint in
    `run_experiments_js_ts.py`).
- Context rules for legal prefix (JS -> TS):
  - `try_catch_rule`: adds `catch(e) {}` to uncaught try statements so tsc can
    compile the prefix.
  - `function_return_rule`: adds `return undefined as any;` to non-void
    functions before closing brace.

### How to Run
- Unit tests: `./.venv/bin/python -m pytest -q`
- Experiments: see "Experiment Infrastructure" below.

### Experiment Infrastructure
Top-level runners. Each takes a required `--strategy {naive,dtv,bon-nsr,s_star}` flag and runs ONE strategy per invocation; produce A/B pairs by invoking twice with different `--output` paths. Inputs are case-id lists passed as positional args.

- `run_experiments_c_rust.py`: C->Rust full-batch runner.
- `run_experiments_js_ts.py`: JS->TS full-batch runner. Saves pass outputs to `*_pass_outputs/{dtv,naive}/*.ts`.
- `run_single_c_rust_eval.py`, `run_single_js_ts_eval.py`, `run_single_js_ts_eval_naive.py`: single-case eval scripts.
- `js_ts/dataset/filter_typeweaver.py`: build the JS->TS dataset by rollup-bundling TypeWeaver packages (LOC 30-1000, exclude already-passing under `tsc --strict`); run before any JS->TS experiment.

Sample lists (paper cohorts, seed=20260416 for C->Rust, seed=42 for JS->TS):
- `300_samples_seed20260416.txt`: full C->Rust eval (n=300, RQ1/RQ3).
- `150_samples_seed20260416_js_ts.txt`: full JS->TS eval (n=150, RQ1/RQ3).
- `100_samples_seed20260416_head.txt`: first 100 of 300 (RQ2 ablation; cost-matched n=200 = head + part2).
- `100_samples_part2_seed20260416.txt`: cases 101-200 of 300 (cost-matched complement).
- `100_samples_seed20260416_js_ts_head.txt`: first 100 of 150 (cost-matched JS->TS n=100).

Datasets:
- `dataset/sXXX/`: C->Rust (CodeNet) cases, paper n=300. Tracked: `source.c` (input), `testcases/*` (differential test inputs), `metadata.json` (construction record). AFL pipeline build artifacts (`afl_corpus/`, `afl_out/`, `coverage/`, `llm_seeds/`, `min_corpus/`, `prog_afl`, `prog_cov`, `prog_san`) are gitignored; the AFL pipeline that produces them lives in a separate repo (`agent_fuzz`) and follows paper Appendix E. License: Apache 2.0 (`dataset/LICENSE`); attribution and selection criteria in `dataset/NOTICE`.
- `dataset_js_ts/<package>/`: JS->TS cases, the n=196 filtered TypeWeaver pool from which paper samples 150 (Appendix E). Each case has `source.js` (rollup-bundled), `metadata.json`, and `LICENSE` (verbatim from upstream npm distribution where shipped, otherwise an SPDX-id stub from `package.json`). Built by `js_ts/dataset/filter_typeweaver.py` from the TypeWeaver release; the 150 paper IDs are in `150_samples_seed20260416_js_ts.txt`. Per-package license terms govern each `source.js`; see `dataset_js_ts/LICENSE.md` for the licensing summary.
