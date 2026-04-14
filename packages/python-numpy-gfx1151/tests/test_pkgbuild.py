from __future__ import annotations

import subprocess
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent.parent
PKGBUILD = PACKAGE_DIR / "PKGBUILD"
MULTIARRAY = (
    PACKAGE_DIR
    / "pkg/python-numpy-gfx1151/usr/lib/python3.14/site-packages/numpy/_core/_multiarray_umath.cpython-314-x86_64-linux-gnu.so"
)


def test_pkgbuild_pins_system_blas_and_lapack() -> None:
    text = PKGBUILD.read_text()
    assert "pkgrel=3" in text
    assert "-Csetup-args=-Dblas=openblas" in text
    assert "-Csetup-args=-Dlapack=openblas" in text
    assert "-Csetup-args=-Dallow-noblas=false" in text


def test_built_numpy_extension_avoids_mkl_runtime_linkage() -> None:
    assert MULTIARRAY.exists(), "build the package before validating runtime linkage"
    result = subprocess.run(
        ["readelf", "-d", str(MULTIARRAY)],
        check=True,
        capture_output=True,
        text=True,
    )
    output = result.stdout
    assert "/opt/intel/oneapi" not in output
    assert "libmkl_" not in output
