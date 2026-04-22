from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..scenario_loader import Scenario


@dataclass(frozen=True)
class ExecutionPlan:
    command: list[str]
    server_log_path: Path | None = None
    env: dict[str, str] | None = None


def _definition_for(scenario: Scenario | dict[str, Any]) -> dict[str, Any]:
    if isinstance(scenario, Scenario):
        return scenario.definition
    return scenario


def build_execution_plan(
    scenario: Scenario | dict[str, Any],
    *,
    repo_root: Path,
    scenario_run_root: Path,
    model_bindings: dict[str, str],
) -> ExecutionPlan:
    definition = _definition_for(scenario)
    engine = str(definition["given"]["engine"])

    if engine == "vllm":
        from .vllm import build_execution_plan as build_vllm_execution_plan

        return build_vllm_execution_plan(
            definition,
            repo_root=repo_root,
            scenario_run_root=scenario_run_root,
            model_bindings=model_bindings,
        )
    if engine == "llama.cpp":
        from .llamacpp import build_execution_plan as build_llamacpp_execution_plan

        return build_llamacpp_execution_plan(
            definition,
            repo_root=repo_root,
            scenario_run_root=scenario_run_root,
            model_bindings=model_bindings,
        )
    if engine == "lemonade":
        from .lemonade import build_execution_plan as build_lemonade_execution_plan

        return build_lemonade_execution_plan(
            definition,
            repo_root=repo_root,
            scenario_run_root=scenario_run_root,
            model_bindings=model_bindings,
        )
    if engine == "transformers":
        from .transformers import build_execution_plan as build_transformers_execution_plan

        return build_transformers_execution_plan(
            definition,
            repo_root=repo_root,
            scenario_run_root=scenario_run_root,
            model_bindings=model_bindings,
        )
    if engine == "torch-migraphx":
        from .torch_migraphx import (
            build_execution_plan as build_torch_migraphx_execution_plan,
        )

        return build_torch_migraphx_execution_plan(
            definition,
            repo_root=repo_root,
            scenario_run_root=scenario_run_root,
            model_bindings=model_bindings,
        )
    raise ValueError(f"UNSUPPORTED_ENGINE: {engine}")
