from __future__ import annotations

from core.types import Granularity, RollbackScope
from rollback.manager import RollbackManager


def test_rollback_stmt_returns_last_checkpoint_without_deleting() -> None:
    m = RollbackManager()
    m.add_stmt_checkpoint("p1")
    out = m.rollback(RollbackScope.STMT)
    assert out == "p1"
    assert [c.prefix for c in m.stmt_checkpoints] == ["p1"]


def test_rollback_program_clears_checkpoints_and_groups() -> None:
    m = RollbackManager()
    m.add_stmt_checkpoint("p1")
    m.open_group(Granularity.BLOCK)
    m.add_stmt_checkpoint("p2")
    out = m.rollback(RollbackScope.PROGRAM)
    assert out == ""
    assert m.stmt_checkpoints == []
    assert m.group_stack == []


def test_rollback_block_truncates_to_block_start_and_drops_frame() -> None:
    m = RollbackManager()
    m.add_stmt_checkpoint("pre")
    m.open_group(Granularity.BLOCK)
    m.add_stmt_checkpoint("pre+a")
    m.add_stmt_checkpoint("pre+b")

    out = m.rollback(RollbackScope.BLOCK)
    assert out == "pre"
    assert [c.prefix for c in m.stmt_checkpoints] == ["pre"]
    assert m.group_stack == []
