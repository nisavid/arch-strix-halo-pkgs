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



def test_pins_the_9_0_0_sdist_by_digest():
    # vLLM 0.30.0 requires py-cpuinfo with no version bound; 9.0.0 is the
    # latest release, and the digest is the one PyPI publishes for its sdist.
    assert pkgbuild_value('"$pkgver"') == ["9.0.0"]
    assert pkgbuild_value('"${source[@]}"') == [
        "https://files.pythonhosted.org/packages/source/p/py-cpuinfo/py-cpuinfo-9.0.0.tar.gz"
    ]
    assert pkgbuild_value('"${sha256sums[@]}"') == [
        "3cdbbf3fac90dc6f118bfd64384f309edeadd902d7c8fb17f02ffa1fc3f49690"
    ]


def test_is_pure_python_with_no_runtime_requirements():
    assert pkgbuild_value('"${arch[@]}"') == ["any"]
    assert pkgbuild_value('"${depends[@]}"') == ["python-gfx1151"]
    assert "python-setuptools" in pkgbuild_value('"${makedepends[@]}"')
    assert "_setup_compiler_env" not in PKGBUILD.read_text()


def test_replaces_the_former_arch_package_name():
    # Arch shipped python-py-cpuinfo 9.0.0 before it left the sync repos.
    assert pkgbuild_value('"${provides[@]}"') == ["python-py-cpuinfo"]
    assert pkgbuild_value('"${conflicts[@]}"') == ["python-py-cpuinfo"]
