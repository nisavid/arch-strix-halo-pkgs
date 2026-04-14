from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-vllm-rocm-gfx1151/PKGBUILD"


def test_vllm_depends_on_local_transformers_lane():
    text = PKGBUILD.read_text()
    assert "python-transformers-gfx1151" in text
    assert "python-transformers " not in text
