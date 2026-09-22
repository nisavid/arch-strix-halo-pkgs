from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from . import ExecutionPlan, required_model_binding


LIVE_SMOKE_MODES = {"text", "provenance", "lifecycle", "pins", "budget", "displacement"}
ISOLATED_LEMOND_MODES = {"lifecycle", "pins", "budget", "displacement"}
GGUF_BINDING_MODES = {"pins", "budget", "displacement"}


def _live_smoke_plan(
    given: dict[str, Any],
    *,
    mode: str,
    argv: list[str],
    repo_root: Path,
    scenario_run_root: Path,
    model_bindings: dict[str, str],
) -> ExecutionPlan:
    if mode not in LIVE_SMOKE_MODES:
        raise ValueError(f"UNSUPPORTED_LEMONADE_LIVE_MODE: {mode}")
    command = [sys.executable, str(repo_root / "tools/lemonade_live_smoke.py"), mode]
    if "lemonade_model" in given:
        command += ["--model", str(given["lemonade_model"])]
    if mode in GGUF_BINDING_MODES:
        command += ["--gguf", required_model_binding(given, model_bindings)]
    server_log = None
    if mode in ISOLATED_LEMOND_MODES:
        server_log = scenario_run_root / "server.log"
        command += ["--server-log", str(server_log)]
    return ExecutionPlan(command=[*command, *argv], server_log_path=server_log)


def build_execution_plan(
    definition: dict[str, Any],
    *,
    repo_root: Path,
    scenario_run_root: Path,
    model_bindings: dict[str, str],
) -> ExecutionPlan:
    given = definition["given"]
    when = definition.get("when") or {}
    argv = [str(value) for value in when.get("argv", [])]
    tool = given.get("tool")
    if tool is not None:
        tool_name = str(tool)
        if tool_name.startswith("lemonade_pooling_smoke."):
            mode = tool_name.rsplit(".", 1)[1]
            if mode not in {"embeddings", "rerank"}:
                raise ValueError(f"UNSUPPORTED_LEMONADE_POOLING_MODE: {mode}")
            return ExecutionPlan(
                command=[
                    sys.executable,
                    str(repo_root / "tools/lemonade_pooling_smoke.py"),
                    str(given["model"]),
                    "--mode",
                    mode,
                    *argv,
                ]
            )
        if tool_name == "lemonade_zerank_smoke.selected-logit":
            return ExecutionPlan(
                command=[
                    sys.executable,
                    str(repo_root / "tools/lemonade_zerank_smoke.py"),
                    str(given["model"]),
                    "--server-log",
                    str(scenario_run_root / "server.log"),
                    *argv,
                ],
                server_log_path=scenario_run_root / "server.log",
            )
        if tool_name.startswith("lemonade_live_smoke."):
            return _live_smoke_plan(
                given,
                mode=tool_name.rsplit(".", 1)[1],
                argv=argv,
                repo_root=repo_root,
                scenario_run_root=scenario_run_root,
                model_bindings=model_bindings,
            )
        raise ValueError(f"UNSUPPORTED_LEMONADE_TOOL: {tool_name}")

    entrypoint = str(definition["given"]["entrypoint"])
    return ExecutionPlan(command=[entrypoint, *argv])
