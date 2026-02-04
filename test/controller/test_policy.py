from __future__ import annotations

from dataclasses import dataclass

from controller.loop import _effective_boundary_granularity, select_oracles_by_granularity
from core.budget import Budget
from core.types import Artifact, ControllerState, Granularity, GroupStackFrame, OracleContext, OracleOutput


@dataclass
class _FakeOracle:
    name: str
    required_granularity: Granularity

    def run(
        self,
        state: ControllerState,
        artifact: Artifact,
        context: OracleContext,
    ) -> OracleOutput:  # pragma: no cover
        _ = state
        _ = artifact
        _ = context
        raise NotImplementedError


def test_select_oracles_respects_granularity_order() -> None:
    artifact = Artifact(code="")
    budget = Budget(gen_tokens_budget=1)
    stmt_oracle = _FakeOracle(name="stmt", required_granularity=Granularity.STMT)
    block_oracle = _FakeOracle(name="block", required_granularity=Granularity.BLOCK)
    func_oracle = _FakeOracle(name="func", required_granularity=Granularity.FUNC)

    selected = select_oracles_by_granularity(
        artifact=artifact,
        budget=budget,
        available=[stmt_oracle, block_oracle, func_oracle],
        selection_granularity=Granularity.BLOCK,
    )
    assert [oracle.name for oracle in selected] == ["stmt", "block"]


def test_select_oracles_respects_min_granularity() -> None:
    artifact = Artifact(code="")
    budget = Budget(gen_tokens_budget=1)
    stmt_oracle = _FakeOracle(name="stmt", required_granularity=Granularity.STMT)
    block_oracle = _FakeOracle(name="block", required_granularity=Granularity.BLOCK)
    func_oracle = _FakeOracle(name="func", required_granularity=Granularity.FUNC)

    selected = select_oracles_by_granularity(
        artifact=artifact,
        budget=budget,
        available=[stmt_oracle, block_oracle, func_oracle],
        selection_granularity=Granularity.FUNC,
        min_granularity=Granularity.BLOCK,
    )
    assert [oracle.name for oracle in selected] == ["block", "func"]


def test_effective_boundary_empty_closed_stack_is_stmt() -> None:
    assert _effective_boundary_granularity(Granularity.STMT, ()) == Granularity.STMT


def test_effective_boundary_block_closed_is_block() -> None:
    closed_stack = (GroupStackFrame(kind=Granularity.BLOCK),)
    assert _effective_boundary_granularity(Granularity.STMT, closed_stack) == Granularity.BLOCK


def test_effective_boundary_prefers_func_over_block() -> None:
    closed_stack = (
        GroupStackFrame(kind=Granularity.BLOCK),
        GroupStackFrame(kind=Granularity.FUNC),
    )
    assert _effective_boundary_granularity(Granularity.STMT, closed_stack) == Granularity.FUNC
