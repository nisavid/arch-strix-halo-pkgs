from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from inference.scenario_loader import load_scenarios


def test_tracked_inference_scenarios_cover_vllm_llamacpp_and_lemonade():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")

    ids = {scenario.id for scenario in scenarios}
    engines = {scenario.engine for scenario in scenarios}
    tags_by_id = {scenario.id: set(scenario.tags) for scenario in scenarios}

    assert "vllm.gemma4.26b-a4b.text.basic" in ids
    assert "vllm.gemma4.26b-a4b.server.basic" in ids
    assert "vllm.gemma4.e2b.server.reasoning" in ids
    assert "vllm.gemma4.e2b.server.tool" in ids
    assert "vllm.gemma4.e2b.server.structured" in ids
    assert "vllm.gemma4.e2b.server.benchmark-lite" in ids
    assert "vllm.gemma4.e2b.server.image" in ids
    assert "vllm.gemma4.e2b.server.attn-triton" in ids
    assert "vllm.gemma4.e2b.server.attn-aiter-fa-blocked" in ids
    assert "vllm.gemma4.26b-a4b.text.compiled" in ids
    assert "vllm.gemma4.26b-a4b.server.moe-aiter" in ids
    assert "vllm.torchao.tiny.generate" in ids
    assert "vllm.gemma4.e2b.torchao.real-model" in ids
    assert "vllm.qwen3_5.0_8b.text.basic" in ids
    assert "vllm.qwen3_6.35b-a3b.text.unquantized-moe-no-aiter-control" in ids
    assert "vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-no-aiter-blocked" in ids
    assert "vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-aiter-blocked" in ids
    assert "llama.cpp.hip.help" in ids
    assert "llama.cpp.vulkan.help" in ids
    assert "lemonade.cli.help" in ids
    assert "lemonade.server.help" in ids
    assert engines == {"vllm", "llama.cpp", "lemonade"}
    assert "smoke" in tags_by_id["vllm.gemma4.26b-a4b.text.basic"]
    assert "exploratory" in tags_by_id["vllm.gemma4.e2b.server.image"]
    assert "kernel-probe" in tags_by_id["vllm.gemma4.e2b.server.attn-triton"]
    assert "exploratory" in tags_by_id["vllm.gemma4.e2b.server.attn-triton"]
    assert "kernel-probe" in tags_by_id[
        "vllm.gemma4.e2b.server.attn-aiter-fa-blocked"
    ]
    assert "flash-attention" in tags_by_id[
        "vllm.gemma4.e2b.server.attn-aiter-fa-blocked"
    ]
    assert "blocked" in tags_by_id[
        "vllm.gemma4.e2b.server.attn-aiter-fa-blocked"
    ]
    assert "kernel-probe" in tags_by_id["vllm.gemma4.26b-a4b.server.moe-aiter"]
    assert "quantization-probe" in tags_by_id["vllm.gemma4.e2b.torchao.real-model"]
    assert "qwen3.5" in tags_by_id["vllm.qwen3_5.0_8b.text.basic"]
    assert "qwen3.6" in tags_by_id[
        "vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-no-aiter-blocked"
    ]
    assert "control" in tags_by_id[
        "vllm.qwen3_6.35b-a3b.text.unquantized-moe-no-aiter-control"
    ]
    assert "moe" in tags_by_id[
        "vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-aiter-blocked"
    ]
    assert "blocked" in tags_by_id[
        "vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-aiter-blocked"
    ]


def test_gemma4_aiter_flash_attention_probe_records_current_blocker():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")
    by_id = {scenario.id: scenario for scenario in scenarios}

    probe = by_id["vllm.gemma4.e2b.server.attn-aiter-fa-blocked"]

    assert probe.model == "google/gemma-4-E2B-it"
    assert set(probe.tags) >= {
        "smoke",
        "gemma4",
        "server",
        "kernel-probe",
        "flash-attention",
        "aiter",
        "blocked",
        "exploratory",
    }
    assert probe.definition["given"]["tool"] == "gemma4_server_smoke.basic"
    assert probe.definition["when"]["argv"] == [
        "--attention-backend",
        "ROCM_AITER_FA",
        "--max-model-len",
        "128",
        "--max-num-batched-tokens",
        "32",
        "--startup-timeout",
        "90",
    ]

    assertions = probe.definition["then"]["assert"]
    for expected in (
        {"kind": "exit_code.equals", "value": 1},
        {
            "kind": "server_log.contains",
            "value": "Selected backend AttentionBackendEnum.ROCM_AITER_FA is not valid",
        },
        {"kind": "server_log.contains", "value": "compute capability not supported"},
    ):
        assert expected in assertions


