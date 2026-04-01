from __future__ import annotations

from dataclasses import dataclass

from controller.loop import _effective_boundary_granularity, select_oracles_by_granularity
from controller.policy import _select_fail_scope, DefaultPolicyConfig
from core.budget import Budget
from core.types import Artifact, ControllerState, Granularity, GroupStackFrame, OracleContext, OracleOutput, Verdict


@dataclass
class _FakeOracle:
    name: str
    required_granularity: Granularity
    rollback_scope: Granularity = Granularity.STMT

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


def test_select_fail_scope_single_oracle_rollback_scope() -> None:
    config = DefaultPolicyConfig()
    outputs = (
        OracleOutput(
            oracle_name="func_oracle",
            verdict=Verdict.FAIL,
            rollback_scope=Granularity.FUNC,
        ),
    )
    assert _select_fail_scope(config, outputs) == Granularity.FUNC


def test_select_fail_scope_max_rollback_scope() -> None:
    config = DefaultPolicyConfig()
    outputs = (
        OracleOutput(
            oracle_name="stmt_oracle",
            verdict=Verdict.FAIL,
            rollback_scope=Granularity.STMT,
        ),
        OracleOutput(
            oracle_name="func_oracle",
            verdict=Verdict.FAIL,
            rollback_scope=Granularity.FUNC,
        ),
    )
    assert _select_fail_scope(config, outputs) == Granularity.FUNC


def test_select_fail_scope_fallback_default() -> None:
    config = DefaultPolicyConfig(default_fail_scope=Granularity.STMT)
    outputs = (
        OracleOutput(
            oracle_name="oracle_no_scope",
            verdict=Verdict.FAIL,
        ),
    )
    assert _select_fail_scope(config, outputs) == Granularity.STMT
