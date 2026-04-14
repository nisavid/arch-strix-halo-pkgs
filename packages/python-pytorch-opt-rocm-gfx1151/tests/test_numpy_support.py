import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
TORCH_SITE = (
    REPO_ROOT
    / "packages/python-pytorch-opt-rocm-gfx1151/pkg/python-pytorch-opt-rocm-gfx1151/usr/lib/python3.14/site-packages"
)
NUMPY_SITE = (
    REPO_ROOT
    / "packages/python-numpy-gfx1151/pkg/python-numpy-gfx1151/usr/lib/python3.14/site-packages"
)
PKGBUILD = REPO_ROOT / "packages/python-pytorch-opt-rocm-gfx1151/PKGBUILD"


def test_pkgbuild_makes_numpy_available_at_build_time():
    text = PKGBUILD.read_text()
    assert "python-numpy-gfx1151" in text
    assert "openblas" in text
    assert "makedepends=(" in text
    assert "0001-setup-allow-skipping-build-deps.patch" in text
    assert "export USE_NUMPY=1" in text
    assert 'export BLAS="OpenBLAS"' in text
    assert 'export OpenBLAS_HOME="${OpenBLAS_HOME:-/usr}"' in text
    assert "export USE_LAPACK=1" in text
    assert 'export CMAKE_PREFIX_PATH="${OpenBLAS_HOME}:/opt/rocm"' in text
    assert 'export AOTRITON_INSTALLED_PREFIX="/usr"' in text
    assert 'rm -rf build' in text
    assert 'export CCACHE_DIR="${_ccache_dir}/store"' in text
    assert "CMAKE_ONLY=1 python setup.py build" in text
    assert 'cmake --build build --config Release -j "${MAX_JOBS}"' in text
    assert "_sysconfigdata__linux_x86_64-linux-gnu.cpython-314.pyc" in text
    assert "SKIP_BUILD_DEPS=1 python setup.py bdist_wheel --dist-dir dist" in text


def test_built_torch_package_supports_tensor_to_numpy():
    env = os.environ.copy()
    openblas_home = env.get("OPENBLAS_HOME")
    if openblas_home:
        openblas_lib = Path(openblas_home) / "lib"
        if openblas_lib.exists():
            ld_library_path = str(openblas_lib)
            if env.get("LD_LIBRARY_PATH"):
                ld_library_path = f"{ld_library_path}{os.pathsep}{env['LD_LIBRARY_PATH']}"
            env["LD_LIBRARY_PATH"] = ld_library_path
    elif not Path("/usr/lib/libopenblas.so.0").exists():
        pytest.skip("OpenBLAS runtime is not available; set OPENBLAS_HOME for this smoke test")

    pythonpath = os.pathsep.join((str(TORCH_SITE), str(NUMPY_SITE)))
    if env.get("PYTHONPATH"):
        pythonpath = f"{pythonpath}{os.pathsep}{env['PYTHONPATH']}"
    env["PYTHONPATH"] = pythonpath

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import torch; "
                "value = torch.tensor([1.0]).numpy().tolist(); "
                "print(value)"
            ),
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, (
        f"torch.tensor(...).numpy() exited with {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert result.stdout.strip() == "[1.0]"
