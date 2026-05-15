from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PATCH = (
    REPO_ROOT
    / "packages/python-vllm-rocm-gfx1151/0016-rocm-refresh-local-carry-for-vllm-0.21.0.patch"
)


def test_patch_maps_cuda_bfloat_vector_aliases_for_rocm():
    text = PATCH.read_text()

    assert "csrc/cuda_vec_utils.cuh" in text
    assert "using vllm_bfloat16 = __hip_bfloat16;" in text
    assert "using vllm_bfloat162 = __hip_bfloat162;" in text
    assert "PackedTypeConverter<vllm_bfloat162>" in text
    assert "c10::BFloat16 -> vllm_bfloat16" in text
    assert "using Type = vllm_bfloat16;" in text


def test_patch_keeps_hipify_byproducts_present_for_unchanged_cuda_sources():
    text = PATCH.read_text()

    assert "cmake/hipify.py" in text
    assert "expected_hipified_path" in text
    assert "shutil.copy2(s_abs, expected_hipified_path)" in text


def test_rocm_amdsmi_fallback_warning_stays_one_shot():
    text = PATCH.read_text()
    fallback_start = text.index("Failed to get GCN arch via amdsmi")
    next_file_start = text.find("diff --git", fallback_start)
    if next_file_start == -1:
        next_file_start = len(text)
    amdsmi_fallback = text[fallback_start:next_file_start]

    assert "Failed to get GCN arch via amdsmi" in amdsmi_fallback
    assert "+        logger.warning_once(" in amdsmi_fallback
    assert "+        logger.warning(" not in amdsmi_fallback
