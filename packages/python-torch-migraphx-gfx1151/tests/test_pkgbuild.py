from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE = REPO_ROOT / "packages/python-torch-migraphx-gfx1151"
PKGBUILD = PACKAGE / "PKGBUILD"
README = PACKAGE / "README.md"
RECIPE_JSON = PACKAGE / "recipe.json"


def test_pkgbuild_tracks_audited_upstream_commit_and_local_rocm_stack():
    text = PKGBUILD.read_text()

    assert "pkgname=python-torch-migraphx-gfx1151" in text
    assert "pkgver=1.2" in text
    assert "pkgrel=3" in text
    assert "6b2cd2237e83b675ae671650d08343dfbb0be5f3" in text
    assert "migraphx-gfx1151" in text
    assert "python-pytorch-opt-rocm-gfx1151" in text
    assert "python-torchao-rocm-gfx1151" in text
    assert "ROCM_HOME=/opt/rocm" in text
    assert "PYTORCH_ROCM_ARCH=gfx1151" in text
    assert "$ORIGIN/torch/lib" in text


def test_patch_carry_records_pt2e_dynamo_and_numpy_boundaries():
    pt2e_patch = (PACKAGE / "0001-import-pt2e-quantization-from-torchao.patch").read_text()
    dynamo_patch = (PACKAGE / "0002-keep-dynamo-registration-lazy.patch").read_text()
    numpy_patch = (PACKAGE / "0003-relax-numpy-runtime-cap.patch").read_text()
    aot_patch = (PACKAGE / "0004-preload-aot-autograd-before-native-extension.patch").read_text()
    readme = README.read_text()
    recipe = RECIPE_JSON.read_text()

    assert "torchao.quantization.pt2e.quantize_pt2e" in pt2e_patch
    assert "def __getattr__(name):" in dynamo_patch
    assert '"numpy>=1.20.0,<2.0"' in numpy_patch
    assert '"numpy>=1.20.0"' in numpy_patch
    assert "import torch._functorch.aot_autograd" in aot_patch
    assert "FX lowering" in readme
    assert "torch.compile(..., backend=\"migraphx\")" in readme
    assert "python-numpy-gfx1151" in readme
    assert "0001-import-pt2e-quantization-from-torchao.patch" in recipe
    assert "0003-relax-numpy-runtime-cap.patch" in recipe
    assert "0004-preload-aot-autograd-before-native-extension.patch" in recipe
