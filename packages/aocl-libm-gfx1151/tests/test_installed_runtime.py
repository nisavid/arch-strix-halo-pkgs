from __future__ import annotations

import ctypes
import math
from pathlib import Path
import subprocess


LIBALM = Path("/usr/lib/libalm.so")
LIBAU_CPUID = Path("/usr/lib/libau_cpuid.so")
HEADERS = (
    Path("/usr/include/libm/alm_special.h"),
    Path("/usr/include/libm/__alm_func_internal.h"),
)


def test_installed_aocl_libm_runtime_is_discoverable() -> None:
    assert LIBALM.exists(), "install aocl-libm-gfx1151 before running this smoke"
    assert LIBAU_CPUID.exists(), "install aocl-utils-gfx1151 before running this smoke"
    for header in HEADERS:
        assert header.exists(), f"missing installed AOCL-LibM header: {header}"

    dynamic = subprocess.run(
        ["readelf", "-d", str(LIBALM)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "Library runpath: [/usr/lib]" in dynamic
    assert "Shared library: [libau_cpuid.so]" in dynamic

    libalm = ctypes.CDLL(str(LIBALM))
    libalm.amd_sin.argtypes = [ctypes.c_double]
    libalm.amd_sin.restype = ctypes.c_double

    assert math.isclose(libalm.amd_sin(0.5), math.sin(0.5), rel_tol=0.0, abs_tol=1e-15)
