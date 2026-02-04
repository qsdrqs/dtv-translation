from __future__ import annotations

from typing import Protocol

from core.llm_output import FenceState
from core.types import (
    Artifact,
    ControllerState,
    GenerateContext,
    GenerateResult,
    Granularity,
    OracleContext,
    OracleOutput,
    RenderResult,
    RollbackScope,
)


class Generator(Protocol):
    def generate_step(self, context: GenerateContext) -> GenerateResult:
        ...

    def reset_output_extractor(self) -> None:
        ...

    def get_output_extractor_state(self) -> FenceState:
        ...


class Renderer(Protocol):
    def try_render(self, prefix: str) -> RenderResult:
        ...


class Oracle(Protocol):
    """Deterministic verifier; raise on tool/infra failures instead of returning a verdict."""
    name: str
    required_granularity: Granularity
    rollback_scope: RollbackScope

    def run(self, state: ControllerState, artifact: Artifact, context: OracleContext) -> OracleOutput:
        ...


class OracleRunner(Protocol):
    def run(
        self,
        oracles: list[Oracle],
        state: ControllerState,
        artifact: Artifact,
        context: OracleContext,
    ) -> list[OracleOutput]:
        ...
