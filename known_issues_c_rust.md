# Known Issues

Last updated: 2026-03-02

## Issue: Rollback loop caused by calls to not-yet-defined functions

### References
- `result/rollback_analysis_live_v3/s168939986/rollback_events.md`
- `result/rollback_analysis_live_v3/s628961975/rollback_events.md` (Rollback 1, lines 6-75)
### Symptom
- Generated code calls a function before its definition is available, triggering `E0425: cannot find function ... in this scope`.
- The controller repeatedly rolls back and retries around the same region but cannot converge because the callee definition is never emitted first.

### Evidence from the rollback log
- (`s168939986`) Rollback 1 shows `factorial(&mut fact, &mut factinv, max_n);` in `main` and then rustc reports `cannot find function factorial in this scope`.
- (`s168939986`) Repair patches attempt to inject `fn factorial()` but the generated patch is incomplete or structurally invalid.
- (`s168939986`) Later rollback events still contain unresolved `factorial`-related compile failures and additional type/structure errors, indicating the loop did not converge.
- (`s628961975`) Rollback 1 shows `read_int(&mut it)` in `main` before `read_int` is defined; rustc reports `E0425: cannot find function read_int in this scope`.

### Root cause hypothesis
- The translation order is unstable: a function call is emitted before the callee definition is available in a valid form.
- Recovery patches try to define the function in-place, but patch quality degrades under repeated rollback/repair cycles.

### Recommended direction
- Reorder C input structure before translation so callee functions are defined before first use in generated Rust.
- Prefer a deterministic prepass that hoists function definitions/prototypes into a stable order (dependency-aware ordering) before entering DTV decode/verify loop.
- Keep `main` generation after helper functions to reduce undefined-symbol retries and improve rollback convergence.

### Follow-up actions
- Add a preprocessing step in the C pipeline that computes function dependency order and emits translation units in that order.
- Add an experiment flag to compare rollback counts with and without the reordering prepass.
- Track issue-specific metric: repeated rollbacks triggered by unresolved function symbols (for example, E0425 clusters).

## Issue: Non-normalized compiler diagnostics leak into repair feedback

### References
- `result/rollback_analysis_live_v3/s168939986/rollback_events.md` (Feedback block around lines 264-351)

### Symptom
- Repair feedback contains a large raw `rustc stderr` blob instead of a normalized diagnostic list.
- High-volume warnings (`unused_mut`, `unused_variables`) are mixed with blocking errors in the same feedback payload.

### Evidence from the rollback log
- The feedback section includes `message: rustc stderr: error[E0308]...` followed by full compiler text output.
- The same block contains many warning lines and ends with `error: aborting due to 2 previous errors; 8 warnings emitted`.
- This indicates diagnostics are being forwarded as unstructured text at least on the `function_diff` failure path (`RUST_CDYLIB_FAIL`).

### Root cause hypothesis
- In cdylib compilation failure handling, the oracle path likely bypasses the structured rustc JSON parser and forwards stderr directly.
- Diagnostic filtering is missing or too late, so non-critical warnings are included in repair context.

### Recommended direction
- Enforce a single diagnostic normalization path for all rustc invocations (including function-diff/cdylib path): collect JSON diagnostics first, then render compact feedback text from parsed records.
- Separate errors from warnings in `OracleOutput`; by default, repair prompt should include only error diagnostics unless warning-only mode is explicitly enabled.
- Add a hard cap and dedupe for feedback diagnostics to avoid context pollution from repeated warning clusters.

### Follow-up actions
- Audit `c_rust/oracles/function_diff_test_oracle/` and related compile helpers to ensure `--error-format=json` is used and parsed.
- Add regression test: given mixed rustc output, feedback text must preserve errors, drop non-actionable warnings, and avoid raw stderr dump.
- Add metric: fraction of feedback payload composed of raw compiler text vs normalized diagnostics.

## Issue: Structural damage from feedback patch causes large STMT rollback drops

### References
- `result/rollback_analysis_live_v3/s660236723/rollback_events.md` (Rollbacks 2-5)
- `controller/loop.py` (`_handle_apply_patch`, `_handle_verify`, `_handle_commit`)
- `controller/policy.py` (`commit_when_no_oracle_selected`, `_continue_or_terminate`)
- `rollback/manager.py` (`add_stmt_checkpoint`)

