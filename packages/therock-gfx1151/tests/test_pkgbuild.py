import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
REPO_PACKAGES = REPO_ROOT / "packages"
PKGBUILD = REPO_ROOT / "packages/therock-gfx1151/PKGBUILD"
MANIFEST = REPO_ROOT / "packages/therock-gfx1151/manifest.json"
MIGRAPHX_FILELIST = REPO_ROOT / "packages/therock-gfx1151/filelists/migraphx-gfx1151.txt"
STAGE_MIGRAPHX = REPO_ROOT / "tools/stage_migraphx_for_therock.zsh"
AMDSMI_PKGDIR = REPO_ROOT / "packages/therock-gfx1151/pkg/amdsmi-gfx1151"
AMDSMI_PTH = AMDSMI_PKGDIR / "usr/lib/python3.14/site-packages/amd_smi.pth"
MIGRAPHX_PKGDIR = REPO_ROOT / "packages/therock-gfx1151/pkg/migraphx-gfx1151"
MIGRAPHX_PTH = MIGRAPHX_PKGDIR / "usr/lib/python3.14/site-packages/migraphx.pth"


def test_migraphx_package_exports_python_import_hook():
    text = PKGBUILD.read_text()
    assert "pkgrel=4" in text
    assert "package_migraphx-gfx1151()" in text
    assert "depends=('abseil-cpp>=20260817.0' 'abseil-cpp<20260818' 'gcc-libs' 'glibc' 'hip-runtime-amd-gfx1151' 'miopen-hip-gfx1151' 'msgpack-cxx' 'libprotobuf.so=36.1.0-64' 'python-gfx1151' 'rocblas-gfx1151' 'rocm-core-gfx1151' 'sqlite')" in text
    assert "migraphx.pth" in text
    assert "import sqlite3" in text
    assert "/opt/rocm/lib" in text

    manifest = json.loads(MANIFEST.read_text())
    assert manifest["packages"]["migraphx-gfx1151"]["depends"] == [
        "abseil-cpp>=20260817.0",
        "abseil-cpp<20260818",
        "gcc-libs",
        "glibc",
        "hip-runtime-amd-gfx1151",
        "miopen-hip-gfx1151",
        "msgpack-cxx",
        "libprotobuf.so=36.1.0-64",
        "python-gfx1151",
        "rocblas-gfx1151",
        "rocm-core-gfx1151",
        "sqlite",
    ]


def test_migraphx_filelist_contains_runtime_payload():
    paths = MIGRAPHX_FILELIST.read_text().splitlines()
    assert "opt/rocm/bin/migraphx-driver" in paths
    assert any(path.startswith("opt/rocm/lib/migraphx/lib/libmigraphx.so") for path in paths)
    assert any(path.startswith("opt/rocm/lib/migraphx.cpython-") for path in paths)


def test_migraphx_staging_pins_protobuf_36_1_and_abseil_2608_and_rejects_stale_sonames():
    text = STAGE_MIGRAPHX.read_text()
    assert "typeset protobuf_dir=/usr/lib/cmake/protobuf" in text
    assert "typeset protobuf_soname=libprotobuf.so.36.1.0" in text
    assert "typeset utf8_validity_soname=libutf8_validity.so.36.1.0" in text
    assert "typeset abseil_soversion=2608.0.0" in text
    assert "-Dprotobuf_DIR=$protobuf_dir" in text
    assert "-Dabsl_DIR=$absl_dir" in text
    assert 'local protobuf_lib_dir=${protobuf_dir%/cmake/protobuf}' in text
    assert "read_soname $protobuf_lib_dir/libprotobuf.so" in text
    assert "read_soname $protobuf_lib_dir/libutf8_validity.so" in text
    assert "read_soname $protobuf_lib_dir/libabsl_base.so" in text
    for stale in (
        "libprotobuf.so.35.1*",
        "libutf8_validity.so.35.1*",
        "libprotobuf.so.35.0*",
        "libutf8_validity.so.35.0*",
        "libprotobuf.so.34*",
        "libutf8_validity.so.34*",
        "libabsl_*.so.2605*",
    ):
        assert stale in text
    assert "libmigraphx_onnx.so" in text
    assert "libmigraphx_tf.so" in text
    stale_check = text.index("staged MIGraphX parser library still links a stale protobuf or Abseil ABI")
    assert stale_check < text.index("staged MIGraphX parser library is not linked against $protobuf_soname")
    assert stale_check < text.index("staged MIGraphX parser library links no Abseil libraries")
    assert text.index("local -a needed") < text.index('status "checking staged Python import"')


