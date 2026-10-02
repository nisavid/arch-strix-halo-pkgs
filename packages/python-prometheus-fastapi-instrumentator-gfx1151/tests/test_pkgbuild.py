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


def test_pins_the_8_1_0_sdist_by_digest():
    # vLLM 0.30.0 requires prometheus-fastapi-instrumentator >= 8.0.0; the
    # sdist digest is the one PyPI publishes for 8.1.0.
    assert pkgbuild_value('"$pkgver"') == ["8.1.0"]
    assert pkgbuild_value('"${source[@]}"') == [
        "https://files.pythonhosted.org/packages/source/p/"
        "prometheus_fastapi_instrumentator/"
        "prometheus_fastapi_instrumentator-8.1.0.tar.gz"
    ]
    assert pkgbuild_value('"${sha256sums[@]}"') == [
        "b77f3043665e8d28e2bbd21017506195a43d9adf1d402d01bf95b494b7e560e1"
    ]


def test_depends_map_upstream_requirements_to_arch_names():
    # 8.1.0 requires starlette >=1.0.0,<2.0.0 and prometheus-client
    # >=0.8.0,<1.0.0; it does not require fastapi itself.
    depends = pkgbuild_value('"${depends[@]}"')

    assert set(depends) == {
        "python-gfx1151",
        "python-prometheus_client",
        "python-starlette",
    }


def test_builds_with_poetry_core_and_checks_build_dependencies():
    # The sdist's build backend is poetry-core >= 2.0, which Arch satisfies,
    # so the build keeps its dependency check.
    assert "python-poetry-core" in pkgbuild_value('"${makedepends[@]}"')
    assert "--skip-dependency-check" not in PKGBUILD.read_text()


def test_replaces_the_aur_package_name():
    assert pkgbuild_value('"${provides[@]}"') == [
        "python-prometheus-fastapi-instrumentator"
    ]
    assert pkgbuild_value('"${conflicts[@]}"') == [
        "python-prometheus-fastapi-instrumentator"
    ]