def test_qwen3_6_fp8_moe_probes_record_backend_modes():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")

    no_aiter = next(
        scenario
        for scenario in scenarios
        if scenario.id
        == "vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-no-aiter-blocked"
    )
    forced_aiter = next(
        scenario
        for scenario in scenarios
        if scenario.id == "vllm.qwen3_6.35b-a3b-fp8.text.fp8-moe-aiter-blocked"
    )

    assert no_aiter.definition["when"]["env"] == {
        "VLLM_ROCM_USE_AITER": "0",
        "VLLM_ROCM_USE_AITER_MOE": "0",
    }
    assert forced_aiter.definition["when"]["env"] == {
        "VLLM_ROCM_USE_AITER": "1",
        "VLLM_ROCM_USE_AITER_MOE": "1",
    }
    assert {
        "kind": "stdout.contains",
        "value": "config_quantization_config_present true",
    } in no_aiter.definition["then"]["assert"]
    assert {
        "kind": "stdout.contains",
        "value": "config_quantization_config_present true",
    } in forced_aiter.definition["then"]["assert"]


def test_qwen3_6_unquantized_moe_control_records_validation_contract():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")
    by_id = {scenario.id: scenario for scenario in scenarios}

    control = by_id[
        "vllm.qwen3_6.35b-a3b.text.unquantized-moe-no-aiter-control"
    ]

    assert control.model == "Qwen/Qwen3.6-35B-A3B"
    assert set(control.tags) >= {
        "smoke",
        "qwen",
        "qwen3.6",
        "moe",
        "unquantized",
        "control",
        "exploratory",
    }
    assert control.definition["given"]["tool"] == "qwen_text_smoke"
    assert control.definition["when"]["argv"] == [
        "--max-num-batched-tokens",
        "32",
        "--gpu-memory-utilization",
        "0.9",
    ]
    assert control.definition["when"]["env"] == {
        "VLLM_ROCM_USE_AITER": "0",
        "VLLM_ROCM_USE_AITER_MOE": "0",
    }

    assertions = control.definition["then"]["assert"]
    for expected in (
        {"kind": "exit_code.equals", "value": 0},
        {
            "kind": "stdout.contains",
            "value": "config_quantization_config_present false",
        },
        {"kind": "stdout.contains", "value": "config_model_type qwen3_5_moe"},
        {
            "kind": "stdout.contains",
            "value": "text_config_model_type qwen3_5_moe_text",
        },
        {"kind": "stdout.contains", "value": "config_num_hidden_layers 40"},
        {"kind": "stdout.contains", "value": "config_num_experts 256"},
        {"kind": "stdout.contains", "value": "config_num_experts_per_tok 8"},
        {
            "kind": "stdout.contains",
            "value": "config_layer_types full_attention:10,linear_attention:30",
        },
        {"kind": "stdout.contains", "value": "llm_init_ok"},
        {"kind": "stdout.contains", "value": "generation_ok"},
        {"kind": "stdout.contains", "value": "basic_ok"},
        {
            "kind": "output.contains",
            "value": "Using TRITON backend for Unquantized MoE",
        },
    ):
        assert expected in assertions


def test_lemonade_help_smokes_assert_current_help_markers():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")
    by_id = {scenario.id: scenario for scenario in scenarios}

    cli_assertions = by_id["lemonade.cli.help"].definition["then"]["assert"]
    server_assertions = by_id["lemonade.server.help"].definition["then"]["assert"]

    assert {"kind": "output.contains", "value": "Lemonade CLI"} in cli_assertions
    assert {"kind": "output.contains", "value": "Lightweight LLM server"} in server_assertions
    assert {"kind": "output.contains", "value": "OPTIONS:"} in cli_assertions
    assert {"kind": "output.contains", "value": "OPTIONS:"} in server_assertions