def test_migraphx_depends_match_stage_script_sonames():
    text = STAGE_MIGRAPHX.read_text()
    depends = json.loads(MANIFEST.read_text())["packages"]["migraphx-gfx1151"]["depends"]

    protobuf_version = re.search(r"^typeset protobuf_soname=libprotobuf\.so\.(\S+)$", text, re.M)[1]
    assert f"libprotobuf.so={protobuf_version}-64" in depends

    # Abseil LTS YYYYMMDD.N ships SOVERSION YYMM.0.0 for every patch release.
    abseil_soversion = re.search(r"^typeset abseil_soversion=(\S+)$", text, re.M)[1]
    floor = next(dep for dep in depends if dep.startswith("abseil-cpp>="))
    ceiling = next(dep for dep in depends if dep.startswith("abseil-cpp<"))
    lts_date = floor.removeprefix("abseil-cpp>=").split(".")[0]
    assert abseil_soversion == f"{lts_date[2:6]}.0.0"
    assert ceiling == f"abseil-cpp<{int(lts_date) + 1}"


def test_rocprofiler_compute_manifest_tracks_runtime_dependencies():
    text = PKGBUILD.read_text()
    assert "package_rocprofiler-compute-gfx1151()" in text
    assert "depends=('gcc-libs' 'glibc' 'python-gfx1151' 'python-astunparse' 'python-numpy-gfx1151' 'python-pandas' 'python-pyyaml-gfx1151' 'python-sqlalchemy' 'python-tabulate' 'python-textual' 'rocprofiler-sdk-gfx1151' 'rocprofiler-systems-gfx1151')" in text
    assert "sed -i -e '/^dash-bootstrap-components==/d' -e '/^dash-svg==/d' -e '/^dash==/d' -e '/^plotext==/d' -e '/^plotille==/d' -e '/^textual_plotext==/d'" in text
    assert 'ln -s ../libexec/rocprofiler-compute/rocprof-compute "${pkgdir}/opt/rocm/bin/rocprof-compute"' in text

    manifest = json.loads(MANIFEST.read_text())
    assert manifest["packages"]["rocprofiler-compute-gfx1151"]["depends"] == [
        "gcc-libs",
        "glibc",
        "python-gfx1151",
        "python-astunparse",
        "python-numpy-gfx1151",
        "python-pandas",
        "python-pyyaml-gfx1151",
        "python-sqlalchemy",
        "python-tabulate",
        "python-textual",
        "rocprofiler-sdk-gfx1151",
        "rocprofiler-systems-gfx1151",
    ]


def test_rocm_gdb_manifest_tracks_non_rocm_runtime_dependencies():
    text = PKGBUILD.read_text()
    assert "package_rocm-gdb-gfx1151()" in text
    assert "depends=('bash' 'expat' 'gcc-libs' 'glibc' 'gmp' 'guile' 'libelf' 'mpfr' 'ncurses' 'python-gfx1151' 'readline' 'rocm-dbgapi-gfx1151' 'rocm-debug-agent-gfx1151' 'xz' 'zlib' 'zstd')" in text

    manifest = json.loads(MANIFEST.read_text())
    assert manifest["packages"]["rocm-gdb-gfx1151"]["depends"] == [
        "bash",
        "expat",
        "gcc-libs",
        "glibc",
        "gmp",
        "guile",
        "libelf",
        "mpfr",
        "ncurses",
        "python-gfx1151",
        "readline",
        "rocm-dbgapi-gfx1151",
        "rocm-debug-agent-gfx1151",
        "xz",
        "zlib",
        "zstd",
    ]


