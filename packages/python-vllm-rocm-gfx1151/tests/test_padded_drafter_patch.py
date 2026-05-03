from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-vllm-rocm-gfx1151/PKGBUILD"
PATCH = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/0016-rocm-refresh-local-carry-for-vllm-0.20.1.patch"
)


def test_pkgbuild_carries_padded_drafter_count_patch():
    text = PKGBUILD.read_text()

    assert PATCH.name in text
    assert '_vllm_source_patch="0016-rocm-refresh-local-carry-for-vllm-${pkgver}.patch"' in text
    assert '_apply_patch_if_needed "${_vllm_source_patch}"' in text
    assert "Keep valid_count type stable across branches" in text


def test_padded_drafter_patch_keeps_valid_count_int32():
    text = PATCH.read_text()

    assert "vllm/v1/spec_decode/utils.py" in text
    assert "valid_count = tl.full((), 0, dtype=tl.int32)" in text
    assert "valid_count = tl.sum(is_valid_mask.to(tl.int32))" in text
    assert "Mismatched type for valid_count" not in text
