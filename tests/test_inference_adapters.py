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


def test_vllm_adapter_resolves_speculative_config_model_binding_for_qwen_server_smoke(
    tmp_path: Path,
):
    plan = build_execution_plan(
        scenario(
            {
                "id": "vllm.speculative.eagle3.llama3_1_8b.server.basic",
                "given": {
                    "engine": "vllm",
                    "model": "meta-llama/Llama-3.1-8B-Instruct",
                    "tool": "qwen_server_smoke.benchmark-lite",
                    "speculative_config": {
                        "method": "eagle3",
                        "model": "RedHatAI/Llama-3.1-8B-Instruct-speculator.eagle3",
                        "draft_tensor_parallel_size": 2,
                        "num_speculative_tokens": 2,
                    },
                },
            }
        ),
        repo_root=REPO_ROOT,
        scenario_run_root=tmp_path,
        model_bindings={
            "meta-llama/Llama-3.1-8B-Instruct": "/models/llama31",
            "RedHatAI/Llama-3.1-8B-Instruct-speculator.eagle3": (
                "/models/eagle3"
            ),
        },
    )

    assert plan.command == [
        sys.executable,
        str(REPO_ROOT / "tools/qwen_server_smoke.py"),
        "/models/llama31",
        "--mode",
        "benchmark-lite",
        "--server-log",
        str(tmp_path / "server.log"),
        "--speculative-config-json",
        (
            '{"draft_tensor_parallel_size":2,"method":"eagle3",'
            '"model":"/models/eagle3","num_speculative_tokens":2}'
        ),
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


def test_flash_attn_adapter_builds_smoke_command(tmp_path: Path):
    plan = build_execution_plan(
        scenario(
            {
                "id": "flash-attn.qkvpacked-tiny",
                "given": {
                    "engine": "flash-attn",
                    "tool": "flash_attn_smoke.qkvpacked-tiny",
                },
                "when": {"argv": ["--max-length", "128"]},
            }
        ),
        repo_root=REPO_ROOT,
        scenario_run_root=tmp_path,
        model_bindings={},
    )

    assert plan.command == [
        sys.executable,
        str(REPO_ROOT / "tools/flash_attn_smoke.py"),
        "--mode",
        "qkvpacked-tiny",
        "--max-length",
        "128",
    ]
    assert plan.server_log_path is None
    assert plan.env is None


def test_flash_attn_adapter_carries_scenario_environment(tmp_path: Path):
    plan = build_execution_plan(
        scenario(
            {
                "id": "flash-attn.backend-import",
                "given": {
                    "engine": "flash-attn",
                    "tool": "flash_attn_smoke.backend-import",
                },
                "when": {
                    "env": {
                        "FLASH_ATTN_MODE": "1",
                        123: 456,
                    }
                },
            }
        ),
        repo_root=REPO_ROOT,
        scenario_run_root=tmp_path,
        model_bindings={},
    )

    assert plan.env == {"FLASH_ATTN_MODE": "1", "123": "456"}


def test_flash_attn_adapter_rejects_unsupported_mode_and_tool(tmp_path: Path):
    with pytest.raises(
        ValueError,
        match=r"^UNSUPPORTED_FLASH_ATTN_SMOKE_MODE: invalid$",
    ):
        build_execution_plan(
            scenario(
                {
                    "id": "flash-attn.invalid",
                    "given": {
                        "engine": "flash-attn",
                        "tool": "flash_attn_smoke.invalid",
                    },
                }
            ),
            repo_root=REPO_ROOT,
            scenario_run_root=tmp_path,
            model_bindings={},
        )

    with pytest.raises(
        ValueError,
        match=r"^UNSUPPORTED_FLASH_ATTN_TOOL: invalid_tool$",
    ):
        build_execution_plan(
            scenario(
                {
                    "id": "flash-attn.invalid-tool",
                    "given": {
                        "engine": "flash-attn",
                        "tool": "invalid_tool",
                    },
                }
            ),
            repo_root=REPO_ROOT,
            scenario_run_root=tmp_path,
            model_bindings={},
        )


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


def test_vllm_adapter_builds_flash_attn_vit_wrapper_command(tmp_path: Path):
    plan = build_execution_plan(
        scenario(
            {
                "id": "vllm.flash-attn.triton-amd.vit-wrapper",
                "given": {
                    "engine": "vllm",
                    "model": "builtin",
                    "tool": "vllm_flash_attn_smoke.vit-wrapper",
                },
                "when": {
                    "argv": ["--seqlen", "16"],
                    "env": {"FLASH_ATTENTION_TRITON_AMD_ENABLE": "TRUE"},
                },
            }
        ),
        repo_root=REPO_ROOT,
        scenario_run_root=tmp_path,
        model_bindings={},
    )

    assert plan.command == [
        sys.executable,
        str(REPO_ROOT / "tools/vllm_flash_attn_smoke.py"),
        "--mode",
        "vit-wrapper",
        "--seqlen",
        "16",
    ]
    assert plan.env == {"FLASH_ATTENTION_TRITON_AMD_ENABLE": "TRUE"}
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


def test_lemonade_adapter_builds_pooling_endpoint_smoke_command(tmp_path: Path):
    plan = build_execution_plan(
        scenario(
            {
                "id": "lemonade.pooling.bge-reranker-v2-m3.rerank",
                "given": {
                    "engine": "lemonade",
                    "model": "user.bge-reranker-v2-m3-Q8_0-GGUF",
                    "tool": "lemonade_pooling_smoke.rerank",
                },
                "when": {
                    "argv": [
                        "--base-url",
                        "http://127.0.0.1:13305/api/v1",
                    ]
                },
            }
        ),
        repo_root=REPO_ROOT,
        scenario_run_root=tmp_path,
        model_bindings={},
    )

    assert plan.command == [
        sys.executable,
        str(REPO_ROOT / "tools/lemonade_pooling_smoke.py"),
        "user.bge-reranker-v2-m3-Q8_0-GGUF",
        "--mode",
        "rerank",
        "--base-url",
        "http://127.0.0.1:13305/api/v1",
    ]
    assert plan.server_log_path is None


def test_transformers_adapter_builds_zeroentropy_pooling_smoke_command(tmp_path: Path):
    plan = build_execution_plan(
        scenario(
            {
                "id": "transformers.zeroentropy.zembed-1.embeddings",
                "given": {
                    "engine": "transformers",
                    "model": "zeroentropy/zembed-1",
                    "tool": "zeroentropy_pooling_smoke.embeddings",
                },
                "when": {
                    "argv": [
                        "--max-length",
                        "512",
                    ]
                },
            }
        ),
        repo_root=REPO_ROOT,
        scenario_run_root=tmp_path,
        model_bindings={"zeroentropy/zembed-1": "/models/zembed-1"},
    )

    assert plan.command == [
        sys.executable,
        str(REPO_ROOT / "tools/zeroentropy_pooling_smoke.py"),
        "/models/zembed-1",
        "--mode",
        "embeddings",
        "--max-length",
        "512",
    ]
    assert plan.server_log_path is None


def test_torch_migraphx_adapter_builds_smoke_command(tmp_path: Path):
    plan = build_execution_plan(
        scenario(
            {
                "id": "torch-migraphx.resnet-tiny.dynamo",
                "given": {
                    "engine": "torch-migraphx",
                    "model": "resnet-tiny",
                    "tool": "torch_migraphx_smoke.dynamo-resnet-tiny",
                },
                "when": {"argv": ["--iterations", "5"]},
            }
        ),
        repo_root=REPO_ROOT,
        scenario_run_root=tmp_path,
        model_bindings={},
    )

    assert plan.command == [
        sys.executable,
        str(REPO_ROOT / "tools/torch_migraphx_smoke.py"),
        "--mode",
        "dynamo-resnet-tiny",
        "--iterations",
        "5",
    ]
    assert plan.server_log_path is None
