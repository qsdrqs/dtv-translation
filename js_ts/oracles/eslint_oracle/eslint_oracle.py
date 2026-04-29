from __future__ import annotations

from core.interfaces import Oracle
from core.types import (
    Artifact,
    ControllerState,
    Granularity,
    OracleContext,
    OracleOutput,
    Verdict,
)
from js_ts.oracles.diagnostic_render import render_diagnostic
from js_ts.oracles.eslint_oracle.eslint_driver import EslintDriver
from js_ts.oracles.eslint_oracle.eslint_parser import (
    filter_post_prefix_diagnostics,
    has_errors,
    parse_eslint_messages,
)


class EslintOracle(Oracle):
    name = "eslint"
    required_granularity = Granularity.STMT
    rollback_scope = Granularity.STMT

    def __init__(self, timeout_s: float = 10.0) -> None:
        self.timeout_s = timeout_s
        self.driver = EslintDriver()

    def run(self, state: ControllerState, artifact: Artifact, context: OracleContext) -> OracleOutput:
        del context
        result = self.driver.check(artifact.code, timeout_s=self.timeout_s)
        diagnostics = parse_eslint_messages(
            result.messages,
            source_code=artifact.code,
            ast_tree=artifact.ast_tree,
        )
        diagnostics = filter_post_prefix_diagnostics(diagnostics, state.prefix)
        rendered_diagnostics = tuple(
            render_diagnostic(d) for d in diagnostics
        )
        verdict = Verdict.FAIL if has_errors(diagnostics) else Verdict.PASS
        return OracleOutput(
            oracle_name=self.name,
            verdict=verdict,
            diagnostics=diagnostics,
            rendered_diagnostics=rendered_diagnostics,
            realized_cost=1,
        )
