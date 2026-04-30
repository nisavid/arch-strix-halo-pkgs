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
    assert "openmp" in text
    assert "openblas" in text
    assert "makedepends=(" in text
    assert "0001-setup-allow-skipping-build-deps.patch" in text
    assert "export USE_NUMPY=1" in text
    assert 'export BLAS="OpenBLAS"' in text
    assert 'export OpenBLAS_HOME="${OpenBLAS_HOME:-/usr}"' in text
    assert "export USE_LAPACK=1" in text
    assert 'export CMAKE_PREFIX_PATH="${OpenBLAS_HOME}:/opt/rocm"' in text
    assert 'export AOTRITON_INSTALLED_PREFIX="/usr"' in text
    assert "export USE_CUDA=0" in text
    assert "export USE_ROCM=1" in text
    assert "0006-enable-aten-cuda-api-for-rocm.patch" in text
    assert 'rm -rf build' in text
    assert 'local _ccache_cache="$srcdir/.ccache/cache"' in text
    assert 'export CCACHE_DIR="${CCACHE_DIR:-${_ccache_cache}}"' in text
    assert "BASH_FUNC_*|module|ml" in text
    assert 'env "${_clean_env[@]}" CMAKE_ONLY=1 python setup.py build' in text
    assert 'cmake --build build --config Release -j "${MAX_JOBS}"' in text
    assert "_sysconfigdata__linux_x86_64-linux-gnu.cpython-314.pyc" in text
    assert 'env "${_clean_env[@]}" SKIP_BUILD_DEPS=1 python setup.py bdist_wheel --dist-dir dist' in text


def test_pkgbuild_loads_clang_openmp_before_torch_cpu():
    text = PKGBUILD.read_text()

    assert 'patchelf --add-needed libomp.so "${_so}"' in text
    assert 'torch/_C*.so' in text
    assert "grep -Eq 'libomp|libiomp5'" in text


def test_pkgbuild_marks_installed_wheel_as_rocm_build():
    text = PKGBUILD.read_text()

    assert '_version_py="${_site}/torch/version.py"' in text
    assert 'env -i PATH=/opt/rocm/bin:/usr/bin:/bin HIP_PATH=/opt/rocm ROCM_PATH=/opt/rocm /opt/rocm/bin/hipconfig --version | sed' in text
    assert '_rocm_version="$(< /opt/rocm/.info/version)"' in text
    assert "hip: Optional[str] = '${_hip_version}'" in text
    assert "rocm: Optional[str] = '${_rocm_version}'" in text


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
