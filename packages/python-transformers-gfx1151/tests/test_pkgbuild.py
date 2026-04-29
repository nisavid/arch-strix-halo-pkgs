from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-transformers-gfx1151/PKGBUILD"
EXPECTED_VERSION = "5.7.0"
DIST_INFO = (
    REPO_ROOT
    / f"packages/python-transformers-gfx1151/pkg/python-transformers-gfx1151/usr/lib/python3.14/site-packages/transformers-{EXPECTED_VERSION}.dist-info/METADATA"
)
GEMMA4_INIT = (
    REPO_ROOT
    / "packages/python-transformers-gfx1151/pkg/python-transformers-gfx1151/usr/lib/python3.14/site-packages/transformers/models/gemma4/__init__.py"
)


def test_pkgbuild_replaces_python_transformers_with_local_gemma4_capable_lane():
    text = PKGBUILD.read_text()
    assert "pkgname=python-transformers-gfx1151" in text
    assert f"pkgver={EXPECTED_VERSION}" in text
    assert "provides=(python-transformers)" in text
    assert "conflicts=(python-transformers)" in text


def test_built_package_exports_gemma4_module():
    if not DIST_INFO.exists():
        import pytest

        pytest.skip("built transformers package image is not present")

    assert DIST_INFO.exists()
    assert f"Version: {EXPECTED_VERSION}" in DIST_INFO.read_text()
    assert GEMMA4_INIT.exists()
