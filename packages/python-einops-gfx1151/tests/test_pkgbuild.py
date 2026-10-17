import subprocess
from pathlib import Path


PKGBUILD = Path(__file__).resolve().parents[1] / "PKGBUILD"


def pkgbuild_value(expr: str) -> list[str]:
    script = f'source "$1" && printf "%s\\n" {expr}'
    out = subprocess.run(
        ["bash", "-c", script, "bash", str(PKGBUILD)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [line for line in out.splitlines() if line]



def test_pins_the_0_8_2_sdist_by_digest():
    # vLLM 0.30.0 requires einops with no version bound; 0.8.2 is the latest
    # stable release, and the digest is the one PyPI publishes for its sdist.
    assert pkgbuild_value('"$pkgver"') == ["0.8.2"]
    assert pkgbuild_value('"${source[@]}"') == [
        "https://files.pythonhosted.org/packages/source/e/einops/einops-0.8.2.tar.gz"
    ]
    assert pkgbuild_value('"${sha256sums[@]}"') == [
        "609da665570e5e265e27283aab09e7f279ade90c4f01bcfca111f3d3e13f2827"
    ]


def test_is_pure_python_with_no_runtime_requirements():
    # einops declares no runtime dependencies; it builds with hatchling.
    assert pkgbuild_value('"${arch[@]}"') == ["any"]
    assert pkgbuild_value('"${depends[@]}"') == ["python-gfx1151"]
    assert "python-hatchling" in pkgbuild_value('"${makedepends[@]}"')
    assert "_setup_compiler_env" not in PKGBUILD.read_text()


def test_replaces_the_aur_package_name():
    assert pkgbuild_value('"${provides[@]}"') == ["python-einops"]
    assert pkgbuild_value('"${conflicts[@]}"') == ["python-einops"]
