from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-vllm-rocm-gfx1151/PKGBUILD"
PATCH = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/0005-rocm-reduce-triton-unified-attention-prefill-tile-for-large-heads.patch"
)


def test_pkgbuild_carries_rocm_large_head_tile_patch():
    text = PKGBUILD.read_text()
    patch_name = PATCH.name

    assert patch_name in text
    assert f'_apply_patch_if_needed "{patch_name}"' in text


def test_patch_reduces_rocm_large_head_prefill_tile_to_16():
    text = PATCH.read_text()

    assert "current_platform.is_rocm()" in text
    assert "and is_prefill" in text
    assert "and element_size >= 2" in text
    assert "and head_size >= 512" in text
    assert "return 16" in text


def test_patch_documents_gemma4_lds_overflow_reason():
    text = PATCH.read_text()

    assert "Gemma4 global heads at 512" in text
    assert "64 KiB hardware limit on gfx1151" in text
