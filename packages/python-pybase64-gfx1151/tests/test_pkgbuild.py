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



def test_pins_the_1_5_0_sdist_by_digest():
    # vLLM 0.30.0 requires pybase64 with no version bound; 1.5.0 is the
    # latest stable release, and the digest is the one PyPI publishes.
    assert pkgbuild_value('"$pkgver"') == ["1.5.0"]
    assert pkgbuild_value('"${source[@]}"') == [
        "https://files.pythonhosted.org/packages/source/p/pybase64/pybase64-1.5.0.tar.gz"
    ]
    assert pkgbuild_value('"${sha256sums[@]}"') == [
        "545ab2a433769e3b8e1ce2b4f7b07218bbde202f4954fbfe52948b2522120727"
    ]


def test_builds_the_c_extension_on_the_native_lane():
    text = PKGBUILD.read_text()

    assert pkgbuild_value('"${arch[@]}"') == ["x86_64"]
    assert "_setup_compiler_env" in text
    # setup.py builds the bundled libbase64 with cmake.
    assert "cmake" in pkgbuild_value('"${makedepends[@]}"')


def test_makes_the_c_extension_mandatory():
    # Outside cibuildwheel, pybase64's setup.py marks the extension optional
    # and falls back to pure Python when libbase64 fails to build.
    # CIBUILDWHEEL=1 turns that fallback into a build failure.
    text = PKGBUILD.read_text()

    assert "export CIBUILDWHEEL=1" in text
    assert text.index("export CIBUILDWHEEL=1") < text.index("python -m build")


def test_depends_only_on_glibc_and_python():
    # pybase64 1.5.0 declares no runtime requirements.
    assert set(pkgbuild_value('"${depends[@]}"')) == {"glibc", "python-gfx1151"}


def test_replaces_the_aur_package_name():
    assert pkgbuild_value('"${provides[@]}"') == ["python-pybase64"]
    assert pkgbuild_value('"${conflicts[@]}"') == ["python-pybase64"]
