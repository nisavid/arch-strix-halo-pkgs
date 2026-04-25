import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/therock-gfx1151/PKGBUILD"
MANIFEST = REPO_ROOT / "packages/therock-gfx1151/manifest.json"
AMDSMI_PKGDIR = REPO_ROOT / "packages/therock-gfx1151/pkg/amdsmi-gfx1151"
AMDSMI_PTH = AMDSMI_PKGDIR / "usr/lib/python3.14/site-packages/amd_smi.pth"


def test_migraphx_package_exports_python_import_hook():
    text = PKGBUILD.read_text()
    assert "package_migraphx-gfx1151()" in text
    assert "depends=('gcc-libs' 'glibc' 'hip-runtime-amd-gfx1151' 'miopen-hip-gfx1151' 'msgpack-cxx' 'protobuf' 'python-gfx1151' 'rocblas-gfx1151' 'rocm-core-gfx1151' 'sqlite')" in text
    assert "migraphx.pth" in text
    assert "/opt/rocm/lib" in text

    manifest = json.loads(MANIFEST.read_text())
    assert manifest["packages"]["migraphx-gfx1151"]["depends"] == [
        "gcc-libs",
        "glibc",
        "hip-runtime-amd-gfx1151",
        "miopen-hip-gfx1151",
        "msgpack-cxx",
        "protobuf",
        "python-gfx1151",
        "rocblas-gfx1151",
        "rocm-core-gfx1151",
        "sqlite",
    ]


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
