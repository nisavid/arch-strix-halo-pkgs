from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKG_DIR = REPO_ROOT / "packages/python-vllm-rocm-gfx1151"
PATCH = PKG_DIR / "0016-rocm-refresh-local-carry-for-vllm-0.20.1.patch"
PKGBUILD = PKG_DIR / "PKGBUILD"
README = PKG_DIR / "README.md"


def test_flash_attn_ck_interface_gate_patch_is_packaged():
    patch_text = PATCH.read_text(encoding="utf-8")
    pkgbuild_text = PKGBUILD.read_text(encoding="utf-8")

    assert PATCH.name in pkgbuild_text
    assert '_vllm_source_patch="0016-rocm-refresh-local-carry-for-vllm-${pkgver}.patch"' in pkgbuild_text
    assert '_apply_patch_if_needed "${_vllm_source_patch}"' in pkgbuild_text
    assert (
        "grep -Fq 'def rocm_flash_attn_supports_vllm_varlen_api() -> bool:'"
        in pkgbuild_text
    )
    assert "def rocm_flash_attn_supports_vllm_varlen_api() -> bool:" in patch_text
    assert "inspect.signature(flash_attn_varlen_func)" in patch_text
    assert "required_keywords" in patch_text


def test_flash_attn_ck_interface_gate_rejects_dao_style_varlen_api():
    patch_text = PATCH.read_text(encoding="utf-8")

    for keyword in (
        "out",
        "seqused_k",
        "scheduler_metadata",
        "fa_version",
        "q_descale",
        "k_descale",
        "v_descale",
        "num_splits",
        "s_aux",
        "return_softmax_lse",
    ):
        assert f'"{keyword}"' in patch_text

    assert "ROCm flash-attn varlen API is not vLLM-compatible" in patch_text
    assert "if not _ROCM_FLASH_ATTN_AVAILABLE:" in patch_text
    assert "The validated upstream ROCm flash-attn lane in this package is FA2." in patch_text
    assert "return 2" in patch_text


def test_flash_attn_ck_interface_gate_is_documented():
    readme_text = README.read_text(encoding="utf-8")

    assert "CK/direct FlashAttention interface gate" in readme_text
    assert "vLLM's paged-KV varlen call surface" in readme_text
    assert "reports FlashAttention version 2 on ROCm" in readme_text
    assert "blocked deeper in the paged-KV CK kernel path" in readme_text
