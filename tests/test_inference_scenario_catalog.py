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

    assert "vllm.gemma4.26b-a4b.text.basic" in ids
    assert "vllm.gemma4.26b-a4b.server.basic" in ids
    assert "llama.cpp.hip.help" in ids
    assert "llama.cpp.vulkan.help" in ids
    assert "lemonade.cli.help" in ids
    assert "lemonade.server.help" in ids
    assert engines == {"vllm", "llama.cpp", "lemonade"}
