from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE = REPO_ROOT / "tools/torch_migraphx_smoke.py"


def test_torch_migraphx_smoke_help_lists_expected_modes():
    completed = subprocess.run(
        [sys.executable, str(SMOKE), "--help"],
        capture_output=True,
        check=True,
        text=True,
    )

    assert "pt2e-quantizer-import" in completed.stdout
    assert "dynamo-resnet-tiny" in completed.stdout
    assert "pt2e-resnet-tiny" in completed.stdout


def test_torch_migraphx_smoke_records_backend_and_metrics_contract():
    text = SMOKE.read_text(encoding="utf-8")

    assert 'torch.compile(model, backend="migraphx")' in text
    assert "convert_pt2e(prepared, fold_quantize=False)" in text
    for marker in [
        "baseline_latency_ms",
        "compiled_latency_ms",
        "peak_memory_bytes",
        "output_close_ok",
        "torch_migraphx_ok",
        "pt2e_quantizer_import_ok",
    ]:
        assert marker in text
