from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from . import ExecutionPlan


def build_execution_plan(
    definition: dict[str, Any],
    *,
    repo_root: Path,
    scenario_run_root: Path,
    model_bindings: dict[str, str],
) -> ExecutionPlan:
    del scenario_run_root
    del model_bindings

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
        raise ValueError(f"UNSUPPORTED_LEMONADE_TOOL: {tool_name}")

    entrypoint = str(definition["given"]["entrypoint"])
    return ExecutionPlan(command=[entrypoint, *argv])
