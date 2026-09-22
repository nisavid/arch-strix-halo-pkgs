from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from . import ExecutionPlan, required_model_binding


def build_execution_plan(
    definition: dict[str, Any],
    *,
    repo_root: Path,
    scenario_run_root: Path,
    model_bindings: dict[str, str],
) -> ExecutionPlan:
    given = definition["given"]
    entrypoint = str(given["entrypoint"])
    when = definition.get("when") or {}
    argv = [str(value) for value in when.get("argv", [])]
    tool = given.get("tool")
    if tool is not None:
        if str(tool) != "llamacpp_server_smoke.completion":
            raise ValueError(f"UNSUPPORTED_LLAMACPP_TOOL: {tool}")
        server_log = scenario_run_root / "server.log"
        return ExecutionPlan(
            command=[
                sys.executable,
                str(repo_root / "tools/llamacpp_server_smoke.py"),
                required_model_binding(given, model_bindings),
                "--server",
                entrypoint,
                "--server-log",
                str(server_log),
                *argv,
            ],
            server_log_path=server_log,
        )

    return ExecutionPlan(command=[entrypoint, *argv])
