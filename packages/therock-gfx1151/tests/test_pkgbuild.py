import json
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
    assert "package_migraphx-gfx1151()" in text
    assert "depends=('gcc-libs' 'glibc' 'hip-runtime-amd-gfx1151' 'miopen-hip-gfx1151' 'msgpack-cxx' 'libprotobuf.so=35.0.0-64' 'python-gfx1151' 'rocblas-gfx1151' 'rocm-core-gfx1151' 'sqlite')" in text
    assert "migraphx.pth" in text
    assert "import sqlite3" in text
    assert "/opt/rocm/lib" in text

    manifest = json.loads(MANIFEST.read_text())
    assert manifest["packages"]["migraphx-gfx1151"]["depends"] == [
        "gcc-libs",
        "glibc",
        "hip-runtime-amd-gfx1151",
        "miopen-hip-gfx1151",
        "msgpack-cxx",
        "libprotobuf.so=35.0.0-64",
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


def test_migraphx_staging_pins_system_protobuf_and_rejects_stale_soname():
    text = STAGE_MIGRAPHX.read_text()
    assert "typeset protobuf_dir=/usr/lib/cmake/protobuf" in text
    assert "typeset protobuf_soname=libprotobuf.so.35.0.0" in text
    assert "typeset utf8_validity_soname=libutf8_validity.so.35.0.0" in text
    assert "-Dprotobuf_DIR=$protobuf_dir" in text
    assert 'local protobuf_lib_dir=${protobuf_dir%/cmake/protobuf}' in text
    assert "read_soname $protobuf_lib_dir/libprotobuf.so" in text
    assert "read_soname $protobuf_lib_dir/libutf8_validity.so" in text
    assert "libprotobuf.so.34*" in text
    assert "libutf8_validity.so.34*" in text
    assert text.index("staged MIGraphX ONNX library still links protobuf 34-era libraries") < text.index(
        "staged MIGraphX ONNX library is not linked against $protobuf_soname"
    )
    assert text.index("local -a needed") < text.index('status "checking staged Python import"')


def test_rocprofiler_compute_manifest_tracks_runtime_dependencies():
    text = PKGBUILD.read_text()
    assert "package_rocprofiler-compute-gfx1151()" in text
    assert "depends=('gcc-libs' 'glibc' 'python-gfx1151' 'python-astunparse' 'python-numpy-gfx1151' 'python-pandas' 'python-pyyaml-gfx1151' 'python-sqlalchemy' 'python-tabulate' 'python-textual' 'rocprofiler-sdk-gfx1151' 'rocprofiler-systems-gfx1151')" in text
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
    assert "depends=('bash' 'gmp' 'guile' 'libelf' 'mpfr' 'ncurses' 'readline' 'rocm-dbgapi-gfx1151' 'rocm-debug-agent-gfx1151' 'xz')" in text

    manifest = json.loads(MANIFEST.read_text())
    assert manifest["packages"]["rocm-gdb-gfx1151"]["depends"] == [
        "bash",
        "gmp",
        "guile",
        "libelf",
        "mpfr",
        "ncurses",
        "readline",
        "rocm-dbgapi-gfx1151",
        "rocm-debug-agent-gfx1151",
        "xz",
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
