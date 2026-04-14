from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
ROCM_PLATFORM = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/pkg/python-vllm-rocm-gfx1151/usr/lib/python3.14/site-packages/vllm/platforms/rocm.py"
)


def test_rocm_platform_fallback_avoids_warning_once_during_import():
    text = ROCM_PLATFORM.read_text()
    start = text.index("def _get_gcn_arch() -> str:")
    end = text.index("\n\n# Resolve once at module load.", start)
    section = text[start:end]
    assert "torch.cuda.get_device_properties" in section
    assert "warning_once" not in section
