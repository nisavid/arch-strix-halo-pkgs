from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from inference.runner import find_stale_vllm_engine_cores


def test_find_stale_vllm_engine_cores_matches_engine_workers():
    ps_output = """
 508399      1    931 VLLM::EngineCore VLLM::EngineCore some args
 508400 508399      2 python          python other process
""".strip()

    assert find_stale_vllm_engine_cores(ps_output) == [
        "508399      1    931 VLLM::EngineCore VLLM::EngineCore some args"
    ]
