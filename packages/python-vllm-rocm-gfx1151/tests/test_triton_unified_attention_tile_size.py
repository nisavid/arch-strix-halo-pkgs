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
