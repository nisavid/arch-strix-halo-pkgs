from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from . import ExecutionPlan


def _env(definition: dict[str, Any]) -> dict[str, str] | None:
    when = definition.get("when") or {}
    raw_env = when.get("env") or {}
    if not raw_env:
        return None
    return {str(key): str(value) for key, value in raw_env.items()}


def build_execution_plan(
    definition: dict[str, Any],
    *,
    repo_root: Path,
    scenario_run_root: Path,
    model_bindings: dict[str, str],
) -> ExecutionPlan:
    del scenario_run_root, model_bindings

    given = definition["given"]
    when = definition.get("when") or {}
    argv = [str(value) for value in when.get("argv", [])]
    tool = str(given["tool"])
    env = _env(definition)

    if tool == "flash_attn_smoke.backend-import":
        return ExecutionPlan(
            command=[
                sys.executable,
                str(repo_root / "tools/flash_attn_smoke.py"),
                "--mode",
                "backend-import",
                *argv,
            ],
            env=env,
        )
    if tool == "flash_attn_smoke.qkvpacked-tiny":
        return ExecutionPlan(
            command=[
                sys.executable,
                str(repo_root / "tools/flash_attn_smoke.py"),
                "--mode",
                "qkvpacked-tiny",
                *argv,
            ],
            env=env,
        )
    if tool == "flash_attn_smoke.ck-backend-import":
        return ExecutionPlan(
            command=[
                sys.executable,
                str(repo_root / "tools/flash_attn_smoke.py"),
                "--mode",
                "ck-backend-import",
                *argv,
            ],
            env=env,
        )
    if tool == "flash_attn_smoke.ck-qkvpacked-tiny":
        return ExecutionPlan(
            command=[
                sys.executable,
                str(repo_root / "tools/flash_attn_smoke.py"),
                "--mode",
                "ck-qkvpacked-tiny",
                *argv,
            ],
            env=env,
        )
    if tool.startswith("flash_attn_smoke."):
        mode = tool.rsplit(".", 1)[1]
        raise ValueError(f"UNSUPPORTED_FLASH_ATTN_SMOKE_MODE: {mode}")
    raise ValueError(f"UNSUPPORTED_FLASH_ATTN_TOOL: {tool}")
