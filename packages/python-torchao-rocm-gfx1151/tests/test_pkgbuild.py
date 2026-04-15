from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-torchao-rocm-gfx1151/PKGBUILD"
README = REPO_ROOT / "packages/python-torchao-rocm-gfx1151/README.md"
RECIPE_JSON = REPO_ROOT / "packages/python-torchao-rocm-gfx1151/recipe.json"
PATCH = (
    REPO_ROOT
    / "packages/python-torchao-rocm-gfx1151/"
    / "0001-setup.py-honor-pytorch-rocm-arch.patch"
)


def test_pkgbuild_uses_torch_2_11_compatible_torchao_lane():
    text = PKGBUILD.read_text()

    assert "pkgname=python-torchao-rocm-gfx1151" in text
    assert "pkgver=0.17.0" in text
    assert "python-pytorch-opt-rocm-gfx1151" in text
    assert "VERSION_SUFFIX=" in text
    assert "ROCM_HOME=/opt/rocm" in text
    assert "PYTORCH_ROCM_ARCH=gfx1151" in text
    assert "patchelf" in text
    assert PATCH.name in text


def test_patch_makes_rocm_arch_configurable():
    text = PATCH.read_text()

    assert '--offload-arch=gfx942' in text
    assert '+        rocm_arch = os.getenv("PYTORCH_ROCM_ARCH", "gfx942")' in text
    assert '+        extra_compile_args["nvcc"].append(f"--offload-arch={rocm_arch}")' in text


def test_package_docs_record_compatibility_and_runpath_story():
    readme = README.read_text()
    recipe = RECIPE_JSON.read_text()

    assert "0.17.0" in readme
    assert "torch 2.11.0+" in readme
    assert "VERSION_SUFFIX" in readme
    assert "ROCM_HOME=/opt/rocm" in readme
    assert "torch/lib" in readme
    assert "0.17.0" in recipe
    assert "ROCM_HOME=/opt/rocm" in recipe