def test_developer_tools_meta_depends_on_debug_and_profile_tools():
    text = PKGBUILD.read_text()
    assert "package_rocm-developer-tools-gfx1151()" in text
    assert "depends=('rocm-llvm-gfx1151' 'rocm-cmake-gfx1151' 'rocm-gdb-gfx1151' 'rocprofiler-compute-gfx1151' 'rocprofiler-systems-gfx1151' 'rocprofiler-sdk-gfx1151' 'roctracer-gfx1151')" in text

    manifest = json.loads(MANIFEST.read_text())
    assert manifest["packages"]["rocm-developer-tools-gfx1151"]["depends"] == [
        "rocm-llvm-gfx1151",
        "rocm-cmake-gfx1151",
        "rocm-gdb-gfx1151",
        "rocprofiler-compute-gfx1151",
        "rocprofiler-systems-gfx1151",
        "rocprofiler-sdk-gfx1151",
        "roctracer-gfx1151",
    ]


def test_built_migraphx_package_preloads_sqlite_before_import_path():
    if not MIGRAPHX_PKGDIR.exists():
        pytest.skip("built package tree is not present in this checkout")
    assert MIGRAPHX_PTH.exists()
    assert MIGRAPHX_PTH.read_text() == "import sqlite3\n/opt/rocm/lib\n"


def test_amdsmi_package_exports_python_import_hook():
    text = PKGBUILD.read_text()
    assert "package_amdsmi-gfx1151()" in text
    assert "python-gfx1151" in text
    assert "amd_smi.pth" in text
    assert "/opt/rocm/share/amd_smi" in text


def test_built_amdsmi_package_installs_python_import_hook():
    if not AMDSMI_PKGDIR.exists():
        pytest.skip("built package tree is not present in this checkout")
    assert AMDSMI_PTH.exists()
    assert AMDSMI_PTH.read_text().strip() == "/opt/rocm/share/amd_smi"


def test_rendered_local_package_dependencies_exist():
    manifest = json.loads(MANIFEST.read_text())
    packages = manifest["packages"]
    missing = sorted(
        {
            dep
            for meta in packages.values()
            for dep in meta["depends"]
            if dep.endswith("-gfx1151")
            and (
                (dep in packages and not packages[dep]["rendered"])
                or (dep not in packages and not (REPO_PACKAGES / dep).exists())
            )
        }
    )
    assert missing == []


def test_rocm_core_pkgbuild_carries_cachy_runtime_baseline():
    text = PKGBUILD.read_text()
    assert "package_rocm-core-gfx1151()" in text
    assert "depends=('gcc-libs' 'glibc' 'python-gfx1151' 'python-prettytable' 'python-pyelftools' 'python-yaml')" in text
    assert 'install -Dm644 /dev/stdin "${pkgdir}/etc/ld.so.conf.d/rocm.conf" <<\'EOF\'' in text
    assert 'install -Dm644 /dev/stdin "${pkgdir}/etc/profile.d/rocm.sh" <<\'EOF\'' in text
    assert 'install -Dm644 /dev/stdin "${pkgdir}/usr/share/fish/vendor_conf.d/rocm.fish" <<\'EOF\'' in text
    assert 'install -Dm644 /dev/stdin "${pkgdir}/opt/rocm/share/doc/rocm-core/LICENSE.md" <<\'EOF\'' in text
    assert 'install -Dm644 /dev/stdin "${pkgdir}/opt/rocm/share/rdhc/README.md" <<\'EOF\'' in text
    assert 'install -Dm644 /dev/stdin "${pkgdir}/opt/rocm/share/rdhc/requirements.txt" <<\'EOF\'' in text
    assert 'install -Dm644 /dev/stdin "${pkgdir}/usr/share/licenses/rocm-core/LICENSE" <<\'EOF\'' in text
    assert 'ln -s ../libexec/rocm-core/rdhc.py "${pkgdir}/opt/rocm/bin/rdhc"' in text


def test_rocm_core_manifest_tracks_cachy_style_runtime_dependencies():
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["packages"]["rocm-core-gfx1151"]["depends"] == [
        "gcc-libs",
        "glibc",
        "python-gfx1151",
        "python-prettytable",
        "python-pyelftools",
        "python-yaml",
    ]
