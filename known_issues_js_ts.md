# Known Issues (JS -> TS)

Last updated: 2026-03-19

## Issue: Scope validator rejects valid Mechanism B patches for first-stmt repairs

### References
- Smoke test log: `/tmp/js2ts_smoke_stderr.log` (steps 10-14)
- `feedback/output_parser.py` (`validate_patch_scope`)

### Symptom
- Mechanism B generates a correct patch with type annotations added (e.g., `const n: number = height.length;`).
- The scope validator rejects it with "patch is not valid TypeScript syntax" or "stmt-scope patch cannot include top-level items (function_declaration)".
- The patch is discarded despite being correct.

### Evidence from the smoke test log
- Step 10 (Mechanism B), model output:
  ```typescript
  function trap(height: number[]): number {
    const n: number = height.length;
  ```
- Scope validator rejects: the patch includes a `function_declaration` node, which is disallowed at STMT scope.
- This repeats 3 times (steps 10, 11, 12) before the policy escalates to FUNC rollback.

### Root cause
- Stop criteria triggers at `;` or `}`, so the first checkpoint is always "function header + 1st statement" as a single unit.
- When eslint flags the 1st statement for missing type annotations, STMT-scope rollback rolls back to before the function header.
- The model's repair patch naturally includes the function header (for context) plus the fixed statement.
- The scope validator sees a `function_declaration` in a STMT-scope patch and rejects it, even though this is the only valid way to repair the first statement.

### Recommended direction
- Refine scope validator to allow `function_declaration` in STMT-scope patches when the repair target is the first statement inside a function.
- Alternative: detect the "function header + 1st stmt" pattern and temporarily promote the repair scope to FUNC for this specific case.

## Issue: Feedback Mechanism A does not guide the model to add type annotations

### References
- Smoke test log: `/tmp/js2ts_smoke_stderr.log` (steps 6-7, 16-17)

### Symptom
- Mechanism A inserts a `/* repair feedback: ... */` comment into the code stream with eslint diagnostics.
- The model generates the exact same code again, completely ignoring the repair instruction.
- This repeats on every Mechanism A attempt throughout the 60s run.

### Evidence from the smoke test log
- Step 6 (Mechanism A), model input includes:
  ```
  /* repair feedback:
  diagnostics:
  - oracle=eslint severity=error code=@typescript-eslint/typedef span=10:9
    message: Expected n to have a type annotation.
  */
  ```
- Model output: `function trap(height: number[]): number { const n = height.length;` -- identical to before, no type annotation added.

### Root cause (hypotheses, needs ablation to isolate)
- **Task framing**: A stays in the same assistant turn ("continue code"), model is not in "follow instruction" mode. B switches to a user turn which triggers instruction following.
- **Content gap**: B provides goal + constraints + scope rules + output contract. A provides only diagnostics in a code comment. The current A vs B comparison is confounded.
- **Comment format**: `/* ... */` is treated as informational by models trained on code. The model's "skip comments" prior may dominate.
- **Context mismatch**: The repair comment exists during generation but not in the final code -- the model conditions on "ghost context."
- NOT concluded as a fundamental flaw of Mechanism A. The design space has not been explored.
- This is NOT specific to JS->TS or lint errors. The same pattern (model ignoring Mechanism A feedback) is observed in C->Rust with compilation errors (see known_issues_c_rust.md Issues 4 and 5).

### Critical constraint
Mechanism A cannot be abandoned. It is the only repair path that preserves DTV at higher rollback scopes (BLOCK/FUNC/PROGRAM). Mechanism B generates entire blocks/functions in one shot, bypassing token-by-token verification.

### Research plan
See `.sisyphus/plans/feedback-mechanism-a-ablation.md` for a controlled ablation plan to isolate the failure factors.

## Issue: Renderer-closed code triggers spurious eslint diagnostics

### References
- Smoke test log: `/tmp/js2ts_smoke_stderr.log` (step 4, line 292)
- `js_ts/render/renderer.py` (function closing logic)

### Symptom
- eslint reports `@typescript-eslint/no-explicit-any: Unexpected any` at a span that does not correspond to any `any` keyword in the model-generated code.

### Evidence
- Model-generated prefix:
  ```typescript
  import * as readline from 'readline';

  function trap(height: number[]): number {
    const n = height.length;
  ```
- Renderer output (after closing):
  ```typescript
  import * as readline from 'readline';

  function trap(height: number[]): number {
    const n = height.length;
  return undefined as any;
  }
  ```
- `return undefined as any;` is injected by the renderer to make the partial function body valid. eslint flags the `any` keyword as a real error.

### Root cause
- The renderer closes unclosed functions with typed return by adding `return undefined as any;`. This is a valid strategy for making partial code compile, but it introduces `any` that eslint's `no-explicit-any` rule flags.
- The eslint oracle has no way to distinguish renderer-generated code from model-generated code.

### Recommended direction
- Add a noise filter to the eslint oracle: filter out diagnostics whose span (line number) falls beyond the model-generated prefix. The renderer-closed portion starts after the last line of the prefix, so any diagnostic with `span.line > prefix_line_count` is renderer noise.
- This filter is sound for AST-only eslint rules (typedef, explicit-function-return-type, no-explicit-any) because they are purely syntactic and cannot be influenced by code elsewhere in the file. If type-checked rules (no-unsafe-*) are added later, the filter model needs re-evaluation since renderer code could affect type inference.
- Do NOT try to make the renderer produce "perfect" closing code -- this is an unbounded problem (the correct return value depends on arbitrary context).
