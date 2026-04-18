from __future__ import annotations

from pathlib import Path
from typing import Any

from . import ExecutionPlan


def build_execution_plan(
    definition: dict[str, Any],
    *,
    repo_root: Path,
    scenario_run_root: Path,
    model_bindings: dict[str, str],
) -> ExecutionPlan:
    del repo_root
    del scenario_run_root
    del model_bindings

    entrypoint = str(definition["given"]["entrypoint"])
    when = definition.get("when") or {}
    argv = [str(value) for value in when.get("argv", [])]
    return ExecutionPlan(command=[entrypoint, *argv])
