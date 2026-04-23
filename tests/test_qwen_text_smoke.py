from __future__ import annotations

from pathlib import Path
from types import ModuleType, SimpleNamespace
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from qwen_text_smoke import (
    build_llm_kwargs,
    print_config_summary,
    print_flash_attn_backend_summary,
)


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
    assert "--expected-flash-attn-backend" in result.stdout


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


def test_print_flash_attn_backend_summary_accepts_ck_backend(monkeypatch, capsys):
    backend = ModuleType("flash_attn_2_cuda")
    backend.__file__ = "/fake/flash_attn_2_cuda.so"
    wrapper = SimpleNamespace(USE_TRITON_ROCM=False, flash_attn_gpu=backend)
    flash_attn = ModuleType("flash_attn")
    flash_attn.flash_attn_interface = wrapper
    monkeypatch.setitem(sys.modules, "flash_attn", flash_attn)

    print_flash_attn_backend_summary("ck")

    output = capsys.readouterr().out
    assert "flash_attn_use_triton_rocm False" in output
    assert "flash_attn_backend_module flash_attn_2_cuda" in output
    assert "flash_attn_backend_file /fake/flash_attn_2_cuda.so" in output


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


def test_print_config_summary_reports_attention_shape(capsys):
    config = SimpleNamespace(
        architectures=["Qwen3_5ForConditionalGeneration"],
        model_type="qwen3_5",
        text_config=SimpleNamespace(
            hidden_size=1024,
            num_attention_heads=8,
            num_key_value_heads=2,
            head_dim=256,
        ),
    )

    print_config_summary(config)

    output = capsys.readouterr().out
    assert "config_hidden_size 1024" in output
    assert "config_num_attention_heads 8" in output
    assert "config_num_key_value_heads 2" in output
    assert "config_head_dim 256" in output
