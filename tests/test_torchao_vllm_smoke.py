from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import torchao_vllm_smoke


def test_real_model_plan_records_serialized_skip_modules(tmp_path: Path):
    plan = torchao_vllm_smoke.build_plan(
        argparse.Namespace(
            work_dir=tmp_path,
            prepare_only=False,
            source_model="google/gemma-4-E2B-it",
            quantized_model=None,
            max_model_len=128,
            gpu_memory_utilization=0.5,
            online_quantization=False,
            execution_mode="eager",
        )
    )

    assert plan["mode"] == "real-model"
    assert plan["serialized_skip_modules"] == [
        "model.vision_tower",
        "model.audio_tower",
        "model.embed_vision",
        "model.embed_audio",
        "vision_tower",
        "audio_tower",
        "embed_vision",
        "embed_audio",
    ]
    assert plan["serialized_quant_patterns"] == [
        r"re:(model\.)?language_model\..*",
        r"re:lm_head\..*",
    ]


def test_online_real_model_plan_has_no_serialized_skip_modules(tmp_path: Path):
    plan = torchao_vllm_smoke.build_plan(
        argparse.Namespace(
            work_dir=tmp_path,
            prepare_only=False,
            source_model="google/gemma-4-E2B-it",
            quantized_model=None,
            max_model_len=128,
            gpu_memory_utilization=0.5,
            online_quantization=True,
            execution_mode="eager",
        )
    )

    assert plan["mode"] == "real-model-online"
    assert plan["serialized_skip_modules"] == []
    assert plan["serialized_quant_patterns"] == []
