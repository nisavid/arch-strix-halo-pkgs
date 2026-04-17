import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SITE_PACKAGES = [
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/pkg/python-vllm-rocm-gfx1151/usr/lib/python3.14/site-packages",
    REPO_ROOT
    / "packages/python-pytorch-opt-rocm-gfx1151/pkg/python-pytorch-opt-rocm-gfx1151/usr/lib/python3.14/site-packages",
    REPO_ROOT
    / "packages/python-torchvision-rocm-gfx1151/pkg/python-torchvision-rocm-gfx1151/usr/lib/python3.14/site-packages",
    REPO_ROOT
    / "packages/python-triton-gfx1151/pkg/python-triton-gfx1151/usr/lib/python3.14/site-packages",
]
VLLM_SCRIPT = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/pkg/python-vllm-rocm-gfx1151/usr/bin/vllm"
)
PKGBUILD = REPO_ROOT / "packages/python-vllm-rocm-gfx1151/PKGBUILD"


def test_pkgbuild_exports_pytorch_rocm_arch():
    text = PKGBUILD.read_text()
    assert 'export PYTORCH_ROCM_ARCH="gfx1151"' in text


def test_pkgbuild_cleans_stale_triton_fetchcontent_state():
    text = PKGBUILD.read_text()
    assert "rm -rf .deps/triton_kernels-*" in text


def test_pkgbuild_reapplies_source_patches_for_noextract_rebuilds():
    text = PKGBUILD.read_text()

    assert "_apply_patch_if_needed" in text
    assert "_apply_all_source_patches" in text
    assert '[[ -f "${startdir}/${_patch_name}" ]]' in text
    assert ".patch-state" not in text
    assert "_reset_source_tree()" in text
    assert "_source_tree_has_all_source_patches()" in text


def test_pkgbuild_drops_old_build_only_librocsolver_shim():
    text = PKGBUILD.read_text()

    assert "librocsolver.so.0" not in text
    assert ".torch-rocm-compat" not in text
    assert 'export LD_LIBRARY_PATH="${_rocm_compat}:/opt/rocm/lib:${LD_LIBRARY_PATH:-}"' not in text


def test_vllm_version_is_metadata_only():
    env = os.environ.copy()
    pythonpath_entries = [*(str(path) for path in SITE_PACKAGES)]
    pythonpath = os.pathsep.join(pythonpath_entries)
    if env.get("PYTHONPATH"):
        pythonpath = f"{pythonpath}{os.pathsep}{env['PYTHONPATH']}"
    env["PYTHONPATH"] = pythonpath

    result = subprocess.run(
        [sys.executable, str(VLLM_SCRIPT), "--version"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, (
        f"vllm --version exited with {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert result.stdout.strip() == "0.19.0"
    assert "openai_harmony" not in result.stderr
    assert "triton.language.target_info" not in result.stderr
    assert "torchao/_C.abi3.so" not in result.stderr
