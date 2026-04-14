import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-torchvision-rocm-gfx1151/PKGBUILD"
BUILT_EXTENSION = (
    REPO_ROOT
    / "packages/python-torchvision-rocm-gfx1151/pkg/python-torchvision-rocm-gfx1151/usr/lib/python3.14/site-packages/torchvision/_C.so"
)
REPO_SRC_PREFIX = str(REPO_ROOT / "packages/python-torchvision-rocm-gfx1151/src")


def test_pkgbuild_does_not_carry_build_only_rocsolver_shim():
    text = PKGBUILD.read_text()
    assert "_compat_libdir" not in text
    assert "librocsolver.so.0" not in text
    assert "LD_LIBRARY_PATH" not in text or ".torch-rocm-compat" not in text


def test_pkgbuild_exports_source_path_sanitizer():
    text = PKGBUILD.read_text()
    assert 'local _debug_prefix="/usr/src/debug/python-torchvision-rocm-gfx1151"' in text
    assert "-ffile-prefix-map=$srcdir=${_debug_prefix}" in text
    assert 'export NVCC_FLAGS="${_debug_map}"' in text


def test_built_extension_does_not_embed_repo_srcdir_path():
    result = subprocess.run(
        ["/usr/bin/strings", "-a", str(BUILT_EXTENSION)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert REPO_SRC_PREFIX not in result.stdout
