from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from inference.adapters import build_execution_plan


def scenario(definition: dict) -> dict:
    return {
        "id": definition["id"],
        "summary": definition.get("summary", definition["id"]),
        "given": definition["given"],
        "when": definition.get("when", {}),
        "then": definition.get("then", {}),
    }


def test_vllm_adapter_uses_model_bindings_for_gemma_text_smoke(tmp_path: Path):
    plan = build_execution_plan(
        scenario(
            {
                "id": "vllm.gemma4.text",
                "given": {
                    "engine": "vllm",
                    "model": "google/gemma-4-26B-A4B-it",
                    "tool": "gemma4_text_smoke",
                },
            }
        ),
        repo_root=REPO_ROOT,
        scenario_run_root=tmp_path,
        model_bindings={
            "google/gemma-4-26B-A4B-it": "/models/google/gemma-4-26B-A4B-it"
        },
    )

    assert plan.command == [
        sys.executable,
        str(REPO_ROOT / "tools/gemma4_text_smoke.py"),
        "/models/google/gemma-4-26B-A4B-it",
    ]
    assert plan.server_log_path is None


def test_vllm_adapter_assigns_server_log_for_basic_server_smoke(tmp_path: Path):
    plan = build_execution_plan(
        scenario(
            {
                "id": "vllm.gemma4.server.basic",
                "given": {
                    "engine": "vllm",
                    "model": "google/gemma-4-26B-A4B-it",
                    "tool": "gemma4_server_smoke.basic",
                },
            }
        ),
        repo_root=REPO_ROOT,
        scenario_run_root=tmp_path,
        model_bindings={},
    )

    assert plan.command[:3] == [
        sys.executable,
        str(REPO_ROOT / "tools/gemma4_server_smoke.py"),
        "google/gemma-4-26B-A4B-it",
    ]
    assert "--mode" in plan.command
    assert plan.command[plan.command.index("--mode") + 1] == "basic"
    assert "--server-log" in plan.command
    assert plan.server_log_path == tmp_path / "server.log"
    assert plan.command[plan.command.index("--server-log") + 1] == str(
        tmp_path / "server.log"
    )


def test_llamacpp_adapter_builds_generic_cli_command(tmp_path: Path):
    plan = build_execution_plan(
        scenario(
            {
                "id": "llama.cpp.hip.help",
                "given": {
                    "engine": "llama.cpp",
                    "model": "builtin",
                    "entrypoint": "llama-cli-hip-gfx1151",
                },
                "when": {"argv": ["--help"]},
            }
        ),
        repo_root=REPO_ROOT,
        scenario_run_root=tmp_path,
        model_bindings={},
    )

    assert plan.command == ["llama-cli-hip-gfx1151", "--help"]
    assert plan.server_log_path is None


def test_lemonade_adapter_builds_generic_cli_command(tmp_path: Path):
    plan = build_execution_plan(
        scenario(
            {
                "id": "lemonade.cli.help",
                "given": {
                    "engine": "lemonade",
                    "model": "builtin",
                    "entrypoint": "lemonade",
                },
                "when": {"argv": ["--help"]},
            }
        ),
        repo_root=REPO_ROOT,
        scenario_run_root=tmp_path,
        model_bindings={},
    )

    assert plan.command == ["lemonade", "--help"]
    assert plan.server_log_path is None
