from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from qwen_text_smoke import print_config_summary


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
