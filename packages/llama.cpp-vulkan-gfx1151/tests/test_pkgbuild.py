from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/llama.cpp-vulkan-gfx1151/PKGBUILD"

EXPECTED_VERSION = "b8911"
EXPECTED_COMMIT = "5d2b52d80d9f375a6e81d07e212d047d8ee4f76e"


def test_pkgbuild_tracks_recorded_llamacpp_release():
    text = PKGBUILD.read_text()
    assert f"pkgver={EXPECTED_VERSION}" in text
    assert EXPECTED_COMMIT in text
    assert "ggml-org/llama.cpp/archive/" in text


def test_pkgbuild_declares_spirv_headers_for_vulkan_backend():
    text = PKGBUILD.read_text()
    assert "spirv-headers" in text
