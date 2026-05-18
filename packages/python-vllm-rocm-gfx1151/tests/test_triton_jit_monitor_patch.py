from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PATCH = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/0016-rocm-refresh-local-carry-for-vllm-0.21.0.patch"
)


def test_triton_jit_monitor_skips_when_knobs_api_is_missing():
    text = PATCH.read_text()
    start = text.index("diff --git a/vllm/triton_utils/jit_monitor.py")
    end = text.find("diff --git", start + 1)
    if end == -1:
        end = len(text)
    section = text[start:end]

    assert "def _triton_knobs():" in section
    assert "from triton import knobs" in section
    assert "except ImportError:" in section
    assert "does not provide triton.knobs" in section
    assert "knobs = _triton_knobs()" in section
