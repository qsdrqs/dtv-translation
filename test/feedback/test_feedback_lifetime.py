from __future__ import annotations

from core.types import Diagnostic, Granularity, OracleOutput, Verdict
from feedback.feedback import FeedbackState


def _make_fail_output(
    oracle_name: str,
    message: str,
    scope: Granularity | None = None,
) -> OracleOutput:
    return OracleOutput(
        oracle_name=oracle_name,
        verdict=Verdict.FAIL,
        diagnostics=(Diagnostic(message=message, severity="error"),),
        rollback_scope=scope,
    )


# Bug reproduction: feedback lifetime after rollback escalation


def test_func_rollback_escalation_promotes_stmt_feedback() -> None:
    """Reproduce the exact bug from the smoke test log:

    1. on_verify at STMT -> tsc FAIL (entries stored at STMT scope)
    2. bind_failures_to_scope(outputs, STMT) from first ROLLBACK(STMT)
    3. ROLLBACK clears last_outputs -> subsequent binds get empty list
    4. bind_failures_to_scope([], FUNC)  -- escalation with empty outputs
       BUG: entries stay at STMT scope, never promoted to FUNC
    5. on_commit(STMT) wipes STMT-scoped entries -> feedback gone

    After fix: step 4 should promote STMT entries to FUNC scope, so
    on_commit(STMT) at step 5 does not clear them.
    """
    fs = FeedbackState()
    tsc_fail = _make_fail_output("tsc", "Property 'length' does not exist on type 'never'.")
    eslint_fail = _make_fail_output("eslint", "Expected isEmptyArray to have a type annotation.")

    # Step 1: VERIFY(STMT) -> FAIL
    fs.on_verify([tsc_fail, eslint_fail], selected_scope=Granularity.STMT)
    assert len(fs.active_snapshot()) == 2

    # Step 2: ROLLBACK(STMT) with the verify outputs
    fs.on_rollback(Granularity.STMT)
    fs.bind_failures_to_scope([tsc_fail, eslint_fail], Granularity.STMT)
    assert len(fs.active_snapshot()) == 2

    # Step 3: After rollback, runtime clears last_outputs.
    # Subsequent feedback attempts fail, so next rollback gets empty outputs.

    # Step 4: ROLLBACK(FUNC) with empty outputs (escalation).
    fs.on_rollback(Granularity.FUNC)
    fs.bind_failures_to_scope([], Granularity.FUNC)

    # After escalation, entries must be at FUNC scope.
    snapshot = fs.active_snapshot()
    assert len(snapshot) == 2, f"expected 2 entries after FUNC escalation, got {len(snapshot)}"
    for output in snapshot:
        assert output.rollback_scope == Granularity.FUNC, (
            f"expected FUNC scope after escalation, got {output.rollback_scope}"
        )

    # Step 5: COMMIT(STMT) must NOT clear FUNC-scoped entries.
    fs.on_commit(Granularity.STMT)
    snapshot_after_commit = fs.active_snapshot()
    assert len(snapshot_after_commit) == 2, (
        f"expected 2 entries after STMT commit, got {len(snapshot_after_commit)}"
    )


def test_escalation_with_new_outputs_uses_new_outputs() -> None:
    fs = FeedbackState()
    old_fail = _make_fail_output("tsc", "old error")
    new_fail = _make_fail_output("tsc", "new error at wider scope")

    fs.on_verify([old_fail], selected_scope=Granularity.STMT)

    fs.on_rollback(Granularity.FUNC)
    fs.bind_failures_to_scope([new_fail], Granularity.FUNC)

    snapshot = fs.active_snapshot()
    assert len(snapshot) == 1
    assert snapshot[0].rollback_scope == Granularity.FUNC
    assert snapshot[0].diagnostics[0].message == "new error at wider scope"


def test_promotion_only_promotes_narrower_not_wider() -> None:
    fs = FeedbackState()
    func_fail = _make_fail_output("tsc", "func-level error")
    stmt_fail = _make_fail_output("eslint", "stmt-level error")

    fs.on_verify([func_fail], selected_scope=Granularity.FUNC)
    fs.on_verify([stmt_fail], selected_scope=Granularity.STMT)

    fs.on_rollback(Granularity.BLOCK)
    fs.bind_failures_to_scope([], Granularity.BLOCK)

    snapshot = fs.active_snapshot()
    assert len(snapshot) == 2
    scopes = {o.oracle_name: o.rollback_scope for o in snapshot}
    assert scopes["eslint"] == Granularity.BLOCK, "STMT entry should be promoted to BLOCK"
    assert scopes["tsc"] == Granularity.FUNC, "FUNC entry should stay at FUNC"
