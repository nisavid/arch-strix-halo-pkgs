from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools/rebuild_publish_install.zsh"


def run_script(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["zsh", str(SCRIPT), *args],
        input=input_text,
        capture_output=True,
        text=True,
        env={"PYTHONPYCACHEPREFIX": "/tmp", "TERM": "xterm-256color"},
    )


def test_noninteractive_without_selector_fails_fast():
    result = run_script("--dry-run")

    assert result.returncode == 2
    assert "INSTALL_SCOPE_REQUIRED" in result.stderr


def test_dry_run_emits_build_order_and_selected_install_scope():
    result = run_script("--dry-run", "--install-scope", "installed")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["install_scope"] == "installed"
    assert isinstance(payload["build_order"], list)
    assert payload["build_order"]


def test_dry_run_accepts_explicit_package_targets():
    result = run_script(
        "--dry-run",
        "python-amd-aiter-gfx1151",
        "python-vllm-rocm-gfx1151",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["install_scope"] == "explicit"
    assert payload["selected_install_outputs"] == [
        "python-amd-aiter-gfx1151",
        "python-vllm-rocm-gfx1151",
    ]
    assert "python-vllm-rocm-gfx1151" in payload["build_order"]
