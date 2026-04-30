from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/llama.cpp-vulkan-gfx1151/PKGBUILD"

EXPECTED_VERSION = "b8966"
EXPECTED_COMMIT = "7b8443ac786c06438e0f407b7adaa72c220b5099"


def test_pkgbuild_tracks_recorded_llamacpp_release():
    text = PKGBUILD.read_text()
    assert f"pkgver={EXPECTED_VERSION}" in text
    assert EXPECTED_COMMIT in text
    assert "ggml-org/llama.cpp/archive/" in text
    assert 'rm -f "$pkgdir${install_root}/bin"/test-*' in text
    assert "$pkgdir$/opt" not in text


def test_pkgbuild_declares_spirv_headers_for_vulkan_backend():
    text = PKGBUILD.read_text()
    assert "spirv-headers" in text
