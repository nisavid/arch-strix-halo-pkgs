from __future__ import annotations

import json
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


def _resolved_draft_model(
    definition: dict[str, Any],
    *,
    model_bindings: dict[str, str],
) -> str | None:
    draft_model = definition["given"].get("draft_model")
    if draft_model is None:
        return None
    draft_model_id = str(draft_model)
    return model_bindings.get(draft_model_id, draft_model_id)


def _draft_model_argv(
    definition: dict[str, Any],
    *,
    model_bindings: dict[str, str],
) -> list[str]:
    draft_model = _resolved_draft_model(definition, model_bindings=model_bindings)
    if draft_model is None:
        return []
    return ["--draft-model", draft_model]


def _speculative_config_argv(
    definition: dict[str, Any],
    *,
    model_bindings: dict[str, str],
) -> list[str]:
    given = definition["given"]
    when = definition.get("when") or {}
    raw_config = given.get("speculative_config") or when.get("speculative_config")
    if raw_config is None:
        return []
    config = dict(raw_config)
    speculative_model = config.get("model")
    if speculative_model is not None:
        speculative_model_id = str(speculative_model)
        config["model"] = model_bindings.get(speculative_model_id, speculative_model_id)
    return [
        "--speculative-config-json",
        json.dumps(config, separators=(",", ":"), sort_keys=True),
    ]


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
    draft_model_argv = _draft_model_argv(
        definition,
        model_bindings=model_bindings,
    )
    speculative_config_argv = _speculative_config_argv(
        definition,
        model_bindings=model_bindings,
    )
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
    if tool.startswith("vllm_pooling_smoke."):
        mode = tool.rsplit(".", 1)[1]
        return ExecutionPlan(
            command=[
                sys.executable,
                str(repo_root / "tools/vllm_pooling_smoke.py"),
                model,
                "--mode",
                mode,
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
                *draft_model_argv,
                *speculative_config_argv,
                *extra_argv,
            ],
            server_log_path=server_log_path,
            env=env,
        )
    if tool.startswith("qwen_server_smoke."):
        mode = tool.rsplit(".", 1)[1]
        server_log_path = scenario_run_root / "server.log"
        return ExecutionPlan(
            command=[
                sys.executable,
                str(repo_root / "tools/qwen_server_smoke.py"),
                model,
                "--mode",
                mode,
                "--server-log",
                str(server_log_path),
                *draft_model_argv,
                *speculative_config_argv,
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
