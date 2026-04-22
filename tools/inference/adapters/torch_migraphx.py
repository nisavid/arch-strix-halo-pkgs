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
    del scenario_run_root, model_bindings

    given = definition["given"]
    when = definition.get("when") or {}
    argv = [str(value) for value in when.get("argv", [])]
    tool = str(given["tool"])

    if tool.startswith("torch_migraphx_smoke."):
        mode = tool.rsplit(".", 1)[1]
        if mode not in {
            "pt2e-quantizer-import",
            "dynamo-resnet-tiny",
            "pt2e-resnet-tiny",
        }:
            raise ValueError(f"UNSUPPORTED_TORCH_MIGRAPHX_SMOKE_MODE: {mode}")
        return ExecutionPlan(
            command=[
                sys.executable,
                str(repo_root / "tools/torch_migraphx_smoke.py"),
                "--mode",
                mode,
                *argv,
            ]
        )

    raise ValueError(f"UNSUPPORTED_TORCH_MIGRAPHX_TOOL: {tool}")
