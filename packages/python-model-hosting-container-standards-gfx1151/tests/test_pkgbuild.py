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



def test_pins_the_0_1_16_sdist_by_digest():
    # vLLM 0.30.0 requires model-hosting-container-standards >=0.1.14,<1.0.0;
    # 0.1.16 is the latest release, and the digest is the one PyPI publishes.
    assert pkgbuild_value('"$pkgver"') == ["0.1.16"]
    assert pkgbuild_value('"${source[@]}"') == [
        "https://files.pythonhosted.org/packages/source/m/"
        "model_hosting_container_standards/"
        "model_hosting_container_standards-0.1.16.tar.gz"
    ]
    assert pkgbuild_value('"${sha256sums[@]}"') == [
        "d34589633900e53c3ee5f7c78280a7cf7e4f6532c35e763341a262fc85cbe84a"
    ]


def test_depends_map_upstream_requirements_to_arch_names():
    # 0.1.16 requires fastapi, starlette >=0.49.1, pydantic, jmespath, httpx,
    # setuptools and supervisor >=4.2.0.
    assert set(pkgbuild_value('"${depends[@]}"')) == {
        "python-gfx1151",
        "python-fastapi",
        "python-starlette",
        "python-pydantic",
        "python-jmespath",
        "python-httpx",
        "python-setuptools",
        "supervisor",
    }


def test_is_pure_python_built_with_poetry_core():
    assert pkgbuild_value('"${arch[@]}"') == ["any"]
    assert "python-poetry-core" in pkgbuild_value('"${makedepends[@]}"')
    assert "_setup_compiler_env" not in PKGBUILD.read_text()


def test_replaces_the_aur_package_name():
    assert pkgbuild_value('"${provides[@]}"') == [
        "python-model-hosting-container-standards"
    ]
    assert pkgbuild_value('"${conflicts[@]}"') == [
        "python-model-hosting-container-standards"
    ]
