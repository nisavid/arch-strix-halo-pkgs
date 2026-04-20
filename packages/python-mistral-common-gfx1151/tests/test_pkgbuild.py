from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-mistral-common-gfx1151/PKGBUILD"
DIST_INFO = (
    REPO_ROOT
    / "packages/python-mistral-common-gfx1151/pkg/python-mistral-common-gfx1151/usr/lib/python3.14/site-packages/mistral_common-1.11.0.dist-info/METADATA"
)
REQUEST_MODULE = (
    REPO_ROOT
    / "packages/python-mistral-common-gfx1151/pkg/python-mistral-common-gfx1151/usr/lib/python3.14/site-packages/mistral_common/protocol/instruct/request.py"
)


def test_pkgbuild_replaces_python_mistral_common_with_local_lane():
    text = PKGBUILD.read_text()
    assert "pkgname=python-mistral-common-gfx1151" in text
    assert "pkgver=1.11.0" in text
    assert "provides=(python-mistral-common)" in text
    assert "conflicts=(python-mistral-common)" in text


def test_built_package_exports_reasoning_effort():
    assert DIST_INFO.exists()
    assert "Version: 1.11.0" in DIST_INFO.read_text()
    assert REQUEST_MODULE.exists()
    assert "ReasoningEffort" in REQUEST_MODULE.read_text()
