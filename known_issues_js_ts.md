# Known Issues (JS -> TS)

Last updated: 2026-04-02

## Issue: Feedback A at BLOCK level breaks try-catch syntactic continuity

### References
- Smoke test: `result/smoke_test.log` (json-parse-better-errors, Rollback 13/22/31)
- Rollback analysis: `result/smoke_test_dtv_rollback_analysis/json-parse-better-errors/rollback_events.md`

### Symptom
- After BLOCK rollback on a catch block, Feedback A embeds a `/* repair feedback: ... */` comment between the closing `}` of try and where `catch` should go.
- The model sees the prefix ending with `}` + comment and outputs `}` to close the function, instead of writing a new `catch (...)` clause.
- This triggers TS1472 ('catch' or 'finally' expected) and cascades into further failures.

### Evidence
Rollback prefix after BLOCK rollback:
```typescript
function parseJson(...): any {
  try {
    return JSON.parse(txt, reviver);
  }
```

Feedback A inserts:
```typescript
  }
/* repair feedback:
failed snippet: catch (e: unknown) { ... e.message ... }
diagnostics: TS1472, TS18046...
*/
```

Model outputs `}` (3-6 chars) instead of `catch (...)`. This happened identically in all 3 BLOCK rollbacks (R13, R22, R31).

### Root cause
Feedback A embeds a repair comment at the rollback point. At BLOCK level, this puts the comment between `try { }` and the expected `catch`, breaking the syntactic continuity that the model relies on to generate the catch clause.

This differs from FUNC-level Feedback A where the comment is at prefix_len=0 (top of assistant content), so the model starts fresh without syntactic expectations.

### Potential fix
Offset the Feedback A comment position to BEFORE the try block (or at the top of the function), so the model sees:
```typescript
/* repair feedback: ... */
function parseJson(...): any {
  try {
    return JSON.parse(txt, reviver);
  }
```
and naturally continues with `catch (...)`.

## Issue: TS18046 ('e' is of type 'unknown') causes deadloop on catch variables

### References
- Smoke test: `result/smoke_test.log` (json-parse-better-errors, 102 occurrences)
- `js_ts/oracles/compiler_oracle/tsc_parser.py`

### Symptom
- Model writes `catch (e: unknown)` (valid TS, passes STMT verify).
- Later `e.message` triggers TS18046 at STMT level. Model cannot go back and change the catch clause.
- TypeScript only allows `any` or `unknown` as catch clause annotations (`catch (e: Error)` triggers TS1196).
- Model consistently writes `e: unknown` instead of `e: any`, leading to TS18046 on every `e.message` usage.

### Root cause
STMT-level oracle cannot foresee that `catch (e: unknown)` will cause TS18046 on every subsequent `e.message` access. By the time TS18046 fires, the catch clause is already committed.

### Potential fix
- Short-term: Add TS18046 to `_TYPE_CORRECTNESS_BLOCKLIST` (same as TS2322/TS2339/TS2345).
- Long-term: Direction A (multi-level oracle) with BLOCK-level tsc oracle verifying the entire catch block together.
