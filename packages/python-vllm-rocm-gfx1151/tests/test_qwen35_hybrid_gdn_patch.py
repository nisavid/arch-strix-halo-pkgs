from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-vllm-rocm-gfx1151/PKGBUILD"
PATCH = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/0016-rocm-refresh-local-carry-for-vllm-0.30.0.patch"
)


def test_pkgbuild_carries_qwen35_hybrid_gdn_patch():
    text = PKGBUILD.read_text()

    assert PATCH.name in text
    assert '_vllm_source_patch="0016-rocm-refresh-local-carry-for-vllm-${pkgver}.patch"' in text
    assert '_apply_patch_if_needed "${_vllm_source_patch}"' in text
    assert "NOTE(gfx1151): On AMD HIP, restrict autotune search" in text


def test_qwen35_patch_restricts_fla_autotune_on_amd():
    text = PATCH.read_text()

    assert "diff --git a/vllm/third_party/flash_linear_attention/ops/chunk_delta_h.py" in text
    assert "diff --git a/vllm/third_party/flash_linear_attention/ops/chunk_o.py" in text
    assert "diff --git a/vllm/model_executor/layers/fla/" not in text
    assert "from .utils import FLA_CHUNK_SIZE, is_amd, use_cuda_graph" in text
    assert "for num_stages in ([2] if is_amd else [2, 3, 4])" in text
    assert "for BV in ([32] if is_amd else [32, 64])" in text
    assert "for BK in ([32] if is_amd else BKV_LIST)" in text
    assert "for BV in ([32] if is_amd else BKV_LIST)" in text
    assert "b_g_diff = b_g_last.to(tl.float32) - b_g.to(tl.float32)" in text
    assert "b_g_last = exp(b_g_last.to(tl.float32))" in text


def test_qwen35_patch_restricts_warmup_to_chunk_size_on_amd():
    text = PATCH.read_text()

    assert "vllm/model_executor/layers/mamba/gdn_linear_attn.py" not in text


def test_qwen35_patch_drops_aiter_only_hybrid_carry():
    text = PATCH.read_text()

    # ROCm no longer raises the hybrid block size, and the AITER attention
    # fallback only mattered while this package enabled AITER on gfx1x.
    assert "diff --git a/vllm/config/vllm.py" not in text
    assert "diff --git a/vllm/platforms/rocm.py" not in text
    assert "Re-run hybrid alignment" not in text
    assert "Hybrid models need TRITON_ATTN" not in text
