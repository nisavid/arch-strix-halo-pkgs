from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from qwen_text_smoke import build_llm_kwargs, print_config_summary


def test_qwen_text_smoke_exposes_help_without_importing_vllm():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools/qwen_text_smoke.py"), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Run a text-only offline Qwen smoke through vLLM" in result.stdout
    assert "--execution-mode" in result.stdout
    assert "--quantization" in result.stdout
    assert "--kv-cache-dtype" in result.stdout
    assert "--dtype" in result.stdout
    assert "--attention-backend" in result.stdout


def test_build_llm_kwargs_carries_quantization_probe_options():
    args = SimpleNamespace(
        execution_mode="eager",
        gpu_memory_utilization=0.72,
        kv_cache_dtype="fp8",
        max_model_len=256,
        max_num_batched_tokens=64,
        quantization="quark",
        dtype="float16",
        attention_backend="FLASH_ATTN",
    )

    kwargs = build_llm_kwargs("Qwen/Qwen3-0.6B-FP8-KV", args)

    assert kwargs["model"] == "Qwen/Qwen3-0.6B-FP8-KV"
    assert kwargs["quantization"] == "quark"
    assert kwargs["kv_cache_dtype"] == "fp8"
    assert kwargs["dtype"] == "float16"
    assert kwargs["attention_backend"] == "FLASH_ATTN"
    assert kwargs["max_num_batched_tokens"] == 64
    assert kwargs["enforce_eager"] is True


def test_print_config_summary_reports_quantization_presence(capsys):
    config_without_quantization = SimpleNamespace(
        architectures=["Qwen3MoeForConditionalGeneration"],
        model_type="qwen3_5_moe",
    )
    config_with_quantization = SimpleNamespace(
        architectures=["Qwen3MoeForConditionalGeneration"],
        model_type="qwen3_5_moe",
        quantization_config={"quant_method": "fp8"},
    )
    config_with_empty_quantization = SimpleNamespace(
        architectures=["Qwen3MoeForConditionalGeneration"],
        model_type="qwen3_5_moe",
        quantization_config={},
    )

    print_config_summary(config_without_quantization)
    without_output = capsys.readouterr().out

    print_config_summary(config_with_quantization)
    with_output = capsys.readouterr().out

    print_config_summary(config_with_empty_quantization)
    empty_output = capsys.readouterr().out

    assert "config_quantization_config_present false" in without_output
    assert "config_quantization_config " not in without_output
    assert "config_quantization_config_present true" in with_output
    assert "config_quantization_config {'quant_method': 'fp8'}" in with_output
    assert "config_quantization_config_present true" in empty_output
    assert "config_quantization_config {}" in empty_output
