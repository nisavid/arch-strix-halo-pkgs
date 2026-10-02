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


def build_command_settings() -> list[str]:
    text = re.sub(r"\\\n\s*", " ", PKGBUILD.read_text())
    lines = [line for line in text.splitlines() if "/usr/bin/python -m build" in line]
    assert len(lines) == 1
    return re.findall(r"-C(\S+)", lines[0])


def test_rebuilds_0_1_10_after_the_unknown_format_libbacktrace_release():
    # 0.1.10-1 was published to the W2A repo with a libbacktrace that had no
    # ELF reader, so the fixed build needs a new pkgrel.
    assert pkgbuild_value('"$pkgrel"') == ["2"]


def test_disables_the_segfault_backtrace_handler_and_keeps_libbacktrace():
    # The segfault handler re-enters TVMFFIBacktrace under a non-recursive
    # mutex, so any crash inside the backtrace path deadlocks the process.
    settings = build_command_settings()

    assert "cmake.define.TVM_FFI_BACKTRACE_ON_SEGFAULT=OFF" in settings
    assert not any("TVM_FFI_USE_LIBBACKTRACE" in s for s in settings)


def test_archives_with_the_rocm_llvm_tools_that_match_amdclang():
    settings = build_command_settings()

    assert "cmake.define.CMAKE_AR=/opt/rocm/lib/llvm/bin/llvm-ar" in settings
    assert "cmake.define.CMAKE_RANLIB=/opt/rocm/lib/llvm/bin/llvm-ranlib" in settings


def test_compiles_libbacktrace_without_lto_so_configure_detects_elf():
    # Under -flto, libbacktrace's configure reads LLVM bitcode in its object
    # format probe, builds unknown.c and leaves syminfo_fn NULL. libbacktrace
    # is the only C code in the build; C++ keeps makepkg's LTO flags.
    out = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1" && _drop_lto_from_cflags && printf "%s\\n%s\\n" "$CFLAGS" "$CXXFLAGS"',
            "bash",
            str(PKGBUILD),
        ],
        check=True,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "CFLAGS": "-O3 -pipe -flto=auto", "CXXFLAGS": "-O3 -flto=auto"},
    ).stdout.splitlines()

    assert out == ["-O3 -pipe", "-O3 -flto=auto"]
    build = PKGBUILD.read_text().split("build() {", 1)[1]
    assert build.index("_drop_lto_from_cflags") < build.index("/usr/bin/python -m build")


def _fake_wheel(dist: Path, files: dict[str, bytes]) -> None:
    import zipfile

    dist.mkdir(parents=True)
    name = "apache_tvm_ffi-0.1.10"
    records = []
    payload = {
        **files,
        f"{name}.dist-info/METADATA": b"Metadata-Version: 2.1\nName: apache-tvm-ffi\nVersion: 0.1.10\n",
        f"{name}.dist-info/WHEEL": b"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: false\nTag: cp312-abi3-linux_x86_64\n",
    }
    with zipfile.ZipFile(dist / f"{name}-cp312-abi3-linux_x86_64.whl", "w") as wheel:
        for member, data in payload.items():
            wheel.writestr(member, data)
            records.append(f"{member},,")
        wheel.writestr(f"{name}.dist-info/RECORD", "\n".join(records + [f"{name}.dist-info/RECORD,,"]) + "\n")


def run_package(tmp_path: Path, library: bytes) -> subprocess.CompletedProcess:
    srcdir = tmp_path / "src"
    _fake_wheel(srcdir / "apache_tvm_ffi-0.1.10" / "dist", {"tvm_ffi/lib/libtvm_ffi.so": library})
    return subprocess.run(
        ["bash", "-c", 'source "$1" && package', "bash", str(PKGBUILD)],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "srcdir": str(srcdir), "pkgdir": str(tmp_path / "pkg")},
    )


def test_package_rejects_a_library_without_the_libbacktrace_elf_reader(tmp_path):
    # unknown.c has none of elf.c's messages; 0.1.10-1 shipped that build.
    result = run_package(tmp_path, b"\x7fELF built with unknown.lo")

    assert result.returncode != 0
    assert "no debug info in ELF executable" in result.stderr


def test_package_accepts_a_library_with_the_libbacktrace_elf_reader(tmp_path):
    result = run_package(tmp_path, b"\x7fELF ... no debug info in ELF executable (make sure")

    assert result.returncode == 0, result.stderr
