from __future__ import annotations

from core.llm_output import AssistantContent
from core.types import Granularity, GroupStackFrame
from rollback.manager import RollbackManager


def _frames(kinds: tuple[Granularity, ...]) -> tuple[GroupStackFrame, ...]:
    return tuple(GroupStackFrame(kind=kind) for kind in kinds)


def _commit(m: RollbackManager, prefix: str, group_stack: tuple[Granularity, ...]) -> None:
    m.sync_groups(_frames(group_stack))
    m.add_stmt_checkpoint(prefix, AssistantContent.empty(), None)


def _named_frames(items: tuple[tuple[Granularity, str | None], ...]) -> tuple[GroupStackFrame, ...]:
    return tuple(GroupStackFrame(kind=kind, name_id=name_id) for kind, name_id in items)


def _commit_named(
    m: RollbackManager,
    prefix: str,
    group_stack: tuple[tuple[Granularity, str | None], ...],
) -> None:
    m.sync_groups(_named_frames(group_stack))
    m.add_stmt_checkpoint(prefix, AssistantContent.empty(), None)


def _identity_frames(
    items: tuple[tuple[Granularity, str | None, str | None], ...],
) -> tuple[GroupStackFrame, ...]:
    return tuple(
        GroupStackFrame(kind=kind, name_id=name_id, group_id=group_id)
        for kind, name_id, group_id in items
    )


def _commit_identity(
    m: RollbackManager,
    prefix: str,
    group_stack: tuple[tuple[Granularity, str | None, str | None], ...],
) -> None:
    m.sync_groups(_identity_frames(group_stack))
    m.add_stmt_checkpoint(prefix, AssistantContent.empty(), None)


def test_sync_groups_opens_block_at_first_commit_inside_block() -> None:
    m = RollbackManager()

    s1 = "stmt1"
    _commit(m, s1, (Granularity.FUNC,))
    assert [(f.kind, f.start_stmt) for f in m.group_stack] == [(Granularity.FUNC, 0)]

    s2 = "stmt2"
    _commit(m, s2, (Granularity.FUNC, Granularity.BLOCK))
    assert [(f.kind, f.start_stmt) for f in m.group_stack] == [
        (Granularity.FUNC, 0),
        (Granularity.BLOCK, 1),
    ]

    out = m.rollback(Granularity.BLOCK)
    assert out.code_prefix == s1
    assert [c.code_prefix for c in m.stmt_checkpoints] == [s1]
    assert [(f.kind, f.start_stmt) for f in m.group_stack] == [(Granularity.FUNC, 0)]


def test_sync_groups_closes_block_when_exiting() -> None:
    m = RollbackManager()

    _commit(m, "s1", (Granularity.FUNC,))
    _commit(m, "s2", (Granularity.FUNC, Granularity.BLOCK))
    _commit(m, "s3", (Granularity.FUNC,))

    assert [(f.kind, f.start_stmt) for f in m.group_stack] == [(Granularity.FUNC, 0)]


def test_sync_groups_closes_func_when_exiting() -> None:
    m = RollbackManager()

    _commit(m, "s1", (Granularity.FUNC,))
    _commit(m, "s2", ())

    assert m.group_stack == []


def test_rollback_func_truncates_to_func_start() -> None:
    m = RollbackManager()

    _commit(m, "before_func", ())
    _commit(m, "in_func_s1", (Granularity.FUNC,))
    _commit(m, "in_func_s2", (Granularity.FUNC, Granularity.BLOCK))

    out = m.rollback(Granularity.FUNC)
    assert out.code_prefix == "before_func"
    assert [c.code_prefix for c in m.stmt_checkpoints] == ["before_func"]
    assert m.group_stack == []


def test_rollback_func_truncates_to_block_start() -> None:
    m = RollbackManager()

    _commit(m, "before_func", ())
    _commit(m, "in_func_s1", (Granularity.FUNC,))
    _commit(m, "in_func_s2", (Granularity.FUNC, Granularity.BLOCK))

    out = m.rollback(Granularity.BLOCK)
    assert out.code_prefix == "in_func_s1"
    assert [c.code_prefix for c in m.stmt_checkpoints] == ["before_func", "in_func_s1"]
    assert [(f.kind, f.start_stmt) for f in m.group_stack] == [(Granularity.FUNC, 1)]


def test_rollback_func_after_function_switch_keeps_previous_function() -> None:
    m = RollbackManager()

    _commit_named(m, "preamble", ())
    _commit_named(m, "main_complete", ((Granularity.FUNC, "main"),))
    _commit_named(m, "min_partial", ((Granularity.FUNC, "min"),))

    out = m.rollback(Granularity.FUNC)
    assert out.code_prefix == "main_complete"
    assert [c.code_prefix for c in m.stmt_checkpoints] == ["preamble", "main_complete"]


def test_rollback_block_after_sibling_switch_uses_block_group_id() -> None:
    m = RollbackManager()

    _commit_identity(m, "preamble", ())
    _commit_identity(
        m,
        "block_a_stmt",
        (
            (Granularity.FUNC, "foo", "func@0"),
            (Granularity.BLOCK, None, "block@10"),
        ),
    )
    _commit_identity(
        m,
        "block_b_stmt",
        (
            (Granularity.FUNC, "foo", "func@0"),
            (Granularity.BLOCK, None, "block@30"),
        ),
    )

    out = m.rollback(Granularity.BLOCK)
    assert out.code_prefix == "block_a_stmt"
    assert [c.code_prefix for c in m.stmt_checkpoints] == ["preamble", "block_a_stmt"]


def test_sync_groups_reopens_func_when_name_mismatch_with_same_group_id() -> None:
    m = RollbackManager()

    _commit_identity(m, "s1", ((Granularity.FUNC, "main", "func@0"),))
    assert [(f.kind, f.name_id, f.group_id, f.start_stmt) for f in m.group_stack] == [
        (Granularity.FUNC, "main", "func@0", 0)
    ]

    _commit_identity(m, "s2", ((Granularity.FUNC, "min", "func@0"),))
    assert [(f.kind, f.name_id, f.group_id, f.start_stmt) for f in m.group_stack] == [
        (Granularity.FUNC, "min", "func@0", 1)
    ]
