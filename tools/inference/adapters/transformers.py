from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from . import ExecutionPlan


def _resolved_model(model: str, model_bindings: dict[str, str]) -> str:
    return model_bindings.get(model, model)


def build_execution_plan(
    definition: dict[str, Any],
    *,
    repo_root: Path,
    scenario_run_root: Path,
    model_bindings: dict[str, str],
) -> ExecutionPlan:
    del scenario_run_root

    given = definition["given"]
    model = _resolved_model(str(given["model"]), model_bindings)
    when = definition.get("when") or {}
    argv = [str(value) for value in when.get("argv", [])]
    tool = str(given["tool"])

    if tool.startswith("zeroentropy_pooling_smoke."):
        mode = tool.rsplit(".", 1)[1]
        if mode not in {"embeddings", "rerank"}:
            raise ValueError(f"UNSUPPORTED_ZEROENTROPY_POOLING_MODE: {mode}")
        return ExecutionPlan(
            command=[
                sys.executable,
                str(repo_root / "tools/zeroentropy_pooling_smoke.py"),
                model,
                "--mode",
                mode,
                *argv,
            ]
        )

    raise ValueError(f"UNSUPPORTED_TRANSFORMERS_TOOL: {tool}")
