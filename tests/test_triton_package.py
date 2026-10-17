from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "packages/python-triton-gfx1151"
LLVM_TARBALL = "llvm-5f07f818-ubuntu-x64-1"
# The ubuntu-x64 sha256 from ROCm/triton 669b31ac cmake/llvm-info.json.
LLVM_SHA256 = "62dd9524eed689360882a7ae06132182b4a724ca5dfdca77667556fcef940022"


def test_triton_pkgbuild_tracks_the_rocm_triton_3_8_release_lane() -> None:
    pkgbuild = (PACKAGE_DIR / "PKGBUILD").read_text()

    assert "pkgver=3.8.0+git669b31ac" in pkgbuild
    assert "provides=(python-triton=3.8.0+git669b31ac)" in pkgbuild
    # libtriton.so links libstdc++ and libz.
    assert "depends=(glibc libgcc libstdc++ python-gfx1151 zlib)" in pkgbuild
    assert "#commit=669b31acc1dd1b3fd93286afd5db67f65d9f7557" in pkgbuild
    assert 'patch -Np1 -i "$srcdir/0001-python-3.14-and-pybind11-build-system.patch"' in pkgbuild
    assert 'patch -Np1 -i "$srcdir/0002-disable-werror-with-therock-llvm-headers.patch"' in pkgbuild
    assert "0003-" not in pkgbuild
    assert not list(PACKAGE_DIR.glob("0003-*.patch"))
    assert "sed -i" not in pkgbuild
    assert "git cherry-pick" not in pkgbuild


def test_triton_pkgbuild_builds_offline_against_the_pinned_llvm() -> None:
    pkgbuild = (PACKAGE_DIR / "PKGBUILD").read_text()

    assert (
        f"{LLVM_TARBALL}.tar.gz::https://oaitriton.blob.core.windows.net/public/llvm-builds/{LLVM_TARBALL}.tar.gz"
        in pkgbuild
    )
    assert f"sha256sums=(SKIP {LLVM_SHA256} " in pkgbuild
    assert "export TRITON_OFFLINE_BUILD=ON" in pkgbuild
    assert f'export LLVM_SYSPATH="$srcdir/{LLVM_TARBALL}"' in pkgbuild
    assert "export JSON_SYSPATH=/usr" in pkgbuild
    assert "nlohmann-json" in pkgbuild
    assert "unset LLVM_SYSPATH" not in pkgbuild
    assert 'cd "$srcdir/triton/python"' not in pkgbuild


def test_triton_build_system_patch_drops_the_pinned_cmake_requirement() -> None:
    patch = (PACKAGE_DIR / "0001-python-3.14-and-pybind11-build-system.patch").read_text()

    assert "+++ b/pyproject.toml" in patch
    assert '-requires = ["setuptools>=40.8.0", "cmake==4.0"' in patch
    assert '+requires = ["setuptools>=40.8.0", "pybind11>=2.13.1"]' in patch
