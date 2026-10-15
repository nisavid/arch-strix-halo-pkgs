import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-transformers-gfx1151/PKGBUILD"
RECIPE = REPO_ROOT / "packages/python-transformers-gfx1151/recipe.json"
EXPECTED_VERSION = "5.18.0"
# Transformers 5.18.0 requires huggingface-hub>=1.31.0,<3.0, and Arch packages
# huggingface-hub under epoch 1.
HUB_DEPENDS = ["python-huggingface-hub>=1:1.31.0", "python-huggingface-hub<1:3"]
DIST_INFO = (
    REPO_ROOT
    / f"packages/python-transformers-gfx1151/pkg/python-transformers-gfx1151/usr/lib/python3.14/site-packages/transformers-{EXPECTED_VERSION}.dist-info/METADATA"
)
GEMMA4_INIT = (
    REPO_ROOT
    / "packages/python-transformers-gfx1151/pkg/python-transformers-gfx1151/usr/lib/python3.14/site-packages/transformers/models/gemma4/__init__.py"
)


def pkgbuild_value(expr: str) -> list[str]:
    script = f'source "$1" && printf "%s\\n" {expr}'
    out = subprocess.run(
        ["bash", "-c", script, "bash", str(PKGBUILD)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def test_pkgbuild_replaces_python_transformers_with_local_gemma4_capable_lane():
    text = PKGBUILD.read_text()
    assert "pkgname=python-transformers-gfx1151" in text
    assert f"pkgver={EXPECTED_VERSION}" in text
    assert "provides=(python-transformers)" in text
    assert "conflicts=(python-transformers)" in text


def test_pins_the_5_18_0_sdist_by_digest():
    # The digest is the one PyPI publishes for the 5.18.0 sdist.
    assert pkgbuild_value('"${source[@]}"') == [
        "https://files.pythonhosted.org/packages/source/t/transformers/transformers-5.18.0.tar.gz"
    ]
    assert pkgbuild_value('"${sha256sums[@]}"') == [
        "d89c206e42e841af7cd314b3d2b21c03e977d819cdb4aef65ada048769a644df"
    ]


def test_depends_declare_the_packaged_hub_range_with_the_arch_epoch():
    # Transformers checks its huggingface-hub range at import, so pacman has
    # to refuse a hub release outside it. Without the epoch, `<3` would reject
    # every epoch-1 hub and `>=1.31.0` would accept all of them.
    depends = pkgbuild_value('"${depends[@]}"')

    assert [dep for dep in depends if dep.startswith("python-huggingface-hub")] == HUB_DEPENDS


def test_runtime_depends_follow_the_published_metadata():
    # Transformers 5.18.0 requires huggingface-hub, numpy, packaging, pyyaml,
    # regex, safetensors, tokenizers, tqdm and typer.
    assert set(pkgbuild_value('"${depends[@]}"')) == {
        "python-gfx1151",
        *HUB_DEPENDS,
        "python-numpy-gfx1151",
        "python-packaging",
        "python-pyyaml-gfx1151",
        "python-regex",
        "python-safetensors-gfx1151",
        "python-tokenizers-gfx1151",
        "python-tqdm",
        "python-typer",
    }


def test_recipe_metadata_matches_the_pkgbuild():
    recipe = json.loads(RECIPE.read_text())

    assert recipe["pkgver"] == EXPECTED_VERSION
    assert recipe["policy"]["upstream_version"] == EXPECTED_VERSION
    assert recipe["policy"]["src_subdir"] == f"transformers-{EXPECTED_VERSION}"
    assert recipe["policy"]["depends"] == pkgbuild_value('"${depends[@]}"')


def test_built_package_exports_gemma4_module():
    if not DIST_INFO.exists():
        import pytest

        pytest.skip("built transformers package image is not present")

    assert DIST_INFO.exists()
    assert f"Version: {EXPECTED_VERSION}" in DIST_INFO.read_text()
    assert GEMMA4_INIT.exists()
