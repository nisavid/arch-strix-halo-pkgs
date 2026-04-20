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
    assert "vllm.gemma4.26b-a4b.text.compiled" in ids
    assert "vllm.gemma4.26b-a4b.server.moe-aiter" in ids
    assert "vllm.torchao.tiny.generate" in ids
    assert "vllm.gemma4.e2b.torchao.real-model" in ids
    assert "vllm.qwen3_5.0_8b.text.basic" in ids
    assert "vllm.qwen3_6.35b-a3b-fp8.text.basic" in ids
    assert "llama.cpp.hip.help" in ids
    assert "llama.cpp.vulkan.help" in ids
    assert "lemonade.cli.help" in ids
    assert "lemonade.server.help" in ids
    assert engines == {"vllm", "llama.cpp", "lemonade"}
    assert "smoke" in tags_by_id["vllm.gemma4.26b-a4b.text.basic"]
    assert "exploratory" in tags_by_id["vllm.gemma4.e2b.server.image"]
    assert "kernel-probe" in tags_by_id["vllm.gemma4.e2b.server.attn-triton"]
    assert "exploratory" in tags_by_id["vllm.gemma4.e2b.server.attn-triton"]
    assert "kernel-probe" in tags_by_id["vllm.gemma4.26b-a4b.server.moe-aiter"]
    assert "quantization-probe" in tags_by_id["vllm.gemma4.e2b.torchao.real-model"]
    assert "qwen3.5" in tags_by_id["vllm.qwen3_5.0_8b.text.basic"]
    assert "qwen3.6" in tags_by_id["vllm.qwen3_6.35b-a3b-fp8.text.basic"]
    assert "moe" in tags_by_id["vllm.qwen3_6.35b-a3b-fp8.text.basic"]


def test_qwen3_6_fp8_moe_smoke_uses_aiter_backend_env():
    scenarios = load_scenarios(REPO_ROOT / "inference/scenarios")

    qwen3_6 = next(
        scenario
        for scenario in scenarios
        if scenario.id == "vllm.qwen3_6.35b-a3b-fp8.text.basic"
    )

    assert qwen3_6.definition["when"]["env"] == {
        "VLLM_ROCM_USE_AITER": "1",
        "VLLM_ROCM_USE_AITER_MOE": "1",
    }
