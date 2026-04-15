from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from safetensors import safe_open


REPO_ROOT = Path(__file__).resolve().parents[3]
SMOKE_TOOL = REPO_ROOT / "tools/torchao_vllm_smoke.py"


def test_prepare_only_builds_torchao_serialized_checkpoint(tmp_path: Path) -> None:
    out_dir = tmp_path / "torchao-smoke"
    env = {"PYTHONPYCACHEPREFIX": "/tmp"}

    result = subprocess.run(
        [sys.executable, str(SMOKE_TOOL), "--prepare-only", "--work-dir", str(out_dir)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    quant_dir = out_dir / "tiny-llama-torchao"
    config = json.loads((quant_dir / "config.json").read_text())

    assert "prepare_ok" in result.stdout
    assert config["quantization_config"]["quant_method"] == "torchao"
    assert set(config["quantization_config"]["quant_type"]) == {"default"}
    assert config["hidden_size"] // config["num_attention_heads"] == 64
    assert (quant_dir / "model.safetensors").exists()

    with safe_open(str(quant_dir / "model.safetensors"), framework="pt") as f:
        metadata = f.metadata()
    weight_metadata = metadata["model.layers.0.self_attn.q_proj.weight"]
    assert '"_type": "Int8Tensor"' in weight_metadata
    assert '"bfloat16"' in weight_metadata
