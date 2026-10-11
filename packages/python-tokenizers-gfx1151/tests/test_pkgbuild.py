import json
import subprocess
import tomllib
from pathlib import Path


PACKAGE = "python-tokenizers-gfx1151"
PKGBUILD = Path(__file__).resolve().parents[1] / "PKGBUILD"
RECIPE = Path(__file__).resolve().parents[1] / "recipe.json"
RECIPE_POLICY = Path(__file__).resolve().parents[3] / "policies" / "recipe-packages.toml"
# tokenizers 0.23.3 requires huggingface-hub>=0.16.4,<3.0, and Arch packages
# huggingface-hub under epoch 1.
HUB_DEPENDS = ["python-huggingface-hub>=1:0.16.4", "python-huggingface-hub<1:3"]


def pkgbuild_value(expr: str) -> list[str]:
    script = f'source "$1" && printf "%s\\n" {expr}'
    out = subprocess.run(
        ["bash", "-c", script, "bash", str(PKGBUILD)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def test_pins_the_0_23_3_sdist_by_digest():
    # Transformers 5.18.0 requires tokenizers >=0.23.1,<0.24. The digest is
    # the one PyPI publishes for the 0.23.3 sdist.
    assert pkgbuild_value('"$pkgver"') == ["0.23.3"]
    assert pkgbuild_value('"${source[@]}"') == [
        "https://files.pythonhosted.org/packages/source/t/tokenizers/tokenizers-0.23.3.tar.gz"
    ]
    assert pkgbuild_value('"${sha256sums[@]}"') == [
        "cded33237c77caeef62944d32aa9a7ef42bdce2b3497e18d137e072a8c4be438"
    ]


def test_depends_declare_the_packaged_hub_range_with_the_arch_epoch():
    # The published metadata makes huggingface-hub a hard requirement, and the
    # extension imports it in Tokenizer.from_pretrained. Without the epoch,
    # `<3` would reject every epoch-1 hub.
    depends = pkgbuild_value('"${depends[@]}"')

    assert [dep for dep in depends if dep.startswith("python-huggingface-hub")] == HUB_DEPENDS


def test_rendered_depends_match_the_policy():
    policy = tomllib.loads(RECIPE_POLICY.read_text(encoding="utf-8"))["packages"][PACKAGE]
    recipe = json.loads(RECIPE.read_text(encoding="utf-8"))["policy"]
    depends = pkgbuild_value('"${depends[@]}"')

    assert depends == policy["depends"]
    assert recipe["depends"] == policy["depends"]
    assert set(depends) == {"glibc", "libgcc", "libstdc++", "python-gfx1151", *HUB_DEPENDS, "zlib"}


def test_build_never_lets_rustup_download_a_toolchain():
    text = PKGBUILD.read_text()

    assert "export RUSTUP_AUTO_INSTALL=0" in text
    assert text.index("export RUSTUP_AUTO_INSTALL=0") < text.index("python -m build")
