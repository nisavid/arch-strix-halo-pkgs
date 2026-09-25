import re
import subprocess
import tomllib
from pathlib import Path


PKGBUILD = Path(__file__).resolve().parents[1] / "PKGBUILD"
RECIPE_POLICY = Path(__file__).resolve().parents[3] / "policies" / "recipe-packages.toml"


def pkgbuild_value(expr: str) -> list[str]:
    script = f'source "$1" && printf "%s\\n" {expr}'
    out = subprocess.run(
        ["bash", "-c", script, "bash", str(PKGBUILD)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def test_pins_the_0_1_10_sdist_by_digest():
    # xgrammar 0.2.3 requires apache-tvm-ffi >=0.1.9, and vLLM 0.30.0
    # requirements/rocm.txt pins apache-tvm-ffi ==0.1.10; 0.1.10 meets both.
    # The digest is the one PyPI publishes for the sdist.
    assert pkgbuild_value('"$pkgver"') == ["0.1.10"]
    assert pkgbuild_value('"${source[@]}"') == [
        "https://files.pythonhosted.org/packages/source/a/apache_tvm_ffi/"
        "apache_tvm_ffi-0.1.10.tar.gz"
    ]
    assert pkgbuild_value('"${sha256sums[@]}"') == [
        "974c208766c304c780c17c6d405449e862f83b22c7b6b2b8c28b29d55a806ae3"
    ]


def test_builds_the_cpp_core_and_cython_module_on_the_native_lane():
    text = PKGBUILD.read_text()

    assert pkgbuild_value('"${arch[@]}"') == ["x86_64"]
    assert "_setup_compiler_env" in text
    # pyproject: scikit-build-core >=0.10.0, cython >=3.0 and setuptools-scm,
    # with CMake and a ninja >=1.11 generator (make fallback disabled).
    assert set(pkgbuild_value('"${makedepends[@]}"')) >= {
        "cmake",
        "ninja",
        "cython",
        "python-scikit-build-core",
        "python-setuptools-scm",
        "rocm-llvm-gfx1151",
    }


def test_installs_exactly_one_wheel():
    text = PKGBUILD.read_text()

    assert "expected exactly one wheel" in text


def test_runtime_depends_are_the_cpp_runtime_and_typing_extensions():
    # apache-tvm-ffi 0.1.10 requires only typing-extensions >=4.5; the
    # shared library and the Cython module link libstdc++.
    assert set(pkgbuild_value('"${depends[@]}"')) == {
        "glibc",
        "libgcc",
        "libstdc++",
        "python-gfx1151",
        "python-typing_extensions",
    }


def test_replaces_the_aur_package_name():
    assert pkgbuild_value('"${provides[@]}"') == ["python-apache-tvm-ffi"]
    assert pkgbuild_value('"${conflicts[@]}"') == ["python-apache-tvm-ffi"]


def test_skips_the_frontend_dependency_check_for_the_pypi_cmake_requirement():
    # scikit-build-core's get_requires_for_build_wheel hook asks for the PyPI
    # cmake distribution, which a no-isolation `python -m build` then reports
    # as unmet. Arch supplies cmake as /usr/bin/cmake, which the backend uses.
    build_lines = [
        line
        for line in re.sub(r"\\\n\s*", " ", PKGBUILD.read_text()).splitlines()
        if "python -m build" in line
    ]
    assert build_lines
    assert all("--skip-dependency-check" in line for line in build_lines)

    policy = tomllib.loads(RECIPE_POLICY.read_text(encoding="utf-8"))
    entry = policy["packages"]["python-apache-tvm-ffi-gfx1151"]
    assert entry["skip_dependency_check"] is True
    assert any(
        "scikit-build-core" in note and "cmake" in note and "/usr/bin/cmake" in note
        for note in entry["divergence_notes"]
    )
