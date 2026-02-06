from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
import tomllib


def _find_file_upwards(start: Path, filename: str) -> Path | None:
    for directory in (start, *start.parents):
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    return None


@lru_cache(maxsize=1)
def pinned_rustup_toolchain() -> str | None:
    toolchain_toml = _find_file_upwards(
        Path(__file__).resolve().parent,
        "rust-toolchain.toml",
    )
    if toolchain_toml is None:
        return None

    with toolchain_toml.open("rb") as handle:
        data = tomllib.load(handle)

    toolchain = data.get("toolchain")
    if not isinstance(toolchain, dict):
        raise RuntimeError(f"invalid {toolchain_toml}: missing [toolchain]")

    channel = toolchain.get("channel")
    if not isinstance(channel, str) or not channel.strip():
        raise RuntimeError(f"invalid {toolchain_toml}: missing toolchain.channel")

    return channel.strip()


def env_with_pinned_rustup_toolchain(base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy() if base_env is None else dict(base_env)
    toolchain = pinned_rustup_toolchain()
    if toolchain is not None:
        env["RUSTUP_TOOLCHAIN"] = toolchain
    return env
