from __future__ import annotations

from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]


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
