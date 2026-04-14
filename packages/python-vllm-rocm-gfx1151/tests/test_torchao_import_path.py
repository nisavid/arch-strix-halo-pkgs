from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-vllm-rocm-gfx1151/PKGBUILD"
PATCH = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/0008-torchao-version-check-stays-metadata-only.patch"
)


def test_pkgbuild_carries_torchao_import_patch():
    text = PKGBUILD.read_text()

    assert "pkgrel=13" in text
    assert PATCH.name in text
    assert f'_apply_patch_if_needed "{PATCH.name}"' in text


def test_patch_moves_generic_version_checks_to_metadata_only_helper():
    text = PATCH.read_text()

    assert "torchao_utils.py" in text
    assert "Check installed torchao version without importing the torchao package" in text
    assert (
        "from vllm.model_executor.layers.quantization.torchao_utils import ("
        in text
    )
    assert (
        "-from vllm.model_executor.layers.quantization.torchao import "
        "torchao_version_at_least" in text
    )
