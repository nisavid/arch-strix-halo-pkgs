from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-amd-aiter-gfx1151/PKGBUILD"
HEADER_PATCH = (
    REPO_ROOT
    / "packages/python-amd-aiter-gfx1151/0001-gfx1151-rdna35-header-compat.patch"
)
HIP_REDUCE_PATCH = (
    REPO_ROOT
    / "packages/python-amd-aiter-gfx1151/0006-rdna35-hip-reduce-wave32-dpp-compat.patch"
)
RUNTIME_PATCH = (
    REPO_ROOT
    / "packages/python-amd-aiter-gfx1151/0002-jit-runtime-finds-hipcc-and-user-jit-modules.patch"
)
FUSED_MOE_PATCH = (
    REPO_ROOT
    / "packages/python-amd-aiter-gfx1151/0003-fused-moe-unknown-gfx-falls-back-to-2stage.patch"
)
TUNER_PATCH = (
    REPO_ROOT
    / "packages/python-amd-aiter-gfx1151/0004-moe-tuner-skips-missing-1stage-asm-metadata.patch"
)
SPLITK_PATCH = (
    REPO_ROOT
    / "packages/python-amd-aiter-gfx1151/0005-ck-moe-normalizes-zero-splitk-and-forwards-stage2.patch"
)


def test_pkgbuild_carries_jit_runtime_patch():
    text = PKGBUILD.read_text()

    assert "pkgrel=7" in text
    assert HEADER_PATCH.name in text
    assert f'patch -Np1 -i "$srcdir/{HEADER_PATCH.name}"' in text
    assert HIP_REDUCE_PATCH.name in text
    assert f'patch -Np1 -i "$srcdir/{HIP_REDUCE_PATCH.name}"' in text
    assert RUNTIME_PATCH.name in text
    assert f'patch -Np1 -i "$srcdir/{RUNTIME_PATCH.name}"' in text
    assert FUSED_MOE_PATCH.name in text
    assert f'patch -Np1 -i "$srcdir/{FUSED_MOE_PATCH.name}"' in text
    assert TUNER_PATCH.name in text
    assert f'patch -Np1 -i "$srcdir/{TUNER_PATCH.name}"' in text
    assert SPLITK_PATCH.name in text
    assert f'patch -Np1 -i "$srcdir/{SPLITK_PATCH.name}"' in text
    assert "0005-unquantized-moe-falls-back-to-torch-on-unsupported-ck-gemm.patch" not in text
    assert 'export PATH="/opt/rocm/bin:${PATH}"' in text
    assert 'export ROCM_HOME="/opt/rocm"' in text
    assert 'export HIP_PATH="/opt/rocm"' in text


def test_header_patch_only_carries_vec_convert_rdna_fallbacks():
    text = HEADER_PATCH.read_text()

    assert "vec_convert.h" in text
    assert "CK_TILE_RDNA3_NO_PK_FP8" in text
    assert "type_convert<fp8_t>(a)" in text
    assert "type_convert<fp8_t>(b)" in text
    assert "hip_reduce.h" not in text
    assert "AITER_RDNA_NO_DPP_BCAST" not in text
    assert 'asm volatile("v_cvt_scalef32_pk_fp4_f32 %0, %1, %2, %3" : "=v"(c) : "v"(b), "v"(a), "v"(scale));' not in text


def test_hip_reduce_patch_isolated_from_vec_convert_changes():
    text = HIP_REDUCE_PATCH.read_text()

    assert "hip_reduce.h" in text
    assert "AITER_RDNA_NO_DPP_BCAST" in text
    assert "warp_swizzle<T, 0x1e0>" in text
    assert "static_assert(WarpSize <= 32" in text
    assert "vec_convert.h" not in text
    assert "CK_TILE_RDNA3_NO_PK_FP8" not in text


def test_runtime_patch_fixes_user_jit_import_and_hipcc_resolution():
    text = RUNTIME_PATCH.read_text()

    assert "if home_jit_dir not in sys.path:" in text
    assert "def get_hipcc_path() -> str:" in text
    assert '"/opt/rocm/bin/hipcc"' in text
    assert '[get_hipcc_path()]' in text
    assert 'or user_jit_dir != this_dir' in text
    assert 'importlib.import_module(md_name)' in text


def test_fused_moe_patch_falls_back_for_unknown_gfx_without_keyerror():
    text = FUSED_MOE_PATCH.read_text()

    assert "unknown gfx targets" in text
    assert "fused_moe_1stage_dict.get(get_gfx(), {})" in text
    assert ") in gfx_1stage_cfgs:" in text


def test_tuner_patch_skips_missing_1stage_asm_metadata():
    text = TUNER_PATCH.read_text()

    assert "Skip 1-stage ASM tuning when the current gfx target has no" in text
    assert "asm_info = self.get_1stage_file_info(" in text
    assert "if asm_info is None:" in text
    assert "return task_1stage" in text


def test_splitk_patch_normalizes_zero_and_forwards_stage2_splitk():
    text = SPLITK_PATCH.read_text()

    assert "def _normalize_splitk(splitk: Optional[int]) -> int:" in text
    assert "return 1 if splitk in (None, 0) else int(splitk)" in text
    assert "+    splitk: Optional[int] = 1," in text
    assert "_normalize_splitk(splitk)," in text
    assert "int32_t splitk_local = splitk.value_or(0) ?: 1;" in text
