from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/llama.cpp-hip-gfx1151/PKGBUILD"

EXPECTED_VERSION = "b8881"
EXPECTED_COMMIT = "0dedb9ef7a71fcebfa6fb17e0d6e6abd6e893376"


def test_pkgbuild_tracks_recorded_llamacpp_release():
    text = PKGBUILD.read_text()
    assert f"pkgver={EXPECTED_VERSION}" in text
    assert EXPECTED_COMMIT in text
    assert "ggml-org/llama.cpp/archive/" in text
