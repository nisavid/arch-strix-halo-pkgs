from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PATCH = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/0016-rocm-refresh-local-carry-for-vllm-0.20.0.patch"
)


def test_patch_maps_cuda_bfloat_vector_aliases_for_rocm():
    text = PATCH.read_text()

    assert "csrc/cuda_vec_utils.cuh" in text
    assert "using vllm_bfloat16 = __hip_bfloat16;" in text
    assert "using vllm_bfloat162 = __hip_bfloat162;" in text
    assert "PackedTypeConverter<vllm_bfloat162>" in text
    assert "CUDATypeConverter<c10::BFloat16>" in text


def test_patch_keeps_hipify_byproducts_present_for_unchanged_cuda_sources():
    text = PATCH.read_text()

    assert "cmake/hipify.py" in text
    assert "expected_hipified_path" in text
    assert "shutil.copy2(s_abs, expected_hipified_path)" in text
