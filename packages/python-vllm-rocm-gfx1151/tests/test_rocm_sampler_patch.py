from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-vllm-rocm-gfx1151/PKGBUILD"
PATCH = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/0016-rocm-refresh-local-carry-for-vllm-0.20.1.patch"
)


def test_pkgbuild_carries_rocm_topk_topp_sampler_patch():
    text = PKGBUILD.read_text()

    assert PATCH.name in text
    assert '_vllm_source_patch="0016-rocm-refresh-local-carry-for-vllm-${pkgver}.patch"' in text
    assert '_apply_patch_if_needed "${_vllm_source_patch}"' in text
    assert "Use PyTorch top-k/top-p filtering on large-vocabulary ROCm" in text


def test_rocm_sampler_patch_uses_pytorch_filtering_instead_of_triton():
    text = PATCH.read_text()

    assert "vllm/v1/sample/ops/topk_topp_sampler.py" in text
    assert "if current_platform.is_rocm() and logits.shape[-1] > 200000:" in text
    assert "return apply_top_k_top_p_pytorch(logits, k, p)" in text
    assert "logits shaped" in text
    assert "(32, 248320)" in text
