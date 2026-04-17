from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-vllm-rocm-gfx1151/PKGBUILD"


def test_pkgbuild_uses_tree_state_instead_of_patch_stamps():
    text = PKGBUILD.read_text()

    assert ".patch-state" not in text
    assert '.applied' not in text
    assert "_reset_source_tree()" in text
    assert "_source_tree_has_all_source_patches()" in text
    assert "VLLM_ROCM_USE_AITER_MOE" in text
    assert "grep -Fq 'VLLM_ROCM_USE_AITER_MOE' vllm/_aiter_ops.py" in text
    assert 'bsdtar -xf "${srcdir}/v0.19.0.tar.gz" -C "${srcdir}"' in text
