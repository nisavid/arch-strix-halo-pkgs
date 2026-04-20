from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/llama.cpp-vulkan-gfx1151/PKGBUILD"


def test_pkgbuild_declares_spirv_headers_for_vulkan_backend():
    text = PKGBUILD.read_text()
    assert "spirv-headers" in text
