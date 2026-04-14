from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-torchvision-rocm-gfx1151/PKGBUILD"


def test_pkgbuild_does_not_carry_build_only_rocsolver_shim():
    text = PKGBUILD.read_text()
    assert "_compat_libdir" not in text
    assert "librocsolver.so.0" not in text
    assert "LD_LIBRARY_PATH" not in text or ".torch-rocm-compat" not in text
