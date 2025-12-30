from __future__ import annotations

from typing import Protocol

from core.types import (
    Artifact,
    ControllerState,
    GenerateContext,
    GenerateResult,
    Granularity,
    OracleOutput,
    RenderResult,
)


class Generator(Protocol):
    def generate_step(self, context: GenerateContext) -> GenerateResult:
        ...


class Renderer(Protocol):
    def try_render(self, prefix: str, granularity: Granularity) -> RenderResult:
        ...


class Oracle(Protocol):
    """Deterministic verifier; raise on tool/infra failures instead of returning a verdict."""
    name: str
    required_granularity: Granularity

    def run(self, state: ControllerState, artifact: Artifact) -> OracleOutput:
        ...


class OracleRunner(Protocol):
    def run(self, oracles: list[Oracle], state: ControllerState, artifact: Artifact) -> list[OracleOutput]:
        ...
