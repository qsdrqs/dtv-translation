from __future__ import annotations

from core.llm_output import AssistantContent
from core.types import Granularity, RollbackScope
from rollback.manager import RollbackManager


def test_rollback_stmt_returns_last_checkpoint_without_deleting() -> None:
    m = RollbackManager()
    m.add_stmt_checkpoint("p1", AssistantContent.empty())
    out = m.rollback(RollbackScope.STMT)
    assert out.code_prefix == "p1"
    assert [c.code_prefix for c in m.stmt_checkpoints] == ["p1"]


def test_rollback_program_clears_checkpoints_and_groups() -> None:
    m = RollbackManager()
    m.add_stmt_checkpoint("p1", AssistantContent.empty())
    m.open_group(Granularity.BLOCK)
    m.add_stmt_checkpoint("p2", AssistantContent.empty())
    out = m.rollback(RollbackScope.PROGRAM)
    assert out.code_prefix == ""
    assert m.stmt_checkpoints == []
    assert m.group_stack == []


def test_rollback_block_truncates_to_block_start_and_drops_frame() -> None:
    m = RollbackManager()
    m.add_stmt_checkpoint("pre", AssistantContent.empty())
    m.open_group(Granularity.BLOCK)
    m.add_stmt_checkpoint("pre+a", AssistantContent.empty())
    m.add_stmt_checkpoint("pre+b", AssistantContent.empty())

    out = m.rollback(RollbackScope.BLOCK)
    assert out.code_prefix == "pre"
    assert [c.code_prefix for c in m.stmt_checkpoints] == ["pre"]
    assert m.group_stack == []
