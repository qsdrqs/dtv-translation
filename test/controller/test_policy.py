from __future__ import annotations

from dataclasses import dataclass

from controller.loop import Policy
from core.budget import Budget
from core.types import Artifact, ControllerState, Granularity, OracleOutput


@dataclass
class _FakeOracle:
    name: str
    required_granularity: Granularity

    def run(self, state: ControllerState, artifact: Artifact) -> OracleOutput:  # pragma: no cover
        raise NotImplementedError


def test_policy_select_oracles_respects_granularity_order() -> None:
    artifact = Artifact(code="", granularity=Granularity.BLOCK)
    budget = Budget(gen_tokens_budget=1)
    stmt_oracle = _FakeOracle(name="stmt", required_granularity=Granularity.STMT)
    block_oracle = _FakeOracle(name="block", required_granularity=Granularity.BLOCK)
    func_oracle = _FakeOracle(name="func", required_granularity=Granularity.FUNC)

    selected = Policy().select_oracles(
        artifact=artifact,
        budget=budget,
        available=[stmt_oracle, block_oracle, func_oracle],
    )
    assert [oracle.name for oracle in selected] == ["stmt", "block"]
