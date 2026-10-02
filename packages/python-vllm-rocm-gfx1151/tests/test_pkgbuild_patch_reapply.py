import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKGBUILD = REPO_ROOT / "packages/python-vllm-rocm-gfx1151/PKGBUILD"


def _sentinels() -> str:
    text = PKGBUILD.read_text()
    start = text.index("_source_tree_has_all_source_patches() {")
    end = text.index("\n}\n", start)
    return text[start:end]


def test_pkgbuild_uses_tree_state_instead_of_patch_stamps():
    text = PKGBUILD.read_text()

    assert ".patch-state" not in text
    assert '.applied' not in text
    assert "_reset_source_tree()" in text
    assert "_source_tree_has_all_source_patches()" in text
    assert "VLLM_ROCM_USE_AITER_MOE" not in text
    assert '_vllm_srcdir="vllm-${pkgver}"' in text
    assert '_vllm_tarball="v${pkgver}.tar.gz"' in text
    assert 'bsdtar -xf "${srcdir}/${_vllm_tarball}" -C "${srcdir}"' in text


def test_pkgbuild_sentinels_track_the_0_30_carry():
    sentinels = _sentinels()

    for sentinel, path in (
        ('requires-python = ">=3.10,<3.15"', "pyproject.toml"),
        ("def _selected_subcommand() -> str | None:", "vllm/entrypoints/cli/main.py"),
        ("using vllm_bfloat16 = __hip_bfloat16;", "csrc/libtorch_stable/cuda_vec_utils.cuh"),
        (
            "def torchao_version_at_least(torchao_version: str) -> bool:",
            "vllm/model_executor/layers/quantization/torchao_utils.py",
        ),
        (
            "Use PyTorch top-k/top-p filtering on large-vocabulary ROCm",
            "vllm/v1/sample/ops/topk_topp_sampler.py",
        ),
        ("Keep valid_count type stable across branches", "vllm/v1/spec_decode/utils.py"),
        (
            "def rocm_flash_attn_supports_vllm_varlen_api() -> bool:",
            "vllm/v1/attention/backends/fa_utils.py",
        ),
        (
            "NOTE(gfx1151): On AMD HIP, restrict autotune search",
            "vllm/third_party/flash_linear_attention/ops/chunk_delta_h.py",
        ),
    ):
        assert re.search(
            re.escape(f"grep -Fq '{sentinel}'") + r"\s+" + re.escape(path), sentinels
        ), sentinel
    assert sentinels.count("grep -Fq") == 8
