from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-vllm-rocm-gfx1151/PKGBUILD"
PATCH = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/0016-rocm-refresh-local-carry-for-vllm-0.20.0.patch"
)


def test_pkgbuild_carries_qwen35_hybrid_gdn_patch():
    text = PKGBUILD.read_text()

    assert PATCH.name in text
    assert f'_apply_patch_if_needed "{PATCH.name}"' in text
    assert "Hybrid models need TRITON_ATTN" in text


def test_qwen35_patch_restricts_fla_autotune_on_amd():
    text = PATCH.read_text()

    assert "vllm/model_executor/layers/fla/ops/chunk_delta_h.py" in text
    assert "vllm/model_executor/layers/fla/ops/chunk_o.py" in text
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


def test_qwen35_patch_preserves_hybrid_block_alignment_after_rocm_platform_update():
    text = PATCH.read_text()

    assert "vllm/config/vllm.py" in text
    assert "Re-run hybrid alignment" in text
    assert "platform minimum" in text
    assert "HybridAttentionMambaModelConfig.verify_and_update_config(self)" in text


def test_qwen35_patch_routes_hybrid_models_away_from_aiter_attention():
    text = PATCH.read_text()

    assert "vllm/platforms/rocm.py" in text
    assert "vllm/v1/attention/backends/rocm_aiter_unified_attn.py" in text
    assert "_is_hybrid" in text
    assert "Hybrid models need TRITON_ATTN" in text
    assert "Selected AITER attention backend" in text
    assert "(block_size & (block_size - 1)) == 0" in text
