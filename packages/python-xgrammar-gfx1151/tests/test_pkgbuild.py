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


def test_pins_the_0_2_3_sdist_by_digest():
    # vLLM 0.30.0 requires xgrammar >=0.2.1,<1.0.0; its CUDA and CPU CI locks
    # test 0.2.3, which ships CPython 3.14 wheels. The digest is the one PyPI
    # publishes for the sdist.
    assert pkgbuild_value('"$pkgver"') == ["0.2.3"]
    assert pkgbuild_value('"${source[@]}"') == [
        "https://files.pythonhosted.org/packages/source/x/xgrammar/xgrammar-0.2.3.tar.gz"
    ]
    assert pkgbuild_value('"${sha256sums[@]}"') == [
        "f76423630ae3ac4e090cb38ce1e30e7bcc69b3dee4d22d94353944386a4c6f18"
    ]


def test_builds_against_the_local_tvm_ffi_lane():
    # The bindings are a TVM-FFI module: CMake finds tvm_ffi through the
    # installed Python package, which is also a runtime import.
    makedepends = set(pkgbuild_value('"${makedepends[@]}"'))
    depends = set(pkgbuild_value('"${depends[@]}"'))

    assert "python-apache-tvm-ffi-gfx1151" in makedepends
    assert "python-apache-tvm-ffi-gfx1151" in depends
    assert makedepends >= {"cmake", "ninja", "python-scikit-build-core", "rocm-llvm-gfx1151"}


def test_keeps_the_cpu_only_cmake_build_offline():
    # The CMake project is CXX-only; the CUDA bitmask kernel is a runtime JIT
    # that vLLM does not use on ROCm. cpptrace and the C++ tests are
    # submodule builds that stay off.
    text = PKGBUILD.read_text()

    assert "-Ccmake.define.XGRAMMAR_ENABLE_CPPTRACE=OFF" in text
    assert "-Ccmake.define.XGRAMMAR_BUILD_CXX_TESTS=OFF" in text
    assert "CUDA" not in text.replace("XGRAMMAR", "")


def test_runtime_depends_follow_the_published_metadata():
    # xgrammar 0.2.3 requires apache-tvm-ffi >=0.1.9, pydantic, torch,
    # transformers, triton (Linux x86_64), numpy and typing-extensions.
    assert set(pkgbuild_value('"${depends[@]}"')) == {
        "glibc",
        "libgcc",
        "libstdc++",
        "python-gfx1151",
        "python-apache-tvm-ffi-gfx1151",
        "python-numpy-gfx1151",
        "python-pydantic",
        "python-pytorch-opt-rocm-gfx1151",
        "python-transformers-gfx1151",
        "python-triton-gfx1151",
        "python-typing_extensions",
    }


def test_replaces_the_aur_package_name():
    assert pkgbuild_value('"${provides[@]}"') == ["python-xgrammar"]
    assert pkgbuild_value('"${conflicts[@]}"') == ["python-xgrammar"]


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
    entry = policy["packages"]["python-xgrammar-gfx1151"]
    assert entry["skip_dependency_check"] is True
    assert any(
        "scikit-build-core" in note and "cmake" in note and "/usr/bin/cmake" in note
        for note in entry["divergence_notes"]
    )


def test_archives_with_the_rocm_llvm_tools_that_match_amdclang():
    text = PKGBUILD.read_text()

    assert "-Ccmake.define.CMAKE_AR=/opt/rocm/lib/llvm/bin/llvm-ar" in text
    assert "-Ccmake.define.CMAKE_RANLIB=/opt/rocm/lib/llvm/bin/llvm-ranlib" in text


def _fake_wheel(dist: Path, files: dict[str, bytes]) -> None:
    import zipfile

    dist.mkdir(parents=True)
    name = "xgrammar-0.2.3"
    records = []
    payload = {
        **files,
        f"{name}.dist-info/METADATA": b"Metadata-Version: 2.1\nName: xgrammar\nVersion: 0.2.3\n",
        f"{name}.dist-info/WHEEL": b"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: false\nTag: cp314-cp314-linux_x86_64\n",
    }
    with zipfile.ZipFile(dist / f"{name}-cp314-cp314-linux_x86_64.whl", "w") as wheel:
        for member, data in payload.items():
            wheel.writestr(member, data)
            records.append(f"{member},,")
        wheel.writestr(f"{name}.dist-info/RECORD", "\n".join(records + [f"{name}.dist-info/RECORD,,"]) + "\n")


def run_package(tmp_path: Path, files: dict[str, bytes]) -> subprocess.CompletedProcess:
    srcdir = tmp_path / "src"
    _fake_wheel(srcdir / "xgrammar-0.2.3" / "dist", files)
    return subprocess.run(
        ["bash", "-c", 'source "$1" && package', "bash", str(PKGBUILD)],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "srcdir": str(srcdir), "pkgdir": str(tmp_path / "pkg")},
    )


def test_package_rejects_a_wheel_without_the_generated_ffi_stubs(tmp_path):
    # base.py imports xgrammar.tvm_ffi_binding._ffi_api, which only the
    # build-time tvm-ffi stub generation writes; the sdist does not carry it.
    result = run_package(tmp_path, {"xgrammar/__init__.py": b""})

    assert result.returncode != 0
    assert "xgrammar/tvm_ffi_binding/_ffi_api.py" in result.stderr


def test_package_accepts_a_wheel_with_the_generated_ffi_stubs(tmp_path):
    result = run_package(
        tmp_path,
        {"xgrammar/__init__.py": b"", "xgrammar/tvm_ffi_binding/_ffi_api.py": b""},
    )

    assert result.returncode == 0, result.stderr
