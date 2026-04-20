from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from . import ExecutionPlan


def _resolved_model(
    definition: dict[str, Any],
    *,
    model_bindings: dict[str, str],
) -> str:
    model = str(definition["given"]["model"])
    return model_bindings.get(model, model)


def _extra_argv(definition: dict[str, Any]) -> list[str]:
    when = definition.get("when") or {}
    return [str(value) for value in when.get("argv", [])]


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
    tool = str(definition["given"]["tool"])
    model = _resolved_model(definition, model_bindings=model_bindings)
    extra_argv = _extra_argv(definition)
    env = _env(definition)

    if tool == "gemma4_text_smoke":
        return ExecutionPlan(
            command=[
                sys.executable,
                str(repo_root / "tools/gemma4_text_smoke.py"),
                model,
                *extra_argv,
            ],
            env=env,
        )
    if tool == "qwen_text_smoke":
        return ExecutionPlan(
            command=[
                sys.executable,
                str(repo_root / "tools/qwen_text_smoke.py"),
                model,
                *extra_argv,
            ],
            env=env,
        )
    if tool.startswith("gemma4_server_smoke."):
        mode = tool.rsplit(".", 1)[1]
        server_log_path = scenario_run_root / "server.log"
        return ExecutionPlan(
            command=[
                sys.executable,
                str(repo_root / "tools/gemma4_server_smoke.py"),
                model,
                "--mode",
                mode,
                "--server-log",
                str(server_log_path),
                *extra_argv,
            ],
            server_log_path=server_log_path,
            env=env,
        )
    if tool == "torchao_vllm_smoke":
        return ExecutionPlan(
            command=[
                sys.executable,
                str(repo_root / "tools/torchao_vllm_smoke.py"),
                *extra_argv,
            ],
            env=env,
        )
    if tool == "torchao_vllm_smoke.real-model":
        return ExecutionPlan(
            command=[
                sys.executable,
                str(repo_root / "tools/torchao_vllm_smoke.py"),
                "--source-model",
                model,
                "--work-dir",
                str(scenario_run_root / "torchao"),
                *extra_argv,
            ],
            env=env,
        )
    raise ValueError(f"UNSUPPORTED_VLLM_TOOL: {tool}")
