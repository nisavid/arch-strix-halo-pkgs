from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools/run_patch_audit_host_checks.sh"


def test_patch_audit_host_checks_reinstalls_target_packages():
    text = SCRIPT.read_text()
    assert "sudo pacman -S --needed python-amd-aiter-gfx1151 python-vllm-rocm-gfx1151" not in text
    assert "sudo pacman -S python-amd-aiter-gfx1151 python-vllm-rocm-gfx1151" in text


def test_patch_audit_host_checks_uses_vllm_cli_for_version_probe():
    text = SCRIPT.read_text()
    assert "python -m vllm --version" not in text
    assert "vllm --version" in text


def test_patch_audit_host_checks_does_not_pick_archives_lexicographically():
    text = SCRIPT.read_text()
    assert "sort | tail -n 1" not in text
    assert "tools/select_latest_package.py" in text
