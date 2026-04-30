from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-vllm-rocm-gfx1151/PKGBUILD"
PATCH = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/0016-rocm-refresh-local-carry-for-vllm-0.20.0.patch"
)


def test_pkgbuild_carries_rocm_large_head_tile_patch():
    pkgbuild_text = PKGBUILD.read_text()
    patch_text = PATCH.read_text()

    assert PATCH.name in pkgbuild_text
    assert f'_apply_patch_if_needed "{PATCH.name}"' in pkgbuild_text
    assert "64 KiB hardware limit on gfx1151" in patch_text


def test_pkgbuild_carries_setup_flag_forwarding_patch():
    pkgbuild_text = PKGBUILD.read_text()
    patch_text = PATCH.read_text()

    assert PATCH.name in pkgbuild_text
    assert f'_apply_patch_if_needed "{PATCH.name}"' in pkgbuild_text
    assert "CMAKE_HIP_FLAGS" in patch_text


def test_pkgbuild_carries_gemma4_aiter_patch():
    pkgbuild_text = PKGBUILD.read_text()
    patch_text = PATCH.read_text()

    assert PATCH.name in pkgbuild_text
    assert f'_apply_patch_if_needed "{PATCH.name}"' in pkgbuild_text
    assert "return on_mi3xx() or on_gfx1x()" in patch_text


def test_pkgbuild_drops_fused_moe_policy_patch():
    text = PKGBUILD.read_text()
    patch_name = "0011-rocm-default-fused-moe-to-aiter-on-supported-systems.patch"

    assert patch_name not in text


def test_pkgbuild_drops_dormant_gemma4_moe_padding_patch():
    text = PKGBUILD.read_text()
    patch_name = "0010-rocm-pad-gemma4-moe-intermediate-for-aiter.patch"
    patch_path = REPO_ROOT / f"packages/python-vllm-rocm-gfx1151/{patch_name}"

    assert patch_name not in text
    assert not patch_path.exists()


def test_pkgbuild_preserves_inherited_makepkg_flags():
    text = PKGBUILD.read_text()

    assert "options=(!lto)" in text or "options=('!lto')" in text
    assert "_strip_incompatible_lto_flags()" in text
    assert 'local _base_cflags="$(_strip_incompatible_lto_flags "${CFLAGS:-}")"' in text
    assert 'local _base_cxxflags="$(_strip_incompatible_lto_flags "${CXXFLAGS:-}")"' in text
    assert 'local _base_hipflags="$(_strip_incompatible_lto_flags "${HIPFLAGS:-}")"' in text
    assert 'local _base_ldflags="$(_strip_incompatible_lto_flags "${LDFLAGS:-}")"' in text
    assert 'export CFLAGS="${_base_cflags} ${_prefix_map_flags} ${_strix_opt_flags}"' in text
    assert 'export CXXFLAGS="${_base_cxxflags} ${_prefix_map_flags} ${_strix_opt_flags}"' in text
    assert 'export HIPFLAGS="${_base_hipflags} ${_prefix_map_flags} ${_strix_opt_flags}"' in text
    assert 'export LDFLAGS="${_base_ldflags}"' in text


def test_pkgbuild_passes_clean_hip_version_to_cmake():
    text = PKGBUILD.read_text()

    assert "env -i PATH=/opt/rocm/bin:/usr/bin:/bin" in text
    assert "HIP_PATH=/opt/rocm ROCM_PATH=/opt/rocm" in text
    assert "/opt/rocm/bin/hipconfig --version" in text
    assert "VLLM_HIP_VERSION_MISSING" in text
    assert 'export CMAKE_ARGS="-DHIP_VERSION=${_hip_version%%-*} ${CMAKE_ARGS:-}"' in text


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
    text = PATCH.read_text()

    assert '("CFLAGS", "CMAKE_C_FLAGS")' in text
    assert '("CXXFLAGS", "CMAKE_CXX_FLAGS")' in text
    assert '("HIPFLAGS", "CMAKE_HIP_FLAGS")' in text
    assert 'cmake_args += [f"-D{cmake_name}={env_value}"]' in text


def test_gemma4_patch_enables_gfx1x_aiter_and_prefers_it():
    text = PATCH.read_text()

    assert "from vllm.platforms.rocm import on_gfx1x, on_mi3xx" in text
    assert "return on_mi3xx() or on_gfx1x()" in text
    assert "AttentionBackendEnum.ROCM_AITER_UNIFIED_ATTN" in text
    assert "decode miscompilation" in text
    assert "def is_fused_moe_enabled(cls) -> bool:" not in text
