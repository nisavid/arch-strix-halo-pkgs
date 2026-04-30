import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-torchvision-rocm-gfx1151/PKGBUILD"
README = REPO_ROOT / "packages/python-torchvision-rocm-gfx1151/README.md"
RECIPE = REPO_ROOT / "packages/python-torchvision-rocm-gfx1151/recipe.json"
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
    patch_text = (PKGBUILD.parent / "0001-setup-relative-sources.patch").read_text()

    assert 'local _debug_prefix="/usr/src/debug/python-torchvision-rocm-gfx1151"' in text
    assert "-ffile-prefix-map=$srcdir=${_debug_prefix}" in text
    assert 'export NVCC_FLAGS="${_debug_map}"' in text
    assert 'local _ccache_cache="$srcdir/.ccache/cache"' in text
    assert 'export CCACHE_DIR="${CCACHE_DIR:-${_ccache_cache}}"' in text
    assert 'vision_hip_source = CSRS_DIR / "vision_hip.cpp"' in patch_text
    assert "sources.remove(vision_hip_source)" in patch_text


def test_pkgbuild_patches_extension_rpath_to_torch_lib():
    text = PKGBUILD.read_text()

    assert "pkgrel=6" in text
    assert "export FORCE_CUDA=1" in text
    assert "patchelf" in text
    assert 'local _rpath="\\$ORIGIN:\\$ORIGIN/../torch/lib:/opt/rocm/lib"' in text
    assert 'patchelf --set-rpath "${_rpath}" "${_extension}"' in text


def test_generated_docs_record_rocm_operator_build_mode():
    note = "FORCE_CUDA=1"

    assert note in README.read_text()
    assert note in RECIPE.read_text()


def test_built_extension_does_not_embed_repo_srcdir_path():
    if not BUILT_EXTENSION.exists():
        pytest.skip("built TorchVision extension is not present")

    result = subprocess.run(
        ["/usr/bin/strings", "-a", str(BUILT_EXTENSION)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert REPO_SRC_PREFIX not in result.stdout