### Symptom
- A `RollbackScope.STMT` rollback drops a disproportionately large segment (237 chars, spanning ~10 statements, block boundaries, and even a function boundary crossing).
- In sample `s660236723`, Rollbacks 2-5 all orbit around the same checkpoint (425/508 chars), unable to escape the structural damage.
- The LLM's feedback patches degrade in quality over rounds (302 -> 142 -> 83 -> 109 -> 2 chars), eventually producing a 2-char whitespace patch (giving up).

### Evidence from the rollback log
- Rollback 1 (step 23) cuts the prefix to 123 chars, inside an open `if b > a {` block.
- Feedback Mechanism A patch (302 chars) adds comments and `let mut a = a;` but does NOT close the `if` block, creating a 425-char prefix with permanent structural damage:
  ```rust
  fn gcd(a: u64, b: u64) -> u64 {
      let mut tmp = a;
      let mut r = 1;
      if b > a {          // NEVER CLOSED
          tmp = a;
      // Fix: ...
      // Corrected implementation:
      let mut a = a;      // prefix ends here, if block still open
  ```
- After COMMIT at 425, the model generates 237 more chars (GCD algorithm, function close, `fn main` start) across ~30 steps without any COMMIT.
- Rollback 2 (step 57) drops all 237 chars back to the 425-char checkpoint.
- Subsequent feedback patches try to "rewrite the entire function" but are appended after the broken structure, producing duplicate `fn gcd` definitions.
- Rollback 3's patch adds `}` to close the `if` block, slightly advancing the checkpoint to 508. Rollbacks 4-5 orbit around 508.

### Root cause
Two mechanisms prevent intermediate COMMITs between step 25 and step 55:

1. **Renderer returns CONTINUE for broken structure.** The unclosed `if b > a {` block creates a structurally ambiguous tree-sitter AST. At intermediate boundaries (each `;` or `}` triggers the stopping criteria), the renderer cannot produce a cleanly completable artifact and returns `RenderStatus.CONTINUE`. When render status is not OK, the policy returns CONTINUE without running any oracle or saving a checkpoint.

