from __future__ import annotations

from core.llm_output import AssistantContent
from core.types import Granularity, GroupStackFrame, RollbackScope
from rollback.manager import RollbackManager


def _frames(kinds: tuple[Granularity, ...]) -> tuple[GroupStackFrame, ...]:
    return tuple(GroupStackFrame(kind=kind) for kind in kinds)


def _commit(m: RollbackManager, prefix: str, group_stack: tuple[Granularity, ...]) -> None:
    m.sync_groups(_frames(group_stack))
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

    out = m.rollback(RollbackScope.BLOCK)
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

    out = m.rollback(RollbackScope.FUNC)
    assert out.code_prefix == "before_func"
    assert [c.code_prefix for c in m.stmt_checkpoints] == ["before_func"]
    assert m.group_stack == []


def test_rollback_func_truncates_to_block_start() -> None:
    m = RollbackManager()

    _commit(m, "before_func", ())
    _commit(m, "in_func_s1", (Granularity.FUNC,))
    _commit(m, "in_func_s2", (Granularity.FUNC, Granularity.BLOCK))

    out = m.rollback(RollbackScope.BLOCK)
    assert out.code_prefix == "in_func_s1"
    assert [c.code_prefix for c in m.stmt_checkpoints] == ["before_func", "in_func_s1"]
    assert [(f.kind, f.start_stmt) for f in m.group_stack] == [(Granularity.FUNC, 1)]
