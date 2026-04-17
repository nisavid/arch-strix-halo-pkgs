from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-vllm-rocm-gfx1151/PKGBUILD"
PATCH = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/0005-rocm-reduce-triton-unified-attention-prefill-tile-for-large-heads.patch"
)
SETUP_FLAGS_PATCH = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/0006-setup.py-forward-host-and-hip-flags-into-cmake.patch"
)
GEMMA4_AITER_PATCH = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/0007-rocm-enable-gfx1x-aiter-and-prefer-it-for-gemma4.patch"
)
GEMMA4_MOE_PADDING_PATCH = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/0010-rocm-pad-gemma4-moe-intermediate-for-aiter.patch"
)


def test_pkgbuild_carries_rocm_large_head_tile_patch():
    text = PKGBUILD.read_text()
    patch_name = PATCH.name

    assert patch_name in text
    assert f'_apply_patch_if_needed "{patch_name}"' in text


def test_pkgbuild_carries_setup_flag_forwarding_patch():
    text = PKGBUILD.read_text()
    patch_name = SETUP_FLAGS_PATCH.name

    assert patch_name in text
    assert f'_apply_patch_if_needed "{patch_name}"' in text


def test_pkgbuild_carries_gemma4_aiter_patch():
    text = PKGBUILD.read_text()
    patch_name = GEMMA4_AITER_PATCH.name

    assert patch_name in text
    assert f'_apply_patch_if_needed "{patch_name}"' in text


def test_pkgbuild_carries_gemma4_moe_padding_patch():
    text = PKGBUILD.read_text()
    patch_name = GEMMA4_MOE_PADDING_PATCH.name

    assert patch_name in text
    assert f'_apply_patch_if_needed "{patch_name}"' in text


def test_pkgbuild_preserves_inherited_makepkg_flags():
    text = PKGBUILD.read_text()

    assert "options=(!lto)" in text
    assert "_strip_incompatible_lto_flags()" in text
    assert 'local _base_cflags="$(_strip_incompatible_lto_flags "${CFLAGS:-}")"' in text
    assert 'local _base_cxxflags="$(_strip_incompatible_lto_flags "${CXXFLAGS:-}")"' in text
    assert 'local _base_hipflags="$(_strip_incompatible_lto_flags "${HIPFLAGS:-}")"' in text
    assert 'local _base_ldflags="$(_strip_incompatible_lto_flags "${LDFLAGS:-}")"' in text
    assert 'export CFLAGS="${_base_cflags} ${_prefix_map_flags} ${_strix_opt_flags}"' in text
    assert 'export CXXFLAGS="${_base_cxxflags} ${_prefix_map_flags} ${_strix_opt_flags}"' in text
    assert 'export HIPFLAGS="${_base_hipflags} ${_prefix_map_flags} ${_strix_opt_flags}"' in text
    assert 'export LDFLAGS="${_base_ldflags}"' in text


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


def test_setup_patch_forwards_host_and_hip_flags_into_cmake():
    text = SETUP_FLAGS_PATCH.read_text()

    assert '("CFLAGS", "CMAKE_C_FLAGS")' in text
    assert '("CXXFLAGS", "CMAKE_CXX_FLAGS")' in text
    assert '("HIPFLAGS", "CMAKE_HIP_FLAGS")' in text
    assert 'cmake_args += [f"-D{cmake_name}={env_value}"]' in text


def test_gemma4_patch_enables_gfx1x_aiter_and_prefers_it():
    text = GEMMA4_AITER_PATCH.read_text()

    assert "from vllm.platforms.rocm import on_gfx1x, on_mi3xx" in text
    assert "return on_mi3xx() or on_gfx1x()" in text
    assert "AttentionBackendEnum.ROCM_AITER_UNIFIED_ATTN" in text
    assert "decode miscompilation" in text


def test_gemma4_patch_auto_enables_fused_moe_when_not_explicitly_disabled():
    text = GEMMA4_AITER_PATCH.read_text()

    assert 'envs.is_set("VLLM_ROCM_USE_AITER")' in text
    assert 'envs.is_set("VLLM_ROCM_USE_AITER_MOE")' in text
    assert "return cls._AITER_ENABLED and cls._FMOE_ENABLED" in text
    assert "return cls._FMOE_ENABLED" in text


def test_gemma4_moe_padding_patch_aligns_704_intermediate_for_aiter():
    text = GEMMA4_MOE_PADDING_PATCH.read_text()

    assert "_maybe_pad_intermediate_for_aiter(" in text
    assert "Padding MoE intermediate dimension from %d to %d for AITER CK GEMM alignment." in text
    assert "aiter_moe_align = 128" in text
    assert "layer.moe_config" in text
    assert "rocm_aiter_ops.shuffle_weights(" in text
