"""The vLLM 0.30.0 re-port drops carry that upstream, Triton 3.8, or AITER removal made obsolete."""

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PKG_DIR = REPO_ROOT / "packages/python-vllm-rocm-gfx1151"
PATCH = PKG_DIR / "0016-rocm-refresh-local-carry-for-vllm-0.30.0.patch"
PKGBUILD = PKG_DIR / "PKGBUILD"


def _patched_files() -> set[str]:
    return {
        line.split(" b/", 1)[1]
        for line in PATCH.read_text().splitlines()
        if line.startswith("diff --git a/")
    }


def test_patch_is_the_only_carried_patch_file() -> None:
    assert sorted(path.name for path in PKG_DIR.glob("*.patch")) == [PATCH.name]


@pytest.mark.parametrize(
    "path",
    [
        # hipify now copies unchanged sources itself.
        "cmake/hipify.py",
        # gfx1x AITER enablement, Gemma 4 AITER preference, hybrid AITER
        # exclusion, amdsmi warning fallback and FA Triton availability.
        "vllm/_aiter_ops.py",
        "vllm/platforms/rocm.py",
        "vllm/config/vllm.py",
        "vllm/v1/attention/backends/rocm_aiter_unified_attn.py",
        # Triton 3.8 ships triton.knobs, target_info and constexpr_function.
        "vllm/triton_utils/jit_monitor.py",
        "vllm/utils/jit_monitor.py",
        "vllm/utils/import_utils.py",
        # Superseded CLI laziness.
        "vllm/engine/arg_utils.py",
        "vllm/entrypoints/cli/__init__.py",
    ],
)
def test_patch_no_longer_touches_dropped_carry(path: str) -> None:
    assert path not in _patched_files()


def test_pkgbuild_no_longer_builds_or_checks_aiter_carry() -> None:
    text = PKGBUILD.read_text()

    assert "VLLM_ROCM_USE_AITER" not in text
    assert "_aiter_ops.py" not in text
    assert "Hybrid models need TRITON_ATTN" not in text
    assert "_flash_attn_uses_triton_rocm" not in text
    assert "_triton_knobs" not in text
