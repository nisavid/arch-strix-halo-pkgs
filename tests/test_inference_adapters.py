from __future__ import annotations

from pathlib import Path
import sys
import pytest


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


def test_vllm_adapter_assigns_server_log_for_qwen_server_smoke(tmp_path: Path):
    plan = build_execution_plan(
        scenario(
            {
                "id": "vllm.qwen3_6.35b-a3b.server.reasoning",
                "given": {
                    "engine": "vllm",
                    "model": "Qwen/Qwen3.6-35B-A3B",
                    "tool": "qwen_server_smoke.reasoning",
                },
                "when": {"env": {"VLLM_ROCM_USE_AITER_MOE": "0"}},
            }
        ),
        repo_root=REPO_ROOT,
        scenario_run_root=tmp_path,
        model_bindings={"Qwen/Qwen3.6-35B-A3B": "/models/qwen"},
    )

    assert plan.command[:3] == [
        sys.executable,
        str(REPO_ROOT / "tools/qwen_server_smoke.py"),
        "/models/qwen",
    ]
    assert "--mode" in plan.command
    assert plan.command[plan.command.index("--mode") + 1] == "reasoning"
    assert "--server-log" in plan.command
    assert plan.command[plan.command.index("--server-log") + 1] == str(
        tmp_path / "server.log"
    )
    assert plan.server_log_path == tmp_path / "server.log"
    assert plan.env == {"VLLM_ROCM_USE_AITER_MOE": "0"}


def test_vllm_adapter_resolves_draft_model_binding_for_qwen_server_smoke(
    tmp_path: Path,
):
    plan = build_execution_plan(
        scenario(
            {
                "id": "vllm.qwen3_6.35b-a3b.server.draft-model",
                "given": {
                    "engine": "vllm",
                    "model": "Qwen/Qwen3.6-35B-A3B",
                    "draft_model": "Qwen/Qwen3.5-0.8B",
                    "tool": "qwen_server_smoke.reasoning",
                },
            }
        ),
        repo_root=REPO_ROOT,
        scenario_run_root=tmp_path,
        model_bindings={
            "Qwen/Qwen3.6-35B-A3B": "/models/qwen36",
            "Qwen/Qwen3.5-0.8B": "/models/qwen35",
        },
    )

    assert plan.command == [
        sys.executable,
        str(REPO_ROOT / "tools/qwen_server_smoke.py"),
        "/models/qwen36",
        "--mode",
        "reasoning",
        "--server-log",
        str(tmp_path / "server.log"),
        "--draft-model",
        "/models/qwen35",
    ]
    assert plan.server_log_path == tmp_path / "server.log"


def test_vllm_adapter_carries_scenario_environment(tmp_path: Path):
    plan = build_execution_plan(
        scenario(
            {
                "id": "vllm.gemma4.aiter-moe",
                "given": {
                    "engine": "vllm",
                    "model": "google/gemma-4-26B-A4B-it",
                    "tool": "gemma4_server_smoke.basic",
                },
                "when": {"env": {"VLLM_ROCM_USE_AITER_MOE": "1"}},
            }
        ),
        repo_root=REPO_ROOT,
        scenario_run_root=tmp_path,
        model_bindings={},
    )

    assert plan.env == {"VLLM_ROCM_USE_AITER_MOE": "1"}


def test_vllm_adapter_builds_torchao_real_model_command(tmp_path: Path):
    plan = build_execution_plan(
        scenario(
            {
                "id": "vllm.gemma4.e2b.torchao.real-model",
                "given": {
                    "engine": "vllm",
                    "model": "google/gemma-4-E2B-it",
                    "tool": "torchao_vllm_smoke.real-model",
                },
                "when": {"argv": ["--max-model-len", "128"]},
            }
        ),
        repo_root=REPO_ROOT,
        scenario_run_root=tmp_path,
        model_bindings={"google/gemma-4-E2B-it": "/models/google/gemma-4-E2B-it"},
    )

    assert plan.command == [
        sys.executable,
        str(REPO_ROOT / "tools/torchao_vllm_smoke.py"),
        "--source-model",
        "/models/google/gemma-4-E2B-it",
        "--work-dir",
        str(tmp_path / "torchao"),
        "--max-model-len",
        "128",
    ]


@pytest.mark.parametrize(
    ("scenario_id", "model", "argv"),
    [
        (
            "vllm.qwen3_5.0_8b.text.basic",
            "Qwen/Qwen3.5-0.8B",
            ["--max-model-len", "128"],
        ),
        (
            "vllm.qwen3_6.35b-a3b.text.unquantized-moe-no-aiter-control",
            "Qwen/Qwen3.6-35B-A3B",
            ["--max-num-batched-tokens", "32", "--gpu-memory-utilization", "0.9"],
        ),
    ],
)
def test_vllm_adapter_builds_qwen_text_smoke_command(
    tmp_path: Path, scenario_id: str, model: str, argv: list[str]
):
    plan = build_execution_plan(
        scenario(
            {
                "id": scenario_id,
                "given": {
                    "engine": "vllm",
                    "model": model,
                    "tool": "qwen_text_smoke",
                },
                "when": {"argv": argv},
            }
        ),
        repo_root=REPO_ROOT,
        scenario_run_root=tmp_path,
        model_bindings={model: f"/models/{model}"},
    )

    assert plan.command == [
        sys.executable,
        str(REPO_ROOT / "tools/qwen_text_smoke.py"),
        f"/models/{model}",
        *argv,
    ]
    assert plan.server_log_path is None


def test_vllm_adapter_builds_pooling_smoke_command(tmp_path: Path):
    plan = build_execution_plan(
        scenario(
            {
                "id": "vllm.pooling.multilingual-e5-small.embeddings",
                "given": {
                    "engine": "vllm",
                    "model": "intfloat/multilingual-e5-small",
                    "tool": "vllm_pooling_smoke.embeddings",
                },
                "when": {
                    "argv": [
                        "--attention-backend",
                        "FLEX_ATTENTION",
                        "--max-model-len",
                        "256",
                    ]
                },
            }
        ),
        repo_root=REPO_ROOT,
        scenario_run_root=tmp_path,
        model_bindings={"intfloat/multilingual-e5-small": "/models/e5"},
    )

    assert plan.command == [
        sys.executable,
        str(REPO_ROOT / "tools/vllm_pooling_smoke.py"),
        "/models/e5",
        "--mode",
        "embeddings",
        "--attention-backend",
        "FLEX_ATTENTION",
        "--max-model-len",
        "256",
    ]
    assert plan.server_log_path is None


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