2. **Oracle skipping amplifies the gap (known issue #3).** Even when the renderer does return OK, the unstable BLOCK `name_id` can promote `effective_granularity` from STMT to BLOCK, causing `RustcOracle` (required=STMT) to be skipped. With `commit_when_no_oracle_selected = False` (default), the policy returns CONTINUE instead of COMMIT.

Both paths converge to the same outcome: GENERATE -> VERIFY (no oracle, no commit) -> CONTINUE -> GENERATE loop for 30+ steps, accumulating content without any checkpoint.

Additionally, `_handle_apply_patch` does not save a checkpoint. The only way to save a checkpoint is via `_handle_commit`, which requires a prior successful VERIFY with a valid artifact. So after APPLY_PATCH, the prefix must pass VERIFY + COMMIT before the new content is checkpointed.

### Recommended direction
- **Feedback-level fix**: Feedback Mechanism A patches should be structurally aware. When the rollback prefix has open blocks (e.g., unclosed `if`), the patch should close them before adding new code. Alternatively, add a structural normalization pass that closes dangling blocks at the patch boundary.
- **Rollback-level fix**: When selecting the rollback target for STMT scope, prefer structurally clean boundaries (e.g., at a complete statement outside any open block) over the raw last checkpoint. This prevents cutting the prefix to inside an open block.
- **Policy-level mitigation**: Consider `commit_when_no_oracle_selected = True` as a fallback when the renderer returns OK but no oracle matches. This would save intermediate checkpoints even when granularity mismatch prevents oracle runs, reducing the blast radius of STMT rollbacks.

### Relationship to other issues
- **Issue #3 (unstable BLOCK name_id)**: Fixing issue #3 would eliminate the oracle-skipping path, but the renderer-CONTINUE path would still prevent intermediate COMMITs for structurally broken prefixes.
- **Issue #2 (if/else arm handling)**: The unclosed `if` block is a specific instance of incomplete control flow structure surviving through rollback + feedback cycles.

### Follow-up actions
- Verify whether the intermediate VERIFYs return `RenderStatus.CONTINUE` or `RenderStatus.OK` by checking `result/ab_experiment_live.log` around log lines 147000-147464 (steps 25-57 of sample s660236723).
- Add a renderer test: given a prefix with an unclosed `if` block followed by additional statements, assert that `try_render` returns OK (not CONTINUE) so that oracles can run.
- Add a feedback integration test: after STMT rollback to inside an open block, assert the feedback patch closes the open block before appending new code.
- Track metric: maximum STMT rollback drop size across samples, flagging drops > 100 chars as anomalous.

## Issue: Feedback Mechanism A patches that are pure comments (no actual code fix)

### References
- `result/rollback_analysis_live_v3/s672064666/rollback_events.md` (lines 537-571)
- `result/rollback_analysis_live_v3/s780263580/rollback_events.md` (lines 321-391)

### Symptom
- After receiving a diagnostic (e.g., `E0277: the trait bound 'usize: Neg' is not satisfied`), the LLM produces a Mechanism A patch consisting entirely of comments that *describe* the intended fix but contain no actual code changes.
- Example patch content:
  ```rust
  // The above error suggests we're trying to do negative arithmetic with usize.
  // We need to use signed integers for dx/dy in movement, but the bounds are unsigned.
  // So we fix: use i32 for coordinates in movement, but keep bounds as usize.
  // We'll rewrite with i32 for movement and convert back to usize for bounds checks.
  // But since the input is small, we can do it safely.
  // Let's refactor the search function to use i32 for movement.
  }
  ```
- The patch is applied (appended after the rollback point), producing a prefix with planning comments but the original error still present. The next VERIFY fails with the same diagnostic, wasting a feedback round.
- In harder cases, the comment-only patch expands into a long "justification" block that explicitly refuses full translation (for example, "we will simplify/rewrite" and "we will not fully translate the original C code") while still providing no executable fix.

### Root cause
- Mechanism A asks the LLM to produce a *replacement suffix* for the code after the rollback point. The LLM interprets this as a chance to "reason" about the fix and emits a chain-of-thought in comments rather than producing corrected code.
- This is especially common when the required fix is non-local (e.g., changing `usize` to `i32` in function signatures, which affects callers). The LLM recognizes the fix is complex and defaults to planning instead of acting.
- There is no validation that the patch contains meaningful code changes before applying it.

### Recommended direction
- **Patch validation**: After receiving a Mechanism A patch, check whether it contains any non-comment, non-whitespace code changes. If the patch is pure comments, reject it and either retry with a stronger prompt or fall back to rollback without feedback.
- **Prompt engineering**: Adjust the Mechanism A prompt to explicitly instruct the model to produce executable code, not comments or plans. E.g., "Do not write comments explaining what to do. Write the corrected code directly."
- **Detection metric**: Track the ratio of comment lines to code lines in feedback patches. Flag patches where comment-to-code ratio exceeds a threshold (e.g., >80% comments) as likely non-fixes.

## Issue: Placeholder comments in patches hide missing implementation

### References
- `result/rollback_analysis_live_v3/s672064666/rollback_events.md` (lines 209-224, 228-244)

### Symptom
- The feedback patch contains some real Rust statements, but leaves critical logic as placeholder comments such as `// ... rest of the logic`.
- Because the patch is not pure comments, a simple "non-comment code exists" check would pass, but the translation is still incomplete and typically fails in subsequent verify steps.

### Root cause
- Mechanism A optimizes for local minimal edits and may satisfy format constraints by outputting a partial snippet plus placeholder text instead of finishing the required logic.
- Current validation focuses on syntax/form and does not detect semantic incompleteness markers like ellipsis placeholders.

### Recommended direction
- **Placeholder guardrail**: Reject feedback patches containing known placeholder patterns (for example `// ...`, `... rest of`, `TODO`, `FIXME`, `omitted`) in executable regions.
- **Stronger output contract**: In Mechanism A prompt, explicitly forbid placeholder comments and require fully executable code for the replaced snippet.
- **Two-stage acceptance**: Accept a patch only if both checks pass: (1) non-comment code exists, and (2) no placeholder markers indicating skipped logic.
- **Escalation policy**: If a placeholder patch is detected, skip APPLY_PATCH and immediately trigger rollback retry (or switch mechanism), so the system does not waste a full verify cycle.

### Relationship to other issues
- Complements the previous issue (pure-comment patches). That issue catches "no code at all" outputs; this one catches "some code + skipped core logic" outputs.
