from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/llama.cpp-hip-gfx1151/PKGBUILD"

EXPECTED_VERSION = "b9101"
EXPECTED_COMMIT = "389ff61d77b5c71cec0cf92fe4e5d01ace80b797"


def test_pkgbuild_tracks_recorded_llamacpp_release():
    text = PKGBUILD.read_text()
    assert f"pkgver={EXPECTED_VERSION}" in text
    assert EXPECTED_COMMIT in text
    assert "ggml-org/llama.cpp/archive/" in text
    assert 'rm -f "$pkgdir${install_root}/bin"/test-*' in text
    assert "$pkgdir$/opt" not in text
