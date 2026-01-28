# Bug: function_diff returns NOT_APPLICABLE at EOS

## Summary
At EOS, `function_diff` often returns `NOT_APPLICABLE` while `rustc` and
`program_diff` pass. This can surface as policy loops or lost signal when
function-level verification should be possible.

## Observed behavior
- On EOS verify, outputs are typically:
  - `rustc`: PASS
  - `function_diff`: NOT_APPLICABLE
  - `program_diff`: PASS

## Expected behavior
When the final program is valid and a function has closed, the function-level
oracle should have a concrete target function and run (or explicitly explain
why it cannot).

## Repro
1. Run:
   `./.venv/bin/python -m pytest -vv -s -o log_cli=true --log-cli-level=INFO test/e2e/c2rust/trap/test_trap.py`
2. Look for EOS verify logs showing `function_diff` = NOT_APPLICABLE.

## Likely cause
`function_diff` requires `OracleContext.closed_function_name`. This context is
only set when the current verify step detects a newly closed function via the
group stack diff. At EOS, no new function closes in that step, so
`closed_function_name` is None and the oracle returns NOT_APPLICABLE.

## Notes / potential fixes (not implemented)
- At EOS, choose a target function (e.g., last closed function or `main`).
- Allow `function_diff` to accept an explicit fallback function name in context.
