from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PKG_DIR = REPO_ROOT / "packages/python-vllm-rocm-gfx1151"
PATCH = PKG_DIR / "0016-rocm-refresh-local-carry-for-vllm-0.20.1.patch"
PKGBUILD = PKG_DIR / "PKGBUILD"


def test_flash_attn_triton_interface_patch_is_packaged():
    patch_text = PATCH.read_text(encoding="utf-8")
    pkgbuild_text = PKGBUILD.read_text(encoding="utf-8")

    assert "def _flash_attn_uses_triton_rocm() -> bool:" in patch_text
    assert 'from flash_attn import flash_attn_interface' in patch_text
    assert 'getattr(flash_attn_interface, "USE_TRITON_ROCM", False)' in patch_text
    assert "aiter.ops.triton._triton_kernels.flash_attn_triton_amd" in patch_text
    added_lines = "\n".join(
        line for line in patch_text.splitlines() if line.startswith("+")
    )
    assert "find_spec(\"flash_attn.flash_attn_triton_amd\")" not in added_lines
    assert PATCH.name in pkgbuild_text
    assert (
        "grep -Fq 'def _flash_attn_uses_triton_rocm() -> bool:'"
        in pkgbuild_text
    )
